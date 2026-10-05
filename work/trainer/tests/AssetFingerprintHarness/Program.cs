int checks = 0, failures = 0;
void Check(bool ok, string name) { checks++; if (!ok) { failures++; Console.WriteLine("FAIL " + name); } }
string fixtureRoot = Path.Combine(AppContext.BaseDirectory, "fixtures"); Directory.CreateDirectory(fixtureRoot);
await AssetFingerprintTests.RunAsync(fixtureRoot, Check);
if (args.Length > 0) await AssetFingerprintTests.RunRealAsync(args[0], Check);
Console.WriteLine($"AssetFingerprint: {checks} checks, {failures} failures");
int prior = checks;
await AssetExplorerTests.RunAsync(Path.Combine(fixtureRoot, Guid.NewGuid().ToString("N")), Check);
Console.WriteLine($"Existing AssetExplorer regression: {checks-prior} checks; total failures {failures}");
return failures == 0 ? 0 : 1;
