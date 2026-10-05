using System.Collections.Concurrent;
using System.Net;
using System.Text.Json.Nodes;
using KH2Trainer.Twitch;

/// <summary>Twitch login, Helix requests and the EventSub protocol against recorded fakes.</summary>
internal static class ApiTests
{
    private static readonly Uri Identity = new("https://id.test/");
    private static readonly Uri Api = new("https://api.test/helix/");

    public static async Task RunAsync(Action<bool, string> check)
    {
        await AuthAsync(check);
        TokenStorage(check);
        await HelixAsync(check);
        await EventSubAsync(check);
    }

    private static async Task AuthAsync(Action<bool, string> check)
    {
        // Device flow: pending, slow_down, then the token.
        {
            int polls = 0;
            var fake = new FakeHttp(request => request.Path switch
            {
                "/oauth2/device" => FakeHttp.Json(HttpStatusCode.OK,
                    """{"device_code":"dev-1","user_code":"ABCD-EFGH","verification_uri":"https://www.twitch.tv/activate?device-code=ABCD-EFGH","expires_in":1800,"interval":5}"""),
                "/oauth2/token" => ++polls switch
                {
                    1 => FakeHttp.Json(HttpStatusCode.BadRequest, """{"status":400,"message":"authorization_pending"}"""),
                    2 => FakeHttp.Json(HttpStatusCode.BadRequest, """{"status":400,"message":"slow_down"}"""),
                    _ => FakeHttp.Json(HttpStatusCode.OK, """{"access_token":"a1","refresh_token":"r1","expires_in":14000,"scope":["channel:manage:redemptions"],"token_type":"bearer"}"""),
                },
                _ => FakeHttp.Json(HttpStatusCode.NotFound, "{}"),
            });
            var delays = new List<TimeSpan>();
            var auth = new TwitchAuth(new HttpClient(fake), Identity, (t, _) => { delays.Add(t); return Task.CompletedTask; });
            var device = await auth.StartDeviceFlowAsync("cid", CancellationToken.None);
            var start = fake.Requests.First();
            check(start.Form("client_id") == "cid" && start.Form("scopes") == TwitchAuth.Scope, "auth: the device request names the client and the redemption scope");
            check(device.UserCode == "ABCD-EFGH" && device.VerificationUri.Contains("activate") && device.Interval == TimeSpan.FromSeconds(5), "auth: the device response is parsed");
            var token = await auth.WaitForDeviceTokenAsync("cid", device, CancellationToken.None);
            check(token.AccessToken == "a1" && token.RefreshToken == "r1" && token.Scopes.Contains(TwitchAuth.Scope), "auth: the token arrives once the streamer confirmed");
            check(delays.Select(d => d.TotalSeconds).SequenceEqual([5.0, 5.0, 10.0]), $"auth: polling honours the interval and slows down on request ({string.Join(",", delays.Select(d => d.TotalSeconds))})");
            var poll = fake.Requests.Last();
            check(poll.Form("grant_type") == "urn:ietf:params:oauth:grant-type:device_code" && poll.Form("device_code") == "dev-1", "auth: polling uses the device code grant");
        }

        // Errors during the device flow.
        {
            string answer = "access_denied";
            var fake = new FakeHttp(request => request.Path == "/oauth2/device"
                ? FakeHttp.Json(HttpStatusCode.BadRequest, """{"status":400,"message":"invalid client"}""")
                : FakeHttp.Json(HttpStatusCode.BadRequest, $$"""{"status":400,"message":"{{answer}}"}"""));
            var auth = new TwitchAuth(new HttpClient(fake), Identity, (_, _) => Task.CompletedTask);
            var startError = await Catch(() => auth.StartDeviceFlowAsync("bad", CancellationToken.None));
            check(startError is TwitchAuthException && startError.Message.Contains("Public"), "auth: a rejected Client ID explains the Public client type");
            var device = new DeviceAuthorization("d", "U", "https://x", DateTimeOffset.UtcNow.AddMinutes(5), TimeSpan.FromSeconds(1));
            var denied = await Catch(() => auth.WaitForDeviceTokenAsync("cid", device, CancellationToken.None));
            check(denied is TwitchAuthException && denied.Message.Contains("declined"), "auth: a declined login is reported");
            answer = "invalid device code";
            var expired = await Catch(() => auth.WaitForDeviceTokenAsync("cid", device, CancellationToken.None));
            check(expired is TwitchAuthException && expired.Message.Contains("expired"), "auth: an expired code asks to start again");
            var late = await Catch(() => auth.WaitForDeviceTokenAsync("cid", device with { ExpiresAt = DateTimeOffset.UtcNow.AddSeconds(-1) }, CancellationToken.None));
            check(late is TwitchAuthException && late.Message.Contains("expired"), "auth: polling stops when the code expired");
        }

        // Refresh, validate and revoke.
        {
            bool refreshWorks = true, twitchDown = false;
            var fake = new FakeHttp(request => request.Path switch
            {
                "/oauth2/token" when twitchDown => FakeHttp.Json(HttpStatusCode.ServiceUnavailable, "{}"),
                "/oauth2/token" when refreshWorks => FakeHttp.Json(HttpStatusCode.OK, """{"access_token":"a2","expires_in":3600,"scope":["channel:manage:redemptions"]}"""),
                "/oauth2/token" => FakeHttp.Json(HttpStatusCode.BadRequest, """{"status":400,"message":"Invalid refresh token"}"""),
                "/oauth2/validate" when request.Authorization == "OAuth good" =>
                    FakeHttp.Json(HttpStatusCode.OK, """{"client_id":"cid","login":"streamer","user_id":"42","scopes":["channel:manage:redemptions"],"expires_in":5000}"""),
                "/oauth2/validate" => FakeHttp.Json(HttpStatusCode.Unauthorized, """{"status":401,"message":"invalid access token"}"""),
                _ => FakeHttp.Json(HttpStatusCode.OK, ""),
            });
            var auth = new TwitchAuth(new HttpClient(fake), Identity);
            var refreshed = await auth.RefreshAsync("cid", "r1", CancellationToken.None);
            check(refreshed.AccessToken == "a2" && refreshed.RefreshToken == "r1", "auth: a refresh keeps the refresh token when Twitch sends none");
            check(fake.Requests.Last().Form("grant_type") == "refresh_token" && fake.Requests.Last().Form("refresh_token") == "r1", "auth: the refresh request uses the refresh grant");
            twitchDown = true;
            check(await Catch(() => auth.RefreshAsync("cid", "r1", CancellationToken.None)) is HttpRequestException, "auth: Twitch being down is a temporary problem, not a lost login");
            twitchDown = false; refreshWorks = false;
            check(await Catch(() => auth.RefreshAsync("cid", "r1", CancellationToken.None)) is TwitchAuthException, "auth: a rejected refresh token asks to connect again");
            var owner = await auth.ValidateAsync("good", CancellationToken.None);
            check(owner is { Login: "streamer", UserId: "42" } && owner.Scopes.Contains(TwitchAuth.Scope), "auth: validation returns the channel and scopes");
            check(await auth.ValidateAsync("stale", CancellationToken.None) is null, "auth: an invalid token validates as null");
            await auth.RevokeAsync("cid", "good", CancellationToken.None);
            check(fake.Requests.Last() is { Path: "/oauth2/revoke" } revoke && revoke.Form("token") == "good" && revoke.Form("client_id") == "cid", "auth: logging out revokes the token");
        }
    }

    private static void TokenStorage(Action<bool, string> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "KH2TwitchTests", Guid.NewGuid().ToString("N"));
        string path = Path.Combine(folder, "token.bin");
        var store = new TokenStore(path, new PlainProtector());
        check(store.Load("cid") is null, "token store: nothing stored yet");
        store.Save("cid", new TwitchToken("a", "r", DateTimeOffset.UtcNow.AddHours(1), [TwitchAuth.Scope]));
        check(store.Load("cid") is { AccessToken: "a", RefreshToken: "r" }, "token store: the login survives a restart");
        check(!File.ReadAllText(path).Contains("\"AccessToken\":\"a\""), "token store: the file is not plain JSON");
        check(store.Load("other") is null, "token store: a different Client ID needs a new login");
        File.WriteAllBytes(path, [1, 2, 3]);
        check(store.Load("cid") is null, "token store: a damaged file is ignored");
        store.Clear();
        check(!File.Exists(path) && Directory.GetFiles(folder).Length == 0, "token store: logging out deletes the file without leftovers");
        Directory.Delete(folder, true);
    }

    private static async Task HelixAsync(Action<bool, string> check)
    {
        string mode = "ok";
        int refreshes = 0, unauthorized = 0, limited = 0;
        string current = "t1";
        var fake = new FakeHttp(request =>
        {
            if (mode == "401" && request.Authorization == "Bearer t1") { unauthorized++; return FakeHttp.Json(HttpStatusCode.Unauthorized, """{"error":"Unauthorized","status":401,"message":"Invalid OAuth token"}"""); }
            if (mode == "401-always") return FakeHttp.Json(HttpStatusCode.Unauthorized, """{"error":"Unauthorized","status":401,"message":"Invalid OAuth token"}""");
            if (mode == "429" && limited++ < 2)
                return FakeHttp.Json(HttpStatusCode.TooManyRequests, """{"status":429,"message":"Too Many Requests"}""", ("Ratelimit-Reset", (DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 3).ToString()));
            if (mode == "429-always") return FakeHttp.Json(HttpStatusCode.TooManyRequests, """{"status":429,"message":"Too Many Requests"}""");
            if (mode == "duplicate") return FakeHttp.Json(HttpStatusCode.BadRequest, """{"error":"Bad Request","status":400,"message":"CREATE_CUSTOM_REWARD_DUPLICATE_REWARD"}""");
            if (mode == "404") return FakeHttp.Json(HttpStatusCode.NotFound, """{"error":"Not Found","status":404,"message":"Not Found"}""");
            return request.Path switch
            {
                "/helix/users" => FakeHttp.Json(HttpStatusCode.OK, """{"data":[{"id":"42","login":"streamer","display_name":"Streamer","broadcaster_type":"affiliate"}]}"""),
                "/helix/channel_points/custom_rewards" when request.Method == HttpMethod.Get =>
                    FakeHttp.Json(HttpStatusCode.OK, """{"data":[{"id":"rw-1","title":"Heal Sora","cost":300,"is_paused":true},{"id":"rw-2","title":"Other","cost":5,"is_paused":false}]}"""),
                "/helix/channel_points/custom_rewards" when request.Method == HttpMethod.Delete => new HttpResponseMessage(HttpStatusCode.NoContent),
                "/helix/channel_points/custom_rewards" => FakeHttp.Json(HttpStatusCode.OK, """{"data":[{"id":"rw-9","title":"New","cost":100,"is_paused":false}]}"""),
                "/helix/channel_points/custom_rewards/redemptions" when request.Method == HttpMethod.Get && request.Query("after") is null =>
                    FakeHttp.Json(HttpStatusCode.OK, """{"data":[{"id":"red-1","user_name":"Ann","user_login":"ann","user_input":"hi","redeemed_at":"2026-01-01T10:00:00Z"}],"pagination":{"cursor":"page2"}}"""),
                "/helix/channel_points/custom_rewards/redemptions" when request.Method == HttpMethod.Get =>
                    FakeHttp.Json(HttpStatusCode.OK, """{"data":[{"id":"red-2","user_name":"","user_login":"bob"}],"pagination":{}}"""),
                "/helix/eventsub/subscriptions" => FakeHttp.Json(HttpStatusCode.Accepted, """{"data":[{"id":"sub-1","status":"enabled"}]}"""),
                _ => FakeHttp.Json(HttpStatusCode.OK, """{"data":[]}"""),
            };
        });
        var delays = new List<TimeSpan>();
        var helix = new HelixClient(new HttpClient(fake), "cid", _ => Task.FromResult(current), (_, _) => { refreshes++; current = "t2"; return Task.FromResult(current); },
            Api, (t, _) => { delays.Add(t); return Task.CompletedTask; });

        var user = await helix.GetUserAsync("42");
        var first = fake.Requests.Last();
        check(user is { Login: "streamer", BroadcasterType: "affiliate" }, "helix: the channel is read");
        check(first.Authorization == "Bearer t1" && first.ClientId == "cid" && first.Query("id") == "42", "helix: requests carry the token, the Client ID and the query");

        var rewards = await helix.GetManageableRewardsAsync("42");
        check(fake.Requests.Last().Query("only_manageable_rewards") == "true" && rewards.Count == 2 && rewards[0] is { Id: "rw-1", Cost: 300, IsPaused: true },
            "helix: only this app's rewards are listed and parsed");

        var spec = new RewardSpec("Heal Sora", 300, "Fully heals Sora.", "#1F8B4C", 30, 0, 2);
        var created = await helix.CreateRewardAsync("42", spec);
        var create = fake.Requests.Last();
        var body = JsonNode.Parse(create.Body)!.AsObject();
        check(created.Id == "rw-9" && create.Method == HttpMethod.Post && create.Query("broadcaster_id") == "42", "helix: rewards are created for the channel");
        check((string?)body["title"] == "Heal Sora" && (int?)body["cost"] == 300 && (string?)body["prompt"] == "Fully heals Sora." && (string?)body["background_color"] == "#1F8B4C",
            "helix: the reward body has title, cost, prompt and colour");
        check((bool?)body["should_redemptions_skip_request_queue"] == false && (bool?)body["is_user_input_required"] == false,
            "helix: redemptions stay in the request queue so they can be fulfilled or refunded");
        check((bool?)body["is_global_cooldown_enabled"] == true && (int?)body["global_cooldown_seconds"] == 30 && (bool?)body["is_max_per_stream_enabled"] == false
            && !body.ContainsKey("max_per_stream") && (int?)body["max_per_user_per_stream"] == 2, "helix: limits are only enabled when set");

        await helix.UpdateRewardAsync("42", "rw-1", null, true);
        var pause = fake.Requests.Last();
        check(pause.Method == HttpMethod.Patch && pause.Query("id") == "rw-1" && pause.Body == """{"is_paused":true}""", "helix: pausing only sends the paused flag");
        await helix.UpdateRedemptionStatusAsync("42", "rw-1", "red-1", true);
        var fulfil = fake.Requests.Last();
        check(fulfil.Path.EndsWith("/redemptions") && fulfil.Query("reward_id") == "rw-1" && fulfil.Query("id") == "red-1" && fulfil.Body.Contains("FULFILLED"),
            "helix: fulfilling marks the redemption FULFILLED");
        await helix.UpdateRedemptionStatusAsync("42", "rw-1", "red-2", false);
        check(fake.Requests.Last().Body.Contains("CANCELED"), "helix: refunding marks the redemption CANCELED");
        var open = await helix.GetUnfulfilledRedemptionsAsync("42", "rw-1");
        check(open.Select(r => r.Id).SequenceEqual(["red-1", "red-2"]) && fake.Requests.Last().Query("status") == "UNFULFILLED" && fake.Requests.Last().Query("after") == "page2",
            "helix: unfulfilled redemptions are listed across pages");
        check(open[0] is { UserName: "Ann", UserInput: "hi", RewardId: "rw-1" } && open[1].UserName == "bob", "helix: redemption details are read (login when the name is empty)");
        await helix.SubscribeRedemptionsAsync("42", "session-1");
        var subscribe = JsonNode.Parse(fake.Requests.Last().Body)!;
        check((string?)subscribe["type"] == EventSubMessage.RedemptionType && (string?)subscribe["transport"]!["session_id"] == "session-1"
            && (string?)subscribe["condition"]!["broadcaster_user_id"] == "42", "helix: the EventSub subscription targets the WebSocket session");
        await helix.DeleteRewardAsync("42", "rw-2");
        check(fake.Requests.Last().Method == HttpMethod.Delete, "helix: rewards are deleted");

        mode = "401";
        await helix.GetUserAsync("42");
        check(refreshes == 1 && unauthorized == 1 && fake.Requests.Last().Authorization == "Bearer t2", "helix: an expired token is refreshed once and the request repeated");
        mode = "401-always"; current = "t1";
        var expired = await Catch(() => helix.GetUserAsync("42"));
        check(expired is TwitchApiException { Status: HttpStatusCode.Unauthorized } && refreshes == 2, "helix: a refresh that does not help reports the expired login");

        mode = "429"; delays.Clear();
        await helix.GetUserAsync("42");
        check(delays.Count == 2 && delays.All(d => d.TotalSeconds is >= 1 and <= 30), "helix: rate limits wait for the reset and retry");
        mode = "429-always"; delays.Clear();
        check(await Catch(() => helix.GetUserAsync("42")) is TwitchApiException { Status: HttpStatusCode.TooManyRequests } && delays.Count == 3,
            "helix: retries stop after three rate limits");

        mode = "duplicate";
        var duplicate = await Catch(() => helix.CreateRewardAsync("42", spec));
        check(duplicate is TwitchApiException && duplicate.Message.Contains("already uses this title"), "helix: duplicate titles get an actionable message");
        mode = "404";
        check(await Catch(() => helix.DeleteRewardAsync("42", "gone")) is null, "helix: deleting a reward that is already gone succeeds");
        check(await Catch(() => helix.UpdateRewardAsync("42", "gone", spec, null)) is TwitchApiException { Status: HttpStatusCode.NotFound }, "helix: updating a missing reward reports 404");
        check(new TwitchApiException(HttpStatusCode.Forbidden, "The broadcaster must have partner or affiliate status.").Message.Contains("Affiliate"),
            "helix: missing affiliate status is explained");
    }

    private static async Task EventSubAsync(Action<bool, string> check)
    {
        var parsed = EventSubMessage.Parse(FakeTransport.Redemption("m", "red-1", "rw-1", "Alice"));
        check(parsed.Redemption is { Id: "red-1", RewardId: "rw-1", UserName: "Alice" } && parsed.MessageType == "notification", "eventsub: redemptions are parsed");
        check(EventSubMessage.Parse(FakeTransport.Welcome("s", 25)) is { SessionId: "s", KeepaliveSeconds: 25 }, "eventsub: the welcome session and keepalive are parsed");

        // Welcome, subscribe, notifications and duplicate deliveries.
        {
            var e = new EventSubHarness();
            var first = e.Add();
            first.Send(FakeTransport.Welcome("s1"));
            var run = e.Start();
            check(await Wait.ForAsync(() => e.Sessions.Contains("s1")) && first.Uri == e.Endpoint, "eventsub: connects and subscribes with the welcome session id");
            check(await Wait.ForAsync(() => e.States.Contains(EventSubState.Connected)), "eventsub: reports connected after subscribing");
            first.Send(FakeTransport.Keepalive("k1"));
            first.Send(FakeTransport.Redemption("m1", "red-1", "rw-1", "Alice"));
            first.Send(FakeTransport.Redemption("m1", "red-1", "rw-1", "Alice"));
            first.Send(FakeTransport.Redemption("m2", "red-2", "rw-1", "Bob"));
            check(await Wait.ForAsync(() => e.Redemptions.Count == 2) && e.Redemptions.Select(r => r.UserName).SequenceEqual(["Alice", "Bob"]),
                "eventsub: redemptions are delivered once, in order");

            // Twitch's reconnect handover: the new socket takes over without a new subscription.
            var second = e.Add();
            second.Send(FakeTransport.Welcome("s2"));
            first.Send(FakeTransport.Reconnect("wss://eventsub.test/reconnect?id=1"));
            first.Send(FakeTransport.Redemption("m-old", "red-old", "rw-1", "Dora")); // Still delivered on the old socket during the handover.
            check(await Wait.ForAsync(() => first.Disposed) && second.Uri?.ToString() == "wss://eventsub.test/reconnect?id=1", "eventsub: follows the reconnect URL and closes the old socket");
            check(e.Sessions.Count == 1, "eventsub: the handover keeps the subscription without subscribing again");
            check(e.Redemptions.Any(r => r.UserName == "Dora"), "eventsub: a redemption sent on the old socket during the handover is not lost");
            second.Send(FakeTransport.Redemption("m3", "red-3", "rw-1", "Cara"));
            check(await Wait.ForAsync(() => e.Redemptions.Count == 4), "eventsub: redemptions arrive on the new socket");

            // A dropped connection reconnects with back-off and subscribes again.
            var third = e.Add();
            third.Send(FakeTransport.Welcome("s3"));
            second.Close();
            check(await Wait.ForAsync(() => e.Sessions.Contains("s3")) && e.Delays.First() == TimeSpan.FromSeconds(2), "eventsub: a closed connection reconnects after a back-off");
            check(await Wait.ForAsync(() => e.Resubscribed.Contains(true)) && e.Resubscribed.First() == false, "eventsub: reports a subscription after a connection loss, so missed redemptions can be fetched");
            check(e.States.Contains(EventSubState.Reconnecting), "eventsub: reports reconnecting");

            e.Stop.Cancel();
            await run.WaitAsync(TimeSpan.FromSeconds(5));
            check(third.Disposed && e.States.Last() == EventSubState.Disconnected, "eventsub: stopping closes the socket and reports disconnected");
        }

        // A missing welcome and failing connects back off further; a revocation stops for good.
        {
            var e = new EventSubHarness();
            var noWelcome = e.Add();
            noWelcome.Send(FakeTransport.Keepalive("k"));
            e.Add().FailConnect = true;
            var good = e.Add();
            good.Send(FakeTransport.Welcome("s9"));
            var run = e.Start();
            check(await Wait.ForAsync(() => e.Sessions.Contains("s9")), "eventsub: recovers after a missing welcome and a failed connect");
            check(e.Delays.Select(d => d.TotalSeconds).SequenceEqual([2.0, 4.0]) && noWelcome.Disposed, "eventsub: the back-off grows with each failure");
            good.Send(FakeTransport.Revocation());
            await run.WaitAsync(TimeSpan.FromSeconds(5));
            check(e.States.Contains(EventSubState.Failed) && e.Texts.Any(t => t.Contains("revoked")), "eventsub: a revoked subscription stops and is reported");
        }

        // A subscription request that fails is retried on a fresh connection.
        {
            var e = new EventSubHarness { FailSubscriptions = 1 };
            e.Add().Send(FakeTransport.Welcome("a"));
            e.Add().Send(FakeTransport.Welcome("b"));
            var run = e.Start();
            check(await Wait.ForAsync(() => e.Sessions.Contains("b") && e.States.Contains(EventSubState.Connected)), "eventsub: a failed subscription is retried");
            e.Stop.Cancel();
            await run.WaitAsync(TimeSpan.FromSeconds(5));
        }
    }

    private sealed class EventSubHarness
    {
        private readonly ConcurrentQueue<FakeTransport> prepared = new();
        public Uri Endpoint { get; } = new("wss://eventsub.test/ws");
        public ConcurrentQueue<string> Sessions { get; } = new();
        public ConcurrentQueue<RedemptionEvent> Redemptions { get; } = new();
        public ConcurrentQueue<EventSubState> States { get; } = new();
        public ConcurrentQueue<string> Texts { get; } = new();
        public ConcurrentQueue<TimeSpan> Delays { get; } = new();
        public ConcurrentQueue<bool> Resubscribed { get; } = new();
        public CancellationTokenSource Stop { get; } = new();
        public int FailSubscriptions { get; set; }

        public FakeTransport Add()
        {
            var transport = new FakeTransport();
            prepared.Enqueue(transport);
            return transport;
        }

        public Task Start()
        {
            var client = new EventSubClient(
                () => prepared.TryDequeue(out var next) ? next : new FakeTransport { FailConnect = true },
                (session, _) =>
                {
                    if (FailSubscriptions-- > 0) return Task.FromException(new TwitchApiException(HttpStatusCode.BadRequest, "subscription failed"));
                    Sessions.Enqueue(session);
                    return Task.CompletedTask;
                },
                Redemptions.Enqueue,
                (state, text) => { States.Enqueue(state); Texts.Enqueue(text); },
                Endpoint,
                (t, c) => { Delays.Enqueue(t); return Delays.Count > 4 ? Task.Delay(Timeout.Infinite, c) : Task.CompletedTask; },
                Resubscribed.Enqueue);
            return Task.Run(() => client.RunAsync(Stop.Token));
        }
    }

    private static async Task<Exception?> Catch(Func<Task> action)
    {
        try { await action(); return null; }
        catch (Exception error) { return error; }
    }
}
