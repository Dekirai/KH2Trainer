int passed = 0, failed = 0;
void Check(bool result, string name) { Console.WriteLine((result ? "PASS " : "FAIL ") + name); if (result) passed++; else failed++; }
string workspace = Path.Combine(Path.GetTempPath(), "KH2AssetExplorerTests", Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(workspace);
try
{
    await AssetExplorerTests.RunAsync(workspace, Check);
    if (args.Length > 0) await AssetExplorerTests.RunRetailAsync(args[0], Check);
}
catch (Exception e) { failed++; Console.WriteLine("UNHANDLED " + e); }
Console.WriteLine($"{passed} passed, {failed} failed. Fixtures: {workspace}");
return failed == 0 ? 0 : 1;
