using System.Buffers.Binary;
using KH2Trainer.Core;

internal static class ContactDefinitionTests
{
    // The nine type 10 records of the original B_LK120 type 23 entry (motion-event27-20261008/asset-census.json).
    private static readonly (int Ordinal, string Raw)[] Lk120Contacts =
    [
        (61, "0c0000000a007f00e903000000000000fa00f401"), (62, "0c0000000a007900e903000000000000fa00f401"),
        (63, "0c0000000a0053000004000000000000fa00bc02"), (64, "0c0000000a0067000004000000000000fa00bc02"),
        (151, "0d0000000a035e00760300000000000014001400"), (160, "0d0000000a007f00e903000000000000fa009b02"),
        (161, "0d0000000a007900e903000000000000fa009b02"), (162, "0d0000000a0067000004000000000000fa009b02"),
        (163, "0d0000000a0053000004000000000000fa009b02"),
    ];

    /// <summary>B_LK120-shaped synthetic payload: 164 records, mask 0xBFF00001, 3,344 bytes and the original contact records.</summary>
    private static byte[] Lk120Shaped()
    {
        byte[] data = new byte[64 + 20 * 164];
        BinaryPrimitives.WriteInt32LittleEndian(data, 164); BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(4), 0xBFF00001);
        // Other records are synthetic group 0 / type 1 rows with distinct bytes; their meaning is not asserted.
        for (int i = 0; i < 164; i++) { data[64 + 20 * i + 4] = 1; data[64 + 20 * i + 8] = (byte)i; }
        foreach (var (ordinal, raw) in Lk120Contacts) Convert.FromHexString(raw).CopyTo(data, 64 + 20 * ordinal);
        return data;
    }

    private static byte[] Payload(int count, int length, uint mask = 0)
    {
        byte[] data = new byte[length];
        BinaryPrimitives.WriteInt32LittleEndian(data, count); BinaryPrimitives.WriteUInt32LittleEndian(data.AsSpan(4), mask);
        return data;
    }

    public static async Task RunAsync(string workspace, Action<bool, string> check)
    {
        void Check(bool ok, string text) => check(ok, "type 23: " + text);
        void Reject(byte[] data, string text)
        {
            try { ContactDefinitionReader.Read(data); Check(false, text); }
            catch (InvalidDataException) { Check(true, text); }
        }
        byte[] lk120 = Lk120Shaped();
        var doc = ContactDefinitionReader.Read(lk120);
        Check(doc.Count == 164 && doc.ByteLength == 3344 && doc.RecordEnd == 3344 && doc.TrailingBytes == 0 && doc.DefaultGroupMask == 0xBFF00001,
            "B_LK120-shaped header gives count, stored default mask and exact record end");
        var contacts = doc.Definitions.Where(d => d.IsContact).ToArray();
        Check(doc.ContactCount == 9 && contacts.Select(c => (c.Ordinal, c.Offset, c.Group, c.JointId, c.Height)).SequenceEqual(new (int, int, byte, ushort?, short?)[]
            { (61,1284,12,127,500), (62,1304,12,121,500), (63,1324,12,83,700), (64,1344,12,103,700), (151,3084,13,94,20),
              (160,3264,13,127,667), (161,3284,13,121,667), (162,3304,13,103,667), (163,3324,13,83,667) }),
            "B_LK120 type 10 records yield the census groups, joints and heights");
        Check(contacts.All(c => !c.EnabledByStoredDefaultMask) && doc.Definitions[0].EnabledByStoredDefaultMask,
            "groups 12 and 13 are disabled by the stored default mask while group 0 is enabled");
        Check(contacts.Select(c => c.RawHex).SequenceEqual(Lk120Contacts.Select(c => c.Raw.ToUpperInvariant())) &&
            doc.HeaderHex == "A40000000100F0BF" + new string('0', 112), "raw record and header bytes are preserved exactly");
        Check(doc.Definitions.Where(d => !d.IsContact).All(d => d.JointId == null && d.Height == null && d.Type == 1 && d.RawHex.Length == 40),
            "records outside types 10/11 get no joint or height label, only raw bytes");
        Check(((System.Collections.IList)doc.Definitions).IsReadOnly && doc.Definitions is not ContactDefinition[],
            "parsed definitions are exposed read-only");

        byte[] mixed = Payload(3, 64 + 60, 1u << 12);
        mixed[64] = 12; mixed[68] = 11; BinaryPrimitives.WriteUInt16LittleEndian(mixed.AsSpan(70), 0x4005); BinaryPrimitives.WriteInt16LittleEndian(mixed.AsSpan(82), -3);
        mixed[84] = 44; mixed[88] = 10;
        mixed[104] = 13; mixed[108] = 12; mixed[110] = 7;
        doc = ContactDefinitionReader.Read(mixed);
        Check(doc.Definitions[0] is { IsContact: true, Type: 11, JointId: 0x4005, Height: -3, EnabledByStoredDefaultMask: true },
            "type 11 shares the joint/height layout and signed height");
        Check(doc.Definitions[1] is { Group: 44, EnabledByStoredDefaultMask: true } && !doc.Definitions[2].EnabledByStoredDefaultMask &&
            doc.Definitions[2].JointId == null, "default-mask test uses the native group index modulo 32 and type 12 stays unlabelled");

        doc = ContactDefinitionReader.Read(Payload(0, 64));
        Check(doc.Count == 0 && doc.Definitions.Count == 0 && doc.TrailingBytes == 0, "empty definition table is valid");
        doc = ContactDefinitionReader.Read(Payload(1, 64 + 23));
        Check(doc.Count == 1 && doc.TrailingBytes == 3, "trailing bytes after the declared records are reported, not parsed");
        Reject(new byte[63], "truncated header rejected");
        Reject(Payload(2, 64 + 39), "truncated final record rejected");
        Reject(Payload(-1, 64 + 20), "negative count rejected");
        Reject(Payload(int.MinValue, 64), "minimum signed count rejected");
        Reject(Payload(int.MaxValue, 4096), "maximum signed count rejected");
        // 20 * 0x0CCCCCCD wraps to 4 in 32-bit arithmetic; the widened span check must still reject it.
        Reject(Payload(0x0CCCCCCD, 64 + 20), "count whose 32-bit span wraps is rejected");
        Reject(new byte[ContactDefinitionReader.MaximumBytes + 1], "payload above the inspection bound rejected");

        string path = Path.Combine(workspace, "B_LK120-shaped.bin"); await File.WriteAllBytesAsync(path, lk120);
        var reader = new AssetArchiveReader(); var payload = reader.OpenLooseFile(path);
        doc = await ContactDefinitionReader.ReadAsync(reader, payload);
        Check(doc.Count == 164 && doc.ContactCount == 9 && File.ReadAllBytes(path).SequenceEqual(lk120), "asset reader path reads the bounded payload without changing it");
        using (var cancelled = new CancellationTokenSource())
        {
            cancelled.Cancel();
            try { await ContactDefinitionReader.ReadAsync(reader, payload, cancelled.Token); Check(false, "pre-cancellation observed"); }
            catch (OperationCanceledException) { Check(true, "pre-cancellation observed"); }
        }
    }
}
