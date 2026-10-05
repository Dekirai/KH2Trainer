// Native ENEMY_SHOT pool operations. Include after GummiFeatures.inl.
// No cached engine pointer, update hook, persistent effect or inverse operation.
namespace gummi_projectile {
constexpr uintptr_t PoolRva=0xAF8288, SpriteRva=0xAF8278, VtableRva=0x5B5B70;
constexpr uintptr_t ClearRva=0x21E830, CleanupRva=0x21F1F0;
constexpr unsigned Count=768, Stride=176, SpriteStride=16;
constexpr size_t PoolBytes=size_t(Count)*Stride, SpriteBytes=size_t(Count)*SpriteStride;
constexpr BYTE code0[] = { 0x48,0x89,0x5c,0x24,0x08,0x57,0x48,0x83,0xec,0x20,0x33,0xdb,0xbf,0x00,0x03,0x00,0x00,0x48,0x8b,0x0d,0x40,0x9a,0x8d,0x00,0x48,0x03,0xcb,0xe8,0xd0,0xf7,0x01,0x00,0x84,0xc0,0x74,0x0f,0x48,0x8b,0x0d,0x2d,0x9a,0x8d,0x00,0x48,0x03,0xcb,0xe8,0x5d,0xf2,0x01,0x00,0x48,0x81,0xc3,0xb0,0x00,0x00,0x00,0x48,0x83,0xef,0x01,0x75,0xd1,0x48,0x8b,0x5c,0x24,0x30,0x48,0x83,0xc4,0x20,0x5f,0xc3 };
constexpr BYTE code1[] = { 0x8b,0x81,0x80,0x00,0x00,0x00,0xc1,0xe8,0x08,0x24,0x01,0xc3 };
constexpr BYTE code2[] = { 0x40,0x53,0x48,0x83,0xec,0x20,0x81,0xa1,0x80,0x00,0x00,0x00,0xff,0xfe,0xff,0xff,0x48,0x8b,0xd9,0x48,0x8b,0x01,0xff,0x50,0x30,0xf6,0x83,0x80,0x00,0x00,0x00,0x01,0x74,0x13,0x48,0x8b,0x03,0xba,0x01,0x00,0x00,0x00,0x48,0x8b,0xcb,0x48,0x83,0xc4,0x20,0x5b,0x48,0xff,0x20,0x48,0x83,0xc4,0x20,0x5b,0xc3 };
constexpr BYTE code3[] = { 0x48,0x63,0x91,0x98,0x00,0x00,0x00,0x48,0x8b,0x05,0x7a,0x90,0x8d,0x00,0x48,0x03,0xd2,0xc7,0x44,0xd0,0x0c,0x00,0x00,0x00,0x00,0xc3 };
struct Signature { uintptr_t rva; const BYTE* bytes; size_t size; };
constexpr Signature signatures[] = {
    {0x21e830,code0,sizeof(code0)},
    {0x23e020,code1,sizeof(code1)},
    {0x23dac0,code2,sizeof(code2)},
    {0x21f1f0,code3,sizeof(code3)}
};
using ClearFn=void (__fastcall*)();
#ifdef KH2_GUMMI_PROJECTILE_TESTS
ClearFn testClear=nullptr;
#endif
template<class T> const T& Field(uintptr_t p,size_t offset) {
    return *reinterpret_cast<const T*>(p+offset);
}
bool Span(uintptr_t address,size_t length) {
    return address && length<=UINTPTR_MAX-address;
}
bool Overlap(uintptr_t a,size_t an,uintptr_t b,size_t bn) {
    // Call only after each span has passed the overflow check.
    return a<b+bn && b<a+an;
}
bool TaskOwned(uintptr_t manager,uintptr_t& task) {
    task=0;
    if (!Span(manager,72) || !Readable(reinterpret_cast<const void*>(manager),72) ||
        Field<uintptr_t>(manager,32)) return false;
    uintptr_t node=Field<uintptr_t>(manager,16), previous=0;
    int previousPriority=INT32_MIN;
    unsigned nodes=0,matches=0;
    while(node) {
        if (++nodes>2048 || !Span(node,152) || !Readable(reinterpret_cast<const void*>(node),152) ||
            Field<uintptr_t>(node,88)!=manager || Field<uintptr_t>(node,128)!=previous) return false;
        const int priority=Field<int>(node,100);
        if(priority<previousPriority) return false;
        previousPriority=priority;
        if(Field<uintptr_t>(node,0)==g_base+0x1F6080) {
            if(Field<unsigned>(node,96)!=1 || priority!=22000 ||
                Field<uintptr_t>(node,104)!=g_base+0x1F60D0 || Field<uintptr_t>(node,112)) return false;
            task=node; ++matches;
        }
        previous=node;node=Field<uintptr_t>(node,120);
    }
    return previous==Field<uintptr_t>(manager,24) && matches==1;
}
struct PoolView { uintptr_t pool=0,sprites=0,task=0; unsigned active=0; };
bool ReadPool(const gummi::Context& c,bool writing,PoolView& result) {
    result={};
    PoolView v{};
    if(!TaskOwned(c.scheduler,v.task) ||
        !gummi::Global(PoolRva,v.pool) || !gummi::Global(SpriteRva,v.sprites) ||
        v.pool<8 || (v.pool&7) || (v.sprites&3) || !Span(v.pool-8,PoolBytes+8) ||
        !Span(v.sprites,SpriteBytes) || Overlap(v.pool-8,PoolBytes+8,v.sprites,SpriteBytes) ||
        !Readable(reinterpret_cast<const void*>(v.pool-8),PoolBytes+8) ||
        !Readable(reinterpret_cast<const void*>(v.sprites),SpriteBytes) ||
        Field<uint64_t>(v.pool-8,0)!=Count) return false;
    if(writing && (!Writable(reinterpret_cast<void*>(v.pool),PoolBytes) ||
                   !Writable(reinterpret_cast<void*>(v.sprites),SpriteBytes))) return false;
    uintptr_t cleanup=0;
    if(!gummi::Global(VtableRva+48,cleanup) || cleanup!=g_base+CleanupRva) return false;
    for(unsigned i=0;i<Count;++i) {
        const uintptr_t record=v.pool+size_t(i)*Stride;
        const unsigned flags=Field<unsigned>(record,128);
        if(Field<uintptr_t>(record,0)!=g_base+VtableRva ||
            Field<int>(record,152)!=static_cast<int>(i) || (flags&1)) return false;
        if(flags&0x100) ++v.active;
    }
    result=v;
    return true;
}
bool CodeReady() {
    for(const auto& s:signatures)
        if(!gummi::CodeMatches(s.rva,s.bytes,s.size)) return false;
    return true;
}
bool SamePool(const PoolView& a,const PoolView& b) {
    return a.pool==b.pool && a.sprites==b.sprites && a.task==b.task;
}
void CallClear() {
#ifdef KH2_GUMMI_PROJECTILE_TESTS
    testClear();
#else
    reinterpret_cast<ClearFn>(g_base+ClearRva)();
#endif
}
} // namespace gummi_projectile

bool GummiProjectileHandle(const TrainerContext& host,unsigned slot,const double args[8],TrainerResult& result) {
    if(slot!=360) return false;
    result={1,L"Enter a running Gummi mission with a living ship and close the pause menu."};
    gummi::Context initial{},fresh{};
    gummi_projectile::PoolView before{},now{};
    if(host.base!=g_base || !gummi::HostAndThreadReady() ||
        !gummi::BuildContext(initial) || !gummi::ActionReady(initial)) return true;
    if(!args) { result={2,L"Command arguments are missing."}; return true; }
    for(unsigned i=0;i<8;++i)
        if(!isfinite(args[i])) { result={2,L"Command arguments must be finite."}; return true; }
    if(!gummi_projectile::ReadPool(initial,true,before) || !gummi_projectile::CodeReady()) {
        result={3,L"The native enemy-bullet pool, owner task or cleanup code is unavailable or changed."}; return true;
    }
    // Validate all borrowed state again immediately before dispatch. No retained
    // pool, record, task or player pointer is read after the native call.
    if(!gummi::BuildContext(fresh) || !gummi::SameLifetime(initial,fresh) || !gummi::ActionReady(fresh) ||
        !gummi_projectile::ReadPool(fresh,true,now) || !gummi_projectile::SamePool(before,now) ||
        !gummi_projectile::CodeReady() || !gummi::HostAndThreadReady()) {
        result={3,L"The Gummi mission or enemy-bullet pool changed during validation. Retry in the current mission."}; return true;
    }
    gummi_projectile::CallClear();
    result={0,L"Current enemy bullets cleared. Lasers and other projectile types remain; enemies can fire again."};
    return true;
}
void GummiProjectileSnapshot(const TrainerContext& host) {
    gummi::Context c{};
    gummi_projectile::PoolView v{};
    if(host.base==g_base && gummi::BuildContext(c) && gummi_projectile::ReadPool(c,false,v))
        SnapshotValue(361,v.active);
}
void GummiProjectileCapabilities() {
    SupportCapability(360); SupportCapability(361);
}
