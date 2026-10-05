// Read-only renderer diagnostics. Include after DisplayFeatures.inl.
// Evidence: research archive (see README): renderer_round5_contract.json and full ASM.
// No renderer, COM, fence or singleton-construction calls are made here.
namespace renderer_diagnostics {
constexpr unsigned First=392, Last=407;
constexpr SIZE_T HistoryOffset=31392, PoolBytes=4712, MaximumNodes=300;
constexpr uintptr_t FrequencyRva=0x79D088;
constexpr uintptr_t PoolRvas[]={0x89D090,0x89E300,0x89F570};
constexpr uintptr_t PoolVtables[]={0x5A8B70,0x5A8B88,0x5A8BA0};
bool faulted=false;
using display_preview::Field;
using display_preview::Range;
struct Values { double value[16]{}; uint16_t valid=0; };
struct Record { int64_t begin=0,end=0; bool valid=false; };
struct ListSpec { SIZE_T offset; unsigned capacity,nodeBytes,beginOffset,endOffset; };
constexpr ListSpec Lists[]={
    {896,300,40,16,24}, // completed GPU command span, already calibrated to QPC
    {944,30,48,16,24},  // CPU time inside Present1
    {912,200,40,16,24}, // native CPU fence wait
    {880,30,56,32,40}  // recorded render interval, not exclusive CPU execution
};
void Put(Values& values,unsigned slot,double value) {
    values.value[slot-First]=value;
    values.valid|=static_cast<uint16_t>(1u<<(slot-First));
}
bool Roots(uintptr_t object) {
    if(!Range(object,HistoryOffset+sizeof(CRITICAL_SECTION)) ||
       !Writable(reinterpret_cast<void*>(object+HistoryOffset),sizeof(CRITICAL_SECTION)) ||
       Field<uintptr_t>(object,1344)!=g_base+0x5A8DA8) return false;
    for(unsigned i=0;i<3;++i) {
        const uintptr_t pool=g_base+PoolRvas[i];
        if(Field<uintptr_t>(object,1608+8*i)!=pool || !Range(pool,PoolBytes) ||
           Field<uintptr_t>(pool)!=g_base+PoolVtables[i]) return false;
    }
    return true;
}
void Scalars(uintptr_t object,Values& values) {
    for(unsigned i=0;i<2;++i) {
        const uint32_t samples=Field<uint32_t>(object,i?1108:1504);
        if(samples==1 || samples==2 || samples==4 || samples==8)Put(values,396+i,samples);
    }
    constexpr SIZE_T dimensions[]={1352,1356,8,12};
    for(unsigned i=0;i<4;++i) {
        const int32_t size=Field<int32_t>(object,dimensions[i]);
        if(size>=1 && size<=16384)Put(values,398+i,size);
    }
    if(Range(Field<uintptr_t>(object,1296),8)) {
        for(unsigned i=0;i<2;++i) {
            const uint64_t bytes=Field<uint64_t>(object,1312+8*i);
            if(bytes && bytes<=(uint64_t(1)<<40) && !(bytes&((uint64_t(1)<<22)-1)))
                Put(values,402+i,static_cast<double>(bytes)/1048576.0);
        }
    }
    const int32_t level=Field<int32_t>(object,30556);
    if(level>=0 && level<=3)Put(values,404,level);
    for(unsigned i=0;i<3;++i) {
        unsigned count=0;
        for(unsigned slot=0;slot<64;++slot)
            if(Field<uintptr_t>(g_base+PoolRvas[i],8+72*slot))++count;
        Put(values,405+i,count); // count references only; never dereference COM
    }
}
bool TagValid(unsigned which,uintptr_t node) {
    if(which==0 || which==2) return Field<uint32_t>(node,32)<=1;
    if(which==1) {
        // +32 records the requested Present interval, not necessarily the one
        // actually passed to DXGI. Padding at+44 is deliberately ignored.
        return Field<uint32_t>(node,32)<=4 && Field<uint32_t>(node,36)<=2 &&
               Field<uint32_t>(node,40)<=2;
    }
    return Field<uint32_t>(node,48)<=1;
}
bool CopyNewest(uintptr_t object,unsigned which,Record& record) {
    record={};
    const auto& spec=Lists[which];
    const uintptr_t sentinel=Field<uintptr_t>(object,spec.offset);
    const uint64_t count=Field<uint64_t>(object,spec.offset+8);
    if(count>spec.capacity || !Range(sentinel,16))return false;
    const uintptr_t first=Field<uintptr_t>(sentinel),tail=Field<uintptr_t>(sentinel,8);
    if(!count)return first==sentinel && tail==sentinel;
    if(first==sentinel || tail==sentinel)return false;
    uintptr_t visited[MaximumNodes]{};
    uintptr_t previous=sentinel,current=first;
    Record candidate{};
    for(unsigned i=0;i<static_cast<unsigned>(count);++i) {
        if(current==sentinel || !Range(current,spec.nodeBytes))return false;
        for(unsigned j=0;j<i;++j)if(visited[j]==current)return false;
        if(Field<uintptr_t>(current,8)!=previous)return false;
        visited[i]=current;
        if(!i && TagValid(which,current)) {
            candidate.begin=Field<int64_t>(current,spec.beginOffset);
            candidate.end=Field<int64_t>(current,spec.endOffset);
            candidate.valid=true;
        }
        previous=current;
        current=Field<uintptr_t>(current);
    }
    // Exact count plus reciprocal links validates every node, including the
    // oldest one. No borrowed pointer leaves this function.
    if(current!=sentinel || previous!=tail)return false;
    record=candidate;
    return true;
}
bool Milliseconds(const Record& r,unsigned which,int64_t frequency,int64_t now,double& value) {
    if(!r.valid || frequency<=0 || frequency>INT64_MAX/10 || now<=0 ||
       r.begin<=0 || r.end<r.begin)return false;
    const int64_t ticks=r.end-r.begin; // both positive and ordered: no overflow
    if(ticks>frequency*10)return false;
    if(r.end>now) {
        if(which!=0 || r.end-now>frequency)return false; // GPU calibration skew only
    } else if(now-r.end>frequency*10)return false;
    value=static_cast<double>(ticks)*1000.0/static_cast<double>(frequency);
    return isfinite(value) && value>=0 && value<=10000;
}
void Timelines(uintptr_t object,Values& values) {
    Record records[4]{};
    auto* const cs=reinterpret_cast<LPCRITICAL_SECTION>(object+HistoryOffset);
    if(!TryEnterCriticalSection(cs))return; // resource values can still be published
    __try {
        for(unsigned i=0;i<4;++i)CopyNewest(object,i,records[i]);
        // Comparison time is obtained after capture, including any time spent
        // waiting for the outer mutex; native records cannot look spuriously new.
        LARGE_INTEGER frequency{},now{};
        if(Range(g_base+FrequencyRva,8) && QueryPerformanceFrequency(&frequency) &&
           QueryPerformanceCounter(&now) && frequency.QuadPart==Field<int64_t>(g_base+FrequencyRva)) {
            for(unsigned i=0;i<4;++i) {
                double ms=0;
                if(Milliseconds(records[i],i,frequency.QuadPart,now.QuadPart,ms))Put(values,First+i,ms);
            }
        }
    } __finally { LeaveCriticalSection(cs); }
}
}
void RendererDiagnosticsSnapshot(const TrainerContext& c) {
    using namespace renderer_diagnostics;
    if(faulted)return;
    display_preview::Lease before{};
    if(!display_preview::Ready(c,before))return;
    void* const mutex=reinterpret_cast<void*>(before.object+display_preview::MutexOffset);
    if(before.lock(mutex)!=0)return;
    Values copied{};
    int unlockResult=0;
    bool completed=false;
    __try {
        display_preview::Lease current{};
        if(display_preview::Ready(c,current) && display_preview::Same(before,current) && Roots(current.object)) {
            Scalars(current.object,copied);
            Timelines(current.object,copied);
        }
        completed=true;
    } __finally {
        if(!completed)faulted=true;
        bool released=false;
        __try {
            unlockResult=before.unlock(mutex);
            released=unlockResult==0;
        } __finally {
            // Display uses this same mutex. Neither component may retry after
            // an error or exception leaves the mutex ownership uncertain.
            if(!released)faulted=display_preview::faulted=true;
        }
    }
    if(!completed || unlockResult || faulted)return;
    for(unsigned i=0;i<16;++i)if(copied.valid&(1u<<i))SnapshotValue(First+i,copied.value[i]);
}
void RendererDiagnosticsCapabilities() {
    for(unsigned slot=renderer_diagnostics::First;slot<=renderer_diagnostics::Last;++slot)SupportCapability(slot);
}
void RendererDiagnosticsReset(const TrainerContext&) {} // no effects or borrowed pointers to restore
void RendererDiagnosticsFailureReset(const TrainerContext&) {
    renderer_diagnostics::faulted=true; // do not resume after a bridge failure
}
