using System.Collections.Concurrent;
using System.Net;
using System.Text.Json.Nodes;
using KH2Trainer.Twitch;

/// <summary>A small in-memory Twitch: login, users, custom rewards, redemptions and EventSub subscriptions.</summary>
internal sealed class FakeTwitch
{
    public sealed class Reward
    {
        public required string Id { get; init; }
        public string Title { get; set; } = "";
        public int Cost { get; set; }
        public string Prompt { get; set; } = "";
        public bool Paused { get; set; }
        public bool Manageable { get; init; } = true;
    }

    private readonly object gate = new();
    private int nextReward, nextToken;
    public string ClientId { get; set; } = "cid";
    public string BroadcasterType { get; set; } = "affiliate";
    public int PendingPolls { get; set; } = 1;
    public bool DeviceRequested { get; private set; }
    public HashSet<string> AccessTokens { get; } = [];
    public HashSet<string> RefreshTokens { get; } = [];
    public List<string> Revoked { get; } = [];
    public Dictionary<string, Reward> Rewards { get; } = new(StringComparer.Ordinal);
    /// <summary>Redemption id → (reward id, status).</summary>
    public Dictionary<string, (string RewardId, string Status)> Redemptions { get; } = new(StringComparer.Ordinal);
    public List<string> Subscriptions { get; } = [];
    public FakeHttp Http { get; }

    public FakeTwitch() => Http = new FakeHttp(Handle);

    public Reward Add(string title, bool manageable = true, int cost = 100)
    {
        lock (gate)
        {
            var reward = new Reward { Id = "rw-" + ++nextReward, Title = title, Cost = cost, Manageable = manageable };
            Rewards[reward.Id] = reward;
            return reward;
        }
    }

    public Reward? Find(string title) { lock (gate) return Rewards.Values.FirstOrDefault(r => r.Title == title); }
    public string? Status(string redemption) { lock (gate) return Redemptions.TryGetValue(redemption, out var r) ? r.Status : null; }
    public int Count(HttpMethod method, string path) => Http.Requests.Count(r => r.Method == method && r.Path == path);

    public string IssueToken()
    {
        lock (gate)
        {
            string access = "access-" + ++nextToken;
            AccessTokens.Add(access); RefreshTokens.Add("refresh-" + nextToken);
            return access;
        }
    }

    private HttpResponseMessage Handle(FakeRequest request)
    {
        lock (gate)
        {
            if (request.Url.Host == "id.test") return Identity(request);
            if (request.ClientId != ClientId) return Error(HttpStatusCode.Unauthorized, "Client ID and OAuth token do not match");
            if (request.Authorization is not { } auth || !auth.StartsWith("Bearer ") || !AccessTokens.Contains(auth[7..]))
                return Error(HttpStatusCode.Unauthorized, "Invalid OAuth token");
            return request.Path switch
            {
                "/helix/users" => Data(new JsonObject { ["id"] = "42", ["login"] = "streamer", ["display_name"] = "Streamer", ["broadcaster_type"] = BroadcasterType }),
                "/helix/channel_points/custom_rewards" => CustomRewards(request),
                "/helix/channel_points/custom_rewards/redemptions" => RedemptionRequest(request),
                "/helix/eventsub/subscriptions" => Subscribe(request),
                _ => Error(HttpStatusCode.NotFound, "Not Found"),
            };
        }
    }

    private HttpResponseMessage Identity(FakeRequest request)
    {
        switch (request.Path)
        {
            case "/oauth2/device":
                DeviceRequested = true;
                return request.Form("client_id") == ClientId
                    ? FakeHttp.Json(HttpStatusCode.OK, """{"device_code":"dev","user_code":"WXYZ-1234","verification_uri":"https://www.twitch.tv/activate?device-code=WXYZ-1234","expires_in":1800,"interval":1}""")
                    : Error(HttpStatusCode.BadRequest, "invalid client");
            case "/oauth2/token" when request.Form("grant_type") == "refresh_token":
                if (!RefreshTokens.Contains(request.Form("refresh_token") ?? "")) return Error(HttpStatusCode.BadRequest, "Invalid refresh token");
                return Token(IssueToken());
            case "/oauth2/token":
                if (PendingPolls-- > 0) return Error(HttpStatusCode.BadRequest, "authorization_pending");
                return Token(IssueToken());
            case "/oauth2/validate":
                string token = request.Authorization?.Replace("OAuth ", "") ?? "";
                return AccessTokens.Contains(token)
                    ? FakeHttp.Json(HttpStatusCode.OK, $$"""{"client_id":"{{ClientId}}","login":"streamer","user_id":"42","scopes":["{{TwitchAuth.Scope}}"],"expires_in":3600}""")
                    : Error(HttpStatusCode.Unauthorized, "invalid access token");
            case "/oauth2/revoke":
                Revoked.Add(request.Form("token") ?? "");
                AccessTokens.Remove(request.Form("token") ?? "");
                return new HttpResponseMessage(HttpStatusCode.OK);
            default:
                return Error(HttpStatusCode.NotFound, "Not Found");
        }
    }

    private static HttpResponseMessage Token(string access) => FakeHttp.Json(HttpStatusCode.OK,
        $$"""{"access_token":"{{access}}","refresh_token":"{{access.Replace("access", "refresh")}}","expires_in":14000,"scope":["{{TwitchAuth.Scope}}"],"token_type":"bearer"}""");

    private HttpResponseMessage CustomRewards(FakeRequest request)
    {
        if (request.Query("broadcaster_id") != "42") return Error(HttpStatusCode.BadRequest, "Missing broadcaster_id");
        string? id = request.Query("id");
        if (request.Method == HttpMethod.Get)
            return Data(Rewards.Values.Where(r => r.Manageable || request.Query("only_manageable_rewards") != "true").Select(Json).ToArray());
        if (request.Method == HttpMethod.Post)
        {
            var body = JsonNode.Parse(request.Body)!;
            string title = (string)body["title"]!;
            if (Rewards.Values.Any(r => string.Equals(r.Title, title, StringComparison.OrdinalIgnoreCase)))
                return Error(HttpStatusCode.BadRequest, "CREATE_CUSTOM_REWARD_DUPLICATE_REWARD");
            if (Rewards.Count >= 50) return Error(HttpStatusCode.BadRequest, "The maximum number of rewards has been reached");
            var reward = new Reward { Id = "rw-" + ++nextReward };
            Apply(reward, body);
            Rewards[reward.Id] = reward;
            return Data(Json(reward));
        }
        if (id is null || !Rewards.TryGetValue(id, out var existing)) return Error(HttpStatusCode.NotFound, "Not Found");
        if (!existing.Manageable) return Error(HttpStatusCode.Forbidden, "The ID in the Client-Id header must match the client ID used to create the custom reward.");
        if (request.Method == HttpMethod.Delete) { Rewards.Remove(id); return new HttpResponseMessage(HttpStatusCode.NoContent); }
        var update = JsonNode.Parse(request.Body)!;
        if (update["title"] is { } newTitle && Rewards.Values.Any(r => r != existing && string.Equals(r.Title, (string?)newTitle, StringComparison.OrdinalIgnoreCase)))
            return Error(HttpStatusCode.BadRequest, "UPDATE_CUSTOM_REWARD_DUPLICATE_REWARD");
        Apply(existing, update);
        return Data(Json(existing));
    }

    private static void Apply(Reward reward, JsonNode body)
    {
        if (body["title"] is { } title) reward.Title = (string)title!;
        if (body["cost"] is { } cost) reward.Cost = (int)cost;
        if (body["prompt"] is { } prompt) reward.Prompt = (string)prompt!;
        if (body["is_paused"] is { } paused) reward.Paused = (bool)paused;
    }

    private HttpResponseMessage RedemptionRequest(FakeRequest request)
    {
        string rewardId = request.Query("reward_id") ?? "";
        if (!Rewards.TryGetValue(rewardId, out var reward)) return Error(HttpStatusCode.NotFound, "Not Found");
        if (!reward.Manageable) return Error(HttpStatusCode.Forbidden, "Not manageable");
        if (request.Method == HttpMethod.Get)
            return Data(Redemptions.Where(r => r.Value.RewardId == rewardId && r.Value.Status == request.Query("status"))
                .Select(r => (JsonNode)new JsonObject { ["id"] = r.Key, ["status"] = r.Value.Status }).ToArray());
        string id = request.Query("id") ?? "";
        if (Redemptions.TryGetValue(id, out var existing) && existing.Status != "UNFULFILLED") return Error(HttpStatusCode.NotFound, "Not Found");
        Redemptions[id] = (rewardId, (string)JsonNode.Parse(request.Body)!["status"]!);
        return Data(new JsonObject { ["id"] = id });
    }

    private HttpResponseMessage Subscribe(FakeRequest request)
    {
        var body = JsonNode.Parse(request.Body)!;
        Subscriptions.Add((string)body["transport"]!["session_id"]!);
        return FakeHttp.Json(HttpStatusCode.Accepted, """{"data":[{"id":"sub","status":"enabled"}]}""");
    }

    private static JsonNode Json(Reward r) => new JsonObject { ["id"] = r.Id, ["title"] = r.Title, ["cost"] = r.Cost, ["prompt"] = r.Prompt, ["is_paused"] = r.Paused };
    private static HttpResponseMessage Data(params JsonNode[] items) => FakeHttp.Json(HttpStatusCode.OK, new JsonObject { ["data"] = new JsonArray(items) }.ToJsonString());
    private static HttpResponseMessage Error(HttpStatusCode status, string message) =>
        FakeHttp.Json(status, new JsonObject { ["error"] = status.ToString(), ["status"] = (int)status, ["message"] = message }.ToJsonString());
}

/// <summary>The Twitch service end to end against the fake Twitch.</summary>
internal static class ServiceTests
{
    private static readonly TwitchEndpoints Endpoints = new(new Uri("https://id.test/"), new Uri("https://api.test/helix/"), new Uri("wss://eventsub.test/ws"));

    private sealed class Harness : IAsyncDisposable
    {
        private readonly ConcurrentQueue<FakeTransport> prepared = new();
        public string Folder { get; } = Path.Combine(Path.GetTempPath(), "KH2TwitchTests", Guid.NewGuid().ToString("N"));
        public FakeTwitch Twitch { get; }
        public TwitchSettings Settings { get; }
        public TokenStore Tokens { get; }
        public TwitchService Service { get; }
        public ConcurrentQueue<Redemption> Submitted { get; } = new();
        public ConcurrentQueue<string> Log { get; } = new();
        public List<string> Authorizations { get; } = [];
        public int Saves;

        public Harness(FakeTwitch? twitch = null, Action<TwitchSettings>? configure = null)
        {
            Twitch = twitch ?? new FakeTwitch();
            Settings = new TwitchSettings { ClientId = "cid" };
            configure?.Invoke(Settings);
            Tokens = new TokenStore(Path.Combine(Folder, "token.bin"), new PlainProtector());
            Service = new TwitchService(new HttpClient(Twitch.Http), Tokens, Settings, () => Interlocked.Increment(ref Saves), Submitted.Enqueue, Log.Enqueue,
                () => prepared.TryDequeue(out var next) ? next : new FakeTransport(), Endpoints, (_, c) => Task.Delay(1, c));
            Service.AuthorizationRequested += Authorizations.Add;
        }

        public FakeTransport Socket(string session)
        {
            var transport = new FakeTransport();
            transport.Send(FakeTransport.Welcome(session));
            prepared.Enqueue(transport);
            return transport;
        }

        public string? RewardId(string key) => Settings.Rewards.GetValueOrDefault(key)?.TwitchRewardId;
        public string Title(string key) => RewardResolver.Title(EffectCatalog.Find(key)!, Settings);

        public async ValueTask DisposeAsync()
        {
            await Service.DisposeAsync();
            try { Directory.Delete(Folder, true); } catch (IOException) { }
        }
    }

    public static async Task RunAsync(Action<bool, string> check)
    {
        // Without a Client ID nothing happens.
        {
            await using var h = new Harness(configure: s => s.ClientId = " ");
            check(h.Service.State == TwitchConnectionState.NotConfigured, "service: asks for a Client ID first");
            await h.Service.ConnectAsync();
            check(h.Service.State == TwitchConnectionState.NotConfigured && h.Twitch.Http.Requests.IsEmpty, "service: connecting without a Client ID sends nothing");
        }

        // First connection: device login, reward sync, leftovers, live redemptions.
        {
            var twitch = new FakeTwitch();
            var unused = twitch.Add("Old trainer reward");
            var foreign = twitch.Add("Hydrate!", manageable: false);
            await using var h = new Harness(twitch, s =>
            {
                s.For("heal").Enabled = true;
                s.For("final").Enabled = true;
                s.For("final").Cost = 2500;
                s.For("regen").Enabled = false;
            });
            var adopted = twitch.Add(h.Title("final"), cost: 1);
            twitch.Redemptions["left-1"] = (adopted.Id, "UNFULFILLED");
            twitch.Redemptions["done-1"] = (adopted.Id, "FULFILLED");
            var socket = h.Socket("session-1");

            await h.Service.ConnectAsync();
            check(h.Service.State == TwitchConnectionState.Connected && h.Service.DisplayName == "Streamer" && h.Service.BroadcasterId == "42",
                $"service: connects with the device login ({h.Service.StatusText})");
            check(h.Authorizations.SingleOrDefault()?.Contains("activate") == true && h.Service.UserCode is null, "service: opens the activation page and clears the code afterwards");
            check(h.Tokens.Load("cid") is { AccessToken.Length: > 0 }, "service: the login is stored for the next start");

            var heal = twitch.Find(h.Title("heal"));
            check(heal is { Cost: 500 } && h.RewardId("heal") == heal.Id, "service: an enabled reward is created on Twitch");
            check(heal!.Prompt == RewardResolver.Prompt(EffectCatalog.Find("heal")!, h.Settings), "service: the reward carries the default description");
            check(h.RewardId("final") == adopted.Id && twitch.Rewards[adopted.Id].Cost == 2500 && twitch.Rewards.Values.Count(r => r.Title == h.Title("final")) == 1,
                "service: an existing reward of this app with the same title is adopted and updated instead of duplicated");
            check(!twitch.Rewards.ContainsKey(unused.Id), "service: rewards of this app that are no longer enabled are deleted");
            check(twitch.Rewards.ContainsKey(foreign.Id), "service: rewards of other apps are never touched");
            check(twitch.Find(h.Title("regen")) is null && h.Service.RewardStatus("regen") == "Off", "service: disabled rewards are not created");
            check(h.Service.RewardStatus("heal") == "On Twitch" && h.Service.RewardsOnTwitch == 2, "service: the reward status shows it is live");
            check(twitch.Status("left-1") == "CANCELED" && twitch.Status("done-1") == "FULFILLED", "service: redemptions made while the trainer was offline are refunded");
            check(h.Saves > 0, "service: reward IDs are saved");

            check(await Wait.ForAsync(() => twitch.Subscriptions.Contains("session-1")), "service: subscribes to redemptions over EventSub");
            check(await Wait.ForAsync(() => h.Service.EventSubState == EventSubState.Connected), "service: reports the live connection");
            socket.Send(FakeTransport.Redemption("m1", "red-1", heal.Id, "Alice"));
            socket.Send(FakeTransport.Redemption("m2", "red-2", foreign.Id, "Bob"));
            socket.Send(FakeTransport.Redemption("m3", "red-3", adopted.Id, "Cara"));
            check(await Wait.ForAsync(() => h.Submitted.Count == 2), "service: redemptions of trainer rewards reach the engine");
            var alice = h.Submitted.First();
            check(alice is { RewardKey: "heal", UserName: "Alice", Id: "red-1", IsTest: false } && alice.TwitchRewardId == heal.Id, "service: the redemption names the effect and viewer");
            check(h.Submitted.All(r => r.UserName != "Bob"), "service: rewards of other apps are ignored");

            twitch.Redemptions["red-1"] = (heal.Id, "UNFULFILLED");
            twitch.Redemptions["red-3"] = (adopted.Id, "UNFULFILLED");
            h.Service.Fulfill(alice);
            h.Service.Refund(h.Submitted.Last(), "Final Form is not possible here");
            check(await Wait.ForAsync(() => twitch.Status("red-1") == "FULFILLED" && twitch.Status("red-3") == "CANCELED"),
                "service: the engine's decision fulfils or refunds the redemption on Twitch");
            check(await Wait.ForAsync(() => h.Log.Any(l => l.Contains("refunded Cara"))), "service: refunds are logged");
            h.Service.Fulfill(new Redemption("test", "heal", "Test", "", DateTimeOffset.UtcNow, heal.Id, IsTest: true));
            await Task.Delay(50);
            check(twitch.Status("test") is null, "service: test runs never touch Twitch");

            // Toggling and editing rewards syncs right away.
            h.Settings.For("heal").Enabled = false;
            await h.Service.SyncRewardAsync("heal");
            check(!twitch.Rewards.ContainsKey(heal.Id) && h.RewardId("heal") is null && h.Service.RewardStatus("heal") == "Off", "service: disabling a reward deletes it on Twitch");
            h.Settings.For("regen").Enabled = true;
            await h.Service.SyncRewardAsync("regen");
            var regen = twitch.Find(h.Title("regen"));
            check(regen != null && h.RewardId("regen") == regen.Id, "service: enabling a reward creates it on Twitch");
            int patches = twitch.Count(HttpMethod.Patch, "/helix/channel_points/custom_rewards");
            await h.Service.SyncRewardAsync("regen");
            check(twitch.Count(HttpMethod.Patch, "/helix/channel_points/custom_rewards") == patches, "service: an unchanged reward is not sent again");
            h.Settings.For("regen").Cost = 777;
            h.Settings.For("regen").DurationSeconds = 90;
            await h.Service.SyncRewardAsync("regen");
            check(regen!.Cost == 777 && regen.Prompt.Contains("90 s"), "service: edits update the reward on Twitch");
            h.Settings.For("regen").Title = "Hydrate!";
            await h.Service.SyncRewardAsync("regen");
            check(h.Service.RewardStatus("regen").Contains("already uses this title") && regen.Title != "Hydrate!", "service: a title clash shows a clear error on the reward");
            h.Settings.For("regen").Title = null;
            await h.Service.SyncRewardAsync("regen");
            check(h.Service.RewardStatus("regen") == "On Twitch", "service: fixing the title recovers");

            // A reward deleted on Twitch meanwhile is recreated.
            twitch.Rewards.Remove(regen.Id);
            h.Settings.For("regen").Cost = 778;
            await h.Service.SyncRewardAsync("regen");
            check(h.RewardId("regen") is { } recreated && recreated != regen.Id && twitch.Rewards.ContainsKey(recreated), "service: a reward deleted on Twitch is created again");

            // Pausing.
            await h.Service.SetPausedAsync(true);
            check(twitch.Rewards.Values.Where(r => r.Manageable).All(r => r.Paused) && h.Service.RewardStatus("regen") == "On Twitch (paused)", "service: pausing pauses every reward");
            h.Settings.For("heal").Enabled = true;
            await h.Service.SyncRewardAsync("heal");
            check(twitch.Find(h.Title("heal")) is { Paused: true }, "service: rewards enabled while paused start paused");
            await h.Service.SetPausedAsync(false);
            check(twitch.Rewards.Values.All(r => !r.Paused), "service: resuming unpauses them");

            // An expired access token is refreshed transparently.
            twitch.AccessTokens.Clear();
            h.Settings.For("heal").Cost = 301;
            await h.Service.SyncRewardAsync("heal");
            check(twitch.Find(h.Title("heal")) is { Cost: 301 } && h.Service.State == TwitchConnectionState.Connected, "service: an expired token is refreshed during a request");

            // Reconnecting keeps redemptions the engine still holds.
            h.Socket("session-2");
            twitch.Redemptions["red-4"] = (h.RewardId("heal")!, "UNFULFILLED");
            twitch.Redemptions["red-5"] = (h.RewardId("heal")!, "UNFULFILLED");
            socket.Send(FakeTransport.Redemption("m4", "red-4", h.RewardId("heal")!, "Dan"));
            check(await Wait.ForAsync(() => h.Submitted.Any(r => r.Id == "red-4")), "service: a new redemption arrives");
            await h.Service.ConnectAsync();
            check(h.Service.State == TwitchConnectionState.Connected && twitch.Count(HttpMethod.Post, "/oauth2/device") == 1
                && await Wait.ForAsync(() => twitch.Subscriptions.Contains("session-2")), "service: reconnects with the saved login");
            check(twitch.Status("red-4") == "UNFULFILLED" && twitch.Status("red-5") == "CANCELED", "service: a reconnect only refunds redemptions the engine never received");
            check(await Wait.ForAsync(() => socket.Disposed), "service: the old EventSub connection is closed on reconnect");

            // Closing the trainer pauses the rewards.
            await h.Service.ShutdownAsync();
            check(twitch.Rewards.Values.Where(r => r.Manageable).All(r => r.Paused), "service: closing the trainer pauses the rewards");
            check(await Wait.ForAsync(() => h.Service.EventSubState == EventSubState.Disconnected), "service: closing stops EventSub");
        }

        // A saved login is reused, an expired one refreshed, logging out revokes it.
        {
            var twitch = new FakeTwitch();
            await using var h = new Harness(twitch);
            string access = twitch.IssueToken();
            h.Tokens.Save("cid", new TwitchToken(access, access.Replace("access", "refresh"), DateTimeOffset.UtcNow.AddHours(1), [TwitchAuth.Scope]));
            h.Socket("s");
            await h.Service.ConnectAsync();
            check(h.Service.IsConnected && !twitch.DeviceRequested, "service: a saved login connects without a new code");
            await h.Service.DisconnectAsync(forgetLogin: false);
            check(h.Service.State == TwitchConnectionState.Disconnected && h.Tokens.Load("cid") != null, "service: disconnecting keeps the login");
            twitch.AccessTokens.Clear();
            h.Socket("s2");
            await h.Service.ConnectAsync();
            check(h.Service.IsConnected && !twitch.DeviceRequested && h.Tokens.Load("cid")!.AccessToken != access, "service: an expired saved login is refreshed");
            await h.Service.DisconnectAsync(forgetLogin: true);
            check(twitch.Revoked.Count == 1 && h.Tokens.Load("cid") is null && h.Service.State == TwitchConnectionState.Disconnected, "service: logging out revokes and forgets the login");
        }

        // Channels without channel points, wrong Client IDs and cancelled logins.
        {
            var twitch = new FakeTwitch { BroadcasterType = "" };
            await using var h = new Harness(twitch, s => s.For("heal").Enabled = true);
            await h.Service.ConnectAsync();
            check(h.Service.State == TwitchConnectionState.Error && h.Service.StatusText.Contains("Affiliate") && twitch.Rewards.Count == 0,
                "service: channels without Affiliate status get a clear error and no rewards");

            await using var wrong = new Harness(new FakeTwitch { ClientId = "other" });
            await wrong.Service.ConnectAsync();
            check(wrong.Service.State == TwitchConnectionState.Error && wrong.Service.StatusText.Contains("Client ID"), "service: a wrong Client ID is explained");

            await using var cancel = new Harness(new FakeTwitch { PendingPolls = int.MaxValue });
            var connecting = cancel.Service.ConnectAsync();
            check(await Wait.ForAsync(() => cancel.Service.State == TwitchConnectionState.WaitingForAuthorization) && cancel.Service.UserCode == "WXYZ-1234",
                "service: shows the code while waiting for the streamer");
            cancel.Service.CancelConnect();
            await connecting.WaitAsync(TimeSpan.FromSeconds(5));
            check(cancel.Service.State == TwitchConnectionState.Disconnected && cancel.Service.UserCode is null, "service: the login can be cancelled");
        }

        // Rewards enabled before connecting show that they will be created.
        {
            await using var h = new Harness(configure: s => s.For("heal").Enabled = true);
            check(h.Service.RewardStatus("heal") == "Created when you connect" && h.Service.RewardStatus("regen") == "Off", "service: offline status explains what happens");
            await h.Service.SyncRewardAsync("heal");
            check(h.Twitch.Http.Requests.IsEmpty && h.Saves == 1, "service: offline edits are only saved");
        }
    }
}
