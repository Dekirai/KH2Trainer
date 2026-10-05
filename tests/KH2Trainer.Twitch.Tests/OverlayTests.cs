using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using KH2Trainer.Core;
using KH2Trainer.Twitch;

/// <summary>The OBS overlay server on a real loopback socket.</summary>
internal static class OverlayTests
{
    public static async Task RunAsync(IReadOnlyList<FeatureDefinition> features, Action<bool, string> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "KH2TwitchTests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string png = Path.Combine(folder, "heal.png");
        byte[] pixel = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==");
        File.WriteAllBytes(png, pixel);
        string text = Path.Combine(folder, "secret.txt");
        File.WriteAllText(text, "not an image");

        // The overlay shows what the engine runs.
        var game = new FakeGame(features);
        var settings = new TwitchSettings();
        settings.For("heal").ImagePath = png;
        settings.For("fisheye").ImagePath = text;
        var engine = new EffectEngine(game, new FeatureMap(features), EffectCatalog.All,
            key => RewardResolver.Options(EffectCatalog.Find(key)!, settings), () => RewardResolver.Engine(settings), new FakeSink(), _ => { }, _ => Task.CompletedTask);
        var now = DateTimeOffset.UtcNow;
        engine.Submit(new Redemption("a", "fisheye", "Alice", "", now, "rw"));
        engine.Submit(new Redemption("b", "tunnel-vision", "Bob", "", now, "rw"));
        await engine.TickAsync(now);
        var state = RewardResolver.Overlay(engine, settings);
        check(state.Active.Count == 1 && state.Active[0] is { Key: "fisheye", Viewers: "Alice" } && state.Active[0].Remaining > 0 && !state.Active[0].Image,
            "overlay: active effects with viewer and time; a non-image file is not offered");
        check(state.Queue.Count == 1 && state.Queue[0] is { Key: "tunnel-vision", Viewer: "Bob" }, "overlay: the queue shows who waits");
        check(state.Events.Count == 1 && state.Events[0].Text.StartsWith("Alice: ", StringComparison.Ordinal), "overlay: the toast names the viewer and effect");

        await using var server = new OverlayServer(0, () => RewardResolver.Overlay(engine, settings), key => RewardResolver.ImagePath(key, settings));
        server.Start();
        check(server.Port > 0 && server.Url == $"http://localhost:{server.Port}/", "overlay: listens on a local port");
        using var http = new HttpClient(new HttpClientHandler { UseProxy = false }) { BaseAddress = new Uri($"http://127.0.0.1:{server.Port}/"), Timeout = TimeSpan.FromSeconds(10) };

        var page = await http.GetAsync("/?side=left");
        string html = await page.Content.ReadAsStringAsync();
        check(page.StatusCode == HttpStatusCode.OK && page.Content.Headers.ContentType?.MediaType == "text/html" && html.Contains("state.json"), "overlay: serves the page");

        var json = await http.GetAsync("/state.json");
        using (var document = JsonDocument.Parse(await json.Content.ReadAsStringAsync()))
        {
            var root = document.RootElement;
            check(json.Headers.CacheControl?.NoStore == true && root.GetProperty("active")[0].GetProperty("key").GetString() == "fisheye"
                && root.GetProperty("queue")[0].GetProperty("viewer").GetString() == "Bob", "overlay: serves the live state as camelCase JSON");
        }

        var image = await http.GetAsync("/image/heal");
        check(image.StatusCode == HttpStatusCode.OK && image.Content.Headers.ContentType?.MediaType == "image/png" && (await image.Content.ReadAsByteArrayAsync()).SequenceEqual(pixel),
            "overlay: serves the chosen reward image");
        check((await http.GetAsync("/image/fisheye")).StatusCode == HttpStatusCode.NotFound, "overlay: files that are not images are never served");
        check((await http.GetAsync("/image/regen")).StatusCode == HttpStatusCode.NotFound, "overlay: rewards without an image return 404");
        check((await http.GetAsync("/image/..%2F..%2Fsecret")).StatusCode == HttpStatusCode.NotFound, "overlay: path tricks in the key are rejected");
        check((await http.GetAsync("/nothing")).StatusCode == HttpStatusCode.NotFound, "overlay: unknown paths return 404");
        check((await http.PostAsync("/state.json", new StringContent("x"))).StatusCode == HttpStatusCode.MethodNotAllowed, "overlay: only GET and HEAD are answered");
        var head = await http.SendAsync(new HttpRequestMessage(HttpMethod.Head, "/state.json"));
        check(head.StatusCode == HttpStatusCode.OK && (await head.Content.ReadAsByteArrayAsync()).Length == 0, "overlay: HEAD has no body");

        // A client that connects and sends nothing does not block others.
        using (var idle = new TcpClient())
        {
            await idle.ConnectAsync(IPAddress.Loopback, server.Port);
            check((await http.GetAsync("/state.json")).StatusCode == HttpStatusCode.OK, "overlay: an idle connection does not block other requests");
        }
        using (var raw = new TcpClient())
        {
            await raw.ConnectAsync(IPAddress.Loopback, server.Port);
            var stream = raw.GetStream();
            await stream.WriteAsync(Encoding.ASCII.GetBytes("GARBAGE\r\n\r\n"));
            var buffer = new byte[256];
            int read = await stream.ReadAsync(buffer);
            check(Encoding.ASCII.GetString(buffer, 0, read).StartsWith("HTTP/1.1 405", StringComparison.Ordinal), "overlay: malformed requests get an error");
        }

        await server.DisposeAsync();
        bool closed;
        try { await http.GetAsync("/state.json"); closed = false; }
        catch (HttpRequestException) { closed = true; }
        check(closed, "overlay: stopping the server closes the port");
        Directory.Delete(folder, true);
    }
}
