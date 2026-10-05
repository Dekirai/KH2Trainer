using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KH2Trainer.Twitch;

public sealed record TwitchToken(string AccessToken, string RefreshToken, DateTimeOffset ExpiresAt, IReadOnlyList<string> Scopes);
public sealed record DeviceAuthorization(string DeviceCode, string UserCode, string VerificationUri, DateTimeOffset ExpiresAt, TimeSpan Interval);
public sealed record TokenValidation(string ClientId, string Login, string UserId, IReadOnlyList<string> Scopes);

public sealed class TwitchAuthException(string message) : Exception(message);

/// <summary>Encrypts secrets at rest (DPAPI in the app, a pass-through in tests).</summary>
public interface ISecretProtector
{
    byte[] Protect(byte[] data);
    byte[] Unprotect(byte[] data);
}

/// <summary>Stores the Twitch login encrypted for the current Windows user.</summary>
public sealed class TokenStore(string path, ISecretProtector protector)
{
    private sealed record Stored(string ClientId, TwitchToken Token);

    public TwitchToken? Load(string clientId)
    {
        try
        {
            if (!File.Exists(path)) return null;
            var stored = JsonSerializer.Deserialize<Stored>(protector.Unprotect(File.ReadAllBytes(path)));
            return stored is not null && stored.ClientId == clientId && stored.Token.AccessToken.Length > 0 ? stored.Token : null;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or System.Security.Cryptography.CryptographicException)
        {
            return null;
        }
    }

    public void Save(string clientId, TwitchToken token)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllBytes(temporary, protector.Protect(JsonSerializer.SerializeToUtf8Bytes(new Stored(clientId, token))));
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    public void Clear() { if (File.Exists(path)) File.Delete(path); }
}

/// <summary>
/// Twitch login with the OAuth device code flow: the streamer confirms a short code on twitch.tv,
/// so the trainer never sees a password and needs no web server or client secret.
/// </summary>
public sealed class TwitchAuth(HttpClient http, Uri? identityBase = null, Func<TimeSpan, CancellationToken, Task>? delay = null)
{
    /// <summary>Create, edit and delete the app's own rewards, fulfil or refund their redemptions, and receive them via EventSub.</summary>
    public const string Scope = "channel:manage:redemptions";
    private readonly Uri identity = identityBase ?? new Uri("https://id.twitch.tv/");
    private readonly Func<TimeSpan, CancellationToken, Task> wait = delay ?? Task.Delay;

    private sealed record DeviceResponse(
        [property: JsonPropertyName("device_code")] string DeviceCode,
        [property: JsonPropertyName("user_code")] string UserCode,
        [property: JsonPropertyName("verification_uri")] string VerificationUri,
        [property: JsonPropertyName("expires_in")] int ExpiresIn,
        [property: JsonPropertyName("interval")] int Interval);

    private sealed record TokenResponse(
        [property: JsonPropertyName("access_token")] string AccessToken,
        [property: JsonPropertyName("refresh_token")] string? RefreshToken,
        [property: JsonPropertyName("expires_in")] int ExpiresIn,
        [property: JsonPropertyName("scope")] string[]? Scope);

    private sealed record ValidateResponse(
        [property: JsonPropertyName("client_id")] string ClientId,
        [property: JsonPropertyName("login")] string Login,
        [property: JsonPropertyName("user_id")] string UserId,
        [property: JsonPropertyName("scopes")] string[]? Scopes);

    public async Task<DeviceAuthorization> StartDeviceFlowAsync(string clientId, CancellationToken cancellation)
    {
        using var response = await http.PostAsync(new Uri(identity, "oauth2/device"), Form(("client_id", clientId), ("scopes", Scope)), cancellation);
        string body = await response.Content.ReadAsStringAsync(cancellation);
        if (!response.IsSuccessStatusCode)
            throw new TwitchAuthException(response.StatusCode == HttpStatusCode.BadRequest
                ? "Twitch did not accept the Client ID. Check it and make sure the app's client type is \"Public\"."
                : $"Twitch login could not start ({(int)response.StatusCode}: {ErrorMessage(body)}).");
        var device = JsonSerializer.Deserialize<DeviceResponse>(body) ?? throw new TwitchAuthException("Twitch sent an empty login response.");
        return new DeviceAuthorization(device.DeviceCode, device.UserCode, device.VerificationUri,
            DateTimeOffset.UtcNow.AddSeconds(device.ExpiresIn), TimeSpan.FromSeconds(Math.Max(1, device.Interval)));
    }

    /// <summary>Polls until the streamer confirmed the code on twitch.tv, the code expired or it was denied.</summary>
    public async Task<TwitchToken> WaitForDeviceTokenAsync(string clientId, DeviceAuthorization device, CancellationToken cancellation)
    {
        var interval = device.Interval;
        while (DateTimeOffset.UtcNow < device.ExpiresAt)
        {
            await wait(interval, cancellation);
            using var response = await http.PostAsync(new Uri(identity, "oauth2/token"), Form(
                ("client_id", clientId), ("scopes", Scope), ("device_code", device.DeviceCode),
                ("grant_type", "urn:ietf:params:oauth:grant-type:device_code")), cancellation);
            string body = await response.Content.ReadAsStringAsync(cancellation);
            if (response.IsSuccessStatusCode) return ParseToken(body);
            string message = ErrorMessage(body);
            if (message.Contains("authorization_pending", StringComparison.OrdinalIgnoreCase)) continue;
            if (message.Contains("slow_down", StringComparison.OrdinalIgnoreCase)) { interval += TimeSpan.FromSeconds(5); continue; }
            if (message.Contains("denied", StringComparison.OrdinalIgnoreCase)) throw new TwitchAuthException("The login was declined on Twitch.");
            throw new TwitchAuthException(message.Contains("invalid device code", StringComparison.OrdinalIgnoreCase)
                ? "The login code expired. Start the connection again." : $"Twitch login failed: {message}");
        }
        throw new TwitchAuthException("The login code expired. Start the connection again.");
    }

    public async Task<TwitchToken> RefreshAsync(string clientId, string refreshToken, CancellationToken cancellation)
    {
        using var response = await http.PostAsync(new Uri(identity, "oauth2/token"), Form(
            ("client_id", clientId), ("grant_type", "refresh_token"), ("refresh_token", refreshToken)), cancellation);
        string body = await response.Content.ReadAsStringAsync(cancellation);
        // Only a rejected refresh token means the login is gone; anything else is a temporary problem.
        if (response.StatusCode is HttpStatusCode.BadRequest or HttpStatusCode.Unauthorized) throw new TwitchAuthException("The Twitch login expired. Connect again.");
        if (!response.IsSuccessStatusCode) throw new HttpRequestException($"Twitch could not renew the login right now ({(int)response.StatusCode}).", null, response.StatusCode);
        return ParseToken(body, refreshToken);
    }

    /// <summary>Returns the token's owner, or null when the token is no longer valid.</summary>
    public async Task<TokenValidation?> ValidateAsync(string accessToken, CancellationToken cancellation)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(identity, "oauth2/validate"));
        request.Headers.TryAddWithoutValidation("Authorization", "OAuth " + accessToken);
        using var response = await http.SendAsync(request, cancellation);
        if (response.StatusCode == HttpStatusCode.Unauthorized) return null;
        string body = await response.Content.ReadAsStringAsync(cancellation);
        if (!response.IsSuccessStatusCode) throw new TwitchAuthException($"Twitch could not check the login ({(int)response.StatusCode}).");
        var result = JsonSerializer.Deserialize<ValidateResponse>(body) ?? throw new TwitchAuthException("Twitch sent an empty validation response.");
        return new TokenValidation(result.ClientId, result.Login, result.UserId, result.Scopes ?? []);
    }

    public async Task RevokeAsync(string clientId, string accessToken, CancellationToken cancellation)
    {
        using var response = await http.PostAsync(new Uri(identity, "oauth2/revoke"), Form(("client_id", clientId), ("token", accessToken)), cancellation);
    }

    private static TwitchToken ParseToken(string body, string? previousRefresh = null)
    {
        var token = JsonSerializer.Deserialize<TokenResponse>(body) ?? throw new TwitchAuthException("Twitch sent an empty token.");
        return new TwitchToken(token.AccessToken, token.RefreshToken ?? previousRefresh ?? "",
            DateTimeOffset.UtcNow.AddSeconds(Math.Max(60, token.ExpiresIn)), token.Scope ?? []);
    }

    internal static string ErrorMessage(string body)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            if (document.RootElement.TryGetProperty("message", out var message) && message.ValueKind == JsonValueKind.String) return message.GetString() ?? "";
        }
        catch (JsonException) { }
        return body.Length > 200 ? body[..200] : body;
    }

    private static FormUrlEncodedContent Form(params (string Key, string Value)[] values) =>
        new(values.Select(v => new KeyValuePair<string, string>(v.Key, v.Value)));
}
