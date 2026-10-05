using System.Collections.Concurrent;
using System.Net;
using System.Threading.Channels;

namespace KH2Trainer.Twitch;

public enum TwitchConnectionState { NotConfigured, Disconnected, WaitingForAuthorization, Connecting, Connected, Error }

/// <summary>Where the service talks to; tests point these at local fakes.</summary>
public sealed record TwitchEndpoints(Uri Identity, Uri Api, Uri EventSub)
{
    public static readonly TwitchEndpoints Twitch = new(new Uri("https://id.twitch.tv/"), new Uri("https://api.twitch.tv/helix/"), EventSubClient.DefaultEndpoint);
}

/// <summary>
/// Connects the trainer to a Twitch channel: device-code login, reward synchronization (an
/// enabled reward exists on Twitch, a disabled one is deleted), live redemptions over EventSub,
/// and fulfilling or refunding each redemption once the effect engine decided.
/// Call the public methods from the UI thread; events are raised on the captured context.
/// </summary>
public sealed class TwitchService : IRedemptionSink, IAsyncDisposable
{
    private readonly HttpClient http;
    private readonly TokenStore tokens;
    private readonly TwitchSettings settings;
    private readonly Action saveSettings;
    private readonly Action<Redemption> submit;
    private readonly Action<string> log;
    private readonly Func<IEventSubTransport> transports;
    private readonly TwitchEndpoints endpoints;
    private readonly SynchronizationContext? context;
    private readonly TwitchAuth auth;
    private readonly ConcurrentDictionary<string, string> rewardKeys = new(StringComparer.Ordinal);
    /// <summary>Redemptions handed to the engine that are not fulfilled or refunded yet.</summary>
    private readonly ConcurrentDictionary<string, byte> open = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> rewardStatus = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim syncLock = new(1, 1), refreshLock = new(1, 1);
    private readonly Channel<(Redemption Redemption, bool Fulfilled, string Reason)> statusUpdates = Channel.CreateUnbounded<(Redemption, bool, string)>();
    private readonly Task statusWorker;
    private volatile TwitchToken? token;
    private DateTimeOffset lastRefresh;
    private HelixClient? helix;
    private CancellationTokenSource? session;
    private Task? eventSub;

    public TwitchService(HttpClient http, TokenStore tokens, TwitchSettings settings, Action saveSettings, Action<Redemption> submit,
        Action<string> log, Func<IEventSubTransport>? transports = null, TwitchEndpoints? endpoints = null, Func<TimeSpan, CancellationToken, Task>? delay = null)
    {
        this.http = http; this.tokens = tokens; this.settings = settings; this.saveSettings = saveSettings; this.submit = submit; this.log = log;
        this.transports = transports ?? (() => new WebSocketTransport());
        this.endpoints = endpoints ?? TwitchEndpoints.Twitch;
        context = SynchronizationContext.Current;
        auth = new TwitchAuth(http, this.endpoints.Identity, delay);
        Delay = delay ?? Task.Delay;
        statusWorker = Task.Run(ProcessStatusUpdatesAsync);
        foreach (var (key, reward) in settings.Rewards) if (reward.TwitchRewardId is { } id) rewardKeys[id] = key;
        State = settings.EffectiveClientId.Length == 0 ? TwitchConnectionState.NotConfigured : TwitchConnectionState.Disconnected;
        StatusText = State == TwitchConnectionState.NotConfigured ? "Enter a Twitch Client ID to get started." : "Not connected to Twitch.";
    }

    private Func<TimeSpan, CancellationToken, Task> Delay { get; }
    public TwitchConnectionState State { get; private set; }
    public string StatusText { get; private set; }
    public string? UserCode { get; private set; }
    public string? VerificationUri { get; private set; }
    public string? Login { get; private set; }
    public string? DisplayName { get; private set; }
    public string? BroadcasterId { get; private set; }
    public EventSubState EventSubState { get; private set; } = EventSubState.Disconnected;
    public string EventSubText { get; private set; } = "";
    public bool RewardsPaused { get; private set; }
    public bool IsConnected => State == TwitchConnectionState.Connected;
    public int RewardsOnTwitch => settings.Rewards.Values.Count(r => r.TwitchRewardId != null);
    public string RewardsDashboardUrl => $"https://dashboard.twitch.tv/u/{Login ?? "me"}/viewer-rewards/channel-points/rewards";

    public event Action? StateChanged;
    public event Action<string>? RewardStatusChanged;
    /// <summary>Raised with the activation URL when the streamer must confirm the login code.</summary>
    public event Action<string>? AuthorizationRequested;

    public string RewardStatus(string key) => rewardStatus.GetValueOrDefault(key)
        ?? (settings.Rewards.GetValueOrDefault(key) is { Enabled: true } ? IsConnected ? "Not on Twitch yet" : "Created when you connect" : "Off");

    public async Task ConnectAsync()
    {
        string clientId = settings.EffectiveClientId;
        if (clientId.Length == 0) { SetState(TwitchConnectionState.NotConfigured, "Enter a Twitch Client ID to get started."); return; }
        await StopSessionAsync();
        var current = session = new CancellationTokenSource();
        var cancellation = current.Token;
        try
        {
            SetState(TwitchConnectionState.Connecting, "Checking the saved Twitch login…");
            token = tokens.Load(clientId);
            TokenValidation? owner = token is null ? null : await auth.ValidateAsync(token.AccessToken, cancellation);
            if (owner is null && token is { RefreshToken.Length: > 0 })
            {
                try { token = await auth.RefreshAsync(clientId, token.RefreshToken, cancellation); tokens.Save(clientId, token); owner = await auth.ValidateAsync(token.AccessToken, cancellation); }
                catch (TwitchAuthException) { owner = null; }
            }
            if (owner is null || !owner.Scopes.Contains(TwitchAuth.Scope))
            {
                var device = await auth.StartDeviceFlowAsync(clientId, cancellation);
                UserCode = device.UserCode; VerificationUri = device.VerificationUri;
                SetState(TwitchConnectionState.WaitingForAuthorization, $"Confirm the code {device.UserCode} on Twitch to finish connecting.");
                AuthorizationRequested?.Invoke(device.VerificationUri);
                token = await auth.WaitForDeviceTokenAsync(clientId, device, cancellation);
                tokens.Save(clientId, token);
                owner = await auth.ValidateAsync(token.AccessToken, cancellation) ?? throw new TwitchAuthException("Twitch rejected the new login. Try again.");
                UserCode = null; VerificationUri = null;
            }
            BroadcasterId = owner.UserId; Login = owner.Login;
            helix = new HelixClient(http, clientId, _ => Task.FromResult(token!.AccessToken), RefreshAccessTokenAsync, endpoints.Api, Delay);
            var user = await helix.GetUserAsync(owner.UserId, cancellation);
            DisplayName = user.DisplayName.Length > 0 ? user.DisplayName : user.Login;
            if (user.BroadcasterType is not ("affiliate" or "partner"))
            {
                helix = null;
                SetState(TwitchConnectionState.Error, $"{DisplayName} is not a Twitch Affiliate or Partner yet. Channel points and custom rewards need one of these.");
                return;
            }
            SetState(TwitchConnectionState.Connecting, "Synchronizing rewards with Twitch…");
            RewardsPaused = false;
            await SyncAllAsync();
            await RefundLeftoversAsync(cancellation);
            string broadcaster = owner.UserId;
            var api = helix;
            var client = new EventSubClient(transports, (id, c) => api.SubscribeRedemptionsAsync(broadcaster, id, c), OnRedemption, OnEventSubState, endpoints.EventSub, Delay);
            eventSub = Task.Run(() => client.RunAsync(cancellation));
            SetState(TwitchConnectionState.Connected, $"Connected as {DisplayName}.");
            log($"Twitch: connected as {DisplayName}.");
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
            UserCode = null; VerificationUri = null;
            SetState(TwitchConnectionState.Disconnected, "Connection cancelled.");
        }
        catch (Exception error) when (error is TwitchAuthException or TwitchApiException or HttpRequestException or TaskCanceledException)
        {
            UserCode = null; VerificationUri = null;
            SetState(TwitchConnectionState.Error, error is HttpRequestException or TaskCanceledException ? $"Twitch is not reachable: {error.Message}" : error.Message);
        }
    }

    /// <summary>Call after the Client ID changed. A different app means a new login, so the session ends.</summary>
    public async Task ClientIdChangedAsync()
    {
        await StopSessionAsync();
        token = null; helix = null; UserCode = null; VerificationUri = null;
        SetState(settings.EffectiveClientId.Length == 0 ? TwitchConnectionState.NotConfigured : TwitchConnectionState.Disconnected,
            settings.EffectiveClientId.Length == 0 ? "Enter a Twitch Client ID to get started." : "Not connected to Twitch.");
    }

    /// <summary>Stops a connection attempt that waits for the login code.</summary>
    public void CancelConnect() => session?.Cancel();

    public async Task DisconnectAsync(bool forgetLogin)
    {
        await StopSessionAsync();
        if (forgetLogin)
        {
            if (token is { } current) { try { await auth.RevokeAsync(settings.EffectiveClientId, current.AccessToken, CancellationToken.None); } catch (Exception) { } }
            tokens.Clear();
            token = null;
        }
        helix = null;
        SetState(settings.EffectiveClientId.Length == 0 ? TwitchConnectionState.NotConfigured : TwitchConnectionState.Disconnected,
            forgetLogin ? "Logged out of Twitch." : "Disconnected from Twitch.");
    }

    /// <summary>Brings every reward on Twitch in line with the settings and removes rewards this app no longer uses.</summary>
    public async Task SyncAllAsync()
    {
        if (helix is not { } api || BroadcasterId is not { } broadcaster) return;
        await syncLock.WaitAsync();
        try
        {
            var remote = await api.GetManageableRewardsAsync(broadcaster);
            var byId = remote.ToDictionary(r => r.Id, StringComparer.Ordinal);
            foreach (var reward in settings.Rewards.Values)
                if (reward.TwitchRewardId is { } id && !byId.ContainsKey(id)) { reward.TwitchRewardId = null; reward.SyncedFingerprint = null; }
            // Adopt this app's rewards by title (for example after a lost settings file); icons set in the dashboard stay.
            var used = settings.Rewards.Values.Select(r => r.TwitchRewardId).OfType<string>().ToHashSet(StringComparer.Ordinal);
            foreach (var effect in EffectCatalog.All)
            {
                if (settings.Rewards.GetValueOrDefault(effect.Key) is not { Enabled: true, TwitchRewardId: null } reward) continue;
                string title = RewardResolver.Title(effect, settings);
                if (remote.FirstOrDefault(r => !used.Contains(r.Id) && string.Equals(r.Title, title, StringComparison.OrdinalIgnoreCase)) is { } orphan)
                {
                    reward.TwitchRewardId = orphan.Id; reward.SyncedFingerprint = null; used.Add(orphan.Id);
                }
            }
            foreach (var reward in remote)
            {
                if (settings.Rewards.Values.Any(r => r.Enabled && r.TwitchRewardId == reward.Id)) continue;
                await api.DeleteRewardAsync(broadcaster, reward.Id);
                foreach (var stale in settings.Rewards.Values.Where(r => r.TwitchRewardId == reward.Id)) { stale.TwitchRewardId = null; stale.SyncedFingerprint = null; }
            }
            foreach (var effect in EffectCatalog.All) await SyncCoreAsync(api, broadcaster, effect, byId);
        }
        catch (TwitchApiException error) { log("Twitch: " + error.Message); SetState(State, error.Message); }
        finally { RebuildKeys(); Save(); syncLock.Release(); }
    }

    /// <summary>Creates, updates or deletes one reward on Twitch to match its settings.</summary>
    public async Task SyncRewardAsync(string key)
    {
        var effect = EffectCatalog.Find(key) ?? throw new ArgumentException($"Unknown reward '{key}'.");
        if (helix is not { } api || BroadcasterId is not { } broadcaster) { SetRewardStatus(key, RewardStatus(key)); Save(); return; }
        await syncLock.WaitAsync();
        try { await SyncCoreAsync(api, broadcaster, effect, null); }
        finally { RebuildKeys(); Save(); syncLock.Release(); }
    }

    private async Task SyncCoreAsync(HelixClient api, string broadcaster, EffectDefinition effect, IReadOnlyDictionary<string, TwitchReward>? remote)
    {
        var reward = settings.For(effect.Key);
        try
        {
            if (!reward.Enabled)
            {
                if (reward.TwitchRewardId is { } id) { await api.DeleteRewardAsync(broadcaster, id); log($"Twitch: deleted reward {RewardResolver.Title(effect, settings)}."); }
                reward.TwitchRewardId = null; reward.SyncedFingerprint = null;
                SetRewardStatus(effect.Key, "Off");
                return;
            }
            var spec = RewardResolver.Spec(effect, settings);
            if (spec.Validate() is { } problem) { SetRewardStatus(effect.Key, "Error: " + problem); return; }
            string fingerprint = spec.Fingerprint();
            if (reward.TwitchRewardId is null)
            {
                var created = await api.CreateRewardAsync(broadcaster, spec);
                reward.TwitchRewardId = created.Id; reward.SyncedFingerprint = fingerprint;
                if (RewardsPaused) await api.UpdateRewardAsync(broadcaster, created.Id, null, true);
                log($"Twitch: created reward {spec.Title}.");
            }
            else if (reward.SyncedFingerprint != fingerprint || remote?.GetValueOrDefault(reward.TwitchRewardId)?.IsPaused is bool paused && paused != RewardsPaused)
            {
                try { await api.UpdateRewardAsync(broadcaster, reward.TwitchRewardId, spec, RewardsPaused); }
                catch (TwitchApiException error) when (error.Status == HttpStatusCode.NotFound)
                {
                    reward.TwitchRewardId = (await api.CreateRewardAsync(broadcaster, spec)).Id; // Deleted on Twitch meanwhile.
                }
                reward.SyncedFingerprint = fingerprint;
            }
            SetRewardStatus(effect.Key, RewardsPaused ? "On Twitch (paused)" : "On Twitch");
        }
        catch (TwitchApiException error) when (error.Status != HttpStatusCode.Unauthorized)
        {
            SetRewardStatus(effect.Key, "Error: " + error.Message);
            log($"Twitch: {RewardResolver.Title(effect, settings)}: {error.Message}");
        }
    }

    /// <summary>Pauses or resumes every reward on Twitch; paused rewards stay visible but cannot be redeemed.</summary>
    public async Task SetPausedAsync(bool paused)
    {
        RewardsPaused = paused;
        if (helix is { } api && BroadcasterId is { } broadcaster)
        {
            await syncLock.WaitAsync();
            try
            {
                foreach (var effect in EffectCatalog.All)
                {
                    var reward = settings.Rewards.GetValueOrDefault(effect.Key);
                    if (reward?.TwitchRewardId is not { } id) continue;
                    try { await api.UpdateRewardAsync(broadcaster, id, null, paused); SetRewardStatus(effect.Key, paused ? "On Twitch (paused)" : "On Twitch"); }
                    catch (TwitchApiException error) { SetRewardStatus(effect.Key, "Error: " + error.Message); }
                }
            }
            finally { syncLock.Release(); }
        }
        StateChanged?.Invoke();
    }

    /// <summary>Called when the trainer closes: optionally pauses the rewards so nobody redeems while it is off.</summary>
    public async Task ShutdownAsync()
    {
        if (settings.PauseRewardsWhenClosed && helix != null)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            try { await SetPausedAsync(true).WaitAsync(timeout.Token); } catch (Exception) { }
        }
        await StopSessionAsync();
        statusUpdates.Writer.TryComplete();
        try { await statusWorker.WaitAsync(TimeSpan.FromSeconds(5)); } catch (Exception) { }
    }

    public void Fulfill(Redemption redemption) => Queue(redemption, true, "");
    public void Refund(Redemption redemption, string reason) => Queue(redemption, false, reason);

    private void Queue(Redemption redemption, bool fulfilled, string reason)
    {
        if (redemption.IsTest || redemption.TwitchRewardId.Length == 0) return;
        open.TryRemove(redemption.Id, out _);
        statusUpdates.Writer.TryWrite((redemption, fulfilled, reason));
    }

    private async Task ProcessStatusUpdatesAsync()
    {
        await foreach (var (redemption, fulfilled, reason) in statusUpdates.Reader.ReadAllAsync())
        {
            if (helix is not { } api || BroadcasterId is not { } broadcaster)
            {
                Post(() => log($"Twitch: not connected; {redemption.UserName}'s redemption stays in your Twitch request queue."));
                continue;
            }
            try
            {
                await api.UpdateRedemptionStatusAsync(broadcaster, redemption.TwitchRewardId, redemption.Id, fulfilled);
                if (!fulfilled) Post(() => log($"Twitch: refunded {redemption.UserName} ({reason})."));
            }
            catch (Exception error)
            {
                Post(() => log($"Twitch: could not {(fulfilled ? "fulfil" : "refund")} {redemption.UserName}'s redemption: {error.Message}"));
            }
        }
    }

    /// <summary>Refunds redemptions made while the trainer was offline; they never ran. Ones the engine still holds stay.</summary>
    private async Task RefundLeftoversAsync(CancellationToken cancellation)
    {
        if (helix is not { } api || BroadcasterId is not { } broadcaster) return;
        int refunded = 0;
        foreach (var reward in settings.Rewards.Values.Where(r => r.TwitchRewardId != null).ToArray())
        {
            try
            {
                foreach (string id in await api.GetUnfulfilledRedemptionIdsAsync(broadcaster, reward.TwitchRewardId!, cancellation))
                {
                    if (open.ContainsKey(id)) continue;
                    await api.UpdateRedemptionStatusAsync(broadcaster, reward.TwitchRewardId!, id, false, cancellation);
                    refunded++;
                }
            }
            catch (TwitchApiException error) { log("Twitch: " + error.Message); }
        }
        if (refunded > 0) log($"Twitch: refunded {refunded} redemption(s) made while the trainer was offline.");
    }

    private async Task<string> RefreshAccessTokenAsync(CancellationToken cancellation)
    {
        await refreshLock.WaitAsync(cancellation);
        try
        {
            if (token is { } current && DateTimeOffset.UtcNow - lastRefresh < TimeSpan.FromSeconds(10)) return current.AccessToken;
            var refreshed = await auth.RefreshAsync(settings.EffectiveClientId, token?.RefreshToken ?? "", cancellation);
            token = refreshed; lastRefresh = DateTimeOffset.UtcNow;
            tokens.Save(settings.EffectiveClientId, refreshed);
            return refreshed.AccessToken;
        }
        catch (TwitchAuthException error)
        {
            Post(() => SetState(TwitchConnectionState.Error, error.Message));
            throw;
        }
        finally { refreshLock.Release(); }
    }

    private void OnRedemption(RedemptionEvent redemption)
    {
        if (!rewardKeys.TryGetValue(redemption.RewardId, out string? key)) return; // Not one of the trainer's rewards.
        open[redemption.Id] = 0;
        submit(new Redemption(redemption.Id, key, redemption.UserName, redemption.UserInput, redemption.RedeemedAt, redemption.RewardId));
    }

    private void OnEventSubState(EventSubState state, string text) => Post(() =>
    {
        EventSubState = state; EventSubText = text;
        if (state == EventSubState.Failed) SetState(TwitchConnectionState.Error, text);
        else StateChanged?.Invoke();
    });

    private async Task StopSessionAsync()
    {
        var current = session;
        session = null;
        if (current is null) return;
        current.Cancel();
        if (eventSub is { } running) { try { await running.WaitAsync(TimeSpan.FromSeconds(5)); } catch (Exception) { } }
        eventSub = null;
        current.Dispose();
    }

    private void RebuildKeys()
    {
        rewardKeys.Clear();
        foreach (var (key, reward) in settings.Rewards) if (reward.TwitchRewardId is { } id) rewardKeys[id] = key;
    }

    private void Save() { try { saveSettings(); } catch (Exception error) { log("Twitch: settings could not be saved: " + error.Message); } }

    private void SetRewardStatus(string key, string status)
    {
        rewardStatus[key] = status;
        RewardStatusChanged?.Invoke(key);
    }

    private void SetState(TwitchConnectionState state, string text)
    {
        State = state; StatusText = text;
        StateChanged?.Invoke();
    }

    private void Post(Action action)
    {
        if (context is null) action();
        else context.Post(_ => action(), null);
    }

    public async ValueTask DisposeAsync()
    {
        await StopSessionAsync();
        statusUpdates.Writer.TryComplete();
        syncLock.Dispose(); refreshLock.Dispose();
    }
}
