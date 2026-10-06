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
    private sealed record Decision(Redemption Redemption, bool Fulfilled, string Reason);

    private readonly HttpClient http;
    private readonly TokenStore tokens;
    private readonly TwitchSettings settings;
    private readonly Action saveSettings;
    private readonly Action<Redemption> submit;
    private readonly Action<string> log;
    /// <summary>Asks the engine to drop a waiting redemption; false when its effect already runs.</summary>
    private readonly Func<string, Task<bool>>? withdraw;
    private readonly Func<IEventSubTransport> transports;
    private readonly TwitchEndpoints endpoints;
    private readonly SynchronizationContext? context;
    private readonly TwitchAuth auth;
    private readonly ConcurrentDictionary<string, string> rewardKeys = new(StringComparer.Ordinal);
    /// <summary>Redemptions handed to the engine that are not fulfilled or refunded yet.</summary>
    private readonly ConcurrentDictionary<string, byte> open = new(StringComparer.Ordinal);
    /// <summary>Fulfil/refund decisions Twitch has not confirmed yet; retried after a reconnect.</summary>
    private readonly ConcurrentDictionary<string, Decision> decisions = new(StringComparer.Ordinal);
    /// <summary>Redemptions already refunded because their reward was deleted; the engine's later decision is dropped.</summary>
    private readonly ConcurrentDictionary<string, byte> withdrawn = new(StringComparer.Ordinal);
    private readonly HashSet<string> seen = new(StringComparer.Ordinal);
    private readonly Queue<string> seenOrder = new();
    private readonly Dictionary<string, string> rewardStatus = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim syncLock = new(1, 1), refreshLock = new(1, 1);
    private readonly Channel<string> statusUpdates = Channel.CreateUnbounded<string>();
    private readonly Task statusWorker;
    private volatile TwitchToken? token;
    private volatile HelixClient? helix;
    private CancellationTokenSource? session;
    private Task? eventSub, validation;

    public TwitchService(HttpClient http, TokenStore tokens, TwitchSettings settings, Action saveSettings, Action<Redemption> submit,
        Action<string> log, Func<IEventSubTransport>? transports = null, TwitchEndpoints? endpoints = null, Func<TimeSpan, CancellationToken, Task>? delay = null,
        Func<string, Task<bool>>? withdraw = null)
    {
        this.http = http; this.tokens = tokens; this.settings = settings; this.saveSettings = saveSettings; this.submit = submit; this.log = log; this.withdraw = withdraw;
        this.transports = transports ?? (() => new WebSocketTransport());
        this.endpoints = endpoints ?? TwitchEndpoints.Twitch;
        context = SynchronizationContext.Current;
        auth = new TwitchAuth(http, this.endpoints.Identity, delay);
        Delay = delay ?? Task.Delay;
        statusWorker = Task.Run(ProcessStatusUpdatesAsync);
        RebuildKeys();
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
    /// <summary>A login is stored for the current Client ID (used to reconnect silently at startup).</summary>
    public bool HasSavedLogin => settings.EffectiveClientId.Length > 0 && tokens.Load(settings.EffectiveClientId) != null;
    public int RewardsOnTwitch => settings.Rewards.Values.Count(r => r.TwitchRewardId != null);
    public string RewardsDashboardUrl => $"https://dashboard.twitch.tv/u/{Login ?? "me"}/viewer-rewards/channel-points/rewards";

    public event Action? StateChanged;
    public event Action<string>? RewardStatusChanged;
    /// <summary>Raised with the activation URL when the streamer must confirm the login code.</summary>
    public event Action<string>? AuthorizationRequested;

    public string RewardStatus(string key) => rewardStatus.GetValueOrDefault(key)
        ?? (settings.Rewards.GetValueOrDefault(key) is { Enabled: true } ? IsConnected ? "Not on Twitch yet" : "Created when you connect" : "Off");

    /// <summary>Connects with the saved login, or (interactive) asks the streamer to confirm a login code.</summary>
    public async Task ConnectAsync(bool interactive = true)
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
                try
                {
                    token = await auth.RefreshAsync(clientId, token.RefreshToken, cancellation);
                    SaveToken(clientId, token);
                    owner = await auth.ValidateAsync(token.AccessToken, cancellation);
                }
                catch (TwitchAuthException) { owner = null; }
            }
            if (owner is null || !owner.Scopes.Contains(TwitchAuth.Scope))
            {
                if (!interactive) { SetState(TwitchConnectionState.Disconnected, "Not connected to Twitch. Press Connect to log in."); return; }
                var device = await auth.StartDeviceFlowAsync(clientId, cancellation);
                UserCode = device.UserCode; VerificationUri = device.VerificationUri;
                SetState(TwitchConnectionState.WaitingForAuthorization, $"Confirm the code {device.UserCode} on Twitch to finish connecting.");
                AuthorizationRequested?.Invoke(device.VerificationUri);
                token = await auth.WaitForDeviceTokenAsync(clientId, device, cancellation);
                SaveToken(clientId, token);
                owner = await auth.ValidateAsync(token.AccessToken, cancellation) ?? throw new TwitchAuthException("Twitch rejected the new login. Try again.");
                UserCode = null; VerificationUri = null;
            }
            BroadcasterId = owner.UserId; Login = owner.Login;
            var api = helix = new HelixClient(http, clientId, _ => Task.FromResult(token!.AccessToken), RefreshAccessTokenAsync, endpoints.Api, Delay);
            var user = await api.GetUserAsync(owner.UserId, cancellation);
            DisplayName = user.DisplayName.Length > 0 ? user.DisplayName : user.Login;
            if (user.BroadcasterType is not ("affiliate" or "partner"))
            {
                helix = null;
                SetState(TwitchConnectionState.Error, $"{DisplayName} is not a Twitch Affiliate or Partner yet. Channel points and custom rewards need one of these.");
                return;
            }
            SetState(TwitchConnectionState.Connecting, "Synchronizing rewards with Twitch…");
            RewardsPaused = false;
            // First the decisions made while offline, then the redemptions nobody handled, then the rewards themselves.
            await DeliverPendingAsync();
            await RefundLeftoversAsync(api, owner.UserId, cancellation);
            await SyncAllAsync();
            string broadcaster = owner.UserId;
            var client = new EventSubClient(transports, (id, c) => api.SubscribeRedemptionsAsync(broadcaster, id, c), OnRedemption, OnEventSubState, endpoints.EventSub, Delay,
                // After every subscription: redemptions made before it (during the sync, or a connection loss) are caught up.
                afterOutage => Post(() => _ = RecoverMissedAsync(cancellation)));
            eventSub = Task.Run(() => client.RunAsync(cancellation));
            validation = Task.Run(() => ValidateRegularlyAsync(cancellation));
            SetState(TwitchConnectionState.Connected, $"Connected as {DisplayName}.");
            log($"Twitch: connected as {DisplayName}.");
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
        {
            UserCode = null; VerificationUri = null;
            if (ReferenceEquals(session, current)) { helix = null; SetState(TwitchConnectionState.Disconnected, "Connection cancelled."); }
        }
        catch (Exception error)
        {
            UserCode = null; VerificationUri = null; helix = null;
            string message = error switch
            {
                TwitchAuthException or TwitchApiException => error.Message,
                HttpRequestException or TaskCanceledException => $"Twitch is not reachable: {error.Message}",
                _ => $"Connecting to Twitch failed: {error.Message}",
            };
            SetState(TwitchConnectionState.Error, message);
            log("Twitch: " + message);
        }
    }

    /// <summary>Call after the Client ID changed. A different app means a new login, so the session ends.</summary>
    public async Task ClientIdChangedAsync()
    {
        await StopSessionAsync();
        token = null; helix = null; UserCode = null; VerificationUri = null;
        rewardStatus.Clear();
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
            try { tokens.Clear(); } catch (Exception error) when (error is IOException or UnauthorizedAccessException) { log("Twitch: the saved login could not be deleted: " + error.Message); }
            token = null;
        }
        helix = null;
        rewardStatus.Clear();
        SetState(settings.EffectiveClientId.Length == 0 ? TwitchConnectionState.NotConfigured : TwitchConnectionState.Disconnected,
            forgetLogin ? "Logged out of Twitch." : "Disconnected from Twitch.");
    }

    /// <summary>
    /// Brings every reward on Twitch in line with the settings. Rewards of this app that no setting
    /// knows (for example after a lost settings file) are adopted by title or paused, never deleted.
    /// </summary>
    public async Task SyncAllAsync()
    {
        if (helix is not { } api || BroadcasterId is not { } broadcaster) return;
        await syncLock.WaitAsync();
        var adopted = new List<string>();
        try
        {
            // Only after a lost or reset settings file are found rewards switched on; otherwise the switch decides.
            bool fresh = settings.LoadProblem != null || !settings.Rewards.Values.Any(r => r.TwitchRewardId != null);
            var remote = await api.GetManageableRewardsAsync(broadcaster);
            var byId = remote.ToDictionary(r => r.Id, StringComparer.Ordinal);
            foreach (var reward in settings.Rewards.Values)
                if (reward.TwitchRewardId is { } id && !byId.ContainsKey(id)) { reward.TwitchRewardId = null; reward.SyncedFingerprint = null; }
            var used = settings.Rewards.Values.Select(r => r.TwitchRewardId).OfType<string>().ToHashSet(StringComparer.Ordinal);
            foreach (var reward in remote.Where(r => !used.Contains(r.Id)))
            {
                var effect = EffectCatalog.All.FirstOrDefault(e => settings.Rewards.GetValueOrDefault(e.Key)?.TwitchRewardId is null && TitleMatches(e, reward.Title));
                if (effect != null)
                {
                    var setting = settings.For(effect.Key);
                    setting.TwitchRewardId = reward.Id; setting.SyncedFingerprint = null;
                    if (!setting.Enabled && fresh) { setting.Enabled = true; log($"Twitch: found the reward {reward.Title} on your channel and switched it on again."); }
                    used.Add(reward.Id);
                    adopted.Add(effect.Key);
                }
                else if (!reward.IsPaused)
                {
                    // Nothing in the trainer reacts to it; pausing stops viewers from spending points on it.
                    try { await api.UpdateRewardAsync(broadcaster, reward.Id, null, true); }
                    catch (TwitchApiException) { }
                    log($"Twitch: the reward {reward.Title} was created by this app but is not in the trainer's list. It was paused; delete it in your reward dashboard if you no longer need it.");
                }
            }
            foreach (var effect in EffectCatalog.All) await SyncCoreAsync(api, broadcaster, effect, byId);
        }
        catch (TwitchApiException error) { log("Twitch: " + error.Message); SetState(State, error.Message); }
        finally
        {
            RebuildKeys(); Save(); syncLock.Release();
            foreach (string key in adopted) RewardStatusChanged?.Invoke(key);
        }
    }

    /// <summary>Creates, updates or deletes one reward on Twitch to match its settings.</summary>
    public async Task SyncRewardAsync(string key)
    {
        var effect = EffectCatalog.Find(key) ?? throw new ArgumentException($"Unknown reward '{key}'.");
        if (helix is not { } api || BroadcasterId is not { } broadcaster)
        {
            rewardStatus.Remove(key);
            RewardStatusChanged?.Invoke(key);
            Save();
            return;
        }
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
                if (reward.TwitchRewardId is { } id)
                {
                    // Deleting a reward marks its waiting redemptions as fulfilled, so refund them first.
                    await RefundQueueAsync(api, broadcaster, id);
                    await api.DeleteRewardAsync(broadcaster, id);
                    log($"Twitch: deleted reward {RewardResolver.Title(effect, settings)}.");
                }
                reward.TwitchRewardId = null; reward.SyncedFingerprint = null;
                SetRewardStatus(effect.Key, "Off");
                return;
            }
            var spec = RewardResolver.Spec(effect, settings);
            if (spec.Validate() is { } problem) { SetRewardStatus(effect.Key, "Error: " + problem); return; }
            string fingerprint = spec.Fingerprint();
            if (reward.TwitchRewardId is null)
            {
                TwitchReward? created = null;
                try { created = await api.CreateRewardAsync(broadcaster, spec); }
                catch (Exception error) when (error is HttpRequestException or TaskCanceledException
                    || error is TwitchApiException duplicate && duplicate.TwitchMessage.Contains("DUPLICATE", StringComparison.OrdinalIgnoreCase))
                {
                    // The answer may have been lost although Twitch created it (or an earlier create did): adopt this app's reward with that title.
                    var mine = await FindUntrackedAsync(api, broadcaster, spec.Title);
                    if (mine is null) throw;
                    reward.TwitchRewardId = mine.Id; reward.SyncedFingerprint = null; remote = null;
                }
                if (created != null)
                {
                    reward.TwitchRewardId = created.Id; reward.SyncedFingerprint = fingerprint;
                    if (RewardsPaused) await api.UpdateRewardAsync(broadcaster, created.Id, null, true);
                    log($"Twitch: created reward {spec.Title}.");
                    SetRewardStatus(effect.Key, RewardsPaused ? "On Twitch (paused)" : "On Twitch");
                    return;
                }
            }
            if (reward.SyncedFingerprint != fingerprint || remote?.GetValueOrDefault(reward.TwitchRewardId!)?.IsPaused is bool paused && paused != RewardsPaused)
            {
                try { await api.UpdateRewardAsync(broadcaster, reward.TwitchRewardId!, spec, RewardsPaused); }
                catch (TwitchApiException error) when (error.Status == HttpStatusCode.NotFound)
                {
                    reward.TwitchRewardId = (await api.CreateRewardAsync(broadcaster, spec)).Id; // Deleted on Twitch meanwhile.
                    if (RewardsPaused) await api.UpdateRewardAsync(broadcaster, reward.TwitchRewardId, null, true);
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

    private async Task<TwitchReward?> FindUntrackedAsync(HelixClient api, string broadcaster, string title)
    {
        var used = settings.Rewards.Values.Select(r => r.TwitchRewardId).OfType<string>().ToHashSet(StringComparer.Ordinal);
        return (await api.GetManageableRewardsAsync(broadcaster)).FirstOrDefault(r => !used.Contains(r.Id) && string.Equals(r.Title, title, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Refunds every redemption still waiting for a reward before it is deleted. Ones the engine holds are
    /// withdrawn from it; ones whose effect already runs stay (the delete marks them fulfilled, which they are).
    /// Throws when something could not be settled, so the reward is not deleted yet.
    /// </summary>
    private async Task RefundQueueAsync(HelixClient api, string broadcaster, string rewardId)
    {
        int refunded = 0;
        foreach (var redemption in await api.GetUnfulfilledRedemptionsAsync(broadcaster, rewardId))
        {
            if (decisions.TryGetValue(redemption.Id, out var decision))
            {
                if (!await DeliverAsync(redemption.Id, decision))
                    throw new TwitchApiException(HttpStatusCode.ServiceUnavailable, "A redemption could not be settled yet; the reward is removed on the next sync.");
                continue;
            }
            if (open.ContainsKey(redemption.Id))
            {
                withdrawn[redemption.Id] = 0;
                if (withdraw != null && !await withdraw(redemption.Id)) { withdrawn.TryRemove(redemption.Id, out _); continue; }
                open.TryRemove(redemption.Id, out _);
            }
            try { await api.UpdateRedemptionStatusAsync(broadcaster, rewardId, redemption.Id, false); refunded++; }
            catch (TwitchApiException error) when (error.Status == HttpStatusCode.NotFound) { /* Already resolved meanwhile. */ }
        }
        if (refunded > 0) log($"Twitch: refunded {refunded} waiting redemption(s) before deleting the reward.");
    }

    private bool TitleMatches(EffectDefinition effect, string title) =>
        new[] { RewardResolver.Title(effect, settings), effect.Title, effect.TitleDe }.Any(t => string.Equals(t, title, StringComparison.OrdinalIgnoreCase));

    /// <summary>Pauses or resumes every reward on Twitch; paused rewards stay visible but cannot be redeemed.</summary>
    public async Task SetPausedAsync(bool paused)
    {
        RewardsPaused = paused;
        if (helix is { } api && BroadcasterId is { } broadcaster)
        {
            await syncLock.WaitAsync();
            try
            {
                var targets = EffectCatalog.All.Select(e => (e.Key, Id: settings.Rewards.GetValueOrDefault(e.Key)?.TwitchRewardId)).Where(t => t.Id != null).ToArray();
                using var parallel = new SemaphoreSlim(6);
                var results = await Task.WhenAll(targets.Select(async target =>
                {
                    await parallel.WaitAsync();
                    try { await api.UpdateRewardAsync(broadcaster, target.Id!, null, paused); return (target.Key, Error: (string?)null); }
                    catch (TwitchApiException error) { return (target.Key, Error: error.Message); }
                    finally { parallel.Release(); }
                }));
                foreach (var (key, error) in results) SetRewardStatus(key, error is null ? paused ? "On Twitch (paused)" : "On Twitch" : "Error: " + error);
            }
            finally { syncLock.Release(); }
        }
        StateChanged?.Invoke();
    }

    /// <summary>First step of closing: optionally pause the rewards, then stop receiving redemptions.</summary>
    public async Task StopListeningAsync()
    {
        if (settings.PauseRewardsWhenClosed && helix != null)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            try { await SetPausedAsync(true).WaitAsync(timeout.Token); } catch (Exception) { }
        }
        await StopSessionAsync();
    }

    /// <summary>Last step of closing: send the remaining fulfil/refund decisions.</summary>
    public async Task FlushAsync()
    {
        statusUpdates.Writer.TryComplete();
        try { await statusWorker.WaitAsync(TimeSpan.FromSeconds(5)); } catch (Exception) { }
    }

    public async Task ShutdownAsync()
    {
        await StopListeningAsync();
        await FlushAsync();
    }

    public void Fulfill(Redemption redemption) => Queue(redemption, true, "");
    public void Refund(Redemption redemption, string reason) => Queue(redemption, false, reason);

    private void Queue(Redemption redemption, bool fulfilled, string reason)
    {
        if (redemption.IsTest || redemption.TwitchRewardId.Length == 0) return;
        open.TryRemove(redemption.Id, out _);
        if (withdrawn.TryRemove(redemption.Id, out _)) return; // Already refunded when its reward was deleted.
        decisions[redemption.Id] = new Decision(redemption, fulfilled, reason);
        statusUpdates.Writer.TryWrite(redemption.Id);
    }

    private async Task ProcessStatusUpdatesAsync()
    {
        await foreach (string id in statusUpdates.Reader.ReadAllAsync())
            if (decisions.TryGetValue(id, out var decision)) await DeliverAsync(id, decision);
    }

    /// <summary>Sends one decision. It stays queued (and is retried after the next connect) until Twitch confirmed it.</summary>
    private async Task<bool> DeliverAsync(string id, Decision decision)
    {
        var redemption = decision.Redemption;
        if (helix is not { } api || BroadcasterId is not { } broadcaster)
        {
            Post(() => log($"Twitch: not connected; {redemption.UserName}'s redemption is {(decision.Fulfilled ? "fulfilled" : "refunded")} after the next connect."));
            return false;
        }
        try
        {
            await api.UpdateRedemptionStatusAsync(broadcaster, redemption.TwitchRewardId, id, decision.Fulfilled);
            decisions.TryRemove(id, out _);
            if (!decision.Fulfilled) Post(() => log($"Twitch: refunded {redemption.UserName} ({decision.Reason})."));
            return true;
        }
        catch (TwitchApiException error) when (error.Status == HttpStatusCode.NotFound)
        {
            decisions.TryRemove(id, out _); // Already resolved on Twitch (for example the reward was deleted).
            return true;
        }
        catch (Exception error)
        {
            Post(() => log($"Twitch: could not {(decision.Fulfilled ? "fulfil" : "refund")} {redemption.UserName}'s redemption yet ({error.Message}); it is retried after the next connect."));
            return false;
        }
    }

    private async Task DeliverPendingAsync()
    {
        foreach (var (id, decision) in decisions.ToArray()) await DeliverAsync(id, decision);
    }

    /// <summary>Refunds redemptions made while the trainer was offline; they never ran. Ones the engine holds or decided stay.</summary>
    private async Task RefundLeftoversAsync(HelixClient api, string broadcaster, CancellationToken cancellation)
    {
        int refunded = 0;
        foreach (var reward in await api.GetManageableRewardsAsync(broadcaster, cancellation))
        {
            try
            {
                foreach (var redemption in await api.GetUnfulfilledRedemptionsAsync(broadcaster, reward.Id, cancellation))
                {
                    if (open.ContainsKey(redemption.Id) || decisions.ContainsKey(redemption.Id)) continue;
                    await api.UpdateRedemptionStatusAsync(broadcaster, reward.Id, redemption.Id, false, cancellation);
                    refunded++;
                }
            }
            catch (TwitchApiException error) { log("Twitch: " + error.Message); }
        }
        if (refunded > 0) log($"Twitch: refunded {refunded} redemption(s) made while the trainer was offline.");
    }

    /// <summary>After EventSub reconnected: hands redemptions made during the outage to the engine.</summary>
    private async Task RecoverMissedAsync(CancellationToken cancellation)
    {
        if (helix is not { } api || BroadcasterId is not { } broadcaster) return;
        int recovered = 0;
        foreach (var (key, reward) in settings.Rewards.ToArray())
        {
            if (!reward.Enabled || reward.TwitchRewardId is not { } rewardId) continue;
            try
            {
                foreach (var redemption in await api.GetUnfulfilledRedemptionsAsync(broadcaster, rewardId, cancellation))
                {
                    if (open.ContainsKey(redemption.Id) || decisions.ContainsKey(redemption.Id) || withdrawn.ContainsKey(redemption.Id) || !Remember(redemption.Id)) continue;
                    open[redemption.Id] = 0;
                    submit(new Redemption(redemption.Id, key, redemption.UserName, redemption.UserInput, redemption.RedeemedAt, rewardId));
                    recovered++;
                }
            }
            catch (Exception error) when (error is TwitchApiException or HttpRequestException or TaskCanceledException) { log("Twitch: " + error.Message); }
        }
        if (recovered > 0) log($"Twitch: caught up on {recovered} redemption(s) made while the connection was interrupted.");
    }

    /// <summary>Twitch asks apps to re-validate tokens regularly; a revoked login is noticed within the hour.</summary>
    private async Task ValidateRegularlyAsync(CancellationToken cancellation)
    {
        while (!cancellation.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(TimeSpan.FromHours(1), cancellation);
                if (token is { } current && await auth.ValidateAsync(current.AccessToken, cancellation) is null) await RefreshAccessTokenAsync(current.AccessToken, cancellation);
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { return; }
            catch (Exception) { /* A lost login is handled by the refresh; network problems retry next hour. */ }
        }
    }

    /// <summary>Renews the login once per rejected token, even when several requests fail at the same time.</summary>
    private async Task<string> RefreshAccessTokenAsync(string rejected, CancellationToken cancellation)
    {
        await refreshLock.WaitAsync(cancellation);
        try
        {
            if (token is { } current && current.AccessToken != rejected) return current.AccessToken; // Another request already renewed it.
            var refreshed = await auth.RefreshAsync(settings.EffectiveClientId, token?.RefreshToken ?? "", cancellation);
            token = refreshed;
            SaveToken(settings.EffectiveClientId, refreshed);
            return refreshed.AccessToken;
        }
        catch (TwitchAuthException error)
        {
            // The login is gone for good: stop listening instead of pretending to be connected.
            Post(() => _ = LoginLostAsync(error.Message));
            throw;
        }
        finally { refreshLock.Release(); }
    }

    private async Task LoginLostAsync(string message)
    {
        if (helix is null) return;
        helix = null;
        await StopSessionAsync();
        SetState(TwitchConnectionState.Error, message);
        log("Twitch: " + message);
    }

    private void SaveToken(string clientId, TwitchToken value)
    {
        try { tokens.Save(clientId, value); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.Cryptography.CryptographicException)
        {
            Post(() => log("Twitch: the login could not be saved for the next start: " + error.Message)); // Can run on a background thread.
        }
    }

    private void OnRedemption(RedemptionEvent redemption)
    {
        if (!rewardKeys.TryGetValue(redemption.RewardId, out string? key)) return; // Not one of the trainer's rewards.
        if (!Remember(redemption.Id)) return; // Already handed over (for example by the catch-up after a reconnect).
        open[redemption.Id] = 0;
        submit(new Redemption(redemption.Id, key, redemption.UserName, redemption.UserInput, redemption.RedeemedAt, redemption.RewardId));
    }

    private bool Remember(string redemptionId)
    {
        lock (seen)
        {
            if (!seen.Add(redemptionId)) return false;
            seenOrder.Enqueue(redemptionId);
            while (seenOrder.Count > 2000) seen.Remove(seenOrder.Dequeue());
            return true;
        }
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
        foreach (var task in new[] { eventSub, validation })
            if (task is { } running) { try { await running.WaitAsync(TimeSpan.FromSeconds(5)); } catch (Exception) { } }
        eventSub = null; validation = null;
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
