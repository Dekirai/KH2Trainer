using System.Buffers.Binary;
using System.Globalization;
using System.Text;

namespace KH2Trainer.Core;

public sealed record BdxReadLimits
{
    public int MaximumBytes { get; init; } = 32 * 1024 * 1024;
    public int MaximumEvents { get; init; } = 16_384;
    public int MaximumInstructions { get; init; } = 100_000;
    public int MaximumDiagnostics { get; init; } = 256;
    internal void Validate()
    {
        if (MaximumBytes is < 36 or > 256 * 1024 * 1024 || MaximumEvents is < 1 or > 1_000_000 ||
            MaximumInstructions is < 1 or > 1_000_000 || MaximumDiagnostics is < 1 or > 10_000)
            throw new ArgumentOutOfRangeException(nameof(BdxReadLimits));
    }
}

public sealed record BdxEvent(int Ordinal, int Id, int Pc, long FileOffset, bool IsFirstForId);
public sealed record BdxHeader(string Name, string NameHex, int WorkBytes, int StackBytes, int TemporaryBytes,
    int HeaderEnd, int TerminatorId, IReadOnlyList<BdxEvent> Events);
public enum BdxEdgeKind { Next, Branch, Call, CallContinuation, YieldResume, NativeContinuation, DynamicReturn }
public sealed record BdxFlowEdge(BdxEdgeKind Kind, int? TargetPc);
public sealed record BdxDiagnostic(string Code, string Message, int? Pc = null, long? FileOffset = null);
public sealed record BdxInstruction(int Pc, int FileOffset, ushort Opcode, IReadOnlyList<ushort> Words,
    string Operation, string Operands, IReadOnlyList<BdxFlowEdge> Edges, int? TrapBank = null, int? TrapIndex = null)
{
    public int WidthInWords => Words.Count;
}
public sealed record BdxDocument(BdxHeader Header, int ByteLength, IReadOnlyList<BdxInstruction> Instructions,
    IReadOnlyList<BdxDiagnostic> Diagnostics, bool HitLimit, int SuppressedDiagnostics)
{
    public int DecodedBytes => Instructions.Sum(i => i.WidthInWords * 2);
    public int UndecodedBytes => ByteLength - Header.HeaderEnd - DecodedBytes;
    public const string Scope = "Stored control flow from the first entry for each event ID. Calls, yields and native callbacks have conditional continuations; runtime state and callbacks can change execution. Undecoded bytes may contain data or other code.";
}

/// <summary>
/// Offline decoder for the verified retail VM at RVA 41B400 and event lookup 41C690.
/// BDX has no magic. The caller explicitly supplies a script payload; this never executes it.
/// See docs/research/bdx-inspection-20261008 for native evidence and format limits.
/// </summary>
public static class BdxInspector
{
    public static async Task<BdxDocument> ReadAsync(AssetArchiveReader reader, AssetPayload payload,
        BdxReadLimits? limits = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(reader); ArgumentNullException.ThrowIfNull(payload);
        limits ??= new(); limits.Validate();
        if (payload.Length < 36 || payload.Length > limits.MaximumBytes)
            throw new InvalidDataException($"BDX inspection requires 36 to {limits.MaximumBytes:N0} bytes.");
        cancellationToken.ThrowIfCancellationRequested();
        await using var stream = await reader.OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
        byte[] bytes = new byte[checked((int)payload.Length)];
        await stream.ReadExactlyAsync(bytes, cancellationToken).ConfigureAwait(false);
        return new Decoder(bytes, limits, cancellationToken).Read();
    }

    public static BdxDocument Inspect(ReadOnlySpan<byte> bytes, BdxReadLimits? limits = null,
        CancellationToken cancellationToken = default)
    {
        limits ??= new(); limits.Validate();
        if (bytes.Length < 36 || bytes.Length > limits.MaximumBytes)
            throw new InvalidDataException($"BDX inspection requires 36 to {limits.MaximumBytes:N0} bytes.");
        cancellationToken.ThrowIfCancellationRequested();
        return new Decoder(bytes.ToArray(), limits, cancellationToken).Read();
    }

    private sealed class Decoder(byte[] bytes, BdxReadLimits limits, CancellationToken token)
    {
        private readonly List<BdxDiagnostic> diagnostics = [];
        private readonly SortedDictionary<int, BdxInstruction> instructions = [];
        private readonly Dictionary<int, int> wordOwners = [];
        private readonly Queue<int> pending = [];
        private readonly HashSet<int> requested = [];
        private int headerEnd, suppressed;
        private bool hitLimit;
        private ushort Word(int offset) => BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(offset, 2));
        private int Int(int offset) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset, 4));
        private static long Offset(int pc) => 16L + 2L * pc;
        private static string Hex(int value) => $"{value} (0x{unchecked((uint)value):X8})";
        private void Note(string code, string message, int? pc = null, long? offset = null)
        {
            if (diagnostics.Count < limits.MaximumDiagnostics) diagnostics.Add(new(code, message, pc, offset));
            else suppressed++;
        }
        private void Enqueue(int pc)
        {
            if (requested.Add(pc)) pending.Enqueue(pc);
        }

        public BdxDocument Read()
        {
            var events = new List<BdxEvent>(); var eventIds = new HashSet<int>();
            int end = 28, terminatorId;
            while (true)
            {
                token.ThrowIfCancellationRequested();
                if (end > bytes.Length - 8) throw new InvalidDataException("The BDX event table has no complete PC=0 terminator.");
                int id = Int(end), pc = Int(end + 4); end += 8;
                if (pc == 0) { terminatorId = id; break; }
                if (events.Count == limits.MaximumEvents) throw new InvalidDataException("The BDX event table exceeds the inspection limit.");
                bool first = eventIds.Add(id);
                events.Add(new(events.Count, id, pc, Offset(pc), first));
                if (!first) Note("duplicate-event", $"Event {id} appears more than once. Native event lookup selects its first entry.", pc, end - 8);
            }
            headerEnd = end;
            int work = Int(16), stack = Int(20), temporary = Int(24);
            if (work < 0 || stack < 0 || temporary < 0)
                Note("negative-size", "A header allocation size is negative. Instructions can be inspected, but native resource requirements are not satisfied.");
            if ((bytes.Length & 1) != 0) Note("odd-length", "The final byte cannot form a complete instruction word.", offset: bytes.Length - 1);
            var name = new StringBuilder();
            for (int i = 0; i < 16 && bytes[i] != 0; i++)
                if (bytes[i] is >= 32 and <= 126) name.Append((char)bytes[i]);
                else name.Append($"\\x{bytes[i]:X2}");
            var header = new BdxHeader(name.ToString(), Convert.ToHexString(bytes.AsSpan(0, 16)), work, stack, temporary,
                headerEnd, terminatorId, events.AsReadOnly());
            foreach (var entry in events.Where(e => e.IsFirstForId)) Enqueue(entry.Pc);
            while (pending.TryDequeue(out int pc))
            {
                token.ThrowIfCancellationRequested();
                if (instructions.ContainsKey(pc)) continue;
                long offset = Offset(pc);
                if (offset < headerEnd || offset > bytes.Length - 2)
                { Note("target-outside-code", "A declared control-flow target is outside the bounded area after the event table.", pc, offset); continue; }
                if (wordOwners.TryGetValue(pc, out int owner))
                { Note("target-inside-operand", $"The target overlaps an operand of the instruction at PC {owner}.", pc, offset); continue; }
                if (instructions.Count == limits.MaximumInstructions)
                { hitLimit = true; Note("instruction-limit", "Stopped after reaching the instruction inspection limit.", pc, offset); break; }
                int at = (int)offset; ushort word = Word(at); int group = word & 15, mode = (word >> 4) & 3, sub = word >> 6;
                int width = group switch { 0 => mode < 2 ? 3 : 2, 1 or 3 or 7 or 8 or 10 => 2, 2 or 11 => 3, _ => 1 };
                if (at > bytes.Length - width * 2)
                { Note("truncated-instruction", $"The {width}-word instruction is truncated.", pc, offset); continue; }
                bool overlap = false;
                for (int i = 1; i < width; i++)
                    if (wordOwners.TryGetValue(pc + i, out owner))
                    { overlap = true; Note("overlapping-instructions", $"This instruction would overlap the instruction at PC {owner}.", pc, offset); break; }
                if (overlap) continue;
                var words = Enumerable.Range(0, width).Select(i => Word(at + 2 * i)).ToArray();
                var edges = new List<BdxFlowEdge>();
                int next = unchecked(pc + width); string operation, operands = "";
                int? bank = null, index = null;
                void Edge(BdxEdgeKind kind, int? target) => edges.Add(new(kind, target));
                void Next() => Edge(BdxEdgeKind.Next, next);
                void Error(string message)
                { operation = "VM error (status 5)"; Note("invalid-opcode", message, pc, offset); }
                string Address(ushort value) => sub switch
                { 0 => $"frame +{value}", 1 => $"work +{value}", 2 => $"object +{value}", 3 => $"script PC {value}", _ => $"invalid selector {sub}, offset {value}" };
                switch (group)
                {
                    case 0:
                        if (mode == 0) { operation = "Push integer"; operands = Hex(Int(at + 2)); }
                        else if (mode == 1) { operation = "Push float"; operands = BitConverter.Int32BitsToSingle(Int(at + 2)).ToString("R", CultureInfo.InvariantCulture) + $" (0x{unchecked((uint)Int(at + 2)):X8})"; }
                        else { operation = mode == 2 ? "Push address" : "Load value"; operands = Address(words[1]); }
                        if (mode >= 2 && sub > 3) Note("invalid-address-selector", "The native address helper returns null for this selector.", pc, offset);
                        if (mode != 3 || sub <= 3) Next();
                        break;
                    case 1:
                        operation = "Store value"; operands = Address(words[1]);
                        if (sub == 3) operands = $"native scratch initialized from script PC {words[1]}";
                        if (sub > 3) Note("invalid-address-selector", "The native store uses a null destination for this selector.", pc, offset);
                        if (sub <= 3) Next();
                        break;
                    case 2:
                        operation = "Copy from popped address";
                        operands = $"{words[1]} bytes to " + (sub == 3 ? "native retained destination" : Address(words[2]));
                        if (sub >= 3) Note("context-dependent-destination", "This destination requires native scratch state or is null; no valid destination is inferred.", pc, offset);
                        if (sub <= 3) Next();
                        break;
                    case 3: operation = "Load through popped address"; operands = $"byte offset {words[1]}"; Next(); break;
                    case 4:
                        operation = sub == 0 ? "Store through popped address" : "Copy between popped addresses";
                        operands = sub == 0 ? "32-bit value" : $"{sub} bytes"; Next(); break;
                    case 5:
                        bool validUnary = mode == 0 ? sub is 0 or >= 2 and <= 11 : mode == 1 && sub is 1 or 2 or >= 5 and <= 11;
                        if (!validUnary) { operation = ""; Error($"Unary mode {mode}, operation {sub} returns VM status 5."); }
                        else
                        {
                            operation = sub switch { 0 => "Integer to float", 1 => "Float to integer", 2 => "Negate", 3 => "Bitwise complement",
                                4 or 8 => "Equal to zero", 5 => "Absolute value", 6 => "Less than zero", 7 => "At most zero", 9 => "Not equal to zero", 10 => "At least zero", _ => "Greater than zero" };
                            operands = mode == 0 ? "integer" : "float"; Next();
                        }
                        break;
                    case 6:
                        if (mode > 1 || (mode == 1 && sub > 4)) { operation = ""; Error($"Binary mode {mode}, operation {sub} returns VM status 5."); }
                        else
                        {
                            operation = sub switch { 0 => "Add", 1 => "Subtract", 2 => "Multiply", 3 => "Divide", 4 => "Remainder", 5 => "Bitwise AND", 6 => "Bitwise OR",
                                7 => "Bitwise XOR", 8 => "Shift left", 9 => "Arithmetic shift right", 10 => "Logical AND", 11 => "Logical OR", _ => "Keep left operand" };
                            operands = mode == 1 ? "float" : sub == 0 ? "integer / native pointer rules" : "integer"; Next();
                        }
                        break;
                    case 7:
                        operands = $"relative {(short)words[1]}, target PC {unchecked(next + (short)words[1])}";
                        if (sub > 2) { operation = ""; Error($"Branch operation {sub} returns VM status 5."); }
                        else { operation = sub switch { 0 => "Jump", 1 => "Jump if zero", _ => "Jump if nonzero" }; Edge(BdxEdgeKind.Branch, unchecked(next + (short)words[1])); if (sub != 0) Next(); }
                        break;
                    case 8:
                    case 11:
                        int relative = group == 8 ? (short)words[1] : Int(at + 2);
                        int target = unchecked(next + relative);
                        operation = group == 8 ? "Call (16-bit offset)" : "Call (32-bit offset)";
                        operands = $"relative {relative}, target PC {target}, frame {sub * 4} bytes";
                        Edge(BdxEdgeKind.Call, target); Edge(BdxEdgeKind.CallContinuation, next);
                        if (sub < 2) Note("small-call-frame", "This call reserves fewer than the eight bytes used by native return metadata.", pc, offset);
                        break;
                    case 9:
                        operation = sub switch { 0 => "Yield (status 1)", 1 => "Stop (status 2)", 2 => "Return", 3 => "Pop", 5 => "Duplicate",
                            6 => "Sine", 7 => "Cosine", 8 => "Degrees to wrapped radians", 9 => "Radians to degrees", _ => "VM error (status 5)" };
                        if (sub == 0) Edge(BdxEdgeKind.YieldResume, next);
                        else if (sub == 2) Edge(BdxEdgeKind.DynamicReturn, null);
                        else if (sub is 3 or >= 5 and <= 9) Next();
                        else if (sub != 1) Error($"Control operation {sub} returns VM status 5.");
                        break;
                    case 10:
                        bank = sub; index = words[1]; operation = "Native call"; operands = $"bank {bank}, index {index}";
                        Edge(BdxEdgeKind.NativeContinuation, next); break;
                    default: operation = ""; Error($"Opcode group {group:X} returns VM status 5."); break;
                }
                var instruction = new BdxInstruction(pc, at, word, Array.AsReadOnly(words), operation, operands, edges.AsReadOnly(), bank, index);
                instructions.Add(pc, instruction);
                for (int i = 0; i < width; i++) wordOwners.Add(pc + i, pc);
                foreach (var edge in edges) if (edge.TargetPc is int target) Enqueue(target);
            }
            return new(header, bytes.Length, Array.AsReadOnly(instructions.Values.ToArray()), diagnostics.AsReadOnly(), hitLimit, suppressed);
        }
    }
}
