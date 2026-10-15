using System.Text.Json;
int passed = 0, failed = 0;
string folder = Path.GetFullPath(args.Single()); Directory.CreateDirectory(folder);
var checks = new List<object>();
await AudioBankInspectionTests.RunAsync(folder, (ok, name) => {
    if (ok) passed++; else failed++;
    Console.WriteLine((ok ? "PASS " : "FAIL ") + name); checks.Add(new { ok, name });
});
var report = new { passed, failed, checks, scope = "Isolated linked production Core sources and committed synthetic test source. No retail game files, GUI, game process, or native execution." };
File.WriteAllText(Path.Combine(folder, "result.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"{passed} passed, {failed} failed"); return failed == 0 ? 0 : 1;
