int checks = 0, failures = 0;
BinaryDiagnosticTests.Run(args[0], (okay, name) =>
{
    checks++;
    if (!okay) failures++;
    Console.WriteLine($"{(okay ? "PASS" : "FAIL")} {name}");
});
Console.WriteLine($"Binary diagnostics: {checks} checks / {failures} failures");
Environment.ExitCode = failures == 0 ? 0 : 1;
