using System.Buffers.Binary;
using KH2Trainer.Core;

internal static class MotionPayloadTests
{
    private static void I(byte[] b,int p,int v)=>BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(p),v);
    private static void H(byte[] b,int p,int v)=>BinaryPrimitives.WriteUInt16LittleEndian(b.AsSpan(p),(ushort)v);
    private static void F(byte[] b,int p,float v)=>I(b,p,BitConverter.SingleToInt32Bits(v));
    private static readonly float[] Identity=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
    private static byte[] Raw(params float[][] frames)
    {
        byte[] b=new byte[128+64*frames.Length];I(b,0,1);I(b,36,frames.Length);I(b,44,128);
        F(b,84,frames.Length-1);F(b,88,60);F(b,92,0);
        for(int i=0;i<frames.Length;i++) for(int j=0;j<16;j++) F(b,128+i*64+j*4,frames[i][j]);
        return b;
    }
    private const int Root=160, Curves=256, Keys=384, Times=1024, Values=1280, Tangents=1536;
    private static byte[] Prototype()
    {
        byte[] b=new byte[2048];I(b,44,Root);I(b,Root+12,1);I(b,32,2);
        I(b,48,Curves);I(b,52,9);I(b,56,Curves+54);I(b,64,Keys);I(b,68,Times);I(b,72,Values);I(b,76,Tangents);
        F(b,144,0);F(b,152,60);F(b,Times,0);F(b,Times+4,10);
        for(int i=0;i<3;i++)F(b,Root+4*i,1);
        for(int i=0;i<9;i++)I(b,Root+48+4*i,-1);
        return b;
    }
    private static byte[] Curve(int channel,int mode=1,int pre=0,int post=0,float v0=2,float v1=12,float t1=10)
    {
        byte[] b=Prototype();I(b,Root+48+channel*4,0);b[Curves+2]=(byte)(channel|(pre<<4)|(post<<6));b[Curves+3]=2;
        H(b,Keys,mode);H(b,Keys+2,0);H(b,Keys+4,0);H(b,Keys+6,1);
        H(b,Keys+8,(1<<2)|mode);H(b,Keys+10,1);H(b,Keys+12,2);H(b,Keys+14,3);
        F(b,Values,v0);F(b,Values+4,v1);F(b,Times+4,t1);
        F(b,Tangents,3);F(b,Tangents+4,4);F(b,Tangents+8,5);F(b,Tangents+12,6);return b;
    }
    public static void Run(Action<bool,string> check)
    {
        void Yes(bool ok,string name)=>check(ok,"motion: "+name);
        void Bad(Action action,string name) { try { action();Yes(false,name); }catch(MotionPayloadException){Yes(true,name);} }
        void Arg(Action action,string name) { try { action();Yes(false,name); }catch(ArgumentOutOfRangeException){Yes(true,name);} }
        MotionRootSample Eval(byte[] b,float frame=0)=>MotionPayloadReader.ReadPayload(b).Evaluate(frame);
        bool Near(float a,float b,float epsilon=0.00001f)=>MathF.Abs(a-b)<=epsilon;
        var noRaw=new byte[48];I(noRaw,0,1);
        Yes(!Eval(noRaw).HasRoot && Eval(noRaw).Matrix[3,3]==1,"RAW no-root early branch");
        var noPrototype=new byte[64];I(noPrototype,44,48);
        Yes(!Eval(noPrototype).HasRoot,"Prototype descriptor flag no-root");
        Yes(Eval(Prototype()).Matrix.Values.SequenceEqual(Identity),"Prototype constant identity");
        var b=Prototype();F(b,Root,2);F(b,Root+4,3);F(b,Root+8,4);F(b,Root+32,5);F(b,Root+36,6);F(b,Root+40,7);
        var sample=Eval(b);Yes(sample.Matrix[0,0]==2&&sample.Matrix[1,1]==3&&sample.Matrix[2,2]==4&&sample.Matrix[3,0]==5&&sample.Matrix[3,1]==6&&sample.Matrix[3,2]==7,"Scale then independent translation channels");
        for(int axis=0;axis<3;axis++) {
            b=Prototype();F(b,Root+16+axis*4,MathF.PI/2);sample=Eval(b);
            int a=axis==0?1:axis==1?2:0,c=axis==0?2:axis==1?0:1;
            Yes(Near(sample.Matrix[a,c],1)&&Near(sample.Matrix[c,a],-1),"rotation orientation "+axis);
        }
        for(int channel=0;channel<9;channel++) {
            b=Curve(channel,1,0,0,0.1f,0.3f);sample=Eval(b,5);
            Yes(sample.Matrix.Values.All(float.IsFinite),"all nine channel refs "+channel);
        }
        Yes(Eval(Curve(6),5).Matrix[3,0]==7,"linear midpoint");
        Yes(Eval(Curve(6,0),5).Matrix[3,0]==2,"constant key");
        Yes(Eval(Curve(6,3),5).Matrix[3,0]==0,"native interpolation mode3 zero");
        Yes(Near(Eval(Curve(6,2),5).Matrix[3,0],5.75f),"Hermite uses left OUT/right IN (4,5)");
        Yes(Eval(Curve(6,1,1,1),-2).Matrix[3,0]==-4,"pre linear uses IN3");
        Yes(Eval(Curve(6,1,1,1),12).Matrix[3,0]==24,"post linear uses OUT6");
        Yes(Eval(Curve(6,1,3,3),0).Matrix[3,0]==0&&Eval(Curve(6,1,3,3),10).Matrix[3,0]==0,"endpoint extrapolation mode3");
        Yes(Eval(Curve(6,1,2,2),-5).Matrix[3,0]==7&&Eval(Curve(6,1,2,2),25).Matrix[3,0]==7,"pre/post repeated wrap");
        b=Curve(3,1,0,0,0,3.2f,2);Yes(Eval(b,1).Matrix.Values.SequenceEqual(Identity),"short rotation discontinuity holds left");
        b=Curve(6);F(b,144,5);F(b,152,30);Yes(Eval(b,0).EffectiveFrame==10,"Prototype native frame offset order");
        b=Curve(6);I(b,52,0);I(b,56,Curves);I(b,60,1);Yes(Eval(b,5).Matrix[3,0]==7,"second curve table indexed after firstCount");
        b=Curve(6);b[Curves+3]=3;I(b,32,3);F(b,Times+4,5);F(b,Times+8,10);
        H(b,Keys+16,(2<<2)|1);H(b,Keys+18,2);F(b,Values+8,22);
        Yes(Eval(b,5).Matrix[3,0]==12&&Eval(b,7.5f).Matrix[3,0]==17,"three-key exact and inner search");
        // Sparse keys: interior global times not represented by a curve still choose surrounding keys.
        b=Curve(6);I(b,32,3);F(b,Times+4,5);F(b,Times+8,10);H(b,Keys+8,(2<<2)|1);
        Yes(Eval(b,5).Matrix[3,0]==7,"sparse global-time key interval");
        b=Curve(6);I(b,32,3);F(b,Times+4,0);F(b,Times+8,10);H(b,Keys+8,(2<<2)|1);
        Yes(Eval(b,5).Matrix[3,0]==7,"duplicate global time allowed when referenced curve spans remain positive");
        // Native RAW preserves truncation and adjusted factor behavior, not floor/modulo.
        var translated=(float[])Identity.Clone();translated[12]=10;translated[15]=3;
        b=Raw(Identity,translated);sample=Eval(b,.25f);
        Yes(sample.FirstRawFrame==0&&sample.SecondRawFrame==1&&sample.RawFraction==.25f&&sample.Matrix[3,0]==2.5f&&sample.Matrix[3,3]==1.5f,"RAW four-component lerp and indices");
        sample=Eval(b,-.5f);Yes(sample.RawFraction==-.5f&&sample.Matrix[3,0]==-5,"negative fractional truncation retained");
        sample=Eval(b,-1.5f);Yes(sample.RawFraction==0&&sample.FirstRawFrame==0,"negative integer truncation zeros factor");
        sample=Eval(b,100);Yes(sample.FirstRawFrame==1&&sample.RawFraction==0&&sample.Matrix[3,0]==10,"upper clamp also zeros factor");
        F(b,84,0);F(b,92,1);sample=Eval(b,.5f);Yes(sample.SecondRawFrame==1&&sample.Matrix[3,0]==5,"RAW explicit loop target");
        F(b,92,99);Yes(Eval(b,.5f).SecondRawFrame==1,"RAW upper loop target clamps to last");
        F(b,92,0.75f);Yes(Eval(b,.5f).SecondRawFrame==0,"RAW loop target truncates");
        // Unit rotations demonstrate nonlinear normalization; lerp16 would produce 0.5, not sqrt(0.5).
        foreach(int axis in new[]{0,1,2}) {
            b=Prototype();F(b,Root+16+axis*4,MathF.PI/2);var rotated=Eval(b).Matrix.Values.ToArray();
            sample=Eval(Raw(Identity,rotated),.5f);
            int changed=axis==0?1:axis==1?0:0;
            Yes(Near(sample.Matrix[changed,changed],MathF.Sqrt(.5f),.00002f),"RAW normalized rotation axis "+axis);
        }
        // Drive every ordered dot-product branch. Both normalized first rows and reconstructed cross axes
        // must have unit XYZ length, pairwise orthogonality and right-handed orientation.
        int permutations=0;
        foreach(var order in new[]{new[]{0,1,2},new[]{0,2,1},new[]{1,0,2},new[]{1,2,0},new[]{2,0,1},new[]{2,1,0}}) {
            float[] right=(float[])Identity.Clone();float[] dots=[.1f,.4f,.8f];
            for(int row=0;row<3;row++) { right[row*4+row]=dots[order[row]];right[row*4+(row+1)%3]=MathF.Sqrt(1-dots[order[row]]*dots[order[row]]); }
            var m=Eval(Raw(Identity,right),.35f).Matrix;
            for(int row=0;row<3;row++)Yes(Near(m[row,0]*m[row,0]+m[row,1]*m[row,1]+m[row,2]*m[row,2],1,.00002f),"RAW branch unit basis "+permutations+":"+row);
            for(int row=0;row<3;row++){int next=(row+1)%3;Yes(Near(m[row,0]*m[next,0]+m[row,1]*m[next,1]+m[row,2]*m[next,2],0,.00002f),"RAW branch orthogonality "+permutations+":"+row);}
            float determinant=m[0,0]*(m[1,1]*m[2,2]-m[1,2]*m[2,1])-m[0,1]*(m[1,0]*m[2,2]-m[1,2]*m[2,0])+m[0,2]*(m[1,0]*m[2,1]-m[1,1]*m[2,0]);
            Yes(Near(determinant,1,.00002f),"RAW branch right handed "+permutations++);
        }
        var huge=(float[])Identity.Clone();huge[0]=float.MaxValue;
        Yes(Eval(Raw(huge,Identity),0).Matrix[0,0]==float.MaxValue,"RAW zero fraction skips normalization");
        Bad(()=>Eval(Raw(huge,Identity),.5f),"normalization square overflow");
        var zero=new float[16];Yes(Eval(Raw(zero,zero),.5f).Matrix.Values.All(v=>v==0),"native zero-length normalize retains zeros");
        var rightW=(float[])Identity.Clone();rightW[3]=100;rightW[7]=200;rightW[11]=300;
        Yes(Eval(Raw(Identity,rightW),.5f).Matrix[0,3]==0,"native same-basis fast path retains left W");
        var twice=Identity.ToArray();var four=Identity.ToArray();for(int i=0;i<3;i++){twice[i*4+i]=2;four[i*4+i]=4;}
        sample=Eval(Raw(twice,four),.5f);Yes(sample.Matrix[0,0]==3&&sample.Matrix[1,1]==3&&sample.Matrix[2,2]==3,"RAW interpolates lengths separately from normalized basis");
        var opposite=Identity.Select(v=>-v).ToArray();Yes(Eval(Raw(Identity,opposite),.5f).Matrix.Values.All(float.IsFinite),"degenerate cross remains finite but not certified invertible");
        b=Raw(Identity);var parsed=MotionPayloadReader.ReadPayload(b);F(b,128,99);Yes(parsed.Evaluate(0).Matrix[0,0]==1,"RAW source buffer immutable copy");
        b=Curve(6);parsed=MotionPayloadReader.ReadPayload(b);F(b,Values,99);Yes(parsed.Evaluate(5).Matrix[3,0]==7,"Prototype source buffer immutable copy");
        var inputs=(float[])Identity.Clone();var matrix=new MotionMatrix(inputs);inputs[0]=99;Yes(matrix[0,0]==1,"matrix constructor copy");
        try{((IList<float>)matrix.Values)[0]=99;Yes(false,"matrix collection readonly");}catch(NotSupportedException){Yes(true,"matrix collection readonly");}
        Arg(()=>{_ = matrix[0,4];},"matrix column bound");
        var entry=new byte[144+Prototype().Length];Prototype().CopyTo(entry,144);Yes(MotionPayloadReader.ReadType9Entry(entry).Evaluate(0).Matrix[3,3]==1,"explicit type9 prefix");
        Bad(()=>MotionPayloadReader.ReadType9Entry(new byte[144]),"truncated type9 prefix");
        for(int len=0;len<48;len++) { int n=len;Bad(()=>MotionPayloadReader.ReadPayload(new byte[n]),"header truncation "+n); }
        b=Prototype();I(b,0,2);Bad(()=>Eval(b),"unknown kind");
        foreach(int field in new[]{44,48,56,64,68,72,76}) {var corrupt=Curve(6);if(field==56)I(corrupt,52,0);I(corrupt,field,-1);Bad(()=>Eval(corrupt),"unsigned offset overflow "+field);}
        foreach(int n in new[]{-1,int.MinValue,0,int.MaxValue}) {var corrupt=Curve(6);I(corrupt,32,n);Bad(()=>Eval(corrupt),"signed time count "+n);corrupt=Raw(Identity);I(corrupt,36,n);Bad(()=>Eval(corrupt),"signed RAW count "+n);}
        foreach(int n in new[]{-2,int.MinValue,65536,int.MaxValue}){var corrupt=Curve(6);I(corrupt,Root+48+6*4,n);Bad(()=>Eval(corrupt),"signed curve index "+n);}
        b=Curve(6);I(b,52,-1);Bad(()=>Eval(b),"negative first table count");
        b=Curve(6);I(b,60,-1);Bad(()=>Eval(b),"negative second table count");
        b=Curve(6);I(b,60,int.MaxValue);Bad(()=>Eval(b),"combined declared curve limit");
        b=Curve(6);I(b,52,0);I(b,56,Curves);Bad(()=>Eval(b),"readable second record outside declared count rejected");
        b=Curve(6);I(b,52,0);I(b,56,Curves);I(b,60,1);I(b,Root+72,1);Bad(()=>Eval(b),"second table index at count rejected");
        b=Curve(6);I(b,60,1);I(b,56,b.Length-5);Bad(()=>Eval(b),"unused declared second table truncated rejected");
        b=Curve(6);b[Curves+3]=0;Bad(()=>Eval(b),"zero key count");
        b=Curve(6);H(b,Keys+8,0);Bad(()=>Eval(b),"duplicate key time");
        b=Curve(6);H(b,Keys+8,65535);Bad(()=>Eval(b),"key time outside table");
        b=Curve(6);F(b,Times+4,0);Bad(()=>Eval(b),"duplicate time span");
        b=Curve(6);F(b,Times+4,-1);Bad(()=>Eval(b),"descending time table");
        b=Curve(6,1,2,2);b[Curves+3]=1;Bad(()=>Eval(b),"single-key wrap zero-span");
        foreach(int field in new[]{144,152,Root,Root+16,Root+32,Times,Values,Tangents})foreach(float v in new[]{float.NaN,float.PositiveInfinity,float.NegativeInfinity}){var corrupt=Curve(6);F(corrupt,field,v);Bad(()=>Eval(corrupt),"nonfinite Prototype field "+field);}
        foreach(int field in new[]{84,88,92,128,188}) {var corrupt=Raw(Identity);F(corrupt,field,float.NaN);Bad(()=>Eval(corrupt),"nonfinite RAW field "+field);}
        b=Curve(6);F(b,152,0);Bad(()=>Eval(b),"zero frame rate divisor");
        b=Curve(6);F(b,144,float.MaxValue);Bad(()=>Eval(b),"frame offset intermediate overflow");
        b=Raw(Identity);F(b,92,-1);Bad(()=>Eval(b),"negative RAW loop target");
        F(b,92,2147483648f);Bad(()=>Eval(b),"overflowing RAW loop conversion");
        foreach(float frame in new[]{float.NaN,float.PositiveInfinity,float.NegativeInfinity})Bad(()=>Eval(noRaw,frame),"nonfinite frame rejected even without root");
        Bad(()=>Eval(Raw(Identity),2147483648f),"RAW frame integer overflow");
        b=Curve(6,1,2,2,1,2,1);Bad(()=>Eval(b,1073741824f),"Float32 wrap subtraction nonprogress");
        b=Prototype();F(b,Root+16,float.MaxValue);Bad(()=>Eval(b),"angle subtraction nonprogress");
        b=Curve(6,1,2,2);Bad(()=>MotionPayloadReader.ReadPayload(b,new(){MaxEvaluationSteps=5}).Evaluate(10000),"shared wrap evaluation budget");
        b=Prototype();F(b,Root+16,10000);Bad(()=>MotionPayloadReader.ReadPayload(b,new(){MaxEvaluationSteps=5}).Evaluate(0),"angle evaluation budget");
        Bad(()=>MotionPayloadReader.ReadPayload(Prototype(),new(){MaxDecodedElements=20}),"cumulative parse budget");
        Bad(()=>MotionPayloadReader.ReadPayload(Raw(Identity,Identity),new(){MaxRawFrames=1}),"RAW frame allocation limit");
        Bad(()=>MotionPayloadReader.ReadPayload(Prototype(),new(){MaxPayloadBytes=64}),"byte limit before decode");
        Bad(()=>MotionPayloadReader.ReadPayload(Prototype(),new(){MaxTimeEntries=1}),"time allocation limit");
        Arg(()=>MotionPayloadReader.ReadPayload(Prototype(),new(){MaxEvaluationSteps=0}),"invalid caller limits");
        Bad(()=>new MotionMatrix(Enumerable.Repeat(1f,17)),"matrix enumeration bounded");
        Bad(()=>MotionRootEvaluator.ScaleBasis(matrix,0),"positive scale policy");
        Bad(()=>MotionRootEvaluator.ScaleBasis(new(huge),2),"scale finite inputs intermediate overflow");
        var translate=Identity.ToArray();translate[12]=3;var scaled=MotionRootEvaluator.ScaleBasis(MotionMatrix.Identity,2);
        Yes(MotionRootEvaluator.Multiply(new(translate),scaled)[3,0]==6,"explicit row-vector projection order");
        var rightHuge=Identity.ToArray();rightHuge[0]=float.MaxValue;
        Bad(()=>MotionRootEvaluator.Multiply(new(rightHuge),MotionRootEvaluator.ScaleBasis(matrix,2)),"composition overflow");
        Yes(parsed.Binding=="OfflineMotionProjection"&&!parsed.Evaluate(0).EstablishesNativeMotionSafety,"no native safety promotion");
        // Deterministic structural mutations must either produce a bounded finite sample or a typed rejection.
        // No live pointer, native function or retail file is involved.
        var random=new Random(0x4D4F54);
        int[] protoFields=[0,32,44,48,52,56,60,64,68,72,76,144,152,Root+48,Root+72,Keys,Times,Values,Tangents];
        int[] rawFields=[0,36,44,84,88,92,128,132,188];
        for(int trial=0;trial<2048;trial++) {
            bool raw=(trial&1)!=0;byte[] mutant=raw?Raw(Identity,translated):Curve(6,trial%4,(trial/4)%4,(trial/16)%4);
            var fields=raw?rawFields:protoFields;int location=fields[random.Next(fields.Length)];
            I(mutant,location,(int)random.NextInt64(int.MinValue,(long)int.MaxValue+1));
            try {
                var m=MotionPayloadReader.ReadPayload(mutant,new(){MaxEvaluationSteps=1000,MaxDecodedElements=10000});
                var value=m.Evaluate((float)(random.NextDouble()*200-100));
                Yes(value.Matrix.Values.Count==16&&value.Matrix.Values.All(float.IsFinite),"bounded mutation accepted "+trial);
            }catch(MotionPayloadException){Yes(true,"bounded mutation rejected "+trial);}
            catch(Exception ex){Yes(false,"unexpected mutation exception "+trial+": "+ex.GetType().Name);}
        }
    }
}
