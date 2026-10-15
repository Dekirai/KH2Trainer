using System.Buffers.Binary;
using KH2Trainer.Core;

internal static class BoundedInputReview
{
    internal sealed record Result(int Seed, int Cases, int Checks, long StreamReads, long StreamBytes,
        IReadOnlyDictionary<string,int> Outcomes, string Scope);
    internal static async Task<Result> RunAsync()
    {
        const int seed = 20261011, cases = 4096;
        var random = new Random(seed); int checks = 0; long reads = 0, bytes = 0;
        var outcomes = new Dictionary<string,int>();
        void Require(bool ok, string why) { ++checks; if (!ok) throw new InvalidDataException("Independent input review: " + why); }
        static void U16(byte[] b, int p, ushort v) => BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(p,2),v);
        static void U32(byte[] b, int p, uint v) => BinaryPrimitives.WriteUInt32LittleEndian(b.AsSpan(p,4),v);
        int Pick(params int[] candidates) => candidates[random.Next(candidates.Length)];
        for (int c = 0; c < cases; c++)
        {
            int length = c % 32 == 0 ? random.Next(21) : random.Next(64, 16385);
            var input = new byte[length]; random.NextBytes(input);
            if (length >= 48 && c % 9 == 0) "ORIGIN\0"u8.CopyTo(input);
            else if (length >= 20)
            {
                "SEDBSSCF"u8.CopyTo(input); uint version = (uint)Pick(3,3,4,4,2,0x03000000);
                U32(input,8,version); input[12]=(byte)Pick(0,0,0,1); input[13]=(byte)Pick(4,4,4,8);
                ushort h = (ushort)Pick(0,16,32,48,length-32,length-31,65535); U16(input,14,h);
                U32(input,16,(uint)Pick(0,length/2,length,length+32,int.MaxValue));
                if ((long)h + 32 <= length)
                {
                    ushort count = (ushort)Pick(0,1,2,16,51,ushort.MaxValue);
                    U16(input,h,count); U16(input,h+2,(ushort)Pick(0,1,2,17)); U16(input,h+4,(ushort)Pick(0,1,2,17));
                    U32(input,h+8,unchecked((uint)Pick(0,32,128,length-4,length-3,-1)));
                    U32(input,h+12,unchecked((uint)Pick(0,32,144,length-4,length-3,int.MinValue)));
                    U32(input,h+16,unchecked((uint)Pick(0,0,160,length-4,-1)));
                    for (int j=0;j<count&&j<16&&(long)h+36+4*j<=length;j++)
                        U32(input,h+32+4*j,unchecked((uint)Pick(-1,int.MinValue,0,1,64,128,4090,4096,length-32,length-16,length-15,length,int.MaxValue)));
                }
            }
            byte[] before=(byte[])input.Clone();
            var limits=new AudioBankReadLimits { MaximumTableEntries=50,MaximumRows=100,
                MaximumMetadataBytes=Pick(1,7,8,20,48,4096,4128,8192),MaximumDiagnostics=Pick(1,2,8) };
            using var stream=new GuardStream(input);
            var doc=await AudioBankInspector.InspectStreamAsync(stream,limits);
            Require(before.AsSpan().SequenceEqual(input),"input bytes changed");
            Require(doc.AvailableLength==length,"wrong logical length");
            Require(doc.MetadataBytesRead==stream.BytesRead&&stream.BytesRead<=limits.MaximumMetadataBytes,"read budget/accounting");
            Require(doc.Rows.Count<=limits.MaximumRows&&doc.Rows.GroupBy(r=>r.TableKind).All(g=>g.Count()<=limits.MaximumTableEntries),"row limits");
            Require(doc.Diagnostics.Count<=limits.MaximumDiagnostics&&doc.Preview.Count<=Math.Min(4096,length),"output bounds");
            Require(!doc.HitLimit||doc.Status==AudioInspectionStatus.LimitReached,"limit cannot masquerade as completed parse");
            Require(doc.Rows.All(r=>!r.SoundId.HasValue||r.TableKind==AudioTableKind.Sequence&&r.Status==AudioTargetStatus.Available),"decoded ID without available sequence header");
            Require(doc.Origin is null||doc.Origin.NameHex.Length<=64,"ORIGIN name escaped outside fixed region");
            string outcome=doc.Format+"/"+doc.Status;outcomes[outcome]=outcomes.GetValueOrDefault(outcome)+1;
            reads+=stream.Reads;bytes+=stream.BytesRead;
        }
        return new(seed,cases,checks,reads,bytes,outcomes,
            "Deterministic malformed and boundary inputs through the real parser, with an independent stream that rejects out-of-bounds seeks/reads. Byte immutability, limits and output invariants checked. This is finite synthetic evidence, not format or semantic completeness.");
    }
    private sealed class GuardStream(byte[] input):Stream
    {
        private long position;
        public int Reads{get;private set;}
        public long BytesRead{get;private set;}
        public override bool CanRead=>true;
        public override bool CanSeek=>true;
        public override bool CanWrite=>false;
        public override long Length=>input.LongLength;
        public override long Position{get=>position;set{if(value<0||value>Length)throw new InvalidOperationException("Invalid metadata seek");position=value;}}
        public override ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken cancellationToken=default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if(buffer.Length>Length-position)throw new InvalidOperationException("Metadata read exceeded bounded stream");
            input.AsMemory(checked((int)position),buffer.Length).CopyTo(buffer);position+=buffer.Length;
            ++Reads;BytesRead+=buffer.Length;return ValueTask.FromResult(buffer.Length);
        }
        public override int Read(byte[] buffer,int offset,int count)=>ReadAsync(buffer.AsMemory(offset,count)).GetAwaiter().GetResult();
        public override long Seek(long offset,SeekOrigin origin){Position=checked((origin==SeekOrigin.Begin?0:origin==SeekOrigin.Current?Position:Length)+offset);return Position;}
        public override void Flush(){}
        public override void SetLength(long value)=>throw new NotSupportedException();
        public override void Write(byte[] buffer,int offset,int count)=>throw new NotSupportedException();
    }
}
