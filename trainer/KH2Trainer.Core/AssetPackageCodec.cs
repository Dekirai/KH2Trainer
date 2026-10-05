using System.Buffers.Binary;
using System.IO.Compression;
using System.Security.Cryptography;

namespace KH2Trainer.Core;

internal static class AssetPackageCodec
{
    internal sealed record PayloadInfo(AssetFileStamp HeaderFile, string HeaderHash, long RecordOffset,
        int MetadataLength, byte[] MetadataHash, byte[] Seed, long StoredOffset, int StoredLength, int Mode,
        int EntryOrdinal, int RemasteredOrdinal);

    internal static PackageAssetInfo Inspect(PackageIndex index, PackageEntryInfo entry, FileStream file,
        AssetReadLimits limits, CancellationToken token)
    {
        if (!entry.IsAvailable) throw new InvalidDataException("This HED entry is an unavailable placeholder.");
        AssetArchiveReader.RequireSpan(entry.Offset, entry.StoredLength, file.Length);
        if (entry.StoredLength < 16) throw new InvalidDataException("Package record header is truncated.");
        byte[] seed = new byte[16]; file.Position = entry.Offset; file.ReadExactly(seed);
        int raw = I32(seed, 0), count = I32(seed, 4), mode = I32(seed, 8), creation = I32(seed, 12);
        long metadataLength = 16L + 48L * count;
        if (count < 0 || count > limits.MaximumBarEntries || metadataLength > limits.MaximumMetadataBytes || metadataLength > entry.StoredLength)
            throw new InvalidDataException("Invalid or oversized remaster table.");
        ValidatePayload(raw, mode, limits);
        byte[] metadata = new byte[(int)metadataLength]; seed.CopyTo(metadata, 0);
        file.ReadExactly(metadata.AsSpan(16));
        byte[] metadataHash = SHA256.HashData(metadata);
        AssetPayload Make(string name, int length, int storedMode, long offset, AssetSourceKind kind, int remasteredOrdinal = -1)
        {
            ValidatePayload(length, storedMode, limits);
            int stored = EffectiveStoredLength(length, storedMode);
            AssetArchiveReader.RequireSpan(offset, stored, entry.StoredLength);
            var info = new PayloadInfo(index.Header, index.HeaderSha256, entry.Offset, metadata.Length,
                metadataHash, seed, offset, stored, storedMode, entry.Ordinal, remasteredOrdinal);
            return new(name, length, kind, index.Package, packageData: info,
                description: $"{Path.GetFileName(index.PackagePath)} / {entry.NameHash} / {name}");
        }
        var original = Make(entry.Name, raw, mode, metadataLength, AssetSourceKind.PackageOriginal);
        long current = checked(metadataLength + PhysicalLength(raw, mode));
        if (count > 0 && current < metadataLength + EffectiveStoredLength(raw, mode))
            throw new InvalidDataException("Original payload overlaps the remaster data.");
        var remasters = new List<RemasteredAssetInfo>(count);
        for (int i = 0; i < count; i++)
        {
            token.ThrowIfCancellationRequested();
            int p = 16 + i * 48;
            string name = AssetArchiveReader.DisplayBytes(metadata.AsSpan(p, 32), true);
            int length = I32(metadata, p + 40), storedMode = I32(metadata, p + 44);
            var payload = Make(name.Length == 0 ? $"remaster_{i:D4}.bin" : name, length, storedMode,
                current, AssetSourceKind.PackageRemastered, i);
            long physicalLength = PhysicalLength(length, storedMode);
            if (physicalLength < EffectiveStoredLength(length, storedMode))
                throw new InvalidDataException("Remaster payload overlaps the following data.");
            AssetArchiveReader.RequireSpan(current, physicalLength, entry.StoredLength);
            remasters.Add(new(i, name, Convert.ToHexString(metadata.AsSpan(p, 32)),
                U32(metadata, p + 32), U32(metadata, p + 36), current, storedMode, payload));
            current = checked(current + physicalLength);
        }
        return new(entry, mode, creation, original, remasters.AsReadOnly());
    }

    internal static async Task<Stream> DecodeAsync(AssetPayload payload, AssetReadLimits limits, CancellationToken token)
    {
        var info = payload.PackageData!;
        int rawLength = checked((int)payload.Length);
        ValidatePayload(rawLength, info.Mode, limits);
        if (info.MetadataLength > limits.MaximumMetadataBytes)
            throw new InvalidDataException("Package metadata exceeds this reader's limit.");
        // Revalidate both the index and the exact inspected record before trusting a locator.
        await using (var hed = info.HeaderFile.Open())
        {
            byte[] hash = await SHA256.HashDataAsync(hed, token).ConfigureAwait(false);
            if (Convert.ToHexString(hash) != info.HeaderHash) throw new IOException("The HED index changed. Reopen it.");
        }
        await using var file = payload.Source.Open();
        file.Position = info.RecordOffset;
        byte[] metadata = new byte[info.MetadataLength];
        await file.ReadExactlyAsync(metadata, token).ConfigureAwait(false);
        if (!CryptographicOperations.FixedTimeEquals(SHA256.HashData(metadata), info.MetadataHash))
            throw new IOException("The package metadata changed. Reopen it.");
        AssetArchiveReader.RequireSpan(checked(info.RecordOffset + info.StoredOffset), info.StoredLength, file.Length);
        // One decoded buffer only; encoded input is streamed through a bounded range.
        byte[] decoded = new byte[rawLength];
        await using var slice = new AssetSliceStream(file, checked(info.RecordOffset + info.StoredOffset), info.StoredLength);
        bool transform = rawLength > 16 && info.Mode >= -1;
        await using var encoded = new PrefixStream(slice, transform ? DeriveMask(info.Seed) : null,
            throttleTail: rawLength > 16 && info.Mode > 0);
        if (rawLength > 16 && info.Mode > 0)
        {
            // Small tail reads retain the exact RFC1950 endpoint instead of allowing
            // decompressor read-ahead to hide a truncated checksum behind padding.
            await using (var inflate = new ZLibStream(encoded, CompressionMode.Decompress, leaveOpen: true))
            {
                await inflate.ReadExactlyAsync(decoded, token).ConfigureAwait(false);
                if (await inflate.ReadAsync(new byte[1], token).ConfigureAwait(false) != 0)
                    throw new InvalidDataException("Decoded package payload exceeds its declared length.");
            }
            if (encoded.Position < 6 || encoded.LastFourBytes != Adler32(decoded, token))
                throw new InvalidDataException("Missing or invalid zlib payload checksum.");
            long padding = encoded.Length - encoded.Position;
            if (padding is < 0 or > 15) throw new InvalidDataException("Unexpected bytes after the zlib payload.");
            var tail = new byte[(int)padding];
            await encoded.ReadExactlyAsync(tail, token).ConfigureAwait(false);
            if (tail.Any(b => b != 0xCD && b != 0))
                throw new InvalidDataException("Unsupported compressed-payload padding.");
        }
        else await encoded.ReadExactlyAsync(decoded, token).ConfigureAwait(false);
        token.ThrowIfCancellationRequested();
        return new MemoryStream(decoded, writable: false);
    }

    private static int I32(byte[] data, int offset) => BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(offset, 4));
    private static uint U32(byte[] data, int offset) => BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(offset, 4));
    private static int EffectiveStoredLength(int raw, int mode) => raw > 16 && mode > 0 ? mode : raw;
    private static long PhysicalLength(int raw, int mode) => mode >= 0 ? mode : ((long)raw + 15) & ~15L;
    private static void ValidatePayload(int raw, int mode, AssetReadLimits limits)
    {
        if (raw < 0 || raw > limits.MaximumDecodedBytes)
            throw new InvalidDataException("Decoded payload exceeds the configured size limit.");
        if (mode != -2 && mode != -1 && mode <= 0)
            throw new InvalidDataException("Unsupported package storage mode.");
        if (mode > limits.MaximumDecodedBytes)
            throw new InvalidDataException("Stored payload exceeds the configured size limit.");
    }

    // Native table at140713540 and key expansion143CE0/144350. The package block
    // helper144280 only XORs the eleven round keys; this is not full AES.
    private static readonly byte[] Substitution = Convert.FromHexString(
        "7E8897550B06F108EBBB141CD87AEC4134B2A346EF6BFEE1CF53A50512D28E52" +
        "4A80E981B0F0B49CFF0F1513DA734E77BED730E5F65A113767BC836F2776D0CD" +
        "690D2E514290B8B64CADCE5B1A1FF5AF01F85E3A6E688BE89FC9D9269229C833" +
        "983254D4442566AC5F9921E48F1DC2D5A462F90261DE59E7079AFA2F953F86D3" +
        "78A775EDD62D6487BDC7C1AAF28C17CB318AC3CC04EE6AAB5C2270CA9E716D85" +
        "455DB9A9A61047FB827D847BC6E238FC2B0E209DC5F339A8A06558437CE33618" +
        "724979AED17440C4914F2463BFBA239650B357DF1E03487F354D3EE6A1DD093C" +
        "3D3B568D932A9B4B0C28B1E0608919DB2CF76CB51B94C0DCEAB70AF416FDA200");
    private static byte[] DeriveMask(byte[] seed)
    {
        Span<byte> keys = stackalloc byte[176];
        for (int i = 0; i < 16; i++) keys[i] = seed[i] == 0 ? (byte)i : seed[i];
        ReadOnlySpan<byte> roundConstants = [1, 2, 4, 8, 16, 32, 64, 128, 27, 54];
        Span<byte> word = stackalloc byte[4];
        for (int i = 16; i < keys.Length; i += 4)
        {
            keys.Slice(i - 4, 4).CopyTo(word);
            if (i % 16 == 0)
            {
                byte first = word[0];
                word[0] = (byte)(Substitution[word[1]] ^ roundConstants[i / 16 - 1]);
                word[1] = Substitution[word[2]]; word[2] = Substitution[word[3]]; word[3] = Substitution[first];
            }
            for (int j = 0; j < 4; j++) keys[i + j] = (byte)(keys[i - 16 + j] ^ word[j]);
        }
        byte[] mask = new byte[16];
        for (int i = 0; i < keys.Length; i++) mask[i % 16] ^= keys[i];
        return mask;
    }
    private static uint Adler32(ReadOnlySpan<byte> bytes, CancellationToken token)
    {
        uint a = 1, b = 0;
        // 5552 bytes is the largest conventional safe block for32-bit Adler sums.
        for (int offset = 0; offset < bytes.Length; offset += 5552)
        {
            token.ThrowIfCancellationRequested();
            foreach (byte value in bytes.Slice(offset, Math.Min(5552, bytes.Length - offset))) { a += value; b += a; }
            a %= 65521; b %= 65521;
        }
        return (b << 16) | a;
    }

    private sealed class PrefixStream(Stream source, byte[]? mask, bool throttleTail) : Stream
    {
        private readonly long transformLength = mask is null ? 0 : Math.Min(source.Length / 16 * 16, 256);
        private long position;
        internal uint LastFourBytes { get; private set; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => source.Length;
        public override long Position { get => position; set => throw new NotSupportedException(); }
        private int Count(int requested)
        {
            long remaining = Length - position;
            if (throttleTail) remaining = remaining > 32 ? remaining - 32 : Math.Min(remaining, 1);
            return (int)Math.Min(requested, remaining);
        }
        private void Transform(Span<byte> bytes)
        {
            for (int i = 0; i < bytes.Length; i++)
            {
                if (position < transformLength) bytes[i] ^= mask![(int)(position % 16)];
                LastFourBytes = (LastFourBytes << 8) | bytes[i]; position++;
            }
        }
        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));
        public override int Read(Span<byte> buffer)
        { int read = source.Read(buffer[..Count(buffer.Length)]); Transform(buffer[..read]); return read; }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            int read = await source.ReadAsync(buffer[..Count(buffer.Length)], cancellationToken).ConfigureAwait(false);
            Transform(buffer.Span[..read]); return read;
        }
        protected override void Dispose(bool disposing) { if (disposing) source.Dispose(); base.Dispose(disposing); }
        public override async ValueTask DisposeAsync() { await source.DisposeAsync().ConfigureAwait(false); GC.SuppressFinalize(this); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }
}
