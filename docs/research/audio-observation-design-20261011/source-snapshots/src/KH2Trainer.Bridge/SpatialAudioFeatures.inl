// Read-only listener diagnostics. Include after AudioFeatures.inl. The supported
// caller is the validated application post-Update hook, never an audio worker or
// teardown callback. Both native audio locks remain held while copying fields.
namespace spatial_audio {
constexpr uintptr_t ManagerRva=0x2B81DF8, LayoutRva=0x2B81DE8;
constexpr uintptr_t ManagerVtable=0x61A3E0, LayoutVtable=0x619DE8;
constexpr uintptr_t BaseVtable=0x61A780, PointVtable=0x61A8D8, LineVtable=0x61A998;
constexpr SIZE_T ManagerSize=992, LayoutSize=1440, LockOffset=776;
constexpr int MaxListeners=1024;

template<class T> T Field(uintptr_t p,SIZE_T offset=0) {
    return *reinterpret_cast<const T*>(p+offset);
}
bool Range(uintptr_t p,SIZE_T size) {
    return p && size && p<=UINTPTR_MAX-size && Readable(reinterpret_cast<const void*>(p),size);
}
struct Roots {
    uintptr_t manager=0,layout=0,list=0;
    int count=0,capacity=0,peak=0;
};
struct Member {
    uintptr_t pointer=0;
    uint32_t id=0,priority=0;
    BYTE kind=0;
    bool enabled=false;
};
struct Sample {
    bool ready=false,active=false;
    unsigned count=0,capacity=0,peak=0,enabled=0;
    uint32_t id=0,priority=0;
    BYTE kind=0;
    float position[3]{};
};

bool RootObjects(Roots& roots) {
    roots.manager=At<uintptr_t>(ManagerRva);
    roots.layout=At<uintptr_t>(LayoutRva);
    if(!Range(roots.manager,ManagerSize) || !Range(roots.layout,LayoutSize)) return false;
    return Field<uintptr_t>(roots.manager)==g_base+ManagerVtable &&
        Field<uintptr_t>(roots.layout)==g_base+LayoutVtable &&
        Field<BYTE>(roots.manager,816)==1 &&
        Field<uintptr_t>(roots.manager,8)==roots.layout &&
        Field<uintptr_t>(roots.layout,8)==roots.manager;
}
bool SameRoots(const Roots& roots,const audio_mix::Graph& audio) {
    Roots current{};
    return audio_mix::SameGraph(audio) && RootObjects(current) &&
        current.manager==roots.manager && current.layout==roots.layout && audio.backend==roots.layout;
}
bool ListHeader(Roots& roots) {
    roots.count=Field<int>(roots.manager,24);
    roots.peak=Field<int>(roots.manager,28);
    roots.capacity=Field<int>(roots.manager,32);
    roots.list=Field<uintptr_t>(roots.manager,768);
    return roots.capacity>=1 && roots.capacity<=MaxListeners && roots.count>=0 &&
        roots.count<=roots.capacity && roots.peak>=roots.count && roots.peak<=roots.capacity &&
        Range(roots.list,static_cast<SIZE_T>(roots.capacity)*sizeof(uintptr_t));
}
bool ReadMember(uintptr_t pointer,uintptr_t manager,Member& member) {
    if(!Range(pointer,136)) return false;
    const uintptr_t vtable=Field<uintptr_t>(pointer);
    const BYTE kind=Field<BYTE>(pointer,8);
    if(!((vtable==g_base+BaseVtable && kind==1) ||
         (vtable==g_base+PointVtable && kind==2) ||
         (vtable==g_base+LineVtable && kind==3 && Range(pointer,184)))) return false;
    const uint32_t id=Field<uint32_t>(pointer,12);
    if(!id || Field<uintptr_t>(pointer,16)!=manager) return false;
    member={pointer,id,Field<uint32_t>(pointer,120),kind,(Field<BYTE>(pointer,132)&1)!=0};
    return true;
}
bool FiniteCache(uintptr_t manager,float position[3]) {
    // Position (including w), native matrix and its cached transformed matrix.
    // These are copied fields, not calls to getters or matrix reconstruction.
    for(SIZE_T offset=132;offset<148;offset+=sizeof(float))
        if(!isfinite(Field<float>(manager,offset))) return false;
    for(SIZE_T offset=164;offset<292;offset+=sizeof(float))
        if(!isfinite(Field<float>(manager,offset))) return false;
    for(unsigned i=0;i<3;++i) position[i]=Field<float>(manager,132+i*sizeof(float));
    return true;
}
bool CopyLocked(const Roots& roots,Sample& sample) {
    Member members[MaxListeners]{};
    int winner=-1;
    unsigned enabled=0;
    for(int i=0;i<roots.count;++i) {
        const uintptr_t pointer=Field<uintptr_t>(roots.list,static_cast<SIZE_T>(i)*sizeof(uintptr_t));
        if(!ReadMember(pointer,roots.manager,members[i])) return false;
        for(int previous=0;previous<i;++previous)
            if(members[previous].pointer==pointer || members[previous].id==members[i].id) return false;
        if(members[i].enabled) {
            ++enabled;
            // Native JA skips only a strictly smaller unsigned priority.
            if(winner<0 || members[i].priority>=members[winner].priority) winner=i;
        }
    }
    sample.count=static_cast<unsigned>(roots.count);
    sample.capacity=static_cast<unsigned>(roots.capacity);
    sample.peak=static_cast<unsigned>(roots.peak);
    sample.enabled=enabled;
    // selected may retain a freed member after Delete-ID/Delete-All. Only compare
    // pointer values; read identity/priority from the already validated copy.
    const uintptr_t selected=Field<uintptr_t>(roots.manager,120);
    if(winner>=0 && selected==members[winner].pointer && FiniteCache(roots.manager,sample.position)) {
        sample.id=members[winner].id;
        sample.kind=members[winner].kind;
        sample.priority=members[winner].priority;
        sample.active=true;
    }
    return true;
}
bool Capture(const TrainerContext& context,Sample& sample) {
    sample={};
    if(!audio_mix::ThreadReady(context)) return false;
    auto outer=reinterpret_cast<CRITICAL_SECTION*>(g_base+audio_mix::LockRva);
    if(!Writable(outer,sizeof(CRITICAL_SECTION))) return false;
    if(!TryEnterCriticalSection(outer)) return false;
    CRITICAL_SECTION* inner=nullptr;
    bool innerAcquired=false;
    __try {
        audio_mix::Graph audio{};
        Roots roots{};
        if(!audio_mix::GraphReady(audio) || !RootObjects(roots) || audio.backend!=roots.layout) return false;
        inner=reinterpret_cast<CRITICAL_SECTION*>(roots.manager+LockOffset);
        // Byte816 can remain1 after DeleteCriticalSection. ThreadReady and the
        // application's observed init/update/shutdown ordering are indispensable.
        if(!Writable(inner,sizeof(CRITICAL_SECTION)) || !TryEnterCriticalSection(inner)) return false;
        innerAcquired=true;
        if(!audio_mix::ThreadReady(context) || !SameRoots(roots,audio) || !ListHeader(roots)) return false;
        Sample copied{};
        if(!CopyLocked(roots,copied) || !SameRoots(roots,audio) ||
            Field<uintptr_t>(roots.manager,768)!=roots.list ||
            Field<int>(roots.manager,24)!=roots.count || Field<int>(roots.manager,28)!=roots.peak ||
            Field<int>(roots.manager,32)!=roots.capacity || !audio_mix::ThreadReady(context)) return false;
        copied.ready=true;
        sample=copied;
        return true;
    } __finally {
        // Release captured addresses, including on early returns or SEH. No
        // subsequent global-root or initialized-byte check can skip this pairing.
        __try { if(innerAcquired) LeaveCriticalSection(inner); }
        __finally { LeaveCriticalSection(outer); }
    }
}
}
void SpatialAudioCapabilities() {
    for(unsigned slot=408;slot<=418;++slot) SupportCapability(slot);
}
void SpatialAudioSnapshot(const TrainerContext& context) {
    SnapshotValue(408,0);
    spatial_audio::Sample sample{};
    if(!spatial_audio::Capture(context,sample)) return;
    SnapshotValue(408,1);
    SnapshotValue(409,sample.count);
    SnapshotValue(410,sample.capacity);
    SnapshotValue(411,sample.peak);
    SnapshotValue(412,sample.enabled);
    if(!sample.active) return;
    SnapshotValue(413,sample.id);
    SnapshotValue(414,sample.kind);
    SnapshotValue(415,sample.priority);
    for(unsigned i=0;i<3;++i) SnapshotValue(416+i,sample.position[i]);
}
