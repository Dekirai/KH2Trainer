using System.Collections.Concurrent;
using System.Net;
using System.Text;
using System.Threading.Channels;
using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>
/// In-memory game: commands are validated against the real feature catalog (kind, argument count
/// and ranges) and simulate their effect on the value slots the engine reads back.
/// </summary>
internal sealed class FakeGame : IGameControl
{
    private readonly Dictionary<int, FeatureDefinition> byCommand;
    private readonly FeatureMap map;

    public FakeGame(IReadOnlyList<FeatureDefinition> catalog)
    {
        byCommand = catalog.Where(f => f.CommandId > 0).ToDictionary(f => f.CommandId);
        map = new FeatureMap(catalog);
        // A plausible scene: Sora in base form with partial HP/MP and some drive.
        Set("player.hp", 60); Set("player.hp.max", 120); Set("player.mp", 50); Set("player.mp.max", 100);
        Set("player.drive.bars", 2); Set("player.drive.max", 5); Set("player.form.id", 0); Set("munny", 1000);
        Set("time.multiplier", 1); Set("camera.fov", 70); Set("camera.fov_enabled", 0); Set("camera.free", 0); Set("camera.roll", 0);
        Set("motion.speed", 1); Set("motion.override", 0); Set("movement.run_speed", 8); Set("movement.walk_speed", 2);
        Set("movement.base_jump_height", 160); Set("movement.fall_speed", 20); Set("loot.draw", 0); Set("loot.jackpot", 0); Set("loot.lucky", 0);
        Set("loot.retained", 100); Set("targeting.search_scale", 1); Set("display.brightness_preview", 0); Set("audio.music", 80); Set("audio.voice", 90);
        Set("damage.player.general", 100); Set("damage.target.general", 100); Set("render.hide_captions", 0); Set("combat.movementcollision", 0);
        Set("practice.field_pause", 0); Set("time.actor_effect_freeze", 0); Set("player_damage_guard", 0); Set("combat.autoheal", 0);
        Set("combat.fullmp", 0); Set("combat.formtimer", 0); Set("drive.result", 0); Set("drive.requested", 0);
    }

    public bool IsConnected { get; set; } = true;
    public bool SceneReady { get; set; } = true;
    public HashSet<int> Unsupported { get; } = [];
    public Dictionary<int, double> Values { get; } = [];
    public Dictionary<int, int> Stock { get; } = [];
    public List<(string Feature, double[] Arguments)> Commands { get; } = [];
    public Func<string, double[], bool>? Reject { get; set; }
    /// <summary>Drive Form transformations complete only when this is true (simulates loading).</summary>
    public bool FormsComplete { get; set; } = true;
    /// <summary>Simulated failure result for drive.trigger.</summary>
    public int? FormResult { get; set; }

    public void Set(string feature, double value) => Values[map.Get(feature).ValueSlot] = value;
    public double? Get(string feature) => Values.TryGetValue(map.Get(feature).ValueSlot, out double v) ? v : null;
    public int Count(string feature) => Commands.Count(c => c.Feature == feature);
    public IEnumerable<double[]> Calls(string feature) => Commands.Where(c => c.Feature == feature).Select(c => c.Arguments);

    public bool Supports(int capabilitySlot) => !Unsupported.Contains(capabilitySlot);
    public bool TryRead(int valueSlot, out double value) => Values.TryGetValue(valueSlot, out value);

    /// <summary>While set, commands wait for it (simulates a game that is slow to acknowledge).</summary>
    public TaskCompletionSource? Hold { get; set; }

    public async Task ExecuteAsync(int command, IReadOnlyList<double> arguments, string label)
    {
        if (!byCommand.TryGetValue(command, out var feature)) throw new InvalidOperationException($"Unknown command {command}.");
        var args = arguments.ToArray();
        Commands.Add((feature.Id, args));
        Validate(feature, args);
        if (Hold is { } hold) await hold.Task;
        if (!IsConnected) throw new InvalidOperationException("Connect to a running game first.");
        if (Reject?.Invoke(feature.Id, args) == true) throw new InvalidOperationException("Rejected by the bridge.");
        Simulate(feature, args);
    }

    private static void Validate(FeatureDefinition feature, double[] args)
    {
        if (feature.Arguments.Count > 0)
        {
            if (args.Length != feature.Arguments.Count) throw new ArgumentException($"{feature.Id}: expected {feature.Arguments.Count} arguments, got {args.Length}.");
            for (int i = 0; i < args.Length; i++)
                if (args[i] < feature.Arguments[i].Minimum || args[i] > feature.Arguments[i].Maximum)
                    throw new ArgumentException($"{feature.Id}: argument {feature.Arguments[i].Name}={args[i]} outside {feature.Arguments[i].Minimum}..{feature.Arguments[i].Maximum}.");
            return;
        }
        if (feature.Kind == FeatureKind.Action)
        {
            if (args.Length != 0) throw new ArgumentException($"{feature.Id}: action takes no arguments, got {args.Length}.");
            return;
        }
        if (args.Length != 1) throw new ArgumentException($"{feature.Id}: expected one value.");
        if (!feature.IsValidValue(args[0])) throw new ArgumentException($"{feature.Id}: value {args[0]} outside {feature.Minimum}..{feature.Maximum}.");
    }

    private void Simulate(FeatureDefinition feature, double[] args)
    {
        if (feature.Kind is FeatureKind.Number or FeatureKind.Toggle or FeatureKind.Choice && feature.ValueSlot >= 0) Values[feature.ValueSlot] = args[0];
        switch (feature.Id)
        {
            case "drive.trigger":
                Set("drive.requested", args[0]);
                Set("drive.result", FormResult ?? (FormsComplete ? 2 : 1));
                if (FormsComplete && FormResult is null) Set("player.form.id", args[0]);
                break;
            case "drive.revert": Set("player.form.id", 0); break;
            case "player.heal": Set("player.hp", Get("player.hp.max") ?? 0); break;
            case "player.mp.restore": Set("player.mp", Get("player.mp.max") ?? 0); break;
            case "player.restore": Set("player.hp", Get("player.hp.max") ?? 0); Set("player.mp", Get("player.mp.max") ?? 0); break;
            case "inspect-item": Set("selected-item-stock", Stock.GetValueOrDefault((int)args[0])); break;
            case "set-item-stock":
                Stock[(int)args[0]] = (int)args[1];
                if (Get("inspect-item") == args[0]) Set("selected-item-stock", args[1]);
                break;
            case "camera.fov": Set("camera.fov_enabled", 1); break;
            case "targeting.reset": Set("targeting.search_scale", 1); break;
            case "display.restore_loaded": Set("display.brightness_preview", 0); break;
            case "camera.free" when args[0] == 0: Set("camera.roll", 0); break;
        }
    }
}

internal sealed class FakeSink : IRedemptionSink
{
    public List<Redemption> Fulfilled { get; } = [];
    public List<(Redemption Redemption, string Reason)> Refunded { get; } = [];
    public void Fulfill(Redemption redemption) => Fulfilled.Add(redemption);
    public void Refund(Redemption redemption, string reason) => Refunded.Add((redemption, reason));
    public bool IsFulfilled(string id) => Fulfilled.Any(r => r.Id == id);
    public bool IsRefunded(string id) => Refunded.Any(r => r.Redemption.Id == id);
}

internal sealed record FakeRequest(HttpMethod Method, Uri Url, string Body, string? Authorization, string? ClientId)
{
    public string Path => Url.AbsolutePath;
    public string? Query(string name) => System.Web.HttpUtility.ParseQueryString(Url.Query)[name];
    public string? Form(string name) => System.Web.HttpUtility.ParseQueryString(Body)[name];
}

/// <summary>Routes HttpClient requests to a handler function; records every request.</summary>
internal sealed class FakeHttp(Func<FakeRequest, HttpResponseMessage> handler) : HttpMessageHandler
{
    public ConcurrentQueue<FakeRequest> Requests { get; } = new();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        string body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(cancellationToken);
        var recorded = new FakeRequest(request.Method, request.RequestUri!, body, request.Headers.TryGetValues("Authorization", out var auth) ? auth.FirstOrDefault() : null,
            request.Headers.TryGetValues("Client-Id", out var client) ? client.FirstOrDefault() : null);
        Requests.Enqueue(recorded);
        return handler(recorded);
    }

    public static HttpResponseMessage Json(HttpStatusCode status, string json, params (string Name, string Value)[] headers)
    {
        var response = new HttpResponseMessage(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        foreach (var (name, value) in headers) response.Headers.TryAddWithoutValidation(name, value);
        return response;
    }
}

/// <summary>An EventSub connection fed by the test.</summary>
internal sealed class FakeTransport : IEventSubTransport
{
    private readonly Channel<string?> messages = Channel.CreateUnbounded<string?>();
    public Uri? Uri { get; private set; }
    public bool Disposed { get; private set; }
    public bool FailConnect { get; set; }

    public Task ConnectAsync(Uri uri, CancellationToken cancellation)
    {
        Uri = uri;
        return FailConnect ? Task.FromException(new IOException("connect failed")) : Task.CompletedTask;
    }

    public async Task<string?> ReceiveAsync(CancellationToken cancellation)
    {
        try { return await messages.Reader.ReadAsync(cancellation); }
        catch (ChannelClosedException) { return null; }
    }

    public void Send(string json) => messages.Writer.TryWrite(json);
    public void Close() => messages.Writer.TryWrite(null);
    public ValueTask DisposeAsync() { Disposed = true; messages.Writer.TryComplete(); return ValueTask.CompletedTask; }

    // Raw JSON with placeholders: the payloads end in "}}}", which interpolated raw strings cannot hold.
    public static string Welcome(string session, int keepalive = 10) =>
        """{"metadata":{"message_id":"w-SESSION","message_type":"session_welcome","message_timestamp":"2026-01-01T00:00:00Z"},"payload":{"session":{"id":"SESSION","status":"connected","keepalive_timeout_seconds":KEEPALIVE,"reconnect_url":null}}}"""
            .Replace("SESSION", session).Replace("KEEPALIVE", keepalive.ToString());

    public static string Keepalive(string id) =>
        """{"metadata":{"message_id":"ID","message_type":"session_keepalive","message_timestamp":"2026-01-01T00:00:00Z"},"payload":{}}""".Replace("ID", id);

    public static string Reconnect(string url) =>
        """{"metadata":{"message_id":"r1","message_type":"session_reconnect","message_timestamp":"2026-01-01T00:00:00Z"},"payload":{"session":{"id":"old","status":"reconnecting","keepalive_timeout_seconds":null,"reconnect_url":"URL"}}}"""
            .Replace("URL", url);

    public static string Revocation() =>
        """{"metadata":{"message_id":"v1","message_type":"revocation","message_timestamp":"2026-01-01T00:00:00Z","subscription_type":"channel.channel_points_custom_reward_redemption.add"},"payload":{"subscription":{"id":"s1","status":"authorization_revoked","type":"channel.channel_points_custom_reward_redemption.add"}}}""";

    public static string Redemption(string messageId, string redemptionId, string rewardId, string user) =>
        """{"metadata":{"message_id":"MESSAGE","message_type":"notification","message_timestamp":"2026-01-01T00:00:00Z","subscription_type":"channel.channel_points_custom_reward_redemption.add","subscription_version":"1"},"payload":{"subscription":{"id":"s1","type":"channel.channel_points_custom_reward_redemption.add"},"event":{"id":"REDEMPTION","broadcaster_user_id":"42","broadcaster_user_login":"streamer","broadcaster_user_name":"Streamer","user_id":"7","user_login":"LOGIN","user_name":"USER","user_input":"","status":"unfulfilled","reward":{"id":"REWARD","title":"Reward","cost":100,"prompt":""},"redeemed_at":"2026-01-01T00:00:00Z"}}}"""
            .Replace("MESSAGE", messageId).Replace("REDEMPTION", redemptionId).Replace("REWARD", rewardId).Replace("LOGIN", user.ToLowerInvariant()).Replace("USER", user);
}

internal sealed class PlainProtector : ISecretProtector
{
    public byte[] Protect(byte[] data) => data.Reverse().ToArray();
    public byte[] Unprotect(byte[] data) => data.Reverse().ToArray();
}

internal static class Wait
{
    /// <summary>Polls a condition that background work makes true; false after the timeout.</summary>
    public static async Task<bool> ForAsync(Func<bool> condition, int milliseconds = 5000)
    {
        var until = DateTime.UtcNow.AddMilliseconds(milliseconds);
        while (!condition())
        {
            if (DateTime.UtcNow > until) return false;
            await Task.Delay(10);
        }
        return true;
    }
}
