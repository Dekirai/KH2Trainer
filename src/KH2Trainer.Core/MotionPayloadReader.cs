using System.Buffers.Binary;

namespace KH2Trainer.Core;

/// <summary>Reads one bounded type9 entry (including its 144-byte runtime prefix), or its payload explicitly.
/// It never follows process pointers and does not certify the rest of a motion, a BAR or a native loader.</summary>
public static class MotionPayloadReader
{
    public const int RuntimePrefixBytes = 144;
    public static MotionPayload ReadType9Entry(ReadOnlySpan<byte> entry, MotionReadLimits? limits = null)
    {
        if (entry.Length < RuntimePrefixBytes + 4) throw new MotionPayloadException("Truncated type9 runtime prefix/payload.");
        return ReadPayload(entry[RuntimePrefixBytes..], limits);
    }
    public static MotionPayload ReadPayload(ReadOnlySpan<byte> payload, MotionReadLimits? limits = null)
    {
        limits ??= new(); limits.Validate();
        if (payload.Length > limits.MaxPayloadBytes) throw new MotionPayloadException("Motion payload byte limit exceeded.");
        var r = new Reader(payload, limits);
        return r.I32(0) switch {
            0 => r.Prototype(), 1 => r.Raw(),
            _ => throw new MotionPayloadException("Unsupported type9 motion kind.")
        };
    }
    private ref struct Reader
    {
        private readonly ReadOnlySpan<byte> bytes;
        private readonly MotionReadLimits limits;
        private int budget;
        internal Reader(ReadOnlySpan<byte> bytes, MotionReadLimits limits)
        { this.bytes = bytes; this.limits = limits; budget = limits.MaxDecodedElements; }
        private void Spend(int amount = 1)
        { if (amount < 0 || amount > budget) throw new MotionPayloadException("Cumulative decoded-element limit exceeded."); budget -= amount; }
        private ReadOnlySpan<byte> Span(long at, long length)
        {
            if (at < 0 || length < 0 || at > bytes.Length || length > bytes.Length - at)
                throw new MotionPayloadException($"Motion span outside payload: offset {at}, length {length}.");
            return bytes.Slice((int)at, (int)length);
        }
        internal int I32(long at) { Spend(); return BinaryPrimitives.ReadInt32LittleEndian(Span(at,4)); }
        private uint U32(long at) { Spend(); return BinaryPrimitives.ReadUInt32LittleEndian(Span(at,4)); }
        private ushort U16(long at) { Spend(); return BinaryPrimitives.ReadUInt16LittleEndian(Span(at,2)); }
        private byte U8(long at) { Spend(); return Span(at,1)[0]; }
        private float F32(long at)
        {
            float value = BitConverter.Int32BitsToSingle(I32(at));
            if (!float.IsFinite(value)) throw new MotionPayloadException($"Nonfinite motion value at {at}.");
            return value;
        }
        private int Count(int value, int max, string field)
        { if (value <= 0 || value > max) throw new MotionPayloadException($"Invalid {field} count: {value}."); return value; }
        internal MotionPayload Raw()
        {
            long matrixOffset = U32(44);
            if (matrixOffset == 0) return new(MotionPayloadKind.Raw, false, limits);
            int count = Count(I32(36), limits.MaxRawFrames, "RAW frame");
            Span(matrixOffset, (long)count * 64);
            float loopEnd = F32(84), rate = F32(88), loopStart = F32(92);
            // Native CVTTSS2SI yields INT_MIN for overflow; reject instead of indexing before the span.
            if (loopStart < 0 || loopStart >= 2147483648.0f)
                throw new MotionPayloadException("RAW loop start must truncate to a nonnegative Int32.");
            Spend(count);
            var matrices = new MotionMatrix[count];
            for (int i=0;i<count;i++) {
                var v = new float[16]; for (int j=0;j<16;j++) v[j]=F32(matrixOffset+(long)i*64+j*4);
                matrices[i]=new(v);
            }
            return new(MotionPayloadKind.Raw,true,limits,matrices:matrices,frameRate:rate,loopEnd:loopEnd,loopStart:loopStart);
        }
        internal MotionPayload Prototype()
        {
            long root = U32(44);
            if (I32(root+12)==0) return new(MotionPayloadKind.Prototype,false,limits);
            Span(root,84);
            int count = Count(I32(32),limits.MaxTimeEntries,"time");
            long timeOffset=U32(68), keys=U32(64), values=U32(72), tangents=U32(76);
            Span(timeOffset,(long)count*4); Spend(count);
            var times=new float[count];
            for(int i=0;i<count;i++) {
                times[i]=F32(timeOffset+(long)i*4);
                if(i>0 && times[i]<times[i-1]) throw new MotionPayloadException("Time table must be nondecreasing.");
            }
            float start=F32(144), rate=F32(152);
            float offset=MotionMath.Div(MotionMath.Mul(start,60),rate);
            int firstCount=I32(52),secondCount=I32(60);
            if(firstCount<0 || secondCount<0 || (long)firstCount+secondCount>limits.MaxCurveRecords)
                throw new MotionPayloadException("Invalid declared curve-table counts.");
            long first=U32(48), second=U32(56);
            Span(first,(long)firstCount*6);Span(second,(long)secondCount*6);
            var initial=new float[9]; var curves=new MotionCurve?[9];
            for(int channel=0;channel<9;channel++) {
                initial[channel]=F32(root+16*(channel/3)+4*(channel%3));
                int index=I32(root+48+channel*4);
                if(index == -1) continue;
                if(index<0 || index>=(long)firstCount+secondCount) throw new MotionPayloadException("Root curve index is outside the declared tables.");
                long curve=index<firstCount ? first+(long)index*6 : second+(long)(index-firstCount)*6;
                Span(curve,6);
                byte flags=U8(curve+2); int keyCount=Count(U8(curve+3),255,"curve key"); int firstKey=U16(curve+4);
                Span(keys+(long)firstKey*8,(long)keyCount*8); Spend(keyCount);
                var output=new MotionKey[keyCount];
                for(int k=0;k<keyCount;k++) {
                    long key=keys+(long)(firstKey+k)*8; int packed=U16(key), ti=packed>>2;
                    if(ti>=times.Length || (k>0 && (ti<=output[k-1].TimeIndex || !(times[ti]>times[output[k-1].TimeIndex]))))
                        throw new MotionPayloadException("Referenced curve times and indices must be bounded and strictly increasing.");
                    output[k]=new(ti,packed&3,F32(values+(long)U16(key+2)*4),
                        F32(tangents+(long)U16(key+4)*4),F32(tangents+(long)U16(key+6)*4));
                }
                if(((flags>>4)&3)==2 || (flags>>6)==2) {
                    float span=MotionMath.Sub(times[output[^1].TimeIndex],times[output[0].TimeIndex]);
                    if(!(span>0)) throw new MotionPayloadException("A wrapping curve needs a positive finite span.");
                }
                curves[channel]=new(flags,output);
            }
            return new(MotionPayloadKind.Prototype,true,limits,times,initial,curves,frameOffset:offset);
        }
    }
}
