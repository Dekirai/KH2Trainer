using KH2Trainer.Core;

internal static class BdxNativeCallCatalogTests
{
    public static void Run(Action<bool, string> check)
    {
        var catalog = BdxNativeCallCatalog.Default;
        void Check(bool ok, string text) => check(ok, "BDX native catalog: " + text);
        void Reject(Action call, string text)
        {
            try { call(); Check(false, text); }
            catch (ArgumentOutOfRangeException) { Check(true, text); }
        }
        Check(catalog.DescriptorCount == 1063 && catalog.AnnotatedCount == 239, "embedded snapshot loads with bounded descriptor and annotation counts");
        var integer = catalog.Lookup(0, 16);
        Check(integer.DescriptorRva == 0x752F00 && integer.HandlerRva == 0x41DBF0 && integer.Flags == 0x40000001 &&
            integer.DeclaredOperandCount == 1 && integer.HasReturnSlot == true, "original RNG descriptor identity and flags are preserved");
        Check(integer.DisplayName == "Random integer" && integer.SearchText.Contains("divide fault") && integer.Details.Contains("Declared operands: 1"),
            "name, side effects and declared metadata reach inspection text");
        foreach (int hole in new[] { 10, 33, 34, 71, 72 })
        {
            var info = catalog.Lookup(0, hole);
            Check(info.DescriptorState == BdxNativeDescriptorState.NullHandler && info.HandlerRva is null && !info.HasAnnotation &&
                info.Details.Contains("does not terminate the table"), $"NULL record {hole} is explicit and not called a valid handler");
        }
        Check(catalog.Lookup(0, 11).DescriptorState == BdxNativeDescriptorState.Present &&
            catalog.Lookup(0, 73).DescriptorState == BdxNativeDescriptorState.Present, "valid records after holes remain visible");
        var unannotated = catalog.Lookup(2, 0);
        Check(unannotated.DescriptorState == BdxNativeDescriptorState.Present && !unannotated.HasAnnotation &&
            unannotated.HandlerRva == 0x431B10, "captured but unannotated handler is distinct from unknown descriptor");
        var after = catalog.Lookup(0, 105);
        Check(after.BankState == BdxNativeBankState.OriginalTable && after.DescriptorState == BdxNativeDescriptorState.Uncatalogued &&
            after.HandlerRva is null && after.DeclaredOperandCount is null && after.HasReturnSlot is null,
            "end of captured extent does not invent a NULL callback or zero-arity descriptor");
        var dynamic = catalog.Lookup(9, 0);
        Check(dynamic.BankState == BdxNativeBankState.ContextInstalled && dynamic.DescriptorState == BdxNativeDescriptorState.Present &&
            dynamic.TableRva == 0x73D080 && dynamic.HandlerRva == 0x288150 && dynamic.DeclaredOperandCount == 1,
            "bank9 activated table stays distinct from its original NULL registry slot");
        Check(dynamic.Details.Contains("original registry slot is NULL") && dynamic.Details.Contains("teardown clears it"),
            "dynamic metadata makes no live availability claim");
        var bank3 = catalog.Lookup(3, 0);
        Check(bank3.BankState == BdxNativeBankState.ContextInstalled && bank3.TableRva == 0x72F1A0 &&
            bank3.DescriptorState == BdxNativeDescriptorState.Present && bank3.HandlerRva == 0x226760,
            "captured bank3 descriptor retains context-dependent registration");
        Check(catalog.Lookup(9, 40).DescriptorState == BdxNativeDescriptorState.Present &&
            catalog.Lookup(9, 41).DescriptorState == BdxNativeDescriptorState.Uncatalogued,
            "bank9 recorded boundary distinguishes the last captured entry from unknown data");
        foreach (int bank in new[] { 11, 1023 })
        {
            var unknown = catalog.Lookup(bank, 65535);
            Check(unknown.BankState == BdxNativeBankState.Uncatalogued && unknown.DescriptorState == BdxNativeDescriptorState.Uncatalogued &&
                unknown.TableRva is null && unknown.Flags is null && unknown.Details.Contains("runtime state is unknown"),
                $"representable bank {bank} beyond snapshot is unknown, not rejected as a native bounds violation");
        }
        var mismatch = catalog.Lookup(1, 6);
        Check(mismatch.DeclaredOperandCount == 12 && mismatch.HasReturnSlot == false && mismatch.Notes.Contains("16-slot scratch") &&
            mismatch.Summary.Contains("12, 13, 14 and 15"), "known extra scratch reads remain visible alongside declared arity");
        foreach (int index in new[] { 9, 95 })
        {
            var rebind = catalog.Lookup(2, index);
            Check(rebind.DisplayName == "Actor STATUS rebind" && rebind.Summary.Contains("wrapper") && rebind.Summary.Contains("+4") &&
                rebind.HasReturnSlot == false && rebind.DeclaredOperandCount == (index == 9 ? 3 : 2),
                $"existing STATUS rebind {index} semantics survive catalog migration");
        }
        Check(catalog.Lookup(0, 4).Notes.Contains("writes to the input memory") && catalog.Lookup(0, 78).Notes.Contains("shared with other vector calls"),
            "input mutation and shared result lifetime are exposed");
        Check(catalog.Lookup(0, 17).Notes.Contains("1.0") && catalog.Lookup(0, 22).Notes.Contains("0x80000000"),
            "native rounding and integer overflow caveats are retained");
        Check(BdxNativeCallCatalog.Scope.Contains("not native bounds") && BdxNativeCallCatalog.Scope.Contains("declared operand count"),
            "catalog scope separates metadata from safe execution");
        Check(Enumerable.Range(0, 105).All(i => catalog.Lookup(0, i).HasAnnotation ==
            (catalog.Lookup(0, i).DescriptorState == BdxNativeDescriptorState.Present)), "all recorded nonnull Bank0 handlers have reviewed annotations");
        Check(catalog.Lookup(0, 76).DisplayName == "Set Drive Form Keyblade" &&
            catalog.Lookup(0, 76).Notes.Contains("validated fallback") && catalog.Lookup(0, 76).Notes.Contains("not checked"),
            "raw script weapon write is distinguished from the trainer transition fallback");
        Check(catalog.Lookup(0, 90).DeclaredOperandCount == 5 && catalog.Lookup(0, 90).HasReturnSlot == false &&
            catalog.Lookup(0, 90).Notes.Contains("discarded") && catalog.Lookup(0, 90).Notes.Contains("NaN"),
            "local transform describes both discarded output and input mutation");
        Check(catalog.Lookup(0, 46).Summary.Contains("local direction w") && catalog.Lookup(0, 46).Notes.Contains("antiparallel"),
            "direction metadata retains the nonfinite-output and degenerate-axis limits");
        Check(catalog.Lookup(0, 52).SearchText.Contains("cleanup") && catalog.Lookup(0, 52).Notes.Contains("seconds"),
            "effect duration does not invent a seconds unit or hide cleanup");
        Check(catalog.Lookup(0, 61).Notes.Contains("null") && catalog.Lookup(0, 62).Notes.Contains("signed"),
            "save-record metadata includes null and full-count limits");
        Check(catalog.Lookup(0, 9).SearchText.Contains("exit") && catalog.Lookup(0, 9).HasReturnSlot == true,
            "child VM metadata retains teardown script effects");
        Check(catalog.Lookup(2, 9).Notes.Contains("self-link") && catalog.Lookup(2, 95).Notes.Contains("not prove an Event27"),
            "Actor self-wrapper evidence does not invent an Event27 rebind witness");
        int[] extents = [105, 368, 98, 179, 59, 35, 72, 37, 9, 41, 60];
        for (int bank = 0; bank < extents.Length; bank++)
            Check(catalog.Lookup(bank, extents[bank] - 1).DescriptorState == BdxNativeDescriptorState.Present &&
                catalog.Lookup(bank, extents[bank]).DescriptorState == BdxNativeDescriptorState.Uncatalogued,
                $"bank {bank} retains its observed last record and leaves following unrelated data uncatalogued");
        foreach (var (bank, index) in new[] { (1,16), (1,116), (1,215), (1,216), (1,282), (4,0), (4,1), (7,20), (7,22), (7,23) })
            Check(catalog.Lookup(bank, index).DescriptorState == BdxNativeDescriptorState.NullHandler &&
                catalog.Lookup(bank, index).HandlerRva is null, $"new NULL hole {bank}:{index} remains explicit");
        foreach (var (bank, index, operands) in new[] { (1,103,3), (1,122,1), (1,163,2), (1,240,3), (1,246,0), (2,36,2) })
        {
            var empty = catalog.Lookup(bank, index);
            Check(empty.DescriptorState == BdxNativeDescriptorState.Present && empty.DisplayName == "Empty native handler" &&
                empty.DeclaredOperandCount == operands && empty.HasReturnSlot == false,
                $"RET-only handler {bank}:{index} still consumes arguments and is distinct from NULL");
        }
        Check(catalog.Lookup(1,157).HandlerRva == 0x42E070 && catalog.Lookup(1,219).HandlerRva == 0x42E070 &&
            catalog.Lookup(1,157).DescriptorRva != catalog.Lookup(1,219).DescriptorRva,
            "shared handler addresses preserve distinct descriptor identities");
        foreach (var (index, handler) in new[] { (14,0x433510u), (15,0x433520u), (25,0x433830u) })
            Check(catalog.Lookup(4,index).DescriptorState == BdxNativeDescriptorState.Present &&
                catalog.Lookup(4,index).HandlerRva == handler,
                $"recorded branch stub 4:{index} remains a nonnull target despite missing IDA function metadata");
        Check(catalog.Lookup(9,9).DeclaredOperandCount == 6 && catalog.Lookup(9,9).Notes.Contains("6..15") &&
            catalog.Lookup(9,9).Notes.Contains("only array element 0"),
            "scratch-copy discrepancy preserves declared arity and distinguishes copied from consumed fields");
        Check(catalog.Lookup(9,18).Summary.Contains("later destruction") && catalog.Lookup(9,18).Notes.Contains("exit script"),
            "VM retirement is described as deferred and retains exit-script effects");
        Check(catalog.Lookup(9,25).Notes.Contains("elements per cooperative yield") && catalog.Lookup(9,25).Notes.Contains("not a duration"),
            "group rebuild parameter is an element count rather than an invented time unit");
        Check(catalog.Lookup(9,32).DisplayName.Contains("radians") && catalog.Lookup(9,32).Summary.Contains("horizontal") &&
            catalog.Lookup(9,32).Summary.Contains("vertical"), "camera FOV units and mode mapping remain explicit");
        Check(catalog.Lookup(2,97).Notes.Contains("+3392 is left unchanged") && catalog.Lookup(2,97).HasReturnSlot == false,
            "conditional Actor target write does not invent a clear or a VM return value");
        Check(catalog.Lookup(1,367).Notes.Contains("success byte") && catalog.Lookup(1,367).Notes.Contains("above 2^31") &&
            catalog.Lookup(1,367).Notes.Contains("Actor memory is read before") &&
            catalog.Lookup(1,147).Summary.Contains("0x756B48"),
            "shared query result exposes stale-output, arithmetic and precheck-pointer limitations");
        Reject(() => catalog.Lookup(-1, 0), "negative bank rejected by opcode representation");
        Reject(() => catalog.Lookup(1024, 0), "bank wider than ten bits rejected");
        Reject(() => catalog.Lookup(0, -1), "negative index rejected");
        Reject(() => catalog.Lookup(0, 65536), "index wider than sixteen bits rejected");
    }
}
