using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace KH2Trainer.Twitch;

public sealed record TwitchUser(string Id, string Login, string DisplayName, string BroadcasterType);
public sealed record TwitchReward(string Id, string Title, int Cost, bool IsPaused);
public sealed record TwitchRedemption(string Id, string RewardId, string UserName, string UserInput, DateTimeOffset RedeemedAt);

/// <summary>A Twitch API error with a message the streamer can act on.</summary>
public sealed class TwitchApiException(HttpStatusCode status, string message) : Exception(Explain(status, message))
{
    public HttpStatusCode Status { get; } = status;
    public string TwitchMessage { get; } = message;

    private static string Explain(HttpStatusCode status, string message)
    {
        if (message.Contains("DUPLICATE_REWARD", StringComparison.OrdinalIgnoreCase))
            return "Another reward on your channel already uses this title. Rename one of them.";
        if (message.Contains("partner or affiliate", StringComparison.OrdinalIgnoreCase))
            return "Channel points require Twitch Affiliate or Partner status.";
        if (message.Contains("maximum", StringComparison.OrdinalIgnoreCase) && message.Contains("reward", StringComparison.OrdinalIgnoreCase))
            return "Twitch allows at most 50 custom rewards per channel. Disable some rewards first.";
        return status switch
        {
            HttpStatusCode.Unauthorized => "The Twitch login expired. Connect again.",
            HttpStatusCode.Forbidden => $"Twitch refused the request: {message}",
            HttpStatusCode.NotFound => "Twitch could not find the reward. It may have been deleted on Twitch.",
            _ => $"Twitch error {(int)status}: {message}",
        };
    }
}

/// <summary>The few Twitch Helix endpoints the trainer needs.</summary>
public sealed class HelixClient
{
    private readonly HttpClient http;
    private readonly string clientId;
    private readonly Func<CancellationToken, Task<string>> accessToken;
    /// <summary>Called with the token Twitch rejected; returns a fresh one.</summary>
    private readonly Func<string, CancellationToken, Task<string>> refreshAccessToken;
    private readonly Uri api;
    private readonly Func<TimeSpan, CancellationToken, Task> delay;

    public HelixClient(HttpClient http, string clientId, Func<CancellationToken, Task<string>> accessToken,
        Func<string, CancellationToken, Task<string>> refreshAccessToken, Uri? apiBase = null, Func<TimeSpan, CancellationToken, Task>? delay = null)
    {
        this.http = http; this.clientId = clientId; this.accessToken = accessToken; this.refreshAccessToken = refreshAccessToken;
        api = apiBase ?? new Uri("https://api.twitch.tv/helix/");
        this.delay = delay ?? Task.Delay;
    }

    public async Task<TwitchUser> GetUserAsync(string userId, CancellationToken cancellation = default)
    {
        var data = await DataAsync(HttpMethod.Get, $"users?id={Uri.EscapeDataString(userId)}", null, cancellation);
        if (data.Length == 0) throw new TwitchApiException(HttpStatusCode.NotFound, "User not found.");
        var user = data[0];
        return new TwitchUser(Text(user, "id"), Text(user, "login"), Text(user, "display_name"), Text(user, "broadcaster_type"));
    }

    /// <summary>Rewards this app (Client ID) created; only those can be edited, deleted or have redemptions updated.</summary>
    public async Task<IReadOnlyList<TwitchReward>> GetManageableRewardsAsync(string broadcasterId, CancellationToken cancellation = default)
    {
        var data = await DataAsync(HttpMethod.Get, $"channel_points/custom_rewards?broadcaster_id={Uri.EscapeDataString(broadcasterId)}&only_manageable_rewards=true", null, cancellation);
        return data.Select(Reward).ToArray();
    }

    public async Task<TwitchReward> CreateRewardAsync(string broadcasterId, RewardSpec spec, CancellationToken cancellation = default)
    {
        var data = await DataAsync(HttpMethod.Post, $"channel_points/custom_rewards?broadcaster_id={Uri.EscapeDataString(broadcasterId)}", RewardBody(spec, null), cancellation);
        return Reward(data.First());
    }

    public async Task<TwitchReward> UpdateRewardAsync(string broadcasterId, string rewardId, RewardSpec? spec, bool? paused, CancellationToken cancellation = default)
    {
        var data = await DataAsync(HttpMethod.Patch, $"channel_points/custom_rewards?broadcaster_id={Uri.EscapeDataString(broadcasterId)}&id={Uri.EscapeDataString(rewardId)}",
            RewardBody(spec, paused), cancellation);
        return Reward(data.First());
    }

    /// <summary>Deletes a reward. A reward that no longer exists counts as deleted.</summary>
    public async Task DeleteRewardAsync(string broadcasterId, string rewardId, CancellationToken cancellation = default)
    {
        try { await SendAsync(HttpMethod.Delete, $"channel_points/custom_rewards?broadcaster_id={Uri.EscapeDataString(broadcasterId)}&id={Uri.EscapeDataString(rewardId)}", null, cancellation); }
        catch (TwitchApiException error) when (error.Status == HttpStatusCode.NotFound) { }
    }

    /// <summary>FULFILLED keeps the points; CANCELED refunds them to the viewer.</summary>
    public Task UpdateRedemptionStatusAsync(string broadcasterId, string rewardId, string redemptionId, bool fulfilled, CancellationToken cancellation = default) =>
        SendAsync(HttpMethod.Patch,
            $"channel_points/custom_rewards/redemptions?broadcaster_id={Uri.EscapeDataString(broadcasterId)}&reward_id={Uri.EscapeDataString(rewardId)}&id={Uri.EscapeDataString(redemptionId)}",
            new JsonObject { ["status"] = fulfilled ? "FULFILLED" : "CANCELED" }, cancellation);

    /// <summary>All redemptions of a reward that still wait in the request queue (follows Twitch's pages of 50).</summary>
    public async Task<IReadOnlyList<TwitchRedemption>> GetUnfulfilledRedemptionsAsync(string broadcasterId, string rewardId, CancellationToken cancellation = default)
    {
        var result = new List<TwitchRedemption>();
        string? cursor = null;
        for (int page = 0; page < 100; page++)
        {
            string path = $"channel_points/custom_rewards/redemptions?broadcaster_id={Uri.EscapeDataString(broadcasterId)}&reward_id={Uri.EscapeDataString(rewardId)}&status=UNFULFILLED&first=50"
                + (cursor is null ? "" : "&after=" + Uri.EscapeDataString(cursor));
            string json = await SendAsync(HttpMethod.Get, path, null, cancellation);
            using var document = JsonDocument.Parse(json.Length == 0 ? "{}" : json);
            var root = document.RootElement;
            if (root.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Array)
                foreach (var r in data.EnumerateArray())
                {
                    string name = Text(r, "user_name");
                    DateTimeOffset.TryParse(Text(r, "redeemed_at"), out var redeemedAt);
                    result.Add(new TwitchRedemption(Text(r, "id"), rewardId, name.Length > 0 ? name : Text(r, "user_login"), Text(r, "user_input"), redeemedAt));
                }
            cursor = root.TryGetProperty("pagination", out var pagination) && pagination.ValueKind == JsonValueKind.Object ? Text(pagination, "cursor") : "";
            if (string.IsNullOrEmpty(cursor)) break;
        }
        return result;
    }

    /// <summary>Subscribes the EventSub WebSocket session to this channel's reward redemptions.</summary>
    public Task SubscribeRedemptionsAsync(string broadcasterId, string sessionId, CancellationToken cancellation = default) =>
        SendAsync(HttpMethod.Post, "eventsub/subscriptions", new JsonObject
        {
            ["type"] = "channel.channel_points_custom_reward_redemption.add",
            ["version"] = "1",
            ["condition"] = new JsonObject { ["broadcaster_user_id"] = broadcasterId },
            ["transport"] = new JsonObject { ["method"] = "websocket", ["session_id"] = sessionId },
        }, cancellation);

    internal static JsonObject RewardBody(RewardSpec? spec, bool? paused)
    {
        var body = new JsonObject();
        if (spec != null)
        {
            body["title"] = spec.Title;
            body["cost"] = spec.Cost;
            body["prompt"] = spec.Prompt;
            body["is_enabled"] = true;
            body["background_color"] = spec.BackgroundColor;
            body["is_user_input_required"] = false;
            body["is_max_per_stream_enabled"] = spec.MaxPerStream > 0;
            if (spec.MaxPerStream > 0) body["max_per_stream"] = spec.MaxPerStream;
            body["is_max_per_user_per_stream_enabled"] = spec.MaxPerUserPerStream > 0;
            if (spec.MaxPerUserPerStream > 0) body["max_per_user_per_stream"] = spec.MaxPerUserPerStream;
            body["is_global_cooldown_enabled"] = spec.GlobalCooldownSeconds > 0;
            if (spec.GlobalCooldownSeconds > 0) body["global_cooldown_seconds"] = spec.GlobalCooldownSeconds;
            // Redemptions must stay in the request queue so they can be fulfilled or refunded.
            body["should_redemptions_skip_request_queue"] = false;
        }
        if (paused is bool value) body["is_paused"] = value;
        return body;
    }

    private static TwitchReward Reward(JsonElement element) =>
        new(Text(element, "id"), Text(element, "title"), element.TryGetProperty("cost", out var cost) && cost.TryGetInt32(out int value) ? value : 0,
            element.TryGetProperty("is_paused", out var paused) && paused.ValueKind == JsonValueKind.True);

    private static string Text(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";

    private async Task<JsonElement[]> DataAsync(HttpMethod method, string path, JsonNode? body, CancellationToken cancellation)
    {
        string json = await SendAsync(method, path, body, cancellation);
        using var document = JsonDocument.Parse(json.Length == 0 ? "{}" : json);
        return document.RootElement.TryGetProperty("data", out var data) && data.ValueKind == JsonValueKind.Array
            ? data.EnumerateArray().Select(e => e.Clone()).ToArray() : [];
    }

    private async Task<string> SendAsync(HttpMethod method, string path, JsonNode? body, CancellationToken cancellation)
    {
        bool refreshed = false;
        string token = await accessToken(cancellation);
        for (int attempt = 0; ; attempt++)
        {
            using var request = new HttpRequestMessage(method, new Uri(api, path));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            request.Headers.TryAddWithoutValidation("Client-Id", clientId);
            if (body != null) request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
            using var response = await http.SendAsync(request, cancellation);
            string text = await response.Content.ReadAsStringAsync(cancellation);
            if (response.IsSuccessStatusCode) return text;
            if (response.StatusCode == HttpStatusCode.Unauthorized && !refreshed) { refreshed = true; token = await refreshAccessToken(token, cancellation); continue; }
            if (response.StatusCode == HttpStatusCode.TooManyRequests && attempt < 3)
            {
                var wait = TimeSpan.FromSeconds(1);
                if (response.Headers.TryGetValues("Ratelimit-Reset", out var values) && long.TryParse(values.FirstOrDefault(), out long reset))
                    wait = TimeSpan.FromSeconds(Math.Clamp(reset - DateTimeOffset.UtcNow.ToUnixTimeSeconds(), 1, 30));
                await delay(wait, cancellation);
                continue;
            }
            throw new TwitchApiException(response.StatusCode, TwitchAuth.ErrorMessage(text));
        }
    }
}
