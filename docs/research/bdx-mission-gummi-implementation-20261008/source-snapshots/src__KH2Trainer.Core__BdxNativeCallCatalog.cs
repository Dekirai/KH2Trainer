using System.Collections.Frozen;
using System.Text.Json;

namespace KH2Trainer.Core;

public enum BdxNativeBankState { Uncatalogued, OriginalTable, ContextInstalled }
public enum BdxNativeDescriptorState { Uncatalogued, Present, NullHandler }

/// <summary>A bounded original-file observation, never a live callback or valid-call guarantee.</summary>
public sealed record BdxNativeCallInfo(int Bank, int Index, BdxNativeBankState BankState,
    BdxNativeDescriptorState DescriptorState, uint? TableRva, uint? DescriptorRva,
    uint? HandlerRva, int? DeclaredOperandCount, bool? HasReturnSlot, uint? Flags,
    string DisplayName, bool HasAnnotation, string Summary, string Notes, string Evidence)
{
    public string SearchText => $"{Bank}:{Index} {DisplayName} {Summary} {Notes} {DescriptorState} {BankState}";
    public string Details
    {
        get
        {
            string bank = BankState switch
            {
                BdxNativeBankState.OriginalTable => $"Original table: RVA 0x{TableRva:X}.",
                BdxNativeBankState.ContextInstalled => $"Context-dependent bank: the original registry slot is NULL. A native setup path installs the table at RVA 0x{TableRva:X}; teardown clears it.",
                _ => "This bank is outside the recorded registry snapshot. Its runtime state is unknown."
            };
            string descriptor = DescriptorState switch
            {
                BdxNativeDescriptorState.Present => $"Descriptor RVA 0x{DescriptorRva:X} · handler RVA 0x{HandlerRva:X}\nDeclared operands: {DeclaredOperandCount} · VM return slot: {(HasReturnSlot == true ? "yes" : "no")} · flags 0x{Flags:X8}",
                BdxNativeDescriptorState.NullHandler => $"Descriptor RVA 0x{DescriptorRva:X}: NULL handler in the recorded table. This hole does not terminate the table; later entries can be valid. Declared operands: {DeclaredOperandCount} · flags 0x{Flags:X8}.",
                _ => "This descriptor has not been catalogued. No handler, parameter count or validity is inferred."
            };
            return $"Native call {Bank}:{Index} · {DisplayName}\n{bank}\n{descriptor}"+
                (Summary.Length == 0 ? "" : "\n\n"+Summary)+(Notes.Length == 0 ? "" : "\n"+Notes)+
                (Evidence.Length == 0 ? "" : "\nEvidence: "+Evidence)+"\n\n"+BdxNativeCallCatalog.Scope;
        }
    }
}

/// <summary>Read-only metadata for the pinned retail binary; independent of the structural BDX decoder.</summary>
public sealed class BdxNativeCallCatalog
{
    public const string OriginalExecutableSha256 = "9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed";
    public const string Scope = "Original retail metadata, with descriptive names assigned during analysis. The catalog is partial; its recorded extents are not native bounds. Runtime registration, arguments, pointer lifetimes and callback effects are not validated. A declared operand count is not proof of every slot read by the handler.";
    public static BdxNativeCallCatalog Default { get; } = Load();
    private readonly FrozenDictionary<int, BankData> banks;
    private readonly FrozenDictionary<(int Bank, int Index), BdxNativeCallInfo> calls;
    public int DescriptorCount => calls.Count;
    public int AnnotatedCount => calls.Values.Count(c => c.HasAnnotation);

    private BdxNativeCallCatalog(CatalogData data)
    {
        if (data.Schema != 1 || data.OriginalSha256 != OriginalExecutableSha256)
            throw new InvalidDataException("The native BDX catalog does not match the supported executable.");
        if (data.Banks.Any(b => b.Bank is < 0 or > 1023 || b.TableRva == 0 ||
            b.State is not (BdxNativeBankState.OriginalTable or BdxNativeBankState.ContextInstalled)))
            throw new InvalidDataException("Invalid native BDX bank metadata.");
        banks = data.Banks.ToFrozenDictionary(b => b.Bank);
        var rows = new Dictionary<(int, int), BdxNativeCallInfo>();
        foreach (var e in data.Descriptors)
        {
            if (e.Index is < 0 or > 65535 || !banks.TryGetValue(e.Bank, out var b) ||
                e.DescriptorRva != checked(b.TableRva + (uint)e.Index * 16))
                throw new InvalidDataException("Invalid native BDX descriptor metadata.");
            var state = e.HandlerRva == 0 ? BdxNativeDescriptorState.NullHandler : BdxNativeDescriptorState.Present;
            bool annotated = !string.IsNullOrWhiteSpace(e.Name);
            string name = annotated ? e.Name : state == BdxNativeDescriptorState.NullHandler ? "Null native handler" : "Unannotated native handler";
            rows.Add((e.Bank, e.Index), new(e.Bank, e.Index, b.State, state, b.TableRva, e.DescriptorRva,
                e.HandlerRva == 0 ? null : e.HandlerRva, (int)(e.Flags & 0xFFFF), (e.Flags & 0x40000000) != 0,
                e.Flags, name, annotated, e.Summary, e.Notes, e.Evidence));
        }
        calls = rows.ToFrozenDictionary();
    }

    public BdxNativeCallInfo Lookup(int bank, int index)
    {
        // These are stored opcode widths, not native table bounds.
        if (bank is < 0 or > 1023) throw new ArgumentOutOfRangeException(nameof(bank));
        if (index is < 0 or > 65535) throw new ArgumentOutOfRangeException(nameof(index));
        if (calls.TryGetValue((bank, index), out var found)) return found;
        banks.TryGetValue(bank, out var b);
        return new(bank, index, b?.State ?? BdxNativeBankState.Uncatalogued,
            BdxNativeDescriptorState.Uncatalogued, b?.TableRva, null, null, null, null, null,
            "Uncatalogued native call", false, "", "", "");
    }

    private static BdxNativeCallCatalog Load()
    {
        using var source = typeof(BdxNativeCallCatalog).Assembly.GetManifestResourceStream("KH2Trainer.Core.BdxNativeCalls.json")
            ?? throw new InvalidDataException("The native BDX catalog is missing.");
        var data = JsonSerializer.Deserialize<CatalogData>(source, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidDataException("The native BDX catalog is empty.");
        return new(data);
    }

    private sealed record CatalogData(int Schema, string OriginalSha256, BankData[] Banks, DescriptorData[] Descriptors);
    private sealed record BankData(int Bank, BdxNativeBankState State, uint TableRva);
    private sealed record DescriptorData(int Bank, int Index, uint DescriptorRva, uint HandlerRva, uint Flags,
        string Name, string Summary, string Notes, string Evidence);
}
