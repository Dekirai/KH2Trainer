// One-time native audio mix changes. The normal MyApp loop serializes init,
// Update and shutdown; its post-Update is the only supported caller. Audio
// workers update bus envelopes under the process-lifetime global Sound CS.
// Evidence: work/trainer/research/audio_lifecycle.* and audio_mix_contract.*.
namespace audio_mix {
constexpr uintptr_t LockRva=0x2B81278, DriverRva=0x2B81DE0;
constexpr uintptr_t MasterRva=0x2B811D0, ListRva=0x2B811C8, CountRva=0x2B811A4;
constexpr uintptr_t DriverVtable=0x61B760, BusVtable=0x61D598;
constexpr uintptr_t MasterXaVtable=0x61DA28, MasterGenericVtable=0x621998, DynamicVtable=0x61ACF0;
constexpr BYTE ConstructCode[]={0x40,0x57,0x48,0x83,0xec,0x30,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff,0x48,0x89,0x5c,0x24,0x40,0x8b,0xfa,0x48,0x8b};
constexpr BYTE SetCode[]={0x40,0x57,0x48,0x83,0xec,0x40,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff,0x48,0x89,0x5c,0x24,0x58,0x0f,0x29,0x74,0x24};
constexpr BYTE DestroyCode[]={0x48,0x8d,0x05,0xe9,0xb4,0x59,0x00,0x48,0x89,0x01,0xc3};
constexpr BYTE FactoryCode[]={0x48,0x8d,0x05,0x29,0x76,0x58,0x00,0x44,0x89,0x42,0x08,0x48,0x89,0x02,0x48,0x8b,0x05,0x33,0xe7,0xae,0x02,0x48,0x89,0x42,0x10,0x48,0x8b,0xc2,0xc3};
constexpr BYTE BusSetCode[]={0x40,0x57,0x48,0x83,0xec,0x30,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff,0x48,0x89,0x5c,0x24,0x40,0x48,0x89,0x6c,0x24};
constexpr BYTE XaSetCode[]={0x40,0x53,0x48,0x83,0xec,0x30,0x0f,0x29,0x74,0x24,0x20,0x0f,0x28,0xf1,0x48,0x8b,0xd9,0x45,0x85,0xc0,0x74,0x47,0xf3,0x0f};
constexpr BYTE GenericSetCode[]={0x40,0x53,0x48,0x83,0xec,0x20,0xf3,0x0f,0x11,0x49,0x24,0x48,0x8b,0xd9,0x45,0x85,0xc0,0x74,0x3d,0xf3,0x0f,0x10,0x51,0x20};
struct Controller { uintptr_t vtable; int id; unsigned padding; uintptr_t backend; };
static_assert(sizeof(Controller)==24);
using ConstructFn=Controller* (__fastcall*)(Controller*,unsigned);
using SetFn=void (__fastcall*)(Controller*,float,unsigned);
using DestroyFn=void (__fastcall*)(Controller*);
#ifdef KH2_AUDIO_TESTS
ConstructFn testConstruct=nullptr; SetFn testSet=nullptr; DestroyFn testDestroy=nullptr;
#endif
template<class T> T Field(uintptr_t p,SIZE_T offset=0) { return *reinterpret_cast<const T*>(p+offset); }
bool Range(uintptr_t p,SIZE_T size) { return p && Readable(reinterpret_cast<const void*>(p),size); }
template<SIZE_T N> bool Code(uintptr_t rva,const BYTE (&bytes)[N]) {
    return Range(g_base+rva,N) && !memcmp(reinterpret_cast<const void*>(g_base+rva),bytes,N);
}
bool ThreadReady(const TrainerContext& c) {
    return g_base && c.base==g_base && !g_disabled && g_shared && g_gameThread && g_gameThread==GetCurrentThreadId() &&
        g_shared->hostHeartbeat && static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000 &&
        Range(g_base+LockRva,sizeof(CRITICAL_SECTION));
}
bool FunctionsReady() {
    return Code(0x079C90,ConstructCode) && Code(0x07FAD0,SetCode) && Code(0x07F7E0,DestroyCode) && Code(0x0936A0,FactoryCode);
}
struct Graph { uintptr_t driver=0,master=0,list=0,backend=0; int count=0; unsigned effects=0,voice=0; float voiceFactor=1; };
bool GraphReady(Graph& g) {
    g.driver=At<uintptr_t>(DriverRva); g.master=At<uintptr_t>(MasterRva); g.list=At<uintptr_t>(ListRva);
    g.backend=At<uintptr_t>(0x2B81DE8); g.count=At<int>(CountRva);
    if(!Range(g.driver,56) || Field<uintptr_t>(g.driver)!=g_base+DriverVtable || !Field<BYTE>(g.driver,52) ||
        Field<uintptr_t>(g_base+DriverVtable,152)!=g_base+0x0936A0 ||
        g.count<1 || g.count>1024 || !Range(g.list,static_cast<SIZE_T>(g.count)*sizeof(uintptr_t)) || !Range(g.master,352)) return false;
    const uintptr_t vt=Field<uintptr_t>(g.master);
    if((vt!=g_base+MasterXaVtable && vt!=g_base+MasterGenericVtable) ||
        Field<uintptr_t>(g.master,336)!=g.list || Field<int>(g.master,344)!=g.count) return false;
    const unsigned swapped=At<unsigned>(0x8BBD14), softened=At<unsigned>(0x8BBD18);
    if(swapped>1 || softened>1) return false;
    g.effects=swapped?3:2; g.voice=swapped?2:3;
    if(!swapped && softened) {
        g.voiceFactor=At<float>(0x5AAA40);
        if(!isfinite(g.voiceFactor) || g.voiceFactor<=0 || g.voiceFactor>1) return false;
    }
    return true;
}
bool SameGraph(const Graph& g) {
    return At<uintptr_t>(DriverRva)==g.driver && At<uintptr_t>(MasterRva)==g.master &&
        At<uintptr_t>(ListRva)==g.list && At<int>(CountRva)==g.count && At<uintptr_t>(0x2B81DE8)==g.backend;
}
bool BusReady(const Graph& g,unsigned id,uintptr_t& bus) {
    if(id>static_cast<unsigned>(g.count)) return false;
    bus=id?Field<uintptr_t>(g.list,id*sizeof(uintptr_t)-sizeof(uintptr_t)):g.master;
    if(!Range(bus,id?336:352) || !Writable(reinterpret_cast<void*>(bus+32),32) ||
        Field<int>(bus,8)!=static_cast<int>(id) || Field<uintptr_t>(bus,24)!=g_base+DynamicVtable) return false;
    const uintptr_t vt=Field<uintptr_t>(bus);
    if(id) {
        if(vt!=g_base+BusVtable || Field<uintptr_t>(vt,24)!=g_base+0x0A54D0 || !Code(0x0A54D0,BusSetCode)) return false;
    } else if(vt==g_base+MasterXaVtable) {
        if(Field<uintptr_t>(vt,24)!=g_base+0x0A8830 || !Code(0x0A8830,XaSetCode)) return false;
    } else if(vt==g_base+MasterGenericVtable) {
        if(Field<uintptr_t>(vt,24)!=g_base+0x0C4B80 || !Code(0x0C4B80,GenericSetCode)) return false;
    } else return false;
    for(unsigned offset : {32u,36u,40u,52u,56u}) {
        const float value=Field<float>(bus,offset);
        if(!isfinite(value) || fabsf(value)>1000000.0f) return false;
    }
    return Field<float>(bus,32)>=0 && Field<float>(bus,36)>=0 && Field<int>(bus,44)>=0 &&
        Field<int>(bus,44)<=0x0fffffff && Field<int>(bus,48)>=0 && Field<int>(bus,48)<=0x0fffffff && Field<BYTE>(bus,61)<=15;
}
Controller* Construct(Controller* c,unsigned id) {
#ifdef KH2_AUDIO_TESTS
    return testConstruct(c,id);
#else
    return reinterpret_cast<ConstructFn>(g_base+0x079C90)(c,id);
#endif
}
void Set(Controller* c,float gain) {
#ifdef KH2_AUDIO_TESTS
    testSet(c,gain,1);
#else
    reinterpret_cast<SetFn>(g_base+0x07FAD0)(c,gain,1);
#endif
}
void Destroy(Controller* c) {
#ifdef KH2_AUDIO_TESTS
    testDestroy(c);
#else
    reinterpret_cast<DestroyFn>(g_base+0x07F7E0)(c);
#endif
}
struct Plan { unsigned ids[9]{}; float gains[9]{}; unsigned count=0; };
void Append(Plan& p,unsigned id,float gain) { p.ids[p.count]=id; p.gains[p.count++]=gain; }
bool MakePlan(const Graph& g,unsigned slot,float gain,Plan& p) {
    if(slot==144 || slot==145) Append(p,slot-144,gain);
    else if(slot==146) { Append(p,g.effects,gain); for(unsigned id=4;id<=8;++id) Append(p,id,gain); }
    else if(slot==147) Append(p,g.voice,gain*g.voiceFactor);
    else {
        // Settings_GetFields returns715364; offsets20/22/24/26 are the four
        // native mixer levels. Read only; this action never saves config files.
        if(memcmp(reinterpret_cast<void*>(g_base+0x715350),"SET-",4) || At<unsigned>(0x715354)!=8 || At<unsigned>(0x715358)!=508) return false;
        float levels[4]{};
        for(unsigned i=0;i<4;++i) {
            const unsigned level=At<uint16_t>(0x715364+20+2*i);
            if(level<1 || level>10) return false;
            levels[i]=At<float>(0x5AB960+4*level);
            if(!isfinite(levels[i]) || levels[i]<0 || levels[i]>1) return false;
        }
        Append(p,0,levels[0]); Append(p,1,levels[1]); Append(p,g.effects,levels[2]);
        for(unsigned id=4;id<=8;++id) Append(p,id,levels[2]);
        Append(p,g.voice,levels[3]*g.voiceFactor);
    }
    return true;
}
bool ApplyPlan(const Graph& g,const Plan& p) {
    uintptr_t buses[9]{}; Controller controls[9]{}; unsigned constructed=0;
    bool success=false;
    // Complete structural preflight before issuing any native gain write.
    for(unsigned i=0;i<p.count;++i) if(!BusReady(g,p.ids[i],buses[i])) return false;
    __try {
        bool ready=true;
        for(unsigned i=0;i<p.count;++i) {
            Controller* result=Construct(&controls[i],p.ids[i]); ++constructed;
            if(result!=&controls[i] || controls[i].vtable!=g_base+0x61ACD0 || controls[i].id!=static_cast<int>(p.ids[i]) ||
                controls[i].backend!=g.backend) { ready=false; break; }
        }
        if(ready && SameGraph(g)) {
            success=true;
            for(unsigned i=0;i<p.count;++i) {
                Set(&controls[i],p.gains[i]);
                if(Field<float>(buses[i],36)!=p.gains[i]) { success=false; break; }
            }
        }
    } __finally {
        for(unsigned i=0;i<constructed;++i) Destroy(&controls[i]);
    }
    return success;
}
}
bool AudioHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace audio_mix;
    if(slot<144 || slot>148) return false;
    if(!ThreadReady(c) || !FunctionsReady()) { result={1,L"Audio control needs the supported engine update and a connected trainer."}; return true; }
    if(slot!=148 && (!isfinite(args[0]) || args[0]<0 || args[0]>100)) { result={1,L"Choose an audio level from 0 to 100 percent."}; return true; }
    auto cs=reinterpret_cast<CRITICAL_SECTION*>(g_base+LockRva);
    if(!TryEnterCriticalSection(cs)) { result={1,L"Audio is busy. Try the action again."}; return true; }
    __try {
        Graph graph{}; Plan plan{};
        if(!GraphReady(graph) || !MakePlan(graph,slot,static_cast<float>(args[0]/100.0),plan))
            result={1,L"The audio mixer or loaded audio settings are not ready."};
        else if(!ApplyPlan(graph,plan))
            result={2,L"The audio change could not be fully applied. Check the live values before retrying."};
        else result={0,slot==148?L"Loaded game audio levels applied to the mixer.":L"Audio level applied. The game's later settings or fades may change it again."};
    } __finally { LeaveCriticalSection(cs); }
    return true;
}
void AudioCapabilities() { for(unsigned slot=144;slot<=159;++slot) SupportCapability(slot); }
void AudioSnapshot(const TrainerContext& c) {
    using namespace audio_mix;
    SnapshotValue(159,0);
    if(!ThreadReady(c) || !FunctionsReady()) return;
    auto cs=reinterpret_cast<CRITICAL_SECTION*>(g_base+LockRva);
    if(!TryEnterCriticalSection(cs)) return;
    __try {
        Graph graph{};
        if(GraphReady(graph)) {
            float targets[9]{}; bool valid[9]{};
            SnapshotValue(149,graph.count); SnapshotValue(159,1);
            for(unsigned id=0;id<=8;++id) {
                uintptr_t bus=0;
                if(BusReady(graph,id,bus)) {
                    targets[id]=Field<float>(bus,36); valid[id]=true;
                    SnapshotValue(150+id,static_cast<double>(Field<float>(bus,32))*100);
                }
            }
            if(valid[0]) SnapshotValue(144,static_cast<double>(targets[0])*100);
            if(valid[1]) SnapshotValue(145,static_cast<double>(targets[1])*100);
            if(valid[graph.voice]) SnapshotValue(147,static_cast<double>(targets[graph.voice]/graph.voiceFactor)*100);
            bool equal=valid[graph.effects];
            for(unsigned id=4;id<=8;++id) equal=equal && valid[id] && targets[id]==targets[graph.effects];
            if(equal) SnapshotValue(146,static_cast<double>(targets[graph.effects])*100);
        }
    } __finally { LeaveCriticalSection(cs); }
}
