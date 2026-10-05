using System.Text;
using System.Text.Json.Nodes;
using KH2Trainer.Core;

internal static class BinaryDiagnosticTests
{
    public static void Run(string catalogPath, Action<bool, string> check)
    {
        byte[] raw = File.ReadAllBytes(catalogPath);
        var catalog = BinaryDiagnosticCatalog.Load(catalogPath);
        check(catalog.SourceSha256 == BinaryDiagnosticCatalog.SupportedSourceSha256, "diagnostics match the verified executable");
        check(catalog.Messages.Count == 8 && catalog.ClosePrompts.Count == 3 && catalog.Languages.Count == 6,
            "diagnostics contain eight error IDs and three exit states in six languages");
        check(catalog.FindMessage(-1) is null && catalog.FindMessage(8) is null, "unknown error IDs are not guessed");
        check(catalog.Languages.Select(x => x.Code).SequenceEqual(new[] { "ja", "en", "fr", "it", "de", "es" }),
            "dialog table language order differs from the native language IDs");
        int[] mapping = [0, 1, 1, 4, 2, 5, 3, 0, 1, 1];
        for (int i = 0; i < mapping.Length; i++)
            check(BinaryDiagnosticCatalog.ResolveNativeLanguage(i) == mapping[i], $"native language {i} resolves to the original table slot");
        check(BinaryDiagnosticCatalog.ResolveNativeLanguage(-1) == 1 && BinaryDiagnosticCatalog.ResolveNativeLanguage(int.MaxValue) == 1,
            "out-of-switch language values follow the constant non-Japanese region fallback");
        string[] texts = [
            "Save data is corrupt and will be deleted.Creating new save data.",
            "Failed to create system data.\nRe-attempting to create system data.",
            "Failed to save game data.", "Failed to delete game data.",
            "Save data is corrupt. Failed to load game data.",
            "The Epic Games Launcher is in Offline Mode.\nPlease check your internet connection.",
            "The Epic Games Launcher is in Offline Mode.\nPlease check your internet connection.",
            "Unable to log in.Returning to the Epic Games Launcher."
        ];
        int[] styles = [0, 2, 0, 0, 0, 1, 1, 0];
        for (int i = 0; i < texts.Length; i++)
        {
            var entry = catalog.FindMessage(i)!;
            check(entry.English.Text == texts[i], $"diagnostic {i} retains exact English source text");
            check(entry.NativeStyle == styles[i] && entry.Localizations.Count == 6, $"diagnostic {i} retains native style and languages");
        }
        check(catalog.FindMessage(1)!.English is { PrimaryButton: "Quit Game", SecondaryButton: "OK" },
            "creation retry dialog preserves the counterintuitive quit-first button order");
        check(catalog.FindMessage(5)!.English.Text == catalog.FindMessage(6)!.English.Text &&
            catalog.FindMessage(5)!.PrimaryEffect != catalog.FindMessage(6)!.PrimaryEffect,
            "identical offline texts preserve different native post-dialog branches");
        check(catalog.FindMessage(7)!.DialogKind == "Information" && catalog.FindMessage(7)!.PrimaryEffect.Contains("unconditionally"),
            "information dialog ID7 still documents its native shutdown branch");
        check(catalog.FindMessage(0)!.Localizations.Single(x => x.LanguageId == 4).PrimaryButton == "O.K." &&
            catalog.FindMessage(0)!.Localizations.Single(x => x.LanguageId == 5).PrimaryButton == "ACEPTAR",
            "localized button overrides are preserved");
        check(catalog.ClosePrompts.Single(x => x.Id == "gameplay").English.Text ==
            "Exit the game?\nAll unsaved game progress will be lost.", "gameplay close warning retains its source text");
        check(catalog.ClosePrompts.Single(x => x.Id == "busy").English.Text ==
            "Exiting game...\nDon't turn off your PC at this time.", "exit-progress text retains its source text");
        check(catalog.Messages.All(x => x.Localizations.All(v => v.RecordAddress.StartsWith("0x140714") &&
            v.TextAddress.StartsWith("0x1405"))), "original native table and UTF16 pointers are exposed as reference addresses");

        using (var stream = new MemoryStream(raw, writable: false))
        {
            var fromStream = BinaryDiagnosticCatalog.Load(stream);
            check(stream.CanRead && fromStream.FindMessage(3)!.English.Text == texts[3], "stream overload leaves caller-owned stream open");
        }
        using (var stream = new ForwardOnlyStream(raw))
            check(BinaryDiagnosticCatalog.Load(stream).Messages.Count == 8 && !stream.Disposed,
                "embedded nonseekable streams are supported without taking ownership");

        void Reject(byte[] bytes, string name)
        {
            try { using var stream = new MemoryStream(bytes); BinaryDiagnosticCatalog.Load(stream); check(false, name); }
            catch (InvalidDataException) { check(true, name); }
        }
        void Mutate(Action<JsonObject> edit, string name)
        { var root = JsonNode.Parse(raw)!.AsObject(); edit(root); Reject(Encoding.UTF8.GetBytes(root.ToJsonString()), name); }
        Reject([], "empty diagnostic catalog rejected");
        Reject("["u8.ToArray(), "malformed diagnostic JSON rejected");
        Reject("null"u8.ToArray(), "null diagnostic catalog rejected");
        Reject(new byte[256 * 1024 + 1], "oversized diagnostic stream rejected");
        Mutate(x => x["SourceSha256"] = new string('0', 64), "unsupported source fingerprint rejected");
        Mutate(x => x["Schema"] = 2, "unknown schema rejected");
        Mutate(x => x["Languages"]![1]!["Id"] = 0, "duplicate language IDs rejected");
        Mutate(x => x["Languages"]![0]!["Code"] = "en", "incorrect native language table mapping rejected");
        Mutate(x => x["Languages"]![0] = null, "null language entry rejected");
        Mutate(x => x["Messages"]![1]!["Id"] = 0, "duplicate message IDs rejected");
        Mutate(x => x["Messages"]![0] = null, "null message entry rejected");
        Mutate(x => x["Messages"]![0]!["NativeStyle"] = 1, "altered native dialog style rejected");
        Mutate(x => x["Messages"]![0]!["Localizations"]![0]!["Text"] = "", "empty source text rejected");
        Mutate(x => x["Messages"]![0]!["Localizations"]![0]!["TextAddress"] = "0x1bf0", "synthetic CIL address cannot masquerade as a native text pointer");
        Mutate(x => x["Messages"]![0]!["Localizations"]![0]!["SecondaryButton"] = "Retry", "invented secondary information-dialog button rejected");
        Mutate(x => x["Messages"]![1]!["Localizations"]![0]!["SecondaryButton"] = null, "missing confirmation button rejected");
        Mutate(x => x["Messages"]![0]!["Localizations"]![0] = null, "null localized record rejected");
        Mutate(x => x["ClosePrompts"]![0]!["NativeGameStatus"] = 1, "duplicate exit state rejected");
        Mutate(x => x["Evidence"] = new JsonArray(), "missing source references rejected");
        Mutate(x => x["Scope"] = new string('a', 16_385), "excessive text field rejected");
    }

    private sealed class ForwardOnlyStream(byte[] bytes) : Stream
    {
        private readonly MemoryStream inner = new(bytes, writable: false);
        public bool Disposed { get; private set; }
        public override bool CanRead => !Disposed;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) => inner.Read(buffer, offset, count);
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { Disposed = true; if (disposing) inner.Dispose(); base.Dispose(disposing); }
    }
}
