using System.Runtime.CompilerServices;

namespace KH2Trainer.Core;

/// <summary>Bounded offline reproduction of root Float32 operations. MathF CRT transcendental results
/// are not promised bit-identical to the game's CRT. Successful sampling is not whole-motion or runtime safety.</summary>
public static class MotionRootEvaluator
{
    public static MotionRootSample Evaluate(MotionPayload payload, float frame)
    {
        ArgumentNullException.ThrowIfNull(payload); MotionMath.Finite(frame);
        var budget=new MotionBudget(payload.Limits.MaxEvaluationSteps);
        if(!payload.HasRoot) return new(MotionMatrix.Identity,false,frame,null,null,null);
        if(payload.Kind==MotionPayloadKind.Raw) return Raw(payload,frame,budget);
        float effective=MotionMath.Add(frame,payload.FrameOffset);
        var channels=(float[])payload.Initial.Clone();
        for(int i=0;i<channels.Length;i++) if(payload.Curves[i] is { } curve)
            channels[i]=Curve(curve,payload.Times,effective,budget);
        var matrix=MotionMatrix.Identity.Copy();
        for(int axis=0;axis<3;axis++) {
            float angle=channels[axis+3];
            if(angle==0) continue;
            angle=WrapAngle(angle,budget);
            float s=MotionMath.Finite(MathF.Sin(angle)), c=MotionMath.Finite(MathF.Cos(angle));
            float[] rotation=axis switch {
                0 => [1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1],
                1 => [c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1],
                _ => [c,s,0,0, -s,c,0,0, 0,0,1,0, 0,0,0,1]
            };
            matrix=MultiplyValues(matrix,rotation,budget);
        }
        for(int i=0;i<3;i++) matrix[12+i]=MotionMath.Add(matrix[12+i],channels[6+i]);
        for(int i=0;i<3;i++) for(int j=0;j<4;j++) matrix[4*i+j]=MotionMath.Mul(matrix[4*i+j],channels[i]);
        return new(new(matrix),true,effective,null,null,null);
    }

    /// <summary>Checks native row-vector multiplication order (left * right), including every Float32
    /// intermediate. The caller supplies the applicable transforms; Actor branch/lifetime validation is separate.</summary>
    public static MotionMatrix Multiply(MotionMatrix left, MotionMatrix right)
    { ArgumentNullException.ThrowIfNull(left); ArgumentNullException.ThrowIfNull(right); return new(MultiplyValues(left.Copy(),right.Copy(),new(1024))); }

    /// <summary>Checks multiplication of all four components of the first three rows by a positive scale.
    /// Translation is retained. This is a numerical operation, not an Actor/attachment ownership proof.</summary>
    public static MotionMatrix ScaleBasis(MotionMatrix matrix, float scale)
    {
        ArgumentNullException.ThrowIfNull(matrix); MotionMath.Finite(scale);
        if(!(scale>0)) throw new MotionPayloadException("Projection scale must be positive.");
        float[] v=matrix.Copy(); for(int i=0;i<12;i++) v[i]=MotionMath.Mul(v[i],scale); return new(v);
    }

    private static float[] MultiplyValues(float[] left,float[] right,MotionBudget budget)
    {
        var result=new float[16];
        for(int r=0;r<4;r++) for(int c=0;c<4;c++) {
            budget.Spend();
            float x=MotionMath.Mul(right[c],left[r*4]);
            x=MotionMath.Add(x,MotionMath.Mul(right[4+c],left[r*4+1]));
            x=MotionMath.Add(x,MotionMath.Mul(right[8+c],left[r*4+2]));
            result[r*4+c]=MotionMath.Add(x,MotionMath.Mul(right[12+c],left[r*4+3]));
        }
        return result;
    }
    private static float WrapAngle(float x,MotionBudget budget)
    {
        while(x>3.1415927f) { budget.Spend(); float next=MotionMath.Sub(x,6.2831855f); Progress(next<x); x=next; }
        while(x< -3.1415927f) { budget.Spend(); float next=MotionMath.Add(x,6.2831855f); Progress(next>x); x=next; }
        return x;
    }
    private static void Progress(bool ok)
    { if(!ok) throw new MotionPayloadException("Native Float32 iteration would not make progress."); }
    private static (int Lower,int Upper) Bracket(float[] times,float frame,MotionBudget budget)
    {
        if(frame>=times[^1]) return(times.Length-1,times.Length);
        if(frame<=times[0]) return(-1,0);
        int lo=0,hi=times.Length-1;
        while(hi-lo>1) {
            budget.Spend(); int mid=(lo+hi)/2; float t=times[mid];
            if(t>frame) hi=mid;
            else { lo=mid; if(frame<=t) { hi=mid; break; } }
        }
        return(lo,hi);
    }
    private static float Curve(MotionCurve curve,float[] times,float frame,MotionBudget budget)
    {
        budget.Spend(); var keys=curve.Keys; var first=keys[0];var last=keys[^1];
        var bracket=Bracket(times,frame,budget);
        bool pre=bracket.Upper<=first.TimeIndex;
        bool post=!pre && bracket.Lower>=last.TimeIndex;
        if(pre||post) {
            int mode=pre ? (curve.Flags>>4)&3 : curve.Flags>>6;
            var edge=pre?first:last;
            if(mode==0) return edge.Value;
            if(mode==3) return 0;
            if(mode==1) return pre
                ? MotionMath.Sub(edge.Value,MotionMath.Mul(MotionMath.Sub(times[edge.TimeIndex],frame),edge.In))
                : MotionMath.Add(MotionMath.Mul(MotionMath.Sub(frame,times[edge.TimeIndex]),edge.Out),edge.Value);
            float start=times[first.TimeIndex],end=times[last.TimeIndex],span=MotionMath.Sub(end,start);
            if(!(span>0)) throw new MotionPayloadException("Invalid wrap span.");
            while(pre ? frame<start : frame>end) {
                budget.Spend(); float next=pre?MotionMath.Add(frame,span):MotionMath.Sub(frame,span);
                Progress(pre?next>frame:next<frame); frame=next;
            }
            bracket=Bracket(times,frame,budget);
        }
        int lo=0,hi=keys.Length-1,li=lo,ri=hi;
        while(hi-lo>1) {
            budget.Spend(); int oldLo=lo,oldHi=hi,mid=(lo+hi)/2; var key=keys[mid];
            if(times[key.TimeIndex]==frame) return key.Value;
            if(key.TimeIndex<bracket.Lower) { lo=mid;li=mid; }
            else if(key.TimeIndex>bracket.Upper) { hi=mid;ri=mid; }
            else if(key.TimeIndex==bracket.Lower) { li=mid;ri=mid+1;break; }
            else if(key.TimeIndex==bracket.Upper) { li=mid-1;ri=mid;break; }
            Progress(lo!=oldLo||hi!=oldHi);
        }
        var left=keys[li];var right=keys[ri];
        if(left.Interpolation==0) return left.Value;
        float t0=times[left.TimeIndex],t1=times[right.TimeIndex],span2=MotionMath.Sub(t1,t0);
        if((curve.Flags&15) is >=3 and <=5 && span2<=2 && MathF.Abs(MotionMath.Sub(right.Value,left.Value))>=3.1400001f)
            return left.Value;
        return left.Interpolation switch {
            1 => MotionMath.Add(MotionMath.Div(MotionMath.Mul(MotionMath.Sub(right.Value,left.Value),MotionMath.Sub(frame,t0)),span2),left.Value),
            2 => Hermite(frame,t0,left.Value,left.Out,t1,right.Value,right.In),
            _ => 0
        };
    }
    private static float Hermite(float frame,float t0,float v0,float out0,float t1,float v1,float in1)
    {
        // 1D3570: intentionally preserve scalar instruction order, not a factored/FMA polynomial.
        float inv=MotionMath.Div(1,MotionMath.Sub(t1,t0));
        float delta=MotionMath.Sub(frame,t0), square=MotionMath.Mul(delta,delta), cube=MotionMath.Mul(square,delta);
        float inv2=MotionMath.Mul(inv,inv), term=MotionMath.Mul(cube,inv2);
        float term3=MotionMath.Mul(MotionMath.Mul(3,square),inv2);
        float twice=MotionMath.Mul(MotionMath.Mul(2,term),inv);
        float a=MotionMath.Mul(v0,MotionMath.Add(MotionMath.Sub(twice,term3),1));
        float b=MotionMath.Mul(v1,MotionMath.Sub(term3,twice));
        float squareInv=MotionMath.Mul(square,inv);
        float c=MotionMath.Mul(out0,MotionMath.Add(MotionMath.Sub(term,MotionMath.Mul(2,squareInv)),delta));
        float d=MotionMath.Mul(in1,MotionMath.Sub(term,squareInv));
        return MotionMath.Add(MotionMath.Add(MotionMath.Add(a,b),c),d);
    }
    private static int Truncate(float f)
    {
        if(!float.IsFinite(f)||f< -2147483648.0f||f>=2147483648.0f)
            throw new MotionPayloadException("Native Float32-to-Int32 conversion would be invalid.");
        return (int)f;
    }
    private static MotionRootSample Raw(MotionPayload p,float frame,MotionBudget budget)
    {
        float scaled=MotionMath.Div(MotionMath.Mul(frame,p.FrameRate),60);
        int original=Truncate(scaled),first=Math.Max(0,original),count=p.Matrices.Length;
        // Negative fractions between -1 and 0 are deliberately retained by native CVTTSS2SI.
        if(original<0) scaled=0;
        if(first>=count) { first=count-1; scaled=first; }
        float next=(float)first==p.LoopEnd?p.LoopStart:first+1;
        int second=Math.Min(Truncate(next),count-1);
        if(second<0) throw new MotionPayloadException("RAW next-frame index is negative.");
        float fraction=MotionMath.Sub(scaled,first);
        return new(new(Interpolate(p.Matrices[first].Copy(),p.Matrices[second].Copy(),fraction,budget)),true,scaled,first,second,fraction);
    }
    private static float[] Row(float[] m,int row) => m.AsSpan(row*4,4).ToArray();
    private static void Set(float[] m,int row,float[] v) => v.CopyTo(m,row*4);
    private static float Normalize(float[] v)
    {
        float squared=MotionMath.Add(MotionMath.Add(MotionMath.Mul(v[0],v[0]),MotionMath.Mul(v[1],v[1])),MotionMath.Mul(v[2],v[2]));
        float length=MotionMath.Finite(MathF.Sqrt(squared));
        if(length!=0) { float inverse=MotionMath.Div(1,length); for(int i=0;i<3;i++)v[i]=MotionMath.Mul(v[i],inverse); }
        return length; // W remains unchanged; native zero length also remains unchanged.
    }
    private static float Dot(float[] a,float[] b) => MotionMath.Add(MotionMath.Add(MotionMath.Mul(a[1],b[1]),MotionMath.Mul(a[0],b[0])),MotionMath.Mul(a[2],b[2]));
    private static float[] Cross(float[] a,float[] b) => [
        MotionMath.Sub(MotionMath.Mul(b[2],a[1]),MotionMath.Mul(b[1],a[2])),
        MotionMath.Sub(MotionMath.Mul(b[0],a[2]),MotionMath.Mul(a[0],b[2])),
        MotionMath.Sub(MotionMath.Mul(a[0],b[1]),MotionMath.Mul(b[0],a[1])),0];
    private static float[] Lerp(float[] left,float[] right,float fraction)
    {
        float complement=MotionMath.Sub(1,fraction);var output=new float[4];
        for(int i=0;i<4;i++) output[i]=MotionMath.Add(MotionMath.Mul(left[i],complement),MotionMath.Mul(right[i],fraction));
        return output;
    }
    private static float[] Interpolate(float[] left,float[] right,float fraction,MotionBudget budget)
    {
        budget.Spend(); if(fraction==0) return left;
        var a=new float[3][];var b=new float[3][];var s0=new float[4];var s1=new float[4];
        for(int i=0;i<3;i++) {
            a[i]=Row(left,i); b[i]=Row(right,i); s0[i]=Normalize(a[i]);s1[i]=Normalize(b[i]);
            if(s0[i]>=0.99999988f && s0[i]<=1.0000001f) { s0[i]=1;a[i]=Row(left,i); }
            if(s1[i]>=0.99999988f && s1[i]<=1.0000001f) { s1[i]=1;b[i]=Row(right,i); }
        }
        float x=Dot(a[0],b[0]),y=Dot(a[1],b[1]),z=Dot(a[2],b[2]);
        var result=(float[])left.Clone(); Set(result,3,Lerp(Row(left,3),Row(right,3),fraction));
        bool same=true;for(int i=0;i<4;i++) same &= BitConverter.SingleToInt32Bits(s0[i])==BitConverter.SingleToInt32Bits(s1[i]);
        if(same && x>=0.99999988f && y>=0.99999988f) return result;
        var rows=new float[3][];
        // Match all six least-aligned-axis branches in 1DB700, including ordered cross products.
        if(x<=y) {
            if(x>z) { rows[2]=Lerp(a[2],b[2],fraction);Normalize(rows[2]);rows[0]=Lerp(a[0],b[0],fraction);rows[1]=Cross(rows[2],rows[0]);Normalize(rows[1]);rows[0]=Cross(rows[1],rows[2]);Normalize(rows[0]); }
            else { rows[0]=Lerp(a[0],b[0],fraction);Normalize(rows[0]);
                if(z>y) { rows[1]=Lerp(a[1],b[1],fraction);rows[2]=Cross(rows[0],rows[1]);Normalize(rows[2]);rows[1]=Cross(rows[2],rows[0]);Normalize(rows[1]); }
                else { rows[2]=Lerp(a[2],b[2],fraction);rows[1]=Cross(rows[2],rows[0]);Normalize(rows[1]);rows[2]=Cross(rows[0],rows[1]);Normalize(rows[2]); } }
        } else {
            if(y>z) { rows[2]=Lerp(a[2],b[2],fraction);Normalize(rows[2]);rows[1]=Lerp(a[1],b[1],fraction);rows[0]=Cross(rows[1],rows[2]);Normalize(rows[0]);rows[1]=Cross(rows[2],rows[0]);Normalize(rows[1]); }
            else { rows[1]=Lerp(a[1],b[1],fraction);Normalize(rows[1]);
                if(z>x) { rows[0]=Lerp(a[0],b[0],fraction);rows[2]=Cross(rows[0],rows[1]);Normalize(rows[2]);rows[0]=Cross(rows[1],rows[2]);Normalize(rows[0]); }
                else { rows[2]=Lerp(a[2],b[2],fraction);rows[0]=Cross(rows[1],rows[2]);Normalize(rows[0]);rows[2]=Cross(rows[0],rows[1]);Normalize(rows[2]); } }
        }
        float[] scales=Lerp(s0,s1,fraction);
        for(int r=0;r<3;r++) { for(int c=0;c<4;c++)rows[r][c]=MotionMath.Mul(rows[r][c],scales[r]);Set(result,r,rows[r]); }
        return result;
    }
}

internal sealed class MotionBudget(int remaining)
{
    public void Spend() { if(remaining--<=0) throw new MotionPayloadException("Motion evaluation work limit exceeded."); }
}
internal static class MotionMath
{
    public static float Finite(float x) => float.IsFinite(x)?x:throw new MotionPayloadException("Nonfinite Float32 motion intermediate.");
    // Prevent fused multiply-add or double intermediates from silently changing the scalar native order.
    [MethodImpl(MethodImplOptions.NoInlining)] public static float Add(float a,float b)=>Finite(a+b);
    [MethodImpl(MethodImplOptions.NoInlining)] public static float Sub(float a,float b)=>Finite(a-b);
    [MethodImpl(MethodImplOptions.NoInlining)] public static float Mul(float a,float b)=>Finite(a*b);
    [MethodImpl(MethodImplOptions.NoInlining)] public static float Div(float a,float b)=>Finite(a/b);
}
