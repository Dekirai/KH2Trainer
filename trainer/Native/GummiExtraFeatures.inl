// Native Gummi runtime tuning. Include AFTER GummiFeatures.inl.
// One-time changes; no retained ship, worker calls, hooks or automatic restoration.
namespace gummi_extra {
using Context=gummi::Context;
template<class T> T& Field(uintptr_t p,size_t offset) { return *reinterpret_cast<T*>(p+offset); }
struct Code { uintptr_t rva; const BYTE* data; SIZE_T size; };
constexpr BYTE code0[]={0x1,0x51,0x28,0xc3};
constexpr BYTE code1[]={0x1,0x51,0x2c,0xc3};
constexpr BYTE code2[]={0x1,0x51,0x24,0xc3};
constexpr BYTE code3[]={0x48,0x83,0xec,0x38,0xf,0x29,0x74,0x24,0x20,0xf,0x57,0xc0,0x66,0xf,0x6e,0x71,0x24,0xf,0x5b,0xf6,0xf,0x2f,0xc6,0x76,0xc,0x33,0xc9,0xe8,0x10,0x1,0xfe,0xff,0xf3,0xf,0x59,0x70,0x10,0xf3,0xf,0x5e,0x35,0x97,0xda,0x3f,0x0,0xf3,0xf,0x10,0x5,0xa3,0xd8,0x3f,0x0,0xf3,0xf,0x58,0x35,0x23,0xd9,0x3f,0x0,0xf,0x2f,0xc6,0x77,0xc,0xf3,0xf,0x10,0x5,0x4e,0x3b,0x38,0x0,0xf3,0xf,0x5d,0xc6,0xf,0x28,0x74,0x24,0x20,0x48,0x83,0xc4,0x38,0xc3};
constexpr BYTE code4[]={0x66,0xf,0x6e,0x49,0x28,0xf,0x57,0xc0,0xf,0x5b,0xc9,0xf3,0xf,0x5e,0xd,0xc1,0xdc,0x3f,0x0,0xf3,0xf,0x58,0xd,0x55,0xdb,0x3f,0x0,0xf,0x2f,0xc1,0x77,0xc,0xf3,0xf,0x10,0x5,0x80,0x3d,0x38,0x0,0xf3,0xf,0x5d,0xc1,0xc3};
constexpr BYTE code5[]={0x66,0xf,0x6e,0x41,0x2c,0xf,0x5b,0xc0,0xc3};
constexpr BYTE code6[]={0x66,0xf,0x6e,0x41,0x34,0xf,0x5b,0xc0,0xf3,0xf,0x5e,0x5,0xe4,0xda,0x3f,0x0,0xf3,0xf,0x58,0x5,0x78,0xd9,0x3f,0x0,0xc3};
constexpr BYTE code7[]={0x48,0x89,0x5c,0x24,0x8,0x57,0x48,0x83,0xec,0x20,0x48,0x8b,0xf9,0x8b,0xda,0x48,0x8b,0x49,0x8,0xe8,0x48,0xa7,0xfc,0xff,0x48,0x8b,0xc8,0xe8,0x0,0x55,0xff,0xff,0x66,0xf,0x6e,0xcb,0xf,0x5b,0xc9,0xf3,0xf,0x59,0xc1,0xf3,0xf,0x2c,0xc0,0x1,0x47,0x38,0x83,0x7f,0x38,0x64,0x7c,0x37,0x8b,0x47,0x3c,0xf,0x1f,0x44,0x0,0x0,0x83,0xf8,0x9,0x7d,0x1f,0x83,0x47,0x38,0x9c,0xff,0xc0,0x89,0x47,0x3c,0x83,0xf8,0x9,0x7d,0x11,0x83,0x7f,0x38,0x64,0x7d,0xe7,0x48,0x8b,0x5c,0x24,0x30,0x48,0x83,0xc4,0x20,0x5f,0xc3,0xc7,0x47,0x38,0x64,0x0,0x0,0x0,0x83,0x4f,0x44,0x4,0x48,0x8b,0x5c,0x24,0x30,0x48,0x83,0xc4,0x20,0x5f,0xc3};
constexpr BYTE code8[]={0x48,0x8b,0x81,0xc8,0x0,0x0,0x0,0xc3};
const Code code[]={{0x225cd0,code0,sizeof(code0)},{0x225db0,code1,sizeof(code1)},{0x225de0,code2,sizeof(code2)},{0x226120,code3,sizeof(code3)},{0x225f10,code4,sizeof(code4)},{0x2260e0,code5,sizeof(code5)},{0x2260f0,code6,sizeof(code6)},{0x230bd0,code7,sizeof(code7)},{0x1fb330,code8,sizeof(code8)}};

bool CodeReady() { for(const auto& s:code) if(!gummi::CodeMatches(s.rva,s.data,s.size))return false;return true; }
using NativeFn=void(__fastcall*)(uintptr_t,int);
#ifdef KH2_GUMMI_EXTRA_TESTS
NativeFn testMobility=nullptr,testRoll=nullptr,testLockon=nullptr,testCharge=nullptr;
#endif
void Call(unsigned slot,uintptr_t object,int value) {
#ifdef KH2_GUMMI_EXTRA_TESTS
    NativeFn fn=slot==320?testMobility:slot==321?testRoll:slot==322?testLockon:testCharge;
    if(fn)fn(object,value);
#else
    const uintptr_t rva=slot==320?0x225DE0:slot==321?0x225CD0:slot==322?0x225DB0:0x230BD0;
    reinterpret_cast<NativeFn>(g_base+rva)(object,value);
#endif
}
bool Range(uintptr_t p,size_t n) { return p && Readable(reinterpret_cast<const void*>(p),n); }
// Resource lookup follows the same FIRST matching ID as206250/1FBD10.
// Limits bound a malformed table scan; they are not a claimed native capacity.
uintptr_t Row(uintptr_t global,size_t stride,int id) {
    uintptr_t table=0;if(!gummi::Global(global,table)||!Range(table,8))return 0;
    const int count=Field<int>(table,4);
    if(count<=0||count>4096||!Range(table,8+stride*static_cast<size_t>(count)))return 0;
    for(int i=0;i<count;++i)if(Field<int>(table+8+stride*i,0)==id)return table+8+stride*i;
    return 0;
}
bool MobilityFactor(const Context& c,int raw,float& factor,uintptr_t& resource) {
    (void)c;resource=0;float value=static_cast<float>(raw);
    if(raw<0) {
        resource=Row(0xAF0780,32,0);if(!resource)return false;
        const float scale=Field<float>(resource,16);
        if(!isfinite(scale)||scale<0 || !isfinite(value*scale))return false;
        value*=scale;
    }
    factor=fmaxf(0.1f,fminf(3.0f,value/100.0f+1.0f));return isfinite(factor);
}
bool TuningReady(const Context& c,uintptr_t& tuning) {
    tuning=Row(0xAEF508,128,0);
    if(!tuning || Field<uintptr_t>(c.player,1376)!=tuning)return false;
    for(unsigned offset:{4u,8u,12u,16u,20u,24u,64u,68u,72u})
        if(!isfinite(Field<float>(tuning,offset)))return false;
    // The new mobility/roll factors can reach3. Reject tuning data whose
    // immediate native products would overflow before its own clamps run.
    for(unsigned offset:{4u,8u,12u,24u})if(!isfinite(3.0f*Field<float>(tuning,offset)))return false;
    if(!isfinite(Field<float>(c.player,1108))||!isfinite(3.0f*Field<float>(c.player,1108)))return false;
    return Field<float>(tuning,4)>=0 && Field<float>(tuning,8)>=0 &&
        Field<float>(tuning,12)>=0 && Field<float>(tuning,64)>0 && Field<float>(tuning,68)>=0;
}
bool LockonReady(const Context& c,int value,uintptr_t rows[4]) {
    const uintptr_t lockon=c.player+2960;
    if(Field<uintptr_t>(lockon,0)!=g_base+0x5B5320)return false;
    uintptr_t table=0;if(!gummi::Global(0xAEF408,table)||!Range(table,8))return false;
    const int count=Field<int>(table,4);
    if(count<=0||count>4096||!Range(table,8+128*static_cast<size_t>(count)))return false;
    for(unsigned i=0;i<4;++i) {
        const uintptr_t row=Field<uintptr_t>(lockon,1848+16*i);rows[i]=row;
        if(row<table+8||row>=table+8+128*static_cast<size_t>(count)||(row-table-8)%128)return false;
        if(Field<int>(row,0)!=At<int>(0x5B51B8+4*i))return false;
        for(unsigned off:{4u,8u,12u,16u})if(!isfinite(Field<float>(row,off))||Field<float>(row,off)<0)return false;
        const float updated=Field<float>(row,8)-static_cast<float>(value)*Field<float>(row,12);
        if(!isfinite(updated))return false;
    }
    return true;
}
struct Combo { uintptr_t address=0,main=0,companion1=0,companion2=0;int phase=0,index=0,progress=0,stock=0,bonus=0;unsigned flags=0; };
bool ComboReady(const Context& c,Combo& q) {
    q.address=c.player+4872;q.main=Field<uintptr_t>(q.address,8);
    q.companion1=Field<uintptr_t>(q.address,16);q.companion2=Field<uintptr_t>(q.address,24);
    q.phase=Field<int>(q.address,0);q.index=Field<int>(q.address,52);
    q.progress=Field<int>(q.address,56);q.stock=Field<int>(q.address,60);
    q.flags=Field<unsigned>(q.address,68);q.bonus=Field<int>(c.state,52);
    if(q.main!=c.player+1160 || Field<uintptr_t>(q.main,0)!=g_base+0x5B5238 ||
        Field<uintptr_t>(q.main,200)!=c.state || !(q.flags&1) || q.phase<0||q.phase>5 ||
        q.index<0||q.index>6||q.progress<0||q.progress>100||q.stock<0||q.stock>9)return false;
    // Installation counts were derived from the current main ship, not a fake flag.
    bool installed=false;for(unsigned i=0;i<5;++i) {
        const int n=Field<int>(q.address,32+4*i);if(n<0||n>1000)return false;installed|=n!=0;
    }
    // A companion-only weapon can set flag1 while no main-ship stages exist.
    if(!installed && !q.companion1 && !q.companion2)return false;
    if(q.phase==1 && q.index>=5)return false; // Native table indexed only in wait phase.
    // Companion-only phase2 starts at index5. 230D20 increments it to6 when
    // entering phase4, and retains6 throughout phase5 until the native reset.
    if(q.index==6 && q.phase!=4 && q.phase!=5)return false;
    return isfinite(Field<float>(q.address,64)) && Field<float>(q.address,64)>=0;
}
bool SameCombo(const Combo& a,const Combo& b) {
    return a.address==b.address&&a.main==b.main&&a.companion1==b.companion1&&a.companion2==b.companion2&&
        a.phase==b.phase&&a.index==b.index&&a.progress==b.progress&&a.stock==b.stock&&a.flags==b.flags&&a.bonus==b.bonus;
}
}
bool GummiExtraHandle(const TrainerContext& host,unsigned slot,const double args[8],TrainerResult& result) {
    if(slot<320||slot>323)return false;
    using namespace gummi_extra;
    result={1,L"This action needs stable, living, unpaused Gummi gameplay."};
    if(host.base!=g_base||!args||!gummi::HostAndThreadReady())return true;
    for(unsigned i=0;i<8;++i)if(!isfinite(args[i])){result={2,L"Every argument must be finite."};return true;}
    const double lo=slot==323?1:slot==322?0:-100,hi=slot==323?900:slot==322?1000:200;
    if(!IsInteger(args[0],lo,hi)){result={2,L"Choose a whole number inside this control's range."};return true;}
    Context c{},fresh{};if(!gummi::BuildContext(c)||!gummi::ActionReady(c))return true;
    const int target=static_cast<int>(args[0]);const unsigned offset=slot==320?36:slot==321?40:44;
    const int old=Field<int>(c.state,offset);int delta=target;uintptr_t tuning=0,resource=0,rows[4]{};
    float factor=0;Combo before{};
    if(slot<323) {
        const int64_t difference=static_cast<int64_t>(target)-old;
        if(difference<INT32_MIN||difference>INT32_MAX||!Writable(reinterpret_cast<void*>(c.state+offset),4)){
            result={3,L"The native stat or memory is invalid; nothing changed."};return true;
        }
        delta=static_cast<int>(difference);
        if((slot<=321&&!TuningReady(c,tuning)) ||
            (slot==320&&!MobilityFactor(c,target,factor,resource)) ||
            (slot==322&&!LockonReady(c,target,rows))){
            result={3,L"The current ship's movement or lock-on resources are not ready."};return true;
        }
    } else {
        if(!ComboReady(c,before)||!Writable(reinterpret_cast<void*>(before.address+56),16)){
            result={3,L"No valid installed special-weapon combo is available."};return true;
        }
        const float multiplier=static_cast<float>(before.bonus)/100.0f+1.0f;
        const float gain=multiplier*static_cast<float>(target);
        if(!isfinite(multiplier)||multiplier<=0||!isfinite(gain)||gain<1.0f||
            gain>2147483520.0f || static_cast<int64_t>(before.progress)+static_cast<int64_t>(gain)>INT32_MAX){
            result={3,L"The native charge multiplier would produce an invalid or zero gain."};return true;
        }
    }
    if(!CodeReady()){result={4,L"Native Gummi functions changed; nothing was called."};return true;}
    if(!gummi::BuildContext(fresh)||!gummi::SameLifetime(c,fresh)||!gummi::ActionReady(fresh))return true;
    if(slot<323) {
        uintptr_t nowTuning=0,nowResource=0,nowRows[4]{};float nowFactor=0;
        if(Field<int>(fresh.state,offset)!=old || !Writable(reinterpret_cast<void*>(fresh.state+offset),4) ||
            (slot<=321&&(!TuningReady(fresh,nowTuning)||nowTuning!=tuning)) ||
            (slot==320&&(!MobilityFactor(fresh,target,nowFactor,nowResource)||nowResource!=resource||nowFactor!=factor)) ||
            (slot==322&&(!LockonReady(fresh,target,nowRows)||memcmp(rows,nowRows,sizeof(rows)))))return true;
    } else { Combo now{};if(!ComboReady(fresh,now)||!SameCombo(before,now)||!Writable(reinterpret_cast<void*>(now.address+56),16))return true; }
    if(!gummi::HostAndThreadReady())return true;
    Call(slot,slot==323?before.address:fresh.state,delta);
    // No pointer reads after native dispatch, and no cached ownership or replay.
    result={0,slot==323?L"Native special-weapon charge added once; normal stock conversion and consumption remain active.":
        L"Current ship runtime stat changed once. Rebuilding or replacing the ship can replace it; no automatic restoration."};
    return true;
}
void GummiExtraSnapshot(const TrainerContext& host) {
    using namespace gummi_extra;Context c{};
    if(host.base!=g_base||!gummi::BuildContext(c))return;
    for(unsigned slot=320;slot<=322;++slot)SnapshotValue(slot,Field<int>(c.state,36+4*(slot-320)));
    float mobility=0;uintptr_t resource=0;
    if(MobilityFactor(c,Field<int>(c.state,36),mobility,resource))SnapshotValue(328,mobility);
    SnapshotValue(329,fmaxf(0.0f,fminf(3.0f,Field<int>(c.state,40)/100.0f+1.0f)));
    const float remaining=Field<float>(c.player,1512);
    if(isfinite(remaining))SnapshotValue(327,fmaxf(0,remaining));
    Combo q{};if(ComboReady(c,q)){SnapshotValue(324,q.stock);SnapshotValue(325,q.progress);SnapshotValue(326,q.phase);}
}
void GummiExtraCapabilities(){for(unsigned slot=320;slot<=329;++slot)SupportCapability(slot);}

