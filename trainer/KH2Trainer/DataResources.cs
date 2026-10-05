using System.IO;
using System.Reflection;

namespace KH2Trainer;

internal static class DataResources
{
    public static Stream Open(string name) => Assembly.GetExecutingAssembly()
        .GetManifestResourceStream("KH2Trainer.Data." + name)
        ?? throw new InvalidDataException($"The trainer is missing its {name} catalog. Rebuild or replace the executable.");
}
