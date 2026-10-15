#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <new>
#include <utility>
#include <vector>

// Evidence: docs/research/motion-native-copy-contract-20261011/contract.md.
// This component is intentionally not connected to TrainerBridge. A readable
// address, matching bytes or revision number cannot supply resource ownership.
namespace motion_payload_copy {
static_assert(sizeof(uintptr_t)==8,"KH2 uses 64-bit addresses");
constexpr size_t RuntimePrefix=144;
constexpr size_t MaxPayloadBytes=64u*1024u*1024u;
constexpr uint32_t MaxTableEntries=65536;
constexpr uintptr_t RegionTableRva=0x2B0D720;

struct Span { uintptr_t address=0; size_t size=0; };
struct Identity {
    uint64_t issuer=0,actorGeneration=0,cacheRevision=0,bindingRevision=0,decoderRevision=0;
};
enum class ReservationKind { Unknown, ObservedOrdinary };
struct Admission {
    Span module{},actor{},reservation{};
    Identity identity{};
    ReservationKind kind=ReservationKind::Unknown;
    std::array<uint64_t,64> regions{};
};

// Trusted caller boundary, NOT an implementation of engine synchronization.
// A derived scope must already hold the Actor, ordinary reservation, bindings,
// decoder and payload alive and serialized throughout Copy, on a permitted
// engine thread. It must reject unknown history, unobserved writers, relocation,
// aliases/child-cache reservations and revoked admission. Capture/Current use
// monotonically increasing, non-reused revisions; equal pointers are insufficient.
// Current(false) is terminal for this call. No callback may mutate/release the
// protected source. Reads copy exactly the requested bytes or return false.
// The implementation owns synchronization and must contain native read faults;
// noexcept is not SEH handling. Callbacks may not throw or reenter this copy.
class ReadScope {
public:
    virtual ~ReadScope()=default;
    virtual bool Capture(Admission& admission) noexcept=0;
    virtual bool Current(const Admission& admission) noexcept=0;
    virtual bool Read(uintptr_t address,void* destination,size_t size) noexcept=0;
};

struct Limits { size_t payloadBytes=MaxPayloadBytes; uint32_t tableEntries=4096; };
enum class Error {
    None,NoAdmission,InvalidAdmission,Changed,ReadFailed,UnsupportedContext,
    UnsupportedProfile,InvalidHeader,InvalidCount,InvalidIndex,UnsupportedEntry,
    InvalidPackedPointer,OutOfSpan,WrongCurrentMotion,WrongMotion,BudgetExceeded,
    AllocationFailed,NotPrepared
};

class Result final {
    Error error_=Error::NoAdmission;
    std::vector<uint8_t> payload_{};
    Identity identity_{};
    int32_t logical_=0,resolved_=0,variant_=0;
    friend class PreparedCopy;
public:
    explicit Result(Error error=Error::NoAdmission) noexcept:error_(error){}
    Error Status() const noexcept { return error_; }
    const std::vector<uint8_t>& Payload() const noexcept { return payload_; }
    const Identity& SourceIdentity() const noexcept { return identity_; }
    int32_t LogicalId() const noexcept { return logical_; }
    int32_t ResolvedId() const noexcept { return resolved_; }
    int32_t Variant() const noexcept { return variant_; }
};

// Prepare and TakeResult run OUTSIDE any engine/resource gate. Copy performs no
// allocation, capacity change or deallocation, including rejection paths. The
// caller retains this object until the held ReadScope has been released. Scope
// callbacks must also avoid heap, loader, engine calls and blocking lock inversions.
// A successful TakeResult consumes the prepared storage. An error leaves that
// storage available for another Copy; it never publishes an earlier success.
// Owned results omit the 144-byte runtime prefix and can be inspected by Core
// MotionPayloadReader.ReadPayload. Success certifies neither the payload format
// nor skeleton compatibility, native playback, a future binding or scale changes.
class PreparedCopy final {
    Limits limits_{};
    std::vector<uint8_t> entries_{},payload_{};
    Identity identity_{};
    int32_t logical_=0,resolved_=0,variant_=0;
    size_t used_=0;
    Error error_=Error::NotPrepared;
    bool prepared_=false;
public:
    PreparedCopy()=default;
    PreparedCopy(const PreparedCopy&)=delete;
    PreparedCopy& operator=(const PreparedCopy&)=delete;
    bool Prepare(Limits limits={}) noexcept;
    Error Copy(ReadScope& scope) noexcept;
    Result TakeResult() noexcept;
    Error Status() const noexcept { return error_; }
};

namespace detail {
inline bool Valid(Span s) noexcept {
    return s.address && s.size && s.size<=UINTPTR_MAX-s.address;
}
inline bool Contains(Span s,uintptr_t address,size_t size) noexcept {
    return Valid(s) && address>=s.address && address-s.address<=s.size &&
        size<=s.size-(address-s.address);
}
inline bool Overlaps(Span a,Span b) noexcept {
    return a.address<b.address+b.size && b.address<a.address+a.size;
}
template<class T> T Get(const uint8_t* p,size_t offset) noexcept {
    T value{}; std::memcpy(&value,p+offset,sizeof(value)); return value;
}
inline bool Revision(uint64_t v) noexcept { return v && v!=UINT64_MAX; }
inline bool Valid(const Admission& a) noexcept {
    const auto& i=a.identity;
    return a.kind==ReservationKind::ObservedOrdinary &&
        Valid(a.module) && Valid(a.actor) && Valid(a.reservation) &&
        !Overlaps(a.module,a.actor) && !Overlaps(a.module,a.reservation) &&
        !Overlaps(a.actor,a.reservation) && a.actor.size>=344+440 &&
        a.module.size>=RegionTableRva+512 &&
        Revision(i.issuer) && Revision(i.actorGeneration) && Revision(i.cacheRevision) &&
        Revision(i.bindingRevision) && Revision(i.decoderRevision);
}
struct Reader {
    ReadScope& scope;
    const Admission& admission;
    Error error=Error::None;
    bool Read(uintptr_t address,void* dst,size_t size) noexcept {
        if(!scope.Current(admission)){error=Error::Changed;return false;}
        if(!scope.Read(address,dst,size)){error=Error::ReadFailed;return false;}
        return true;
    }
    bool Same(uintptr_t address,const void* expected,size_t size) noexcept {
        std::array<uint8_t,512> part{};
        const auto* bytes=static_cast<const uint8_t*>(expected);
        for(size_t offset=0;offset<size;) {
            const size_t count=(size-offset<part.size())?size-offset:part.size();
            if(!Read(address+offset,part.data(),count))return false;
            if(std::memcmp(part.data(),bytes+offset,count)!=0){error=Error::Changed;return false;}
            offset+=count;
        }
        return true;
    }
    bool Decode(uint32_t word,uintptr_t& address) noexcept {
        if(!(word&0x80000000u)){error=Error::InvalidPackedPointer;return false;}
        const uint64_t base=admission.regions[(word&0x7FFFFFFFu)>>25];
        if(!base || base==UINT64_MAX || (base&0x1FFFFFFu)){
            error=Error::InvalidPackedPointer;return false;
        }
        address=static_cast<uintptr_t>(base | (word&0x1FFFFFFu));
        return true;
    }
};
struct Header {
    std::array<uint8_t,16> bytes{};
    int32_t count=0;
    size_t tableEnd=0;
};
inline bool ReadHeader(Reader& r,Span container,const Limits& limits,Header& h) noexcept {
    if(!Contains(container,container.address,16)){r.error=Error::OutOfSpan;return false;}
    if(!r.Read(container.address,h.bytes.data(),h.bytes.size()))return false;
    const auto* b=h.bytes.data();
    if(b[0]!='B' || b[1]!='A' || b[2]!='R'){r.error=Error::InvalidHeader;return false;}
    // Sora's obj/P_EX100 request worker sets bit 0x80 before ordinary BAR
    // fixup. 3A6840 treats only class 0x40 specially. We admit the verified
    // ordinary 0x80 profile, while 0x40 and combined 0xC0 remain unsupported.
    if((b[3]&15)!=1 || (b[3]&0x40)){r.error=Error::UnsupportedProfile;return false;}
    h.count=Get<int32_t>(b,4);
    if(h.count<=0){r.error=Error::InvalidCount;return false;}
    if(static_cast<uint32_t>(h.count)>limits.tableEntries){r.error=Error::BudgetExceeded;return false;}
    // The configured hard limit makes this multiplication bounded on x64.
    h.tableEnd=16+static_cast<size_t>(h.count)*16;
    if(!Contains(container,container.address,h.tableEnd)){r.error=Error::OutOfSpan;return false;}
    uintptr_t self=0;
    if(!r.Decode(Get<uint32_t>(b,8),self))return false;
    if(self!=container.address){r.error=Error::InvalidHeader;return false;}
    return true;
}
inline bool Child(Reader& r,Span parent,size_t tableEnd,const uint8_t* entry,Span& child) noexcept {
    if(Get<uint16_t>(entry,2)){r.error=Error::UnsupportedEntry;return false;}
    if(!r.Decode(Get<uint32_t>(entry,8),child.address))return false;
    child.size=Get<uint32_t>(entry,12);
    if(!child.size || !Contains(parent,child.address,child.size) ||
       child.address-parent.address<tableEnd){r.error=Error::OutOfSpan;return false;}
    return true;
}
inline bool PrivateBuffer(const Admission& a,const std::vector<uint8_t>& bytes) noexcept {
    const Span buffer{reinterpret_cast<uintptr_t>(bytes.data()),bytes.size()};
    return Valid(buffer) && !Overlaps(buffer,a.actor) &&
        !Overlaps(buffer,a.reservation) && !Overlaps(buffer,a.module);
}
} // namespace detail

// Allocate all scratch storage before acquiring the source scope. Ordinary C++
// object-lifetime rules apply; Prepare and destruction require a released scope.
inline bool PreparedCopy::Prepare(Limits limits) noexcept {
    prepared_=false;identity_={};logical_=resolved_=variant_=0;used_=0;
    error_=Error::NotPrepared;
    if(limits.payloadBytes<4 || limits.payloadBytes>MaxPayloadBytes ||
       !limits.tableEntries || limits.tableEntries>MaxTableEntries){
        error_=Error::BudgetExceeded;return false;
    }
    try {
        std::vector<uint8_t> entries(static_cast<size_t>(limits.tableEntries)*16);
        std::vector<uint8_t> payload(limits.payloadBytes);
        entries_.swap(entries);payload_.swap(payload);
        limits_=limits;prepared_=true;return true;
    } catch(const std::bad_alloc&) {error_=Error::AllocationFailed;return false;}
}

inline Error PreparedCopy::Copy(ReadScope& scope) noexcept {
    identity_={};logical_=resolved_=variant_=0;used_=0;
    const auto Reject=[&](Error error) noexcept {error_=error;return error;};
    if(!prepared_)return Reject(Error::NotPrepared);
    const Limits limits=limits_;
    using namespace detail;
    if(limits.payloadBytes<4 || limits.payloadBytes>MaxPayloadBytes ||
       !limits.tableEntries || limits.tableEntries>MaxTableEntries)return Reject(Error::BudgetExceeded);
    Admission admission{};
    if(!scope.Capture(admission))return Reject(Error::NoAdmission);
    if(!Valid(admission))return Reject(Error::InvalidAdmission);
    Reader r{scope,admission};
    {
        const uintptr_t regionTable=admission.module.address+RegionTableRva;
        // Compare the retained decoder witness, rather than accepting fresh globals
        // as proof that an old packed pointer still belongs to the same resource.
        if(!r.Same(regionTable,admission.regions.data(),sizeof(admission.regions)))return Reject(r.error);
        const uintptr_t controller=admission.actor.address+344;
        std::array<uint8_t,440> c{};
        if(!r.Read(controller,c.data(),c.size()))return Reject(r.error);
        const auto q=[&](size_t n){return Get<uint64_t>(c.data(),n);};
        if(q(8) || q(16)!=admission.actor.address || q(328)!=admission.actor.address+128 ||
           q(344) || q(352) || q(432))return Reject(Error::UnsupportedContext);
        const uintptr_t primary=q(0);
        if(!Contains(admission.reservation,primary,16))return Reject(Error::OutOfSpan);
        const Span outer{primary,admission.reservation.size-(primary-admission.reservation.address)};
        Header outerHeader{};
        if(!ReadHeader(r,outer,limits,outerHeader))return Reject(r.error);
        const int32_t resolved=Get<int32_t>(c.data(),44);
        if(resolved<0 || resolved>=outerHeader.count)return Reject(Error::InvalidIndex);
        const int32_t variant=Get<int32_t>(c.data(),48);
        if(variant!=((outerHeader.bytes[12]&1)?(resolved%4):-1))return Reject(Error::UnsupportedContext);
        const uintptr_t outerEntry=primary+16+static_cast<size_t>(resolved)*16;
        std::array<uint8_t,16> selected{};
        if(!r.Read(outerEntry,selected.data(),selected.size()))return Reject(r.error);
        if(Get<uint16_t>(selected.data(),0)!=17)return Reject(Error::UnsupportedEntry);
        Span inner{};
        if(!Child(r,outer,outerHeader.tableEnd,selected.data(),inner))return Reject(r.error);
        Header innerHeader{};
        if(!ReadHeader(r,inner,limits,innerHeader))return Reject(r.error);
        const size_t entryBytes=innerHeader.tableEnd-16;
        auto* const entries=entries_.data();
        if(!PrivateBuffer(admission,entries_))return Reject(Error::InvalidAdmission);
        if(!r.Read(inner.address+16,entries,entryBytes))return Reject(r.error);
        const uint8_t* type9=nullptr;
        for(int32_t i=0;i<innerHeader.count;++i) {
            const auto* entry=entries+static_cast<size_t>(i)*16;
            if(Get<uint16_t>(entry,0)==9){type9=entry;break;}
        }
        if(!type9)return Reject(Error::UnsupportedEntry);
        Span motion{};
        if(!Child(r,inner,innerHeader.tableEnd,type9,motion))return Reject(r.error);
        if(motion.size<RuntimePrefix+4)return Reject(Error::WrongMotion);
        if(motion.address!=q(24))return Reject(Error::WrongCurrentMotion);
        const size_t payloadSize=motion.size-RuntimePrefix;
        if(payloadSize>limits.payloadBytes)return Reject(Error::BudgetExceeded);
        std::array<uint8_t,16> prefix{};
        if(!r.Read(motion.address,prefix.data(),prefix.size()))return Reject(r.error);
        if(Get<uint64_t>(prefix.data(),8)!=motion.address+RuntimePrefix)return Reject(Error::WrongMotion);
        if(!PrivateBuffer(admission,payload_))return Reject(Error::InvalidAdmission);
        if(!r.Read(motion.address+RuntimePrefix,payload_.data(),payloadSize))return Reject(r.error);
        const uint32_t kind=Get<uint32_t>(payload_.data(),0);
        if(kind>1 || Get<uint64_t>(prefix.data(),0)!=admission.module.address+(kind?0x5B4A38:0x5B4958))
            return Reject(Error::WrongMotion);
        // Metadata checks detect unsupported/stale providers. They do not replace
        // held ownership: no source dereference is justified by a later comparison.
        if(!r.Same(controller,c.data(),c.size()) ||
           !r.Same(primary,outerHeader.bytes.data(),outerHeader.bytes.size()) ||
           !r.Same(outerEntry,selected.data(),selected.size()) ||
           !r.Same(inner.address,innerHeader.bytes.data(),innerHeader.bytes.size()) ||
           !r.Same(inner.address+16,entries,entryBytes) ||
           !r.Same(motion.address,prefix.data(),prefix.size()) ||
           !r.Same(regionTable,admission.regions.data(),sizeof(admission.regions)))return Reject(r.error);
        if(!scope.Current(admission))return Reject(Error::Changed);
        identity_=admission.identity;
        logical_=Get<int32_t>(c.data(),40);
        resolved_=resolved;variant_=variant;used_=payloadSize;
        error_=Error::None;return error_;
    }
}
inline Result PreparedCopy::TakeResult() noexcept {
    if(!prepared_)return Result(Error::NotPrepared);
    if(error_!=Error::None)return Result(error_);
    // Called after releasing the resource scope. Shrinking uint8_t storage and
    // moving its vector cannot allocate; ownership leaves the workspace once.
    Result result(Error::None);
    payload_.resize(used_);result.payload_=std::move(payload_);
    result.identity_=identity_;result.logical_=logical_;
    result.resolved_=resolved_;result.variant_=variant_;
    prepared_=false;error_=Error::NotPrepared;used_=0;
    identity_={};logical_=resolved_=variant_=0;
    return result;
}

// Convenience for privately owned source scopes with no allocator/engine lock
// inversion risk. A production held gate must use Prepare -> acquire scope ->
// Copy -> release scope -> TakeResult, never this allocating convenience call.
inline Result TryCopy(ReadScope& scope,Limits limits={}) noexcept {
    PreparedCopy prepared;
    if(!prepared.Prepare(limits))return Result(prepared.Status());
    if(prepared.Copy(scope)!=Error::None)return Result(prepared.Status());
    return prepared.TakeResult();
}

} // namespace motion_payload_copy
