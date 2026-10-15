using System.Buffers.Binary;

static class Metadata
{
    public static ushort U16(byte[] d, int p) => BinaryPrimitives.ReadUInt16LittleEndian(d.AsSpan(p, 2));
    public static uint U32(byte[] d, int p) => BinaryPrimitives.ReadUInt32LittleEndian(d.AsSpan(p, 4));
    static int I32(byte[] d, int p) => BinaryPrimitives.ReadInt32LittleEndian(d.AsSpan(p, 4));
    static bool Span(long p, long n, long length) => p >= 0 && n >= 0 && p <= length && n <= length - p;
    public static bool IsScd(byte[] d) => d.Length >= 20 && d.AsSpan(0, 8).SequenceEqual("SEDBSSCF"u8);
    public static object Scd(byte[] d)
    {
        uint version = U32(d, 8), declared = U32(d, 16); int h = U16(d, 14);
        if (version is not (3 or 4) || !Span(h, 32, d.Length)) throw new InvalidDataException("Selected SCD version/header outside probe design.");
        int sequences = U16(d, h), b = U16(d, h + 2), c = U16(d, h + 4), bank = U16(d, h + 6);
        long sequenceTable = h + 32L, tableB = U32(d, h + 8), tableC = U32(d, h + 12), auxTable = U32(d, h + 16);
        var seqOffsets = Offsets(d, sequenceTable, sequences); var bOffsets = Offsets(d, tableB, b); var cOffsets = Offsets(d, tableC, c);
        int[]? auxOffsets = auxTable == 0 ? null : Offsets(d, auxTable, sequences);
        int headerBytes = version == 3 ? 16 : 32;
        var seqRows = new List<object>(); var ids = new List<ushort>(); var kinds = new List<byte>(); var cachedBytes = new List<byte>();
        int interpreted = 0;
        for (int i = 0; i < seqOffsets.Length; i++)
        {
            int p = seqOffsets[i];
            if (p <= 0 || !Span(p, headerBytes, d.Length)) continue;
            interpreted++; ushort id = U16(d, p + 12); ids.Add(id); kinds.Add(d[p + 3]); cachedBytes.Add(d[p + 15]);
            seqRows.Add(new { index = i, relativeOffset = p, basicHeaderInDeclaredLength = Span(p, headerBytes, declared), tracksInSequence = d[p], kind = d[p + 3], flags = U32(d, p + 4), sequenceId = id, fieldByte15 = d[p + 15] });
        }
        return new { signature = "SEDBSSCF", version, headerOffset = h, fieldByte12 = d[12], fieldByte13 = d[13], declaredLengthAt16 = declared, physicalLength = d.Length, physicalMinusDeclared = (long)d.Length - declared, bankId = bank, sequenceCount = sequences, tableBCount = b, tableCCount = c, sequenceOffsetsTable = sequenceTable, tableBOffset = tableB, tableCOffset = tableC, auxOffsetsTable = auxTable, headerInDeclaredLength = Span(h, 32, declared), sequenceTableStats = Stats(seqOffsets, sequenceTable, headerBytes, d.Length, declared), tableBStats = Stats(bOffsets, tableB, 1, d.Length, declared), tableCStats = Stats(cOffsets, tableC, 1, d.Length, declared), auxTableStats = auxOffsets is null ? null : Stats(auxOffsets, auxTable, 128, d.Length, declared), interpretedSequenceHeaders = interpreted, uniqueSequenceIds = ids.Distinct().Count(), duplicateSequenceIdCount = ids.Count - ids.Distinct().Count(), sequenceKinds = kinds.GroupBy(v => v).Select(g => new { value = g.Key, count = g.Count() }).OrderBy(g => g.value), sequenceByte15Values = cachedBytes.GroupBy(v => v).Select(g => new { value = g.Key, count = g.Count() }).OrderBy(g => g.value), sequenceHeaders = seqRows, tableExtentNote = "Offsets are signed DWORD file-relative values. Table B/C referent checks cover one byte only; their complete object extents are not inferred. Zero offsets are counted and are not interpreted as sequence headers." };
    }
    static int[] Offsets(byte[] d, long table, int count)
    {
        if (!Span(table, 4L * count, d.Length)) throw new InvalidDataException("Selected offset table lies outside physical file.");
        return Enumerable.Range(0, count).Select(i => I32(d, checked((int)(table + 4L * i)))).ToArray();
    }
    static object Stats(int[] offsets, long table, int minimumExtent, long physical, long declared) => new { count = offsets.Length, tableBytes = 4L * offsets.Length, tableInPhysicalLength = Span(table, 4L * offsets.Length, physical), tableInDeclaredLength = Span(table, 4L * offsets.Length, declared), negativeOffsets = offsets.Count(o => o < 0), zeroOffsets = offsets.Count(o => o == 0), distinctOffsets = offsets.Distinct().Count(), minimumOffset = offsets.Length == 0 ? (int?)null : offsets.Min(), maximumOffset = offsets.Length == 0 ? (int?)null : offsets.Max(), referentMinimumBytes = minimumExtent, referentSpansInPhysicalLength = offsets.Count(o => Span(o, minimumExtent, physical)), referentSpansInDeclaredLength = offsets.Count(o => Span(o, minimumExtent, declared)) };
}
