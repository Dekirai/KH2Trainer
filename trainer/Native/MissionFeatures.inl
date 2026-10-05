// Native mission diagnostics and one-time timer restart.
// Evidence and ABI: work/trainer/research/missions_deep* and missions_contract.txt.
// All entry points run after update on the game thread. No persistent leases.
namespace mission_features {
constexpr uintptr_t kMission=0x2A0FF68,kStorage=0x2A0F8B0,kDescriptor=0x2A0FF70;
constexpr uintptr_t kClock=0xABB850,kPause=0xABB854,kOrigin=0xABB858,kLimit=0xABB85C,kValue=0xABB860,kPhase=0xABB864,kMode=0xABB868;
using RestartFn=char (__fastcall*)(int,int);
#ifdef KH2_MISSION_TESTS
RestartFn testRestart=nullptr;
#endif
template<class T> T Field(uintptr_t p,SIZE_T offset) { return *reinterpret_cast<const T*>(p+offset); }
bool Range(uintptr_t p,SIZE_T length) { return p && Readable(reinterpret_cast<const void*>(p),length); }
bool Allowed() {
    return g_base && g_gameThread && GetCurrentThreadId()==g_gameThread &&
        !InterlockedCompareExchange(&g_disabled,0,0) && g_shared && g_shared->hostHeartbeat &&
        static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000;
}
constexpr BYTE code0[]={0x48,0x89,0x5c,0x24,0x8,0x57,0x48,0x83,0xec,0x20,0x48,0x63,0xda,0x8b,0xf9,0xe8,0x3c,0x80,0xfa,0xff,0x84,0xc0,0x74,0x51,0x48,0x6b,0xdb,0x38,0xe8,0xaf,0x7f,0xfa,0xff,0xf6,0x84,0x18,0x40,0x1,0x0,0x0,0x1,0x74,0x3e,0xe8,0xa0,0x7f,0xfa,0xff,0x48,0x3,0xd8,0x8b,0x83,0x40,0x1,0x0,0x0,0xc1,0xe8,0x2,0xa8,0x1,0x75,0x11,0x48,0x8b,0x83,0x28,0x1,0x0,0x0,0x48,0x8d,0x8b,0x28,0x1,0x0,0x0,0xff,0x50,0x10,0x85,0xff,0x79,0x6,0x8b,0xbb,0x4c,0x1,0x0,0x0,0x8b,0xd7,0x48,0x8d,0x8b,0x28,0x1,0x0,0x0,0xe8,0xc7,0xeb,0xff,0xff,0x48,0x8b,0x5c,0x24,0x30,0x48,0x83,0xc4,0x20,0x5f,0xc3};
constexpr BYTE code1[]={0x48,0x8b,0x5,0x71,0xc5,0x66,0x2,0x48,0x85,0xc0,0x74,0xd,0x8b,0x40,0x4,0xc1,0xe8,0x2,0xa8,0x1,0x75,0x3,0xb0,0x1,0xc3,0x32,0xc0,0xc3};
constexpr BYTE code2[]={0x48,0x8b,0x5,0xf1,0xc5,0x66,0x2,0xc3};
constexpr BYTE code3[]={0x48,0x83,0xec,0x28,0x85,0xd2,0x7e,0x1a,0x8b,0xca,0xe8,0x61,0xcb,0xd5,0xff,0xe8,0xac,0xcb,0xd5,0xff,0xb9,0x2,0x0,0x0,0x0,0x48,0x83,0xc4,0x28,0xe9,0x1e,0xcb,0xd5,0xff,0x8b,0x49,0x24,0xe8,0x76,0xcb,0xd5,0xff,0xe8,0x91,0xcb,0xd5,0xff,0xb9,0x2,0x0,0x0,0x0,0x48,0x83,0xc4,0x28,0xe9,0x3,0xcb,0xd5,0xff};
constexpr BYTE code4[]={0x6b,0xc1,0x3c,0xc6,0x5,0x1e,0x47,0x96,0x0,0x1,0xc7,0x5,0x10,0x47,0x96,0x0,0x0,0x0,0x0,0x0,0x89,0x5,0x6,0x47,0x96,0x0,0x89,0x5,0xfc,0x46,0x96,0x0,0xc3};
constexpr BYTE code5[]={0x33,0xc0,0xc6,0x5,0xef,0x46,0x96,0x0,0x0,0x89,0x5,0xe5,0x46,0x96,0x0,0x89,0x5,0xdb,0x46,0x96,0x0,0x6b,0xc1,0x3c,0x89,0x5,0xce,0x46,0x96,0x0,0xc3};
constexpr BYTE code6[]={0x8b,0x5,0xba,0x46,0x96,0x0,0x89,0x5,0xbc,0x46,0x96,0x0,0xc7,0x5,0xbe,0x46,0x96,0x0,0x1,0x0,0x0,0x0,0xc3};
constexpr BYTE code7[]={0x8b,0x5,0x3e,0x47,0x96,0x0,0xf7,0xd1,0x23,0xc1,0x89,0x5,0x34,0x47,0x96,0x0,0xc3};
struct Code { uintptr_t rva; const BYTE* bytes; SIZE_T length; };
const Code code[]={{0x3fb9a0,code0,sizeof(code0)},{0x3a39f0,code1,sizeof(code1)},{0x3a3970,code2,sizeof(code2)},{0x3fa5d0,code3,sizeof(code3)},{0x157140,code4,sizeof(code4)},{0x157170,code5,sizeof(code5)},{0x157190,code6,sizeof(code6)},{0x157110,code7,sizeof(code7)}};

bool CodeReady() {
    for(const auto& entry:code)
        if(!Range(g_base+entry.rva,entry.length) ||
            memcmp(reinterpret_cast<const void*>(g_base+entry.rva),entry.bytes,entry.length)) return false;
    return true;
}
struct View {
    uintptr_t mission=0,descriptor=0,bar=0,heap=0,fieldScheduler=0,outerScheduler=0;
    unsigned id=0,flags=0; int phase=0,count=0; BYTE room[10]{};
    uintptr_t objects[9]{};
};
bool KnownObject(uintptr_t mission,uintptr_t object) {
    if(object==mission+296 || object==mission+808 || object==mission+880) return true;
    for(unsigned i=0;i<3;++i)
        if(object==mission+352+80*i || object==mission+592+72*i) return true;
    return false;
}
bool ReadView(const TrainerContext& c,View& v) {
    if(!Allowed() || c.base!=g_base || !c.sceneReady || At<BYTE>(0x9BA8D0)!=1 ||
        At<BYTE>(0x9BA8D1) || At<uintptr_t>(0x9BA928) ||
        (At<int>(0x716884)!=1 && At<int>(0x716884)!=2)) return false;
    v.mission=At<uintptr_t>(kMission);
    if(v.mission!=g_base+kStorage || !Range(v.mission,1708)) return false;
    v.descriptor=Field<uintptr_t>(v.mission,8); v.bar=Field<uintptr_t>(v.mission,96);
    v.heap=At<uintptr_t>(0x9BA920); v.fieldScheduler=At<uintptr_t>(0x716868); v.outerScheduler=At<uintptr_t>(0x9BA888);
    if(v.descriptor!=At<uintptr_t>(kDescriptor) || !Range(v.descriptor,28) || !Range(v.bar,16) ||
        !Range(v.heap,8) || !Range(v.fieldScheduler,72) || !Range(v.outerScheduler,72)) return false;
    v.id=Field<unsigned>(v.mission,0); v.flags=Field<unsigned>(v.mission,4);
    v.phase=Field<int>(v.mission,1072); v.count=Field<int>(v.mission,1048);
    if(v.phase<0 || v.phase>4 || v.count<0 || v.count>9) return false;
    memcpy(v.room,reinterpret_cast<const void*>(g_base+0x717008),sizeof(v.room));
    for(int i=0;i<v.count;++i) {
        v.objects[i]=Field<uintptr_t>(v.mission,976+8*i);
        if(!KnownObject(v.mission,v.objects[i])) return false;
        for(int j=0;j<i;++j) if(v.objects[j]==v.objects[i]) return false;
    }
    return true;
}
bool SameView(const View& a,const View& b) {
    if(a.mission!=b.mission || a.descriptor!=b.descriptor || a.bar!=b.bar || a.id!=b.id ||
        a.flags!=b.flags || a.phase!=b.phase || a.count!=b.count || a.heap!=b.heap ||
        a.fieldScheduler!=b.fieldScheduler || a.outerScheduler!=b.outerScheduler ||
        memcmp(a.room,b.room,sizeof(a.room))) return false;
    return !memcmp(a.objects,b.objects,sizeof(a.objects));
}
bool Object(const View& v,uintptr_t offset,uintptr_t vtable,int index) {
    const uintptr_t object=v.mission+offset; bool registered=false;
    for(int i=0;i<v.count;++i) registered|=v.objects[i]==object;
    // Constructor alone sets flags1 on unused objects. Registry membership and
    // matching ID are needed before interpreting retained inline value fields.
    return registered && Field<uintptr_t>(object,0)==g_base+vtable &&
        Field<int>(object,28)==index && (Field<unsigned>(object,24)&1)!=0;
}
bool Timer(const View& v) {
    return Object(v,296,0x5C4208,0) && (Field<unsigned>(v.mission,320)&4) &&
        At<BYTE>(kMode)<=1 && At<int>(kPhase)>=0 && At<int>(kPhase)<=2 &&
        At<int>(kLimit)>=0 && At<int>(kValue)>=0;
}
bool LivingPlayer(const TrainerContext& c) {
    if(!c.player || !c.status || At<uintptr_t>(0x2A105D0)!=c.player ||
        !Range(c.player,3608) || !Range(c.status,632) ||
        Field<uintptr_t>(c.player,1472)!=c.status || DecodePacked(Field<uint32_t>(c.status,616))!=c.player) return false;
    const int hp=Field<int>(c.status,0),max=Field<int>(c.status,4),character=Field<int>(c.status,608);
    return hp>0 && hp<=max && max<=255 && character>=1 && character<=15 &&
        (Field<unsigned>(c.player,1736)&0x80) && !(Field<unsigned>(c.player,288)&0x10080100) &&
        !(Field<unsigned>(c.player,2488)&4);
}
bool MayRestart(const TrainerContext& c,const View& v,bool countUp) {
    if(!Allowed() || !LivingPlayer(c) || v.phase!=1 || !(v.flags&1) || (v.flags&0x14) ||
        At<int>(0x716884)!=1 || At<BYTE>(0x9006B0) || At<uintptr_t>(0xAC0F48) ||
        At<BYTE>(0xABAC58) || At<BYTE>(0xABAC59) || At<BYTE>(0xABADE0) ||
        At<uintptr_t>(0x2A11478) || At<uintptr_t>(0x2AE8050) ||
        At<uintptr_t>(0x2AE9FA8) || (At<unsigned>(0x2A10504)&2) ||
        !Timer(v) || (Field<unsigned>(v.mission,320)&0x10) ||
        At<int>(kPhase)==0 || At<unsigned>(kPause) ||
        !Writable(reinterpret_cast<void*>(g_base+kPause),21)) return false;
    const int limit=Field<int>(v.mission,332);
    // Preserve the mission's configured count-up limit. Native multiplication
    // is signed32-bit; larger limits are unsafe, while zero means no limit.
    return !countUp || (limit>=0 && limit<=35791394);
}
void NativeRestart(int seconds) {
#ifdef KH2_MISSION_TESTS
    if(testRestart) testRestart(seconds,0);
#else
    reinterpret_cast<RestartFn>(g_base+0x3FB9A0)(seconds,0);
#endif
}
}
bool MissionHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace mission_features;
    if(slot<208 || slot>229) return false;
    if(slot!=226 && slot!=227) { result={1,L"This mission value is read-only."}; return true; }
    for(unsigned i=0;i<8;++i)
        if(!isfinite(args[i])) { result={1,L"Mission timer arguments must be finite."}; return true; }
    const bool countUp=slot==227;
    if(!countUp && !IsInteger(args[0],1,3599)) {
        result={1,L"Choose a whole countdown from 1 to 3599 seconds."}; return true;
    }
    View before{},fresh{};
    if(!ReadView(c,before) || !MayRestart(c,before,countUp)) {
        result={1,L"Restart needs an active mission timer, living player and stable unpaused gameplay with unchanged native code."}; return true;
    }
    const int initial=Field<int>(before.mission,328),maximum=Field<int>(before.mission,332);
    const unsigned timerFlags=Field<unsigned>(before.mission,320);
    const uint32_t origin=At<uint32_t>(kOrigin); const int phase=At<int>(kPhase),mode=At<BYTE>(kMode),limit=At<int>(kLimit);
    if(!CodeReady()) { result={1,L"Native mission timer code differs from the supported build."}; return true; }
    // Re-read after code validation. Never retain a request for a later mission
    // or silently use the same static storage after its descriptor changes.
    if(!ReadView(c,fresh) || !SameView(before,fresh) || !MayRestart(c,fresh,countUp) ||
        Field<int>(fresh.mission,328)!=initial || Field<int>(fresh.mission,332)!=maximum ||
        Field<unsigned>(fresh.mission,320)!=timerFlags || At<uint32_t>(kOrigin)!=origin ||
        At<int>(kPhase)!=phase || At<BYTE>(kMode)!=mode || At<int>(kLimit)!=limit) {
        result={1,L"Mission or timer state changed before the restart. Try again in stable gameplay."}; return true;
    }
    const int seconds=countUp?0:static_cast<int>(args[0]);
    NativeRestart(seconds);
    // Native AL is unspecified. Verify the synchronous state instead; never
    // retry automatically after a native call whose outcome is uncertain.
    const int expectedLimit=60*(countUp?maximum:seconds);
    View after{};
    if(!ReadView(c,after) || !SameView(fresh,after) || At<BYTE>(kMode)!=(countUp?0:1) ||
        At<int>(kPhase)!=1 || At<int>(kLimit)!=expectedLimit || At<int>(kValue)!=(countUp?0:expectedLimit)) {
        result={2,L"Native timer restart was called, but its resulting state could not be confirmed. No automatic retry."}; return true;
    }
    result={0,countUp?L"Native count-up restarted at zero with its configured limit. Mission timeout events still apply.":
        L"Native countdown restarted. Mission timeout events still apply."};
    return true;
}
void MissionCapabilities() { for(unsigned i=208;i<=229;++i) SupportCapability(i); }
void MissionSnapshot(const TrainerContext& c) {
    using namespace mission_features;
    View v{}; if(!ReadView(c,v)) return;
    SnapshotValue(208,v.id); SnapshotValue(209,v.phase);
    if(Timer(v)) {
        SnapshotValue(210,At<int>(kValue)/60.0); SnapshotValue(211,At<BYTE>(kMode));
        SnapshotValue(212,At<int>(kPhase)); SnapshotValue(228,At<int>(kLimit)/60.0);
        SnapshotValue(229,At<unsigned>(kPause)?1:0);
    }
    for(unsigned i=0;i<3;++i) {
        uintptr_t p=v.mission+352+80*i;
        if(Object(v,352+80*i,0x5C4248,static_cast<int>(i))) {
            const int value=Field<int>(p,56),maximum=Field<int>(p,36);
            if(value>=0 && maximum>=value) { SnapshotValue(213+2*i,value); SnapshotValue(214+2*i,maximum); }
        }
        p=v.mission+592+72*i;
        if(Object(v,592+72*i,0x5C4288,static_cast<int>(i))) {
            const float value=Field<float>(p,56); const int maximum=Field<int>(p,36);
            if(isfinite(value) && value>=0 && maximum>=0 && static_cast<double>(value)<=maximum) {
                SnapshotValue(219+2*i,value); SnapshotValue(220+2*i,maximum);
            }
        }
    }
    const uintptr_t score=v.mission+1088;
    if(Field<uintptr_t>(score,0)==g_base+0x5C9E38 && (Field<unsigned>(score,24)&5)==5 &&
        Field<int>(score,36)==9999 && Field<int>(score,56)>=0 && Field<int>(score,56)<=9999)
        SnapshotValue(225,Field<int>(score,56));
}
void MissionTick(const TrainerContext&) {}
void MissionReset(const TrainerContext&) {}
