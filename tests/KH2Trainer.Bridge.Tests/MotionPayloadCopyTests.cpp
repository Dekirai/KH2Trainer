#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include "../../src/KH2Trainer.Bridge/MotionPayloadCopy.h"

#ifdef MOTION_PAYLOAD_COPY_PRODUCTION_COMPILE
motion_payload_copy::Result CompileCopy(motion_payload_copy::ReadScope& scope) {
    return motion_payload_copy::TryCopy(scope);
}
motion_payload_copy::Result CompilePreparedCopy(motion_payload_copy::ReadScope& scope) {
    motion_payload_copy::PreparedCopy copy;
    if(!copy.Prepare({256,4}))return motion_payload_copy::Result(copy.Status());
    copy.Copy(scope);
    return copy.TakeResult();
}
#else
// Failure injection only replaces this private test executable's allocator.
// It neither changes the production header nor allocates/reads a game process.
namespace allocation_fault {
int after=-1;
unsigned attempts=0,deallocations=0,copyAllocations=0,copyDeallocations=0;
bool inCopy=false;
}
void* operator new(size_t size) {
    ++allocation_fault::attempts;
    if(allocation_fault::inCopy)++allocation_fault::copyAllocations;
    if(allocation_fault::after==0){allocation_fault::after=-1;throw std::bad_alloc();}
    if(allocation_fault::after>0)--allocation_fault::after;
    if(void* p=std::malloc(size?size:1))return p;
    throw std::bad_alloc();
}
void Delete(void* p) noexcept {
    ++allocation_fault::deallocations;
    if(allocation_fault::inCopy)++allocation_fault::copyDeallocations;
    std::free(p);
}
void operator delete(void* p) noexcept {Delete(p);}
void operator delete(void* p,size_t) noexcept {Delete(p);}

namespace {
using namespace motion_payload_copy;
unsigned checks=0,failures=0,cases=0;
void Check(bool value,const char* label) {
    ++checks;if(!value){++failures;std::printf("FAIL %s\n",label);}
}
constexpr uintptr_t Module=0x140000000ull,Actor=0x400000000ull,Resource=0x600000000ull;
constexpr size_t Controller=344,OuterEntry=48,Inner=256,InnerEntry=Inner+32;
constexpr size_t Motion=1024,LaterMotion=1536,EntryBytes=176,PayloadBytes=EntryBytes-RuntimePrefix;
constexpr Limits FixtureLimits{PayloadBytes,3};
template<class T,size_t N> void Put(std::array<uint8_t,N>& bytes,size_t offset,T value) {
    std::memcpy(bytes.data()+offset,&value,sizeof(value));
}
uint32_t Packed(size_t offset) {return 0x80000000u|static_cast<uint32_t>(offset);}
bool Inside(uintptr_t address,size_t size,uintptr_t base,size_t extent) {
    return address>=base && address-base<=extent && size<=extent-(address-base);
}
enum class Mutation {None,Controller,OuterHeader,OuterEntry,InnerHeader,InnerEntry,Prefix,Region,Binding,Cache};
struct Scope final : ReadScope {
    Admission admission{};
    std::array<uint8_t,1024> actor{};
    std::array<uint8_t,8192> resource{};
    std::array<uint64_t,64> regions{};
    unsigned reads=0,currents=0,captures=0,badReads=0,readsAfterRevocation=0;
    unsigned failCurrent=0,failRead=0,regionReads=0;
    bool allowCapture=true,revoked=false,partialFailure=false,revokeOnPayload=false,revokeOnFinalRead=false;
    Mutation mutation=Mutation::None;
    struct ReadCall {uintptr_t address;size_t size;};
    std::array<ReadCall,64> calls{};

    explicit Scope(uint32_t kind=1) {
        admission.module={Module,0x3000000};admission.actor={Actor,actor.size()};
        admission.reservation={Resource,resource.size()};
        admission.identity={1,2,3,4,5};admission.kind=ReservationKind::ObservedOrdinary;
        regions[0]=Resource;admission.regions=regions;
        Put<uint64_t>(actor,Controller,Resource);
        Put<uint64_t>(actor,Controller+16,Actor);
        Put<uint64_t>(actor,Controller+24,Resource+Motion);
        Put<int32_t>(actor,Controller+40,-1);
        Put<int32_t>(actor,Controller+44,2);
        Put<int32_t>(actor,Controller+48,-1);
        Put<uint64_t>(actor,Controller+328,Actor+128);
        Header(0,3);Header(Inner,3);
        Entry(16,17,0x1234,0,0);Entry(32,9,2,0,0);
        Entry(OuterEntry,17,0xDEADBEEF,Packed(Inner),2048);
        Entry(Inner+16,16,2,0,0);
        Entry(InnerEntry,9,0x76543210,Packed(Motion),EntryBytes);
        Entry(Inner+48,9,0,Packed(LaterMotion),EntryBytes);
        MotionData(Motion,kind);MotionData(LaterMotion,kind);
    }
    void Header(size_t offset,int32_t count) {
        resource[offset]='B';resource[offset+1]='A';resource[offset+2]='R';resource[offset+3]=1;
        Put<int32_t>(resource,offset+4,count);Put<uint32_t>(resource,offset+8,Packed(offset));
    }
    void Entry(size_t offset,uint16_t type,uint32_t tag,uint32_t pointer,uint32_t size) {
        Put<uint16_t>(resource,offset,type);Put<uint32_t>(resource,offset+4,tag);
        Put<uint32_t>(resource,offset+8,pointer);Put<uint32_t>(resource,offset+12,size);
    }
    void MotionData(size_t offset,uint32_t kind) {
        Put<uint64_t>(resource,offset,Module+(kind?0x5B4A38:0x5B4958));
        Put<uint64_t>(resource,offset+8,Resource+offset+RuntimePrefix);
        for(size_t i=0;i<PayloadBytes;++i)resource[offset+RuntimePrefix+i]=static_cast<uint8_t>(0x80+i);
        Put<uint32_t>(resource,offset+RuntimePrefix,kind);
    }
    bool Capture(Admission& result) noexcept override {
        ++captures;if(!allowCapture)return false;result=admission;return true;
    }
    bool Current(const Admission& expected) noexcept override {
        ++currents;
        if(failCurrent && currents==failCurrent)revoked=true;
        return !revoked && !std::memcmp(&expected.identity,&admission.identity,sizeof(Identity));
    }
    void Mutate() noexcept {
        // Intentionally dishonest providers demonstrate detection only. They do
        // not model a safe concurrent resource owner or validate a live scope.
        switch(mutation) {
        case Mutation::Controller:actor[Controller+40]^=1;break;
        case Mutation::OuterHeader:resource[12]^=2;break;
        case Mutation::OuterEntry:resource[OuterEntry+4]^=1;break;
        case Mutation::InnerHeader:resource[Inner+12]^=1;break;
        case Mutation::InnerEntry:resource[Inner+16+4]^=1;break;
        case Mutation::Prefix:resource[Motion]^=1;break;
        case Mutation::Region:regions[63]=0x2000000;break;
        case Mutation::Binding:++admission.identity.bindingRevision;break;
        case Mutation::Cache:++admission.identity.cacheRevision;break;
        default:break;
        }
        mutation=Mutation::None;
    }
    bool Read(uintptr_t address,void* destination,size_t size) noexcept override {
        if(revoked)++readsAfterRevocation;
        ++reads;if(reads<=calls.size())calls[reads-1]={address,size};
        const uint8_t* source=nullptr;
        if(Inside(address,size,Actor,actor.size()))source=actor.data()+static_cast<size_t>(address-Actor);
        else if(Inside(address,size,Resource,resource.size()))source=resource.data()+static_cast<size_t>(address-Resource);
        else if(Inside(address,size,Module+RegionTableRva,sizeof(regions)))
            source=reinterpret_cast<const uint8_t*>(regions.data())+static_cast<size_t>(address-Module-RegionTableRva);
        else {++badReads;return false;}
        if(failRead && reads==failRead) {
            if(partialFailure && size)std::memcpy(destination,source,size/2);
            return false;
        }
        std::memcpy(destination,source,size);
        if(address==Resource+Motion+RuntimePrefix) {
            Mutate();if(revokeOnPayload)revoked=true;
        }
        if(address==Module+RegionTableRva && ++regionReads==2 && revokeOnFinalRead)revoked=true;
        return true;
    }
};

bool EmptyFailure(const Result& result) {
    const auto& i=result.SourceIdentity();
    return result.Payload().empty() && !i.issuer && !i.actorGeneration && !i.cacheRevision &&
        !i.bindingRevision && !i.decoderRevision && !result.LogicalId() && !result.ResolvedId() && !result.Variant();
}
void Reject(Scope& s,Error expected,const char* label,Limits limits=FixtureLimits) {
    ++cases;const auto beforeActor=s.actor;const auto beforeResource=s.resource;const auto beforeRegions=s.regions;
    auto result=TryCopy(s,limits);
    Check(result.Status()==expected,label);Check(EmptyFailure(result),"failure publishes no bytes, identity or selection");
    Check(s.badReads==0 && s.readsAfterRevocation==0,"rejection never reads outside fixture or after terminal revocation");
    Check(s.actor==beforeActor && s.resource==beforeResource && s.regions==beforeRegions,"rejected copy leaves all source bytes unchanged");
}
void Accept(Scope& s,const char* label,size_t expectedSize=PayloadBytes,Limits limits=FixtureLimits) {
    ++cases;const auto beforeActor=s.actor;const auto beforeResource=s.resource;const auto beforeRegions=s.regions;
    const auto result=TryCopy(s,limits);
    Check(result.Status()==Error::None,label);
    Check(result.Payload().size()==expectedSize &&
        !std::memcmp(result.Payload().data(),s.resource.data()+Motion+RuntimePrefix,expectedSize),"payload-only bytes copied exactly");
    Check(result.SourceIdentity().actorGeneration==2 && result.SourceIdentity().bindingRevision==4 &&
        result.LogicalId()==-1 && result.ResolvedId()==2 &&
        result.Variant()==((s.resource[12]&1)?2:-1),"identity and historical selection copied without remapping logical -1");
    Check(s.actor==beforeActor && s.resource==beforeResource && s.regions==beforeRegions,"successful copy leaves every source byte unchanged");
    Check(s.badReads==0 && s.readsAfterRevocation==0,"all successful source reads stay inside private provider maps");
}

void SelectionAndOwnership() {
    Scope raw;Accept(raw,"RAW selected by mixed physical ordinal despite misleading tags");
    Scope prototype(0);Accept(prototype,"prototype payload copied without interpreting its root tables");
    Scope flags;flags.resource[3]=0x31;flags.resource[Inner+3]=0x21;flags.resource[12]=1;
    Put<int32_t>(flags.actor,Controller+48,2);Accept(flags,"primary flag selects variant; metadata header bits remain supported");
    Scope innerFlag;innerFlag.resource[Inner+12]=1;Accept(innerFlag,"inner variant flag cannot change primary variant -1");
    Scope wrongFlag;wrongFlag.resource[Inner+12]=1;Put<int32_t>(wrongFlag.actor,Controller+48,2);
    Reject(wrongFlag,Error::UnsupportedContext,"using inner flag for variant is rejected");
    Scope firstEmpty;Put<uint32_t>(firstEmpty.resource,InnerEntry+12,0);
    Reject(firstEmpty,Error::OutOfSpan,"zero-sized first type9 is not rescued by a later valid type9");
    Scope firstLinked;Put<uint16_t>(firstLinked.resource,InnerEntry+2,1);
    Reject(firstLinked,Error::UnsupportedEntry,"linked first type9 is not rescued by a later valid type9");
    Scope absent;Put<uint16_t>(absent.resource,InnerEntry,16);Put<uint16_t>(absent.resource,Inner+48,16);
    Reject(absent,Error::UnsupportedEntry,"no type9 returns unsupported");
    Scope type;Put<uint16_t>(type.resource,OuterEntry,9);Reject(type,Error::UnsupportedEntry,"outer ordinal must meet type17 policy");
    Scope link;Put<uint16_t>(link.resource,OuterEntry+2,0x100);Reject(link,Error::UnsupportedEntry,"entire link word is rejected, not only native bit0");
    Scope current;Put<uint64_t>(current.actor,Controller+24,Resource+LaterMotion);
    Reject(current,Error::WrongCurrentMotion,"current motion must equal first selected type9");
    ++cases;Result retained;
    {Scope transient;retained=TryCopy(transient,FixtureLimits);transient.resource.fill(0);}
    Check(retained.Status()==Error::None && retained.Payload().size()==PayloadBytes && retained.Payload()[4]==0x84,
        "result owns bytes after the private scope and source are destroyed");
}

void BoundsAndAdmission() {
    Scope no;no.allowCapture=false;Reject(no,Error::NoAdmission,"failed capture rejects before reading");Check(no.reads==0,"no-admission has no reads");
    Scope unknown;unknown.admission.kind=ReservationKind::Unknown;Reject(unknown,Error::InvalidAdmission,"unknown reservation origin rejected");
    Scope wrap;wrap.admission.reservation={UINTPTR_MAX-8,16};Reject(wrap,Error::InvalidAdmission,"wrapping reservation rejected before dereference");
    Scope overlap;overlap.admission.actor={Resource,1024};Reject(overlap,Error::InvalidAdmission,"actor cannot alias admitted resource");
    Scope shortActor;shortActor.admission.actor.size=783;Reject(shortActor,Error::InvalidAdmission,"controller witness requires complete actor span");
    Scope era;era.admission.identity.bindingRevision=UINT64_MAX;Reject(era,Error::InvalidAdmission,"exhausted revision cannot be reused");
    Scope zeroEra;zeroEra.admission.identity.cacheRevision=0;Reject(zeroEra,Error::InvalidAdmission,"unknown cache history rejected");
    Scope negative;Put<int32_t>(negative.resource,4,-1);Reject(negative,Error::InvalidCount,"signed negative count rejected");
    Scope zero;Put<int32_t>(zero.resource,Inner+4,0);Reject(zero,Error::InvalidCount,"empty inner table rejected");
    Scope huge;Put<int32_t>(huge.resource,4,INT32_MAX);Reject(huge,Error::BudgetExceeded,"huge count rejected before table arithmetic or oversized reads");
    Scope countLimit;Reject(countLimit,Error::BudgetExceeded,"configured table limit applies",{PayloadBytes,2});
    Scope negativeId;Put<int32_t>(negativeId.actor,Controller+44,-1);Reject(negativeId,Error::InvalidIndex,"negative resolved ID rejected");
    Scope endId;Put<int32_t>(endId.actor,Controller+44,3);Reject(endId,Error::InvalidIndex,"ordinal equal to count rejected");
    Scope table;table.admission.reservation.size=63;Reject(table,Error::OutOfSpan,"complete outer table must fit before selected row read");
    Scope innerTable;Put<uint32_t>(innerTable.resource,OuterEntry+12,63);Reject(innerTable,Error::OutOfSpan,"complete inner table must fit parent entry");
    Scope end;Put<uint32_t>(end.resource,OuterEntry+12,static_cast<uint32_t>(Motion+EntryBytes-Inner));
    end.admission.reservation.size=Motion+EntryBytes;Accept(end,"payload ending exactly at inner and reservation ends is allowed");
    Scope past;Put<uint32_t>(past.resource,OuterEntry+12,static_cast<uint32_t>(Motion+EntryBytes-Inner-1));
    Reject(past,Error::OutOfSpan,"inner parent one byte too short rejects despite larger readable reservation");
    Scope tableAlias;Put<uint32_t>(tableAlias.resource,InnerEntry+8,Packed(Inner+32));
    Reject(tableAlias,Error::OutOfSpan,"motion prefix cannot overlap inner table");
    Scope outerAlias;Put<uint32_t>(outerAlias.resource,OuterEntry+8,Packed(32));
    Reject(outerAlias,Error::OutOfSpan,"inner BAR cannot overlap outer table");
    Scope shortType;Put<uint32_t>(shortType.resource,InnerEntry+12,147);Reject(shortType,Error::WrongMotion,"147-byte type9 lacks complete kind");
    Scope minimum;Put<uint32_t>(minimum.resource,InnerEntry+12,148);Accept(minimum,"148-byte type9 copies four kind bytes only",4,{4,3});
    Scope budget;Reject(budget,Error::BudgetExceeded,"payload limit enforced before reading outside prepared capacity",{PayloadBytes-1,3});
    Scope invalidLimit;Reject(invalidLimit,Error::BudgetExceeded,"zero table budget rejected before capture",{4,0});Check(invalidLimit.captures==0,"invalid limits cannot reach scope");
    Scope tooLargeLimit;Reject(tooLargeLimit,Error::BudgetExceeded,"hard payload cap enforced",{MaxPayloadBytes+1,3});
}

void PointerProfileAndContext() {
    Scope marker;Put<uint32_t>(marker.resource,InnerEntry+8,static_cast<uint32_t>(Motion));Reject(marker,Error::InvalidPackedPointer,"markerless packed pointer rejected by trainer policy");
    Scope zero;Put<uint32_t>(zero.resource,OuterEntry+8,0);Reject(zero,Error::InvalidPackedPointer,"null packed child pointer rejected");
    Scope freeRegion;freeRegion.admission.regions[0]=freeRegion.regions[0]=UINT64_MAX;Reject(freeRegion,Error::InvalidPackedPointer,"native free-region sentinel rejected");
    Scope alignment;alignment.admission.regions[0]=alignment.regions[0]=Resource+1;Reject(alignment,Error::InvalidPackedPointer,"misaligned decode base rejected");
    Scope staleRegion;staleRegion.regions[0]+=0x2000000;Reject(staleRegion,Error::Changed,"retained decoder witness must match source before decode");
    Scope index63;index63.regions[63]=Resource;index63.admission.regions=index63.regions;
    Put<uint32_t>(index63.resource,InnerEntry+8,0xFE000000u|static_cast<uint32_t>(Motion));Accept(index63,"packed region index63 resolves with bitwise OR");
    Scope external;Put<uint32_t>(external.resource,InnerEntry+8,Packed(8192));Reject(external,Error::OutOfSpan,"decoded target outside parent rejects before read");
    Scope self;Put<uint32_t>(self.resource,Inner+8,Packed(Inner+16));Reject(self,Error::InvalidHeader,"inner self pointer must equal container base");
    Scope magic;magic.resource[0]='X';Reject(magic,Error::InvalidHeader,"BAR magic mismatch rejected");
    Scope profile;profile.resource[Inner+3]=0x41;Reject(profile,Error::UnsupportedProfile,"special BAR profile rejected");
    for(uint8_t ordinary:{uint8_t(0x81),uint8_t(0x91),uint8_t(0xA1),uint8_t(0xB1)}) {
        Scope sora;sora.resource[3]=ordinary;sora.resource[Inner+3]=ordinary;
        Accept(sora,"ordinary Sora bit80 with metadata bits is admitted in both BAR levels");
    }
    for(size_t header:{size_t(0),Inner}) {
        Scope combined;combined.resource[header+3]=0xC1;
        Reject(combined,Error::UnsupportedProfile,"combined C0 profile remains unsupported at either level");
    }
    Scope version;version.resource[3]=2;Reject(version,Error::UnsupportedProfile,"unsupported version low nibble rejected");
    for(size_t offset:{size_t(8),size_t(344),size_t(352),size_t(432)}) {
        Scope context;Put<uint64_t>(context.actor,Controller+offset,1);
        Reject(context,Error::UnsupportedContext,"override, borrowed source and refcounter contexts are unsupported");
    }
    Scope owner;Put<uint64_t>(owner.actor,Controller+16,Actor+8);Reject(owner,Error::UnsupportedContext,"foreign controller owner rejected");
    Scope root;Put<uint64_t>(root.actor,Controller+328,Actor+136);Reject(root,Error::UnsupportedContext,"foreign root context rejected");
    Scope payload;Put<uint64_t>(payload.resource,Motion+8,Resource+Motion+RuntimePrefix+1);Reject(payload,Error::WrongMotion,"payload pointer must equal motion+144");
    Scope kind;Put<uint32_t>(kind.resource,Motion+RuntimePrefix,2);Reject(kind,Error::WrongMotion,"unsupported payload kind rejected");
    Scope vtable;Put<uint64_t>(vtable.resource,Motion,Module+0x5B4958);Reject(vtable,Error::WrongMotion,"RAW kind with prototype vtable rejected");
}

void FailuresAndPublication() {
    Scope baseline;const auto baselineResult=TryCopy(baseline,FixtureLimits);
    Check(baselineResult.Status()==Error::None && baseline.currents==baseline.reads+1,"successful copy performs explicit final Current beyond per-read checks");
    Scope before;before.failCurrent=1;Reject(before,Error::Changed,"revocation before initial source read");Check(before.reads==0,"revoked scope is never read");
    Scope during;during.revokeOnPayload=true;Reject(during,Error::Changed,"revocation immediately after payload copy prevents publication");
    Scope final;final.failCurrent=baseline.currents;Reject(final,Error::Changed,"last explicit Current can revoke a fully copied result");
    Check(final.reads==baseline.reads,"final-only rejection happens after all source witness reads");
    Scope lastRead;lastRead.revokeOnFinalRead=true;Reject(lastRead,Error::Changed,"revocation during final source read caught before publication");
    // Three distinct paths: metadata failure, partial payload write, final reread failure.
    for(unsigned read:{2u,8u,baseline.reads}) {
        Scope failure;failure.failRead=read;failure.partialFailure=true;
        Reject(failure,Error::ReadFailed,"provider failure never publishes a partially filled result");
        Check(failure.reads==read,"read failure is terminal");
    }
    for(Mutation mutation:{Mutation::Controller,Mutation::OuterHeader,Mutation::OuterEntry,Mutation::InnerHeader,
        Mutation::InnerEntry,Mutation::Prefix,Mutation::Region,Mutation::Binding,Mutation::Cache}) {
        ++cases;Scope changed;changed.mutation=mutation;const auto result=TryCopy(changed,FixtureLimits);
        Check(result.Status()==Error::Changed && EmptyFailure(result),"changed witness or era rejects identical-pointer payload after copy");
        Check(changed.badReads==0 && changed.readsAfterRevocation==0,"changed-provider fixture stays bounded");
    }
    for(int failAfter:{0,1}) {
        Scope allocation;allocation_fault::after=failAfter;const unsigned previous=allocation_fault::attempts;
        Reject(allocation,Error::AllocationFailed,"inner table/payload allocation failure has no published result");
        allocation_fault::after=-1;
        Check(allocation_fault::attempts==previous+static_cast<unsigned>(failAfter)+1,"fault targets one of the actual two internal allocations");
    }
}

// This marker measures only the real PreparedCopy::Copy call, including scope
// callbacks. There is no OS lock or engine lifetime provider in this fixture.
void CopyWithoutHeap(PreparedCopy& prepared,Scope& scope,Error expected,const char* label) {
    ++cases;
    const unsigned allocations=allocation_fault::attempts,deallocations=allocation_fault::deallocations;
    allocation_fault::inCopy=true;
    const Error result=prepared.Copy(scope);
    allocation_fault::inCopy=false;
    Check(result==expected && prepared.Status()==expected,label);
    Check(allocation_fault::attempts==allocations,"Copy performs no operator new calls");
    Check(allocation_fault::deallocations==deallocations,"Copy performs no operator delete calls, including failure paths");
    Check(!scope.badReads && !scope.readsAfterRevocation,"prepared copy does not read outside provider maps or after revocation");
}
void PreparedLifecycle() {
    PreparedCopy prepared;Scope before;
    CopyWithoutHeap(prepared,before,Error::NotPrepared,"Copy before Prepare rejects");
    Check(before.captures==0,"unprepared Copy cannot reach provider");
    const auto empty=prepared.TakeResult();
    Check(empty.Status()==Error::NotPrepared && EmptyFailure(empty),"Take before Copy cannot publish bytes");

    const unsigned allocations=allocation_fault::attempts;
    Check(prepared.Prepare({PayloadBytes+16,5}),"Prepare owns larger bounded buffers outside Copy");
    Check(allocation_fault::attempts==allocations+2,"both buffer allocations happen during Prepare");
    Scope first;const auto source=first.resource;
    CopyWithoutHeap(prepared,first,Error::None,"prepared ordinary copy succeeds");
    Check(first.resource==source,"prepared copy preserves all source bytes");
    auto retained=prepared.TakeResult();
    Check(retained.Status()==Error::None && retained.Payload().size()==PayloadBytes &&
        !std::memcmp(retained.Payload().data(),source.data()+Motion+RuntimePrefix,PayloadBytes),
        "Take publishes only used payload bytes, not the larger prepared capacity");
    Check(retained.SourceIdentity().bindingRevision==4 && retained.LogicalId()==-1 &&
        retained.ResolvedId()==2 && retained.Variant()==-1,"prepared publication preserves identity and selection");
    const auto repeated=prepared.TakeResult();
    Check(repeated.Status()==Error::NotPrepared && EmptyFailure(repeated),"successful Take cannot publish twice");
    Scope consumed;CopyWithoutHeap(prepared,consumed,Error::NotPrepared,"Copy after successful Take requires reprepare");
    Check(consumed.captures==0,"consumed workspace cannot reach provider");

    Check(prepared.Prepare(FixtureLimits),"explicit reprepare restores consumed workspace");
    Scope next(0);next.resource[Motion+RuntimePrefix+4]=0x37;
    CopyWithoutHeap(prepared,next,Error::None,"reprepared workspace copies a different payload kind");
    const auto newer=prepared.TakeResult();
    Check(newer.Status()==Error::None && newer.Payload()[0]==0 && newer.Payload()[4]==0x37 &&
        retained.Payload()[0]==1 && retained.Payload()[4]==0x84,"new publication cannot modify a previously taken result");

    Check(prepared.Prepare(FixtureLimits),"prepare for success-to-failure replacement");
    Scope good;CopyWithoutHeap(prepared,good,Error::None,"first unpublished prepared result succeeds");
    Scope failed;failed.failRead=8;failed.partialFailure=true;
    CopyWithoutHeap(prepared,failed,Error::ReadFailed,"later partial payload failure clears prior successful publication");
    const auto stale=prepared.TakeResult();
    Check(stale.Status()==Error::ReadFailed && EmptyFailure(stale),"failed newer Copy never returns older successful bytes or identity");
    Check(failed.reads==8,"partial prepared payload read failure is terminal");
    const auto failedAgain=prepared.TakeResult();
    Check(failedAgain.Status()==Error::ReadFailed && EmptyFailure(failedAgain),
        "failed Take is a repeatable status read and does not consume prepared storage");
    Scope recovered(0);
    CopyWithoutHeap(prepared,recovered,Error::None,"Copy can reuse retained buffers after failed Take without reprepare");
    const auto recoveredResult=prepared.TakeResult();
    Check(recoveredResult.Status()==Error::None && recoveredResult.Payload().size()==PayloadBytes &&
        recoveredResult.Payload()[0]==0,"retry after failed Take publishes only the fresh successful payload");
}
void PreparedFailures() {
    PreparedCopy prepared;
    Check(prepared.Prepare(FixtureLimits),"prepare workspace for bounded rejection cases");
    Scope no;no.allowCapture=false;
    CopyWithoutHeap(prepared,no,Error::NoAdmission,"prepared Capture rejection uses no heap");
    Check(no.reads==0 && EmptyFailure(prepared.TakeResult()),"Capture failure publishes nothing and reads nothing");
    Scope before;before.failCurrent=1;
    CopyWithoutHeap(prepared,before,Error::Changed,"prepared initial revocation uses no heap");
    Check(before.reads==0 && EmptyFailure(prepared.TakeResult()),"initial revocation prevents first source read");
    Scope final;final.revokeOnFinalRead=true;
    CopyWithoutHeap(prepared,final,Error::Changed,"revocation during last witness read rejects prepared result");
    Check(final.regionReads==2 && EmptyFailure(prepared.TakeResult()),"final Current prevents publication after last read revokes");
    Scope metadata;metadata.failRead=2;
    CopyWithoutHeap(prepared,metadata,Error::ReadFailed,"prepared metadata read failure uses no heap");
    Check(metadata.reads==2 && EmptyFailure(prepared.TakeResult()),"metadata read failure is terminal and empty");
    Scope changed;changed.mutation=Mutation::Prefix;
    CopyWithoutHeap(prepared,changed,Error::Changed,"changed reread witness clears prepared result without freeing buffers");
    Check(EmptyFailure(prepared.TakeResult()),"changed witness publishes no identity or payload");

    Check(prepared.Prepare({PayloadBytes-1,3}),"prepare payload budget smaller than selected payload");
    Scope budget;CopyWithoutHeap(prepared,budget,Error::BudgetExceeded,"prepared payload budget failure uses no heap");
    Check(EmptyFailure(prepared.TakeResult()) && budget.reads==6,"payload budget rejects before prefix or payload reads");
    Check(prepared.Prepare({PayloadBytes,2}),"prepare table budget smaller than outer table");
    Scope table;CopyWithoutHeap(prepared,table,Error::BudgetExceeded,"prepared table budget failure uses no heap");
    Check(EmptyFailure(prepared.TakeResult()) && table.reads==3,"table budget rejects before selected entry read");

    for(int failAfter:{0,1}) {
        Check(prepared.Prepare(FixtureLimits),"prepare valid workspace before reprepare allocation fault");
        Scope good;CopyWithoutHeap(prepared,good,Error::None,"unpublished success precedes failed reprepare");
        allocation_fault::after=failAfter;
        Check(!prepared.Prepare(FixtureLimits) && prepared.Status()==Error::AllocationFailed,
            "failed reprepare invalidates older success");
        allocation_fault::after=-1;
        Scope unavailable;CopyWithoutHeap(prepared,unavailable,Error::NotPrepared,"allocation-failed workspace cannot copy until reprepare");
        const auto empty=prepared.TakeResult();
        Check(empty.Status()==Error::NotPrepared && EmptyFailure(empty) && unavailable.captures==0,
            "allocation-failed reprepare cannot leak prior bytes or access scope");
    }
    Check(prepared.Prepare(FixtureLimits),"prepare before invalid-limit replacement");
    Scope good;CopyWithoutHeap(prepared,good,Error::None,"success precedes invalid-limit reprepare");
    Check(!prepared.Prepare({4,0}) && prepared.Status()==Error::BudgetExceeded,"invalid reprepare clears old success");
    const auto empty=prepared.TakeResult();
    Check(empty.Status()==Error::NotPrepared && EmptyFailure(empty),"invalid reprepare cannot publish prior bytes");
    Check(allocation_fault::copyAllocations==0 && allocation_fault::copyDeallocations==0,
        "all measured Copy windows have zero allocations and zero deallocations");
}
}
int main() {
    SelectionAndOwnership();BoundsAndAdmission();PointerProfileAndContext();FailuresAndPublication();
    PreparedLifecycle();PreparedFailures();
    std::printf("MotionPayloadCopyTests: %u checks, %u failures. %u focused cases; virtual-address ReadScope only, no live consumer.\n",checks,failures,cases);
    return failures?1:0;
}
#endif
