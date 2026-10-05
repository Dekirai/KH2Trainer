using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

namespace KH2Trainer.Twitch;

public sealed record RedemptionEvent(string Id, string RewardId, string RewardTitle, string UserName, string UserInput, DateTimeOffset RedeemedAt);

public enum EventSubState { Disconnected, Connecting, Connected, Reconnecting, Failed }

/// <summary>A message-oriented connection; abstracted so the protocol can be tested without a network.</summary>
public interface IEventSubTransport : IAsyncDisposable
{
    Task ConnectAsync(Uri uri, CancellationToken cancellation);
    /// <summary>Returns the next text message, or null when the server closed the connection.</summary>
    Task<string?> ReceiveAsync(CancellationToken cancellation);
}

public sealed class WebSocketTransport : IEventSubTransport
{
    private readonly ClientWebSocket socket = new();

    public Task ConnectAsync(Uri uri, CancellationToken cancellation) => socket.ConnectAsync(uri, cancellation);

    public async Task<string?> ReceiveAsync(CancellationToken cancellation)
    {
        var buffer = new byte[16 * 1024];
        using var message = new MemoryStream();
        while (true)
        {
            var result = await socket.ReceiveAsync(buffer, cancellation);
            if (result.MessageType == WebSocketMessageType.Close) return null;
            message.Write(buffer, 0, result.Count);
            if (message.Length > 1024 * 1024) throw new InvalidDataException("EventSub message too large.");
            if (result.EndOfMessage) return Encoding.UTF8.GetString(message.ToArray());
        }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (socket.State == WebSocketState.Open)
            {
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", timeout.Token);
            }
        }
        catch (Exception) { }
        socket.Dispose();
    }
}

/// <summary>An EventSub message reduced to the fields the trainer uses.</summary>
public sealed record EventSubMessage(string MessageId, string MessageType, string SubscriptionType, string? SessionId,
    string? ReconnectUrl, int KeepaliveSeconds, RedemptionEvent? Redemption, string? RevocationStatus)
{
    public const string RedemptionType = "channel.channel_points_custom_reward_redemption.add";

    public static EventSubMessage Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        var metadata = root.GetProperty("metadata");
        var payload = root.TryGetProperty("payload", out var p) ? p : default;
        string type = Text(metadata, "message_type"), subscription = Text(metadata, "subscription_type");
        string? sessionId = null, reconnect = null, revocation = null;
        int keepalive = 10;
        if (payload.ValueKind == JsonValueKind.Object && payload.TryGetProperty("session", out var session))
        {
            sessionId = Text(session, "id");
            reconnect = session.TryGetProperty("reconnect_url", out var url) && url.ValueKind == JsonValueKind.String ? url.GetString() : null;
            // The reconnect message sends null here.
            if (session.TryGetProperty("keepalive_timeout_seconds", out var seconds) && seconds.ValueKind == JsonValueKind.Number && seconds.TryGetInt32(out int value)) keepalive = value;
        }
        RedemptionEvent? redemption = null;
        if (type == "notification" && subscription == RedemptionType && payload.TryGetProperty("event", out var e))
        {
            var reward = e.GetProperty("reward");
            DateTimeOffset.TryParse(Text(e, "redeemed_at"), out var redeemedAt);
            string name = Text(e, "user_name");
            redemption = new RedemptionEvent(Text(e, "id"), Text(reward, "id"), Text(reward, "title"),
                name.Length > 0 ? name : Text(e, "user_login"), Text(e, "user_input"), redeemedAt);
        }
        if (type == "revocation" && payload.TryGetProperty("subscription", out var sub)) revocation = Text(sub, "status");
        return new EventSubMessage(Text(metadata, "message_id"), type, subscription, sessionId, reconnect, keepalive, redemption, revocation);
    }

    private static string Text(JsonElement element, string name) =>
        element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
}

public sealed class EventSubRevokedException(string status) : Exception($"Twitch revoked the redemption subscription ({status}). Connect again.");

/// <summary>
/// Receives channel point redemptions over EventSub WebSockets: subscribes after the welcome
/// message, watches the keepalive, follows Twitch's reconnect handover without losing the
/// subscription, ignores duplicate deliveries and reconnects with back-off after failures.
/// </summary>
public sealed class EventSubClient(
    Func<IEventSubTransport> transportFactory,
    Func<string, CancellationToken, Task> subscribe,
    Action<RedemptionEvent> onRedemption,
    Action<EventSubState, string> onState,
    Uri? endpoint = null,
    Func<TimeSpan, CancellationToken, Task>? delay = null,
    Action<bool>? onSubscribed = null)
{
    public static readonly Uri DefaultEndpoint = new("wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30");
    private readonly Uri start = endpoint ?? DefaultEndpoint;
    private readonly Func<TimeSpan, CancellationToken, Task> wait = delay ?? Task.Delay;
    private readonly HashSet<string> seen = new(StringComparer.Ordinal);
    private readonly Queue<string> seenOrder = new();

    public async Task RunAsync(CancellationToken cancellation)
    {
        IEventSubTransport? current = null;
        int failures = 0, keepalive = 30;
        bool hadSession = false;
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                try
                {
                    if (current is null)
                    {
                        onState(failures == 0 ? EventSubState.Connecting : EventSubState.Reconnecting, "Connecting to Twitch EventSub…");
                        current = transportFactory();
                        await current.ConnectAsync(start, cancellation);
                        var welcome = await ExpectWelcomeAsync(current, cancellation);
                        keepalive = welcome.KeepaliveSeconds;
                        await subscribe(welcome.SessionId!, cancellation);
                        // After a connection loss, redemptions made meanwhile were not delivered; the owner can catch up on them.
                        onSubscribed?.Invoke(hadSession);
                        hadSession = true;
                        failures = 0;
                        onState(EventSubState.Connected, "Listening for channel point redemptions.");
                    }
                    string? json = await ReceiveAsync(current, TimeSpan.FromSeconds(keepalive + 10), cancellation)
                        ?? throw new IOException("The EventSub connection was closed or went quiet.");
                    var message = EventSubMessage.Parse(json);
                    switch (message.MessageType)
                    {
                        case "notification":
                            Deliver(message);
                            break;
                        case "session_reconnect" when message.ReconnectUrl is { } url:
                            // Twitch hands the subscriptions to the new session and keeps delivering on the old
                            // socket until the new one is welcomed, so both are read during the handover.
                            var replacement = transportFactory();
                            try
                            {
                                await replacement.ConnectAsync(new Uri(url), cancellation);
                                keepalive = (await HandOverAsync(current, replacement, cancellation)).KeepaliveSeconds;
                            }
                            catch { await replacement.DisposeAsync(); throw; }
                            await current.DisposeAsync();
                            current = replacement;
                            break;
                        case "revocation":
                            throw new EventSubRevokedException(message.RevocationStatus ?? "unknown");
                    }
                }
                catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { break; }
                catch (EventSubRevokedException error)
                {
                    onState(EventSubState.Failed, error.Message);
                    return;
                }
                catch (Exception error)
                {
                    if (current is not null) { await current.DisposeAsync(); current = null; }
                    failures++;
                    var backoff = TimeSpan.FromSeconds(Math.Min(60, Math.Pow(2, Math.Min(failures, 6))));
                    onState(EventSubState.Reconnecting, $"Connection to Twitch lost ({error.Message}). Retrying in {backoff.TotalSeconds:0} s.");
                    try { await wait(backoff, cancellation); }
                    catch (OperationCanceledException) { break; }
                }
            }
        }
        finally
        {
            if (current is not null) await current.DisposeAsync();
            onState(EventSubState.Disconnected, "Disconnected from Twitch EventSub.");
        }
    }

    private void Deliver(EventSubMessage message)
    {
        if (message.Redemption is { } redemption && Remember(message.MessageId)) onRedemption(redemption);
    }

    /// <summary>
    /// Waits for the new socket's welcome while still delivering notifications from the old one, then
    /// takes what the old socket still has until it closes or stays quiet for a moment.
    /// </summary>
    private async Task<EventSubMessage> HandOverAsync(IEventSubTransport old, IEventSubTransport replacement, CancellationToken cancellation)
    {
        var welcome = ExpectWelcomeAsync(replacement, cancellation);
        using var draining = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        try
        {
            Task<string?>? receive = null;
            Task? quiet = null;
            while (true)
            {
                receive ??= old.ReceiveAsync(draining.Token);
                if (welcome.IsCompleted) quiet ??= Task.Delay(HandoverQuietPeriod, cancellation);
                if (await Task.WhenAny(receive, quiet ?? welcome) != receive)
                {
                    if (quiet != null) break; // Welcomed and the old socket has nothing more.
                    continue;
                }
                string? json = await receive;
                receive = null; quiet = null;
                if (json is null) break; // The old socket closed.
                var message = EventSubMessage.Parse(json);
                if (message.MessageType == "notification") Deliver(message);
            }
        }
        catch (Exception error) when (error is not OperationCanceledException || !cancellation.IsCancellationRequested) { /* The old socket failed; the new one counts. */ }
        finally { draining.Cancel(); }
        return await welcome;
    }

    private static readonly TimeSpan HandoverQuietPeriod = TimeSpan.FromMilliseconds(300);

    private async Task<EventSubMessage> ExpectWelcomeAsync(IEventSubTransport transport, CancellationToken cancellation)
    {
        string json = await ReceiveAsync(transport, TimeSpan.FromSeconds(15), cancellation)
            ?? throw new IOException("Twitch did not send a welcome message.");
        var message = EventSubMessage.Parse(json);
        if (message.MessageType != "session_welcome" || string.IsNullOrEmpty(message.SessionId))
            throw new IOException($"Expected a welcome message but received '{message.MessageType}'.");
        return message;
    }

    private static async Task<string?> ReceiveAsync(IEventSubTransport transport, TimeSpan timeout, CancellationToken cancellation)
    {
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        limit.CancelAfter(timeout);
        try { return await transport.ReceiveAsync(limit.Token); }
        catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { return null; }
    }

    private bool Remember(string messageId)
    {
        if (messageId.Length == 0) return true;
        if (!seen.Add(messageId)) return false;
        seenOrder.Enqueue(messageId);
        while (seenOrder.Count > 500) seen.Remove(seenOrder.Dequeue());
        return true;
    }
}
