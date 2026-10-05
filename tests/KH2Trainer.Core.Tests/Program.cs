using System.IO.Compression;
using System.IO.MemoryMappedFiles;
using System.Text;
using System.Text.Json;
using KH2Trainer.Core;

int passed = 0, failed = 0;
void Check(bool condition, string name) { Console.WriteLine((condition ? "PASS " : "FAIL ") + name); if (condition) passed++; else failed++; }
void Reject(Action action, string name) { try { action(); Check(false, name); } catch { Check(true, name); } }
string workspace = Path.Combine(Path.GetTempPath(), "KH2TrainerTests", Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(workspace);
var feature = new FeatureDefinition { Id = "time.test", Category = "Time", Name = "Test setting", Description = "Fixture", Kind = FeatureKind.Number, CommandId = 1048, ValueSlot = 48, CapabilitySlot = 48, Minimum = .1, Maximum = 3, DefaultValue = 1, CanSaveInProfile = true, Evidence = [new Evidence("fixture", "Test fixture only", "test")] };
IReadOnlyList<FeatureDefinition> catalog = [feature];
feature.Validate(); Check(!feature.IsValidValue(double.NaN) && !feature.IsValidValue(double.PositiveInfinity), "non-finite feature values rejected");
Check(!feature.IsValidValue(0) && feature.IsValidValue(1) && !feature.IsValidValue(4), "feature boundaries enforced");
var profileStore = new ProfileStore(Path.Combine(workspace, "profiles"));
var profile = new TrainerProfile { Name = "Fixture", Values = new() { [feature.Id] = .5 } };
string profilePath = profileStore.Save(profile, catalog);
Check(profileStore.Read(profilePath, catalog).Values[feature.Id] == .5, "profile round-trip preserves numeric settings");
Reject(() => profileStore.Save(profile with { Name = "../outside" }, catalog), "profile path traversal rejected");
Reject(() => ProfileStore.Validate(profile with { GameHash = "wrong" }, catalog), "wrong game profile rejected");
Reject(() => ProfileStore.Validate(profile with { Values = new() { [feature.Id] = 100 } }, catalog), "profile value outside range rejected");
Reject(() => ProfileStore.Validate(profile with { Values = new() { ["unknown.action"] = 1 } }, catalog), "unknown profile operation rejected");
Reject(() => GameSession.ValidatePayload(new byte[128]), "invalid embedded DLL rejected");

string saves = Path.Combine(workspace, "saves"); Directory.CreateDirectory(saves); Directory.CreateDirectory(Path.Combine(saves, "nested"));
byte[] firstSave = Enumerable.Range(0, 10000).Select(i => (byte)(i % 251)).ToArray();
File.WriteAllBytes(Path.Combine(saves, "slot.png"), firstSave); File.WriteAllText(Path.Combine(saves, "nested", "system.dat"), "original fixture");
var backupStore = new BackupStore(Path.Combine(workspace, "backups"));
Reject(() => backupStore.Create(saves, () => true), "backup creation refused while game is running");
int backupRunningChecks = 0;
Reject(() => backupStore.Create(saves, () => ++backupRunningChecks >= 3), "game starting during multi-file backup aborts creation");
Check(!Directory.EnumerateFiles(backupStore.Folder).Any(), "interrupted backup leaves no published or temporary archive");
string archive = backupStore.Create(saves, () => false); var manifest = BackupStore.Verify(archive);
Check(manifest.Files.Count == 2, "backup enumerates nested files and verifies checksums");
File.WriteAllText(Path.Combine(saves, "slot.png"), "new state");
Reject(() => backupStore.Restore(archive, saves, () => true), "restore refused while game is running");
string previous = backupStore.Restore(archive, saves, () => false);
Check(File.ReadAllBytes(Path.Combine(saves, "slot.png")).SequenceEqual(firstSave), "restore reproduces original binary bytes");
Check(BackupStore.Verify(previous).Files.Single(e => e.Path == "slot.png").Length == Encoding.UTF8.GetByteCount("new state"), "restore preserves a verified backup of the pre-restore state");
string emptyTarget = Path.Combine(workspace, "empty-saves"); Directory.CreateDirectory(emptyTarget);
string emptyPrevious = backupStore.Restore(archive, emptyTarget, () => false);
Check(File.ReadAllBytes(Path.Combine(emptyTarget, "slot.png")).SequenceEqual(firstSave), "restore recovers saves into an existing empty folder");
var emptyManifest = BackupStore.Verify(emptyPrevious);
Check(emptyManifest.EmptySource && emptyManifest.Files.Count == 0, "empty pre-restore state is explicitly recorded and verified");
Reject(() => backupStore.Restore(emptyPrevious, emptyTarget, () => false), "empty-state record does not silently erase existing save files");
File.WriteAllText(Path.Combine(emptyTarget, "newer-extra.dat"), "preserve this extra file");
backupStore.Restore(archive, emptyTarget, () => false);
Check(File.ReadAllText(Path.Combine(emptyTarget, "newer-extra.dat")) == "preserve this extra file", "restore preserves additional target files outside the backup manifest");
string unmarkedEmpty = Path.Combine(workspace, "unmarked-empty.zip");
using (var zip = ZipFile.Open(unmarkedEmpty, ZipArchiveMode.Create))
{
    using var writer = new StreamWriter(zip.CreateEntry("manifest.json").Open());
    writer.Write(JsonSerializer.Serialize(new BackupManifest(1, saves, DateTimeOffset.UtcNow, [])));
}
Reject(() => BackupStore.Verify(unmarkedEmpty), "an empty manifest requires the explicit empty-source marker");
string corrupt = Path.Combine(workspace, "corrupt.zip"); File.Copy(archive, corrupt);
using (var zip = ZipFile.Open(corrupt, ZipArchiveMode.Update)) { var entry = zip.GetEntry("files/slot.png")!; entry.Delete(); using var stream = zip.CreateEntry("files/slot.png").Open(); stream.Write(new byte[10000]); }
Reject(() => BackupStore.Verify(corrupt), "corrupted backup rejected before restore");
string traversal = Path.Combine(workspace, "traversal.zip");
using (var zip = ZipFile.Open(traversal, ZipArchiveMode.Create))
{
    var bad = new BackupManifest(1, saves, DateTimeOffset.UtcNow, [new BackupEntry("../escape.dat", 0, "")]);
    using var writer = new StreamWriter(zip.CreateEntry("manifest.json").Open()); writer.Write(JsonSerializer.Serialize(bad));
}
Reject(() => BackupStore.Verify(traversal), "archive traversal rejected");
string EmptyHash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Array.Empty<byte>())).ToLowerInvariant();
foreach (string unsafeName in new[] { "slot.dat.", "slot.dat ", "CON.dat", "nested\\slot.dat", "slot.dat:stream" })
{
    string unsafeArchive = Path.Combine(workspace, Guid.NewGuid() + ".zip");
    using (var zip = ZipFile.Open(unsafeArchive, ZipArchiveMode.Create))
    {
        zip.CreateEntry("files/" + unsafeName);
        using var writer = new StreamWriter(zip.CreateEntry("manifest.json").Open());
        writer.Write(JsonSerializer.Serialize(new BackupManifest(1, saves, DateTimeOffset.UtcNow, [new BackupEntry(unsafeName, 0, EmptyHash)])));
    }
    Reject(() => BackupStore.Verify(unsafeArchive), "unsafe Windows backup path rejected: " + unsafeName);
}
File.WriteAllText(Path.Combine(saves, "slot.png"), "state before interrupted restore");
File.WriteAllText(Path.Combine(saves, "nested", "system.dat"), "second state before interrupted restore");
var beforeInterrupted = Directory.EnumerateFiles(saves, "*", SearchOption.AllDirectories).ToDictionary(p => p, File.ReadAllBytes);
Reject(() => backupStore.Restore(archive, saves, () => beforeInterrupted.Any(p => !File.ReadAllBytes(p.Key).SequenceEqual(p.Value))), "game starting between restored files aborts restore");
Check(beforeInterrupted.All(p => File.ReadAllBytes(p.Key).SequenceEqual(p.Value)), "interrupted multi-file restore rolls back every changed file");
string unexpected = Path.Combine(workspace, "unexpected.zip"); File.Copy(archive, unexpected);
using (var zip = ZipFile.Open(unexpected, ZipArchiveMode.Update)) zip.CreateEntry("unlisted.dat");
Reject(() => BackupStore.Verify(unexpected), "backup entries outside the manifest rejected");

using (var mapping = MemoryMappedFile.CreateNew(BridgeProtocol.MappingPrefix + Environment.ProcessId, BridgeProtocol.MappingSize))
using (var view = mapping.CreateViewAccessor())
{
    Reject(() => { using var unpublished = new BridgeConnection(Environment.ProcessId); }, "unpublished mapping is not accepted");
    view.Write(4, BridgeProtocol.Version); view.Write(12, 1); view.Write(0, BridgeProtocol.Magic);
    view.Write(BridgeProtocol.SceneReady, 1); view.Write(BridgeProtocol.ValidBits, 1UL << 48); view.Write(BridgeProtocol.SupportedBits, 1UL << 48); view.Write(BridgeProtocol.Values + 48 * 8, .5);
    using var bridge = new BridgeConnection(Environment.ProcessId);
    var snapshot = bridge.ReadSnapshot();
    Check(snapshot.Connected && snapshot.SceneReady && snapshot.HasValue(48) && snapshot.Supports(48) && snapshot.Values[48] == .5, "snapshot fields, masks and doubles agree with protocol layout");
    // Independent wire offsets from the native SharedState static assertions.
    view.Write(2072, 1UL); view.Write(2136, 1UL); view.Write(3208, 128.25);
    view.Write(2112, 1UL << 63); view.Write(2176, 1UL << 63); view.Write(6272, 511.75);
    snapshot = bridge.ReadSnapshot();
    Check(snapshot.HasValue(128) && snapshot.Supports(128) && snapshot.Values[128] == 128.25 &&
        snapshot.HasValue(511) && snapshot.Supports(511) && snapshot.Values[511] == 511.75 &&
        !snapshot.HasValue(127) && !snapshot.HasValue(512), "extended native wire masks and final value slot are read without aliasing");
    Check(view.ReadUInt32(BridgeProtocol.Heartbeat) != 0, "snapshot poll publishes host heartbeat");
    view.Write(BridgeProtocol.SnapshotSequence, 1);
    Reject(() => bridge.ReadSnapshot(), "in-progress snapshot is not returned as coherent"); view.Write(BridgeProtocol.SnapshotSequence, 2);
    var responder = Task.Run(async () =>
    {
        while (view.ReadInt32(BridgeProtocol.RequestSequence) == 0) await Task.Delay(1);
        int sequence = view.ReadInt32(BridgeProtocol.RequestSequence);
        bool correct = view.ReadInt32(BridgeProtocol.Command) == 1048 && view.ReadDouble(BridgeProtocol.Arguments) == .75 &&
            unchecked((uint)Environment.TickCount - view.ReadUInt32(BridgeProtocol.CommandIssuedAt)) < 1000;
        view.Write(BridgeProtocol.ResultCode, correct ? 0 : 99);
        byte[] message = Encoding.Unicode.GetBytes("Acknowledged fixture\0"); view.WriteArray(BridgeProtocol.ResultText, message, 0, message.Length);
        Thread.MemoryBarrier(); view.Write(BridgeProtocol.ResponseSequence, sequence);
    });
    var response = await bridge.ExecuteAsync(1048, [.75]); await responder;
    Check(response.Success && response.Sequence == 1 && response.Message == "Acknowledged fixture", "command arguments and acknowledgement round-trip");
    view.Write(BridgeProtocol.RequestSequence, 2);
    try { await bridge.ExecuteAsync(1048, [1]); Check(false, "pending command cannot be overwritten"); } catch (InvalidOperationException) { Check(view.ReadInt32(BridgeProtocol.RequestSequence) == 2, "pending command cannot be overwritten"); }
    view.Write(4, 2); Reject(() => { using var previous = new BridgeConnection(Environment.ProcessId); }, "previous 128-slot bridge rejected before reading the new layout");
    view.Write(4, 99); Reject(() => { using var incompatible = new BridgeConnection(Environment.ProcessId); }, "incompatible bridge version rejected");
    bridge.Dispose();
    Check(view.ReadUInt32(BridgeProtocol.CommandIssuedAt) == 0 && view.ReadUInt32(BridgeProtocol.Heartbeat) == 0,
        "closing connection invalidates unstarted commands and stops its heartbeat immediately");
}

if (args.Length > 0)
{
    using var stream = File.OpenRead(args[0]); var real = FeatureCatalog.Load(stream);
    Check(real.Count > 0 && real.Where(f => f.Kind != FeatureKind.ReadOnly).All(f => f.CommandId == 1000 + f.CapabilitySlot), "compiled feature catalog command/slot mapping is consistent");
    var drive = real.Single(f => f.Id == "drive.trigger");
    var forms = drive.Arguments.Single();
    Check(forms.Minimum == 1 && forms.Maximum == 6 &&
        forms.Choices.Select(c => c.Value).Order().SequenceEqual(new double[] { 1, 2, 3, 4, 5, 6 }),
        "packaged Drive selector exposes all six exact forms including Antiform");
    Check(drive.ChangesProgression && drive.Description.Contains("second Keyblade") &&
        drive.RestoreBehavior.Contains("normal save"),
        "Drive equipment fallback discloses its persistent form-slot assignment");
    Check(real.Single(f => f.Id == "drive.cancel") is { Kind: FeatureKind.Action, RequiresScene: false, CanSaveInProfile: false } &&
        !drive.CanSaveInProfile, "Drive cancellation remains available without a playable scene and actions are excluded from profiles");
    Check(new[] { 124, 125, 127 }.All(slot => real.Any(f => f.CapabilitySlot == slot && f.ValueSlot == slot && f.Kind == FeatureKind.ReadOnly)),
        "packaged Drive queue exposes requested form, phase and result snapshots");
    AudioMotionCatalogTests.Run(real, workspace, Check);
    MissionRescueCatalogTests.Run(real, workspace, Check);
    var cameraExtra = real.Where(f => f.CapabilitySlot is >= 240 and <= 248).OrderBy(f => f.CapabilitySlot).ToArray();
    Check(cameraExtra.Select(f => f.CapabilitySlot).SequenceEqual(Enumerable.Range(240, 9)) &&
        cameraExtra.All(f => !f.CanSaveInProfile && !f.ChangesProgression),
        "extended camera controls retain their exact slots and cannot replay a scene-bound pose through profiles");
    Check(cameraExtra.Single(f => f.CapabilitySlot == 240) is { Kind: FeatureKind.Number, Minimum: -180, Maximum: 180, CommandId: 1240, ValueSlot: 240 } &&
        cameraExtra.Where(f => f.CapabilitySlot is 243 or 244).All(f => f.Kind == FeatureKind.Action && f.Arguments.Count == 0),
        "camera exposes bounded roll and two parameterless native follow requests");
    Check(cameraExtra.Where(f => f.CapabilitySlot is not (240 or 243 or 244)).All(f => f.Kind == FeatureKind.ReadOnly && f.CommandId == 0),
        "camera ownership, mode and target diagnostics cannot issue native commands");
    var damage = real.Where(f=>f.CapabilitySlot is >= 272 and <= 293).ToArray();
    Check(damage.Length==22 && damage.All(f=>!f.CanSaveInProfile && !f.ChangesProgression && f.RequiresScene) &&
        damage.Where(f=>f.CapabilitySlot<=285).All(f=>f.Kind==FeatureKind.Number && f.Minimum==0 && f.Maximum==255) &&
        damage.Where(f=>f.CapabilitySlot>=286).All(f=>f.Kind==FeatureKind.ReadOnly && f.CommandId==0),
        "runtime damage bytes are bounded, explicit edits while base limits remain diagnostics");
    var display = real.Where(f=>f.CapabilitySlot is >= 304 and <= 306).ToArray();
    Check(display.Length==3 && display.All(f=>!f.RequiresScene && !f.ChangesProgression) &&
        display.Single(f=>f.CapabilitySlot==304) is {Kind:FeatureKind.Number, Minimum:-50,Maximum:50,CanSaveInProfile:true} &&
        display.Where(f=>f.CapabilitySlot!=304).All(f=>f.Kind==FeatureKind.Action && !f.CanSaveInProfile),
        "display previews expose one bounded profile setting and two explicit actions without save writes");
    Check(display.Single(f=>f.CapabilitySlot==306).Arguments.Select(a=>(a.Minimum,a.Maximum)).SequenceEqual(new[]{(0.0,3.0),(1.0,10.0)}),
        "color mode and severity use the paired native argument contract");
    var movement = real.Where(f=>f.CapabilitySlot is >=344 and <=347).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(movement.Length==4 && movement.All(f=>f.Kind==FeatureKind.Number && f.RequiresScene &&
        !f.ChangesProgression && f.CanSaveInProfile) &&
        movement.Select(f=>(f.Minimum,f.Maximum)).SequenceEqual(new[]{(0.0,32.0),(0.0,64.0),(0.1,100.0),(0.0,1000.0)}),
        "Sora movement exposes four bounded one-time numeric settings with explicit profile application");
    var loot = real.Where(f=>f.CapabilitySlot is >=352 and <=359).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(loot.Length==8 && loot.All(f=>f.RequiresScene && !f.ChangesProgression && !f.CanSaveInProfile) &&
        loot.Take(4).All(f=>f.Kind==FeatureKind.Number) &&
        loot.Skip(4).All(f=>f.Kind==FeatureKind.ReadOnly && f.CommandId==0),
        "loot edits and party diagnostics occupy separate commands and cannot replay through profiles");
    Check(loot.Take(4).Select(f=>(f.Minimum,f.Maximum)).SequenceEqual(new[]{(0.0,5000.0),(0.0,9.0),(0.0,99.0),(0.0,100.0)}),
        "loot modifier limits match native float conversion and displayed percent input");
    var gummiExtra = real.Where(f=>f.CapabilitySlot is >=320 and <=329).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(gummiExtra.Length==10 && gummiExtra.All(f=>!f.RequiresScene && !f.CanSaveInProfile) &&
        gummiExtra.Take(3).All(f=>f.Kind==FeatureKind.Number) && gummiExtra[3].Kind==FeatureKind.Action &&
        gummiExtra.Skip(4).All(f=>f.Kind==FeatureKind.ReadOnly && f.CommandId==0),
        "Gummi extras use independent module gates and separate runtime edits from diagnostics");
    BinaryDiagnosticTests.Run(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(args[0]))!,"runtime_diagnostics.json"),Check);
    var targeting = real.Where(f=>f.CapabilitySlot is >=368 and <=373).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(targeting.Length==6 && targeting.All(f=>f.RequiresScene && !f.CanSaveInProfile && !f.ChangesProgression) &&
        targeting.Count(f=>f.Kind==FeatureKind.Number)==2 && targeting.Count(f=>f.Kind==FeatureKind.ReadOnly)==3 &&
        targeting.Single(f=>f.CapabilitySlot==372).Kind==FeatureKind.Action,
        "targeting separates two one-time scalar edits, loaded-default reset and three diagnostics");
    Check(targeting[0].Minimum==.05 && targeting[0].Maximum==10 && targeting[1].Minimum==1 && targeting[1].Maximum==100000,
        "targeting edit policies exclude the native zero-radius bypass and nonfinite values");
    var projectiles = real.Where(f=>f.CapabilitySlot is >=360 and <=361).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(projectiles.Length==2 && projectiles[0].Kind==FeatureKind.Action && projectiles[1].Kind==FeatureKind.ReadOnly &&
        projectiles.All(f=>!f.RequiresScene && !f.CanSaveInProfile && !f.ChangesProgression),
        "Gummi bullet clear and count use independent mission gates without persistent profiles");
    var collision = real.Where(f=>f.CapabilitySlot is >=376 and <=391).OrderBy(f=>f.CapabilitySlot).ToArray();
    Check(collision.Length==16 && collision[0].Kind==FeatureKind.Toggle && collision.Skip(1).All(f=>f.Kind==FeatureKind.ReadOnly) &&
        collision.All(f=>!f.ChangesProgression),"body-separation control is distinct from fifteen cached collision diagnostics");
    Round5CatalogTests.Run(real, Check);
    Round7CatalogTests.Run(real, Check);
    Console.WriteLine($"Validated {real.Count} real feature definitions.");
}
await AssetExplorerTests.RunAsync(workspace, Check);
await AssetFingerprintTests.RunAsync(workspace, Check);
if(args.Length>1) {
    await AssetExplorerTests.RunRetailAsync(args[1],Check);
    await AssetFingerprintTests.RunRealAsync(Path.Combine(args[1],"Modding","openkh","data","kh2","00battle.bin"),Check);
}
Console.WriteLine($"{passed} passed, {failed} failed. Test files: {workspace}");
return failed == 0 ? 0 : 1;
