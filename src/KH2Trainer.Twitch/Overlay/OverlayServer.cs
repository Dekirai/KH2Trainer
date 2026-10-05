using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace KH2Trainer.Twitch;

public sealed record OverlayEffect(string Key, string Title, string Viewers, string? Detail, double Remaining, double Duration, string Color, bool Image, bool Starting);
public sealed record OverlayQueued(string Key, string Title, string Viewer, string Status, string Color, bool Image);
public sealed record OverlayEvent(long Time, string Key, string Text, string Color, bool Image);
public sealed record OverlayState(IReadOnlyList<OverlayEffect> Active, IReadOnlyList<OverlayQueued> Queue, IReadOnlyList<OverlayEvent> Events);

/// <summary>
/// A tiny local web server for an OBS browser source. It listens on 127.0.0.1 only, answers
/// GET requests for the overlay page, its state and reward images, and serves images by reward
/// key so no file path ever comes from a request.
/// </summary>
public sealed class OverlayServer : IAsyncDisposable
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private readonly TcpListener listener;
    private readonly Func<OverlayState> state;
    private readonly Func<string, string?> imagePath;
    private readonly CancellationTokenSource stop = new();
    private readonly string page;
    private Task? loop;
    private bool disposed;

    public OverlayServer(int port, Func<OverlayState> state, Func<string, string?> imagePath)
    {
        listener = new TcpListener(IPAddress.Loopback, port);
        this.state = state; this.imagePath = imagePath;
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("KH2Trainer.Twitch.overlay.html")
            ?? throw new InvalidOperationException("The overlay page is missing from the build.");
        using var reader = new StreamReader(stream);
        page = reader.ReadToEnd();
    }

    public int Port => ((IPEndPoint)listener.LocalEndpoint).Port;
    public string Url => $"http://localhost:{Port}/";

    public void Start()
    {
        listener.Start();
        loop = Task.Run(AcceptAsync);
    }

    private async Task AcceptAsync()
    {
        while (!stop.IsCancellationRequested)
        {
            TcpClient client;
            try { client = await listener.AcceptTcpClientAsync(stop.Token); }
            catch (Exception) { break; }
            _ = Task.Run(() => ServeAsync(client));
        }
    }

    private async Task ServeAsync(TcpClient client)
    {
        using (client)
        {
            try
            {
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stop.Token);
                timeout.CancelAfter(TimeSpan.FromSeconds(5));
                var stream = client.GetStream();
                string? requestLine = await ReadRequestLineAsync(stream, timeout.Token);
                var parts = requestLine?.Split(' ');
                if (parts is not { Length: >= 2 } || parts[0] is not ("GET" or "HEAD"))
                {
                    await WriteAsync(stream, 405, "text/plain", "Method not allowed"u8.ToArray(), false, timeout.Token);
                    return;
                }
                bool head = parts[0] == "HEAD";
                string path = parts[1].Split('?')[0];
                if (path is "/" or "/index.html") await WriteAsync(stream, 200, "text/html; charset=utf-8", Encoding.UTF8.GetBytes(page), head, timeout.Token);
                else if (path == "/state.json") await WriteAsync(stream, 200, "application/json", JsonSerializer.SerializeToUtf8Bytes(state(), Json), head, timeout.Token);
                else if (path.StartsWith("/image/", StringComparison.Ordinal) && ImageFor(Uri.UnescapeDataString(path[7..])) is { } image)
                    await WriteAsync(stream, 200, image.Type, image.Bytes, head, timeout.Token);
                else await WriteAsync(stream, 404, "text/plain", "Not found"u8.ToArray(), head, timeout.Token);
            }
            catch (Exception) { /* A browser that disconnects early is not an error. */ }
        }
    }

    private (string Type, byte[] Bytes)? ImageFor(string key)
    {
        if (key.Length is 0 or > 64 || key.Any(c => !(char.IsAsciiLetterOrDigit(c) || c == '-'))) return null;
        string? path = imagePath(key);
        if (path is null || !File.Exists(path)) return null;
        var info = new FileInfo(path);
        if (info.Length > MaxImageBytes || ImageType(path) is not { } type) return null;
        return (type, File.ReadAllBytes(path));
    }

    public const long MaxImageBytes = 8 * 1024 * 1024;

    /// <summary>The content type of a supported image file, or null for anything else.</summary>
    public static string? ImageType(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".gif" => "image/gif", ".bmp" => "image/bmp", ".webp" => "image/webp",
        _ => null,
    };

    private static async Task<string?> ReadRequestLineAsync(NetworkStream stream, CancellationToken cancellation)
    {
        var buffer = new byte[8192];
        int length = 0;
        while (length < buffer.Length)
        {
            int read = await stream.ReadAsync(buffer.AsMemory(length), cancellation);
            if (read == 0) break;
            length += read;
            string text = Encoding.ASCII.GetString(buffer, 0, length);
            if (text.Contains("\r\n\r\n", StringComparison.Ordinal)) return text[..text.IndexOf("\r\n", StringComparison.Ordinal)];
        }
        return null;
    }

    private static async Task WriteAsync(NetworkStream stream, int status, string type, byte[] body, bool head, CancellationToken cancellation)
    {
        string reason = status switch { 200 => "OK", 404 => "Not Found", 405 => "Method Not Allowed", _ => "Error" };
        string header = $"HTTP/1.1 {status} {reason}\r\nContent-Type: {type}\r\nContent-Length: {body.Length}\r\n" +
            "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n";
        await stream.WriteAsync(Encoding.ASCII.GetBytes(header), cancellation);
        if (!head) await stream.WriteAsync(body, cancellation);
    }

    public async ValueTask DisposeAsync()
    {
        if (disposed) return;
        disposed = true;
        stop.Cancel();
        listener.Stop();
        if (loop != null) { try { await loop; } catch (Exception) { } }
        stop.Dispose();
    }
}
