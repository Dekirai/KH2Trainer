// Native targeting scalar setters 3ABD60/3ABD80 and consumers 3BEA30/3DD280.
// One-time game-thread writes. No target/reticle allocation and no retained pointers.
namespace targeting {
using combat::Field;
constexpr unsigned First=368,Last=373;
constexpr uintptr_t Factor=0x2A1141C,BreakDistance=0x2A11420;
struct Span { uintptr_t data=0; SIZE_T size=0; };
bool Inside(Span span,uintptr_t p,SIZE_T n) {
    return span.data && p>=span.data && p-span.data<=span.size && n<=span.size-(p-span.data);
}
bool Tag(Span bar,const char tag[5],Span& entry) {
    entry={};
    if(bar.size<16 || !Readable(reinterpret_cast<void*>(bar.data),bar.size) ||
       (Field<unsigned>(bar.data,0)&0x00ffffff)!=0x00524142 ||
       DecodePacked(Field<uint32_t>(bar.data,8))!=bar.data) return false;
    const int count=Field<int>(bar.data,4);
    if(count<=0 || uint64_t(count)*16+16>bar.size) return false;
    const SIZE_T end=16+static_cast<SIZE_T>(count)*16;
    for(int i=0;i<count;++i) {
        const uintptr_t row=bar.data+16+static_cast<SIZE_T>(i)*16;
        if(Field<uint16_t>(row,0)!=2 || memcmp(reinterpret_cast<void*>(row+4),tag,4)) continue;
        // Preserve native first-match precedence even for linked/duplicate tags.
        const uintptr_t data=DecodePacked(Field<uint32_t>(row,8));
        const unsigned size=Field<unsigned>(row,12);
        if(!size || !Inside(bar,data,size) || data-bar.data<end) return false;
        entry={data,size}; return true;
    }
    return false;
}
bool Parameters(float& acquire,float& retain) {
    acquire=retain=0;
    const uintptr_t outer=At<uintptr_t>(0x2AE5E50);
    if(outer<16 || !Readable(reinterpret_cast<void*>(outer-16),32) ||
       Field<unsigned>(outer-16,4)!=0x23234141 || Field<unsigned>(outer-16,8)!=1) return false;
    const unsigned bytes=Field<unsigned>(outer-16,0);
    if(bytes<16 || (bytes&63) || bytes>UINTPTR_MAX-outer) return false;
    Span pref,sstm;
    if(!Tag({outer,bytes},"pref",pref) || pref.data!=At<uintptr_t>(0x2AE5768) ||
       !Tag(pref,"sstm",sstm) || sstm.size<8) return false;
    const int offset=Field<int>(sstm.data,4);
    if(offset<=0 || static_cast<unsigned>(offset)>sstm.size || 84>sstm.size-static_cast<unsigned>(offset)) return false;
    const uintptr_t params=sstm.data+offset;
    if(params!=At<uintptr_t>(0x2AE5760)) return false;
    acquire=Field<float>(params,76);retain=Field<float>(params,80);
    return combat::FiniteRange(acquire,0.000001,1000000) && combat::FiniteRange(retain,0.000001,1000000);
}
bool Pins() {
    static const BYTE scale[]={0x48,0x8B,0x05,0xF9,0x99,0x73,0x02,0xF3,0x0F,0x11,0x05,0xAD,0x56,0x66,0x02,0xF3,0x0F,0x59,0x40,0x50,0xF3,0x0F,0x11,0x05,0xA4,0x56,0x66,0x02,0xC3};
    static const BYTE distance[]={0xF3,0x0F,0x11,0x05,0x98,0x56,0x66,0x02,0xC3};
    return Readable(reinterpret_cast<void*>(g_base+0x3ABD60),sizeof(scale)) &&
        Readable(reinterpret_cast<void*>(g_base+0x3ABD80),sizeof(distance)) &&
        !memcmp(reinterpret_cast<void*>(g_base+0x3ABD60),scale,sizeof(scale)) &&
        !memcmp(reinterpret_cast<void*>(g_base+0x3ABD80),distance,sizeof(distance));
}
bool Ready(const TrainerContext& c,float& acquire,float& retain,bool allowPause=false) {
    return actor_movement::Ready(c,allowPause) && Pins() && Parameters(acquire,retain);
}
uint32_t Bits(float value) { uint32_t bits=0;memcpy(&bits,&value,4);return bits; }
float Float(uint32_t bits) { float value=0;memcpy(&value,&bits,4);return value; }
bool PairValid(float factor,float distance,float acquire) {
    // Includes every ordinary scale/default product, plus separate break overrides.
    return isfinite(factor) && factor>=0.05f && factor<=10.0f &&
        isfinite(distance) && distance>0 && distance<=10000000.0f && isfinite(factor*acquire);
}
bool PairHandle(const TrainerContext& c,const double args[8],TrainerResult& result) {
    if(!args || !IsInteger(args[0],0,1)) {result={2,L"Choose apply or conditional restore."};return true;}
    for(unsigned i=1;i<6;++i) if(!IsInteger(args[i],0,UINT32_MAX)) {
        result={2,L"Targeting pair arguments must be exact Float32 bit patterns."};return true;
    }
    const bool restore=args[0]==1;
    const uint32_t expectedScale=static_cast<uint32_t>(args[1]),expectedBreak=static_cast<uint32_t>(args[2]);
    const uint32_t desiredScale=static_cast<uint32_t>(args[3]),desiredBreak=static_cast<uint32_t>(args[4]);
    float acquire=0,retain=0;
    if(!combat::HostFresh() || !Ready(c,acquire,retain) ||
       !Writable(reinterpret_cast<void*>(g_base+Factor),8)) {
        result={3,L"A stable playable Sora scene with writable targeting values is required."};return true;
    }
    const float factor=Float(desiredScale),distance=Float(desiredBreak);
    if(!PairValid(factor,distance,acquire) || !PairValid(Float(expectedScale),Float(expectedBreak),acquire) ||
       (!restore && (Bits(retain)!=static_cast<uint32_t>(args[5]) || Bits(factor*retain)!=desiredBreak))) {
        result={2,L"The targeting pair or its native default changed. Wait for a fresh snapshot."};return true;
    }
    // Current game-thread dispatch and Ready serialize native/script writers. These globals
    // are only four-byte aligned: this is NOT an aligned 64-bit hardware compare/exchange.
    // No calls, waits or yields between comparing the whole pair and both Float32 stores.
    const uint32_t scale=At<uint32_t>(Factor),currentBreak=At<uint32_t>(BreakDistance);
    if(scale!=expectedScale || currentBreak!=expectedBreak) {
        result={restore?0:4,restore?L"Targeting changed elsewhere; its complete current pair was preserved.":
            L"Targeting changed before apply; no values were changed."};return true;
    }
    At<uint32_t>(Factor)=desiredScale;At<uint32_t>(BreakDistance)=desiredBreak;
    result={0,restore?L"The original targeting pair was restored exactly.":L"The targeting pair was applied once."};return true;
}
}
bool TargetingHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace targeting;
    if(slot==475)return PairHandle(c,args,result);
    if(slot!=368 && slot!=369 && slot!=372) return false;
    if((slot==368 && !combat::FiniteRange(args[0],0.05,10)) ||
       (slot==369 && !combat::FiniteRange(args[0],1,100000))) {
        result={2,L"Choose a finite targeting value within the displayed range."};return true;
    }
    float acquire=0,retain=0;
    if(!combat::HostFresh() || !Ready(c,acquire,retain)) {
        result={3,L"A stable playable Sora scene with verified targeting parameters is required."};return true;
    }
    const float factor=slot==372?1.0f:static_cast<float>(args[0]);
    const float distance=slot==369?factor:factor*retain;
    if(!isfinite(distance) || distance<=0 || !isfinite(factor*acquire) ||
       !Writable(reinterpret_cast<void*>(g_base+BreakDistance),sizeof(float)) ||
       (slot!=369 && !Writable(reinterpret_cast<void*>(g_base+Factor),sizeof(float)))) {
        result={3,L"The targeting values are unavailable or not writable."};return true;
    }
    // Same float32 arithmetic/write order as 3ABD60; 3ABD80 writes only distance.
    if(slot!=369) At<float>(Factor)=factor;
    At<float>(BreakDistance)=distance;
    result={0,slot==369?L"Lock-on break distance applied once. Native exempt targets and scripted rules can bypass this distance.":
        slot==372?L"Targeting scale and break distance reset to the currently loaded native parameters.":
        L"Target search scale applied once; lock-on break distance was recalculated from its native default. Scripts and scene changes can replace these values."};
    return true;
}
void TargetingSnapshot(const TrainerContext& c) {
    using namespace targeting;
    float acquire=0,retain=0;if(!Ready(c,acquire,retain,true))return;
    const float factor=At<float>(Factor),distance=At<float>(BreakDistance);
    if(isfinite(factor)) {SnapshotValue(368,factor);if(isfinite(factor*acquire))SnapshotValue(370,factor*acquire);}
    if(isfinite(distance))SnapshotValue(369,distance);
    SnapshotValue(371,acquire);SnapshotValue(373,retain);
    if(PairValid(factor,distance,acquire)) {SnapshotValue(475,Bits(factor));SnapshotValue(476,Bits(distance));}
}
void TargetingCapabilities() { for(unsigned slot=targeting::First;slot<=targeting::Last;++slot) SupportCapability(slot);SupportCapability(475);SupportCapability(476); }
