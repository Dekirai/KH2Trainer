using System.Buffers.Binary;

namespace KH2Trainer.Core;

/// <summary>One stored 20-byte BAR type 23 record. Only group, type and, for types 10/11, joint and height are named;
/// every other byte stays in <see cref="RawHex"/>.</summary>
public sealed record ContactDefinition(int Ordinal, int Offset, byte Group, byte Type, ushort? JointId, short? Height,
    bool EnabledByStoredDefaultMask, string RawHex)
{
    public bool IsContact => Type is 10 or 11;
}

public sealed record ContactDefinitionDocument(int Count, uint DefaultGroupMask, int ByteLength, string HeaderHex,
    IReadOnlyList<ContactDefinition> Definitions)
{
    public int RecordEnd => ContactDefinitionReader.HeaderBytes + ContactDefinitionReader.EntryBytes * Count;
    public int TrailingBytes => ByteLength - RecordEnd;
    public int ContactCount => Definitions.Count(d => d.IsContact);
    public const string Scope = "Stored definitions only. Enabled means the group bit is set in the stored default mask at header +4. At runtime the Actor enable/disable bitsets at +1440 and +1448 take priority per group, and RVA 0x3B6310 can replace the definitions; neither is visible offline. Joint and height are named only for types 10/11; other bytes are shown raw.";
}

/// <summary>
/// Offline reader for BAR type 23 (RVA 0x3C9B80): signed count at +0, default group mask at +4, a 64-byte header and
/// 20-byte records with group BYTE +0 and type BYTE +4. Types 10/11 hold the joint as u16 +6 and the height as i16 +18
/// (RVA 0x3C8070). Native code receives no payload length; the bounds here are reader policy.
/// See docs/research/motion-event27-20261008 and actor-scale-writers-20261007.
/// </summary>
public static class ContactDefinitionReader
{
    public const int HeaderBytes = 64, EntryBytes = 20, MaximumBytes = 1024 * 1024;

    public static async Task<ContactDefinitionDocument> ReadAsync(AssetArchiveReader reader, AssetPayload payload,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(reader); ArgumentNullException.ThrowIfNull(payload);
        RequireLength(payload.Length);
        await using var stream = await reader.OpenReadAsync(payload, cancellationToken).ConfigureAwait(false);
        byte[] bytes = new byte[checked((int)payload.Length)];
        await stream.ReadExactlyAsync(bytes, cancellationToken).ConfigureAwait(false);
        return Read(bytes);
    }

    public static ContactDefinitionDocument Read(ReadOnlySpan<byte> data)
    {
        RequireLength(data.Length);
        int count = BinaryPrimitives.ReadInt32LittleEndian(data);
        uint mask = BinaryPrimitives.ReadUInt32LittleEndian(data[4..]);
        if (count < 0) throw new InvalidDataException($"The type 23 definition count is negative ({count}).");
        if (HeaderBytes + (long)EntryBytes * count > data.Length)
            throw new InvalidDataException($"{count:N0} type 23 definitions need {HeaderBytes + (long)EntryBytes * count:N0} bytes; the payload has {data.Length:N0}.");
        var definitions = new ContactDefinition[count];
        for (int i = 0; i < count; i++)
        {
            int at = HeaderBytes + EntryBytes * i;
            var entry = data.Slice(at, EntryBytes);
            byte group = entry[0], type = entry[4];
            bool contact = type is 10 or 11;
            // RVA 0x3BA5BE tests the default mask with BT on a register, which uses the group index modulo 32.
            definitions[i] = new(i, at, group, type,
                contact ? BinaryPrimitives.ReadUInt16LittleEndian(entry[6..]) : null,
                contact ? BinaryPrimitives.ReadInt16LittleEndian(entry[18..]) : null,
                ((mask >> (group & 31)) & 1) != 0, Convert.ToHexString(entry));
        }
        return new(count, mask, data.Length, Convert.ToHexString(data[..HeaderBytes]), Array.AsReadOnly(definitions));
    }

    private static void RequireLength(long length)
    {
        if (length < HeaderBytes || length > MaximumBytes)
            throw new InvalidDataException($"Type 23 inspection requires {HeaderBytes} to {MaximumBytes:N0} bytes; the payload has {length:N0}.");
    }
}
