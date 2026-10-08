#define KH2DEV_PAYLOAD_TESTS
#define KH2_ACTOR_LIFETIME_TESTS
#define KH2_PLAYER_POSITION_TESTS
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <stdio.h>
#include <limits>

namespace {
unsigned checks = 0, failures = 0;
void Check(bool condition, const char* name) {
    ++checks;
    if (!condition) { ++failures; printf("FAIL: %s\n", name); }
}
alignas(8) BYTE actorData[4096]{};
alignas(8) BYTE statusData[632]{};
alignas(8) BYTE managerData[72]{};
alignas(8) BYTE itemData[32]{};
SharedState shared{};
uint32_t EncodeFixture(uintptr_t address) {
    if (!address) return 0;
    const uintptr_t region = address & ~uintptr_t(0x1ffffff);
    for (unsigned i = 1; i < 64; ++i) {
        uintptr_t& entry = At<uintptr_t>(0x2B0D720 + i * 8);
        if (!entry || entry == region) {
            entry = region;
            return 0x80000000u | (i << 25) | static_cast<uint32_t>(address & 0x1ffffff);
        }
    }
    abort();
}
bool PlayerCommand(const TrainerContext& c, unsigned slot, double value, TrainerResult& result) {
    const double args[8]{value};
    return PlayerHandle(c, slot, args, result);
}
bool Valid(unsigned slot) { return (g_shared->validValues[slot / 64] & (uint64_t(1) << (slot % 64))) != 0; }
bool Supported(unsigned slot) { return (g_shared->supportedCapabilities[slot / 64] & (uint64_t(1) << (slot % 64))) != 0; }
void Request(LONG id, double value) {
    g_shared->commandId = id;
    g_shared->commandIssuedAt = GetTickCount();
    ZeroMemory(g_shared->arguments, sizeof(g_shared->arguments));
    g_shared->arguments[0] = value;
    InterlockedIncrement(&g_shared->requestSequence);
}
void TypedMovementIntegrationTests() {
    using movement_tx::Operation; using movement_tx::Outcome; using movement_tx::Reason;
    SharedState savedShared{}; memcpy(&savedShared,&shared,sizeof(shared));
    movement_tx::Receipt savedReceipts[movement_tx::ReceiptCount];
    movement_tx::Lease savedLeases[movement_tx::LeaseCount];
    memcpy(savedReceipts,movement_tx::receipts,sizeof(savedReceipts));
    memcpy(savedLeases,movement_tx::leases,sizeof(savedLeases));
    const auto savedNextLease=movement_tx::nextLease;
    const LONG savedObserver=actor_lifetime::observerStatus;
    const uint64_t savedInstance=actor_lifetime::bridgeInstance;
    const bool savedExpired=g_hostExpired;
    ZeroMemory(movement_tx::receipts,sizeof(movement_tx::receipts));
    ZeroMemory(movement_tx::leases,sizeof(movement_tx::leases));
    movement_tx::nextLease=0;
    // No real observer, game callback or hook is installed in this fixture.
    // Only a known fault and an opaque nonce are required to exercise the real
    // TrainerFrame typed packet dispatch, including immutable receipt replay.
    actor_lifetime::observerStatus=actor_lifetime::Fault;
    constexpr uint64_t nonce=0xFEDCBA9876543210ULL;
    actor_lifetime::bridgeInstance=nonce;
    const uintptr_t birthSlot=At<uintptr_t>(actor_lifetime::kBirthSlot);
    const uintptr_t soraSlot=At<uintptr_t>(actor_lifetime::kSoraSlot);
    const uintptr_t mickeySlot=At<uintptr_t>(actor_lifetime::kMickeySlot);
    BYTE actorBefore[sizeof(actorData)],statusBefore[sizeof(statusData)];
    memcpy(actorBefore,actorData,sizeof(actorBefore));memcpy(statusBefore,statusData,sizeof(statusBefore));
    uint64_t nextOperation=1000;
    auto acquire=[&]() {
        movement_tx::Request q{};
        q.magic=movement_tx::Magic;q.schema=movement_tx::Schema;q.size=sizeof(q);
        q.clientId=0x1122334455667788ULL;q.opId=++nextOperation;q.bridgeInstance=nonce;
        q.actorGeneration=123;q.effectOwnerId=77;q.operation=Operation::Acquire;q.mask=3;
        q.expectedBits[0]=movement_tx::Bits(2.f);q.expectedBits[1]=movement_tx::Bits(8.f);
        q.desiredBits[0]=movement_tx::Bits(4.f);q.desiredBits[1]=movement_tx::Bits(16.f);
        return q;
    };
    auto queue=[&](const movement_tx::Request& q) {
        shared.hostHeartbeat=GetTickCount();
        Request(movement_tx::Command,0);
        BYTE* wire=reinterpret_cast<BYTE*>(&shared);
        memcpy(wire+movement_tx::RequestOffset,&q,sizeof(q));
        memset(wire+movement_tx::ResponseOffset,0xCD,sizeof(movement_tx::Response));
        memset(wire+movement_tx::ResponseOffset+sizeof(movement_tx::Response),0xD7,
            offsetof(SharedState,snapshotSequence)-movement_tx::ResponseOffset-sizeof(movement_tx::Response));
    };
    auto finish=[&](const movement_tx::Request& q) {
        const DWORD before=GetTickCount();TrainerFrame();const DWORD after=GetTickCount();
        movement_tx::Response response{};
        const BYTE* wire=reinterpret_cast<const BYTE*>(&shared);
        memcpy(&response,wire+movement_tx::ResponseOffset,sizeof(response));
        Check(shared.commandId==1466 && shared.responseSequence==shared.requestSequence &&
            response.requestSequence==static_cast<uint32_t>(shared.responseSequence),
            "actual typed command1466 publishes correlated response before acknowledgement");
        Check(response.magic==movement_tx::Magic&&response.schema==1&&response.size==192&&
            response.clientId==q.clientId&&response.opId==q.opId&&response.bridgeInstance==nonce,
            "typed response is decoded from binary ResponseOffset with full uint64 identities");
        Check(static_cast<DWORD>(response.tick-before)<=static_cast<DWORD>(after-before),
            "typed response contains a tick from this dispatch");
        Check(!memcmp(wire+movement_tx::RequestOffset,&q,sizeof(q)),
            "typed dispatch preserves the copied request bytes");
        bool tail=true;
        for(size_t i=movement_tx::ResponseOffset+sizeof(response);i<offsetof(SharedState,snapshotSequence);++i)
            if(wire[i]!=0xD7)tail=false;
        Check(tail&&!(shared.snapshotSequence&1),
            "typed response respects its192-byte extent and completed snapshot seqlock");
        return response;
    };
    auto reject=[&](const movement_tx::Response& response,Reason reason,bool receipt=false) {
        Check(response.outcome==Outcome::Rejected&&response.reason==reason&&shared.resultCode==3,
            "typed rejection is represented in both binary receipt and common result");
        Check(((response.flags&movement_tx::HasReceipt)!=0)==receipt &&
              response.appliedMask==0 && response.restoredMask==0 && response.leaseId==0,
            "rejection cannot fabricate mutation masks or a committed lease");
    };
    auto q=acquire();queue(q);auto first=finish(q);reject(first,Reason::ObserverFault,true);
    Check(movement_tx::FindReceipt(q.clientId,q.opId)!=nullptr&&first.receiptOpId==q.opId,
        "valid fresh request reaches native transaction guard and stores its immutable rejection");
    for(unsigned slot=466;slot<=471;++slot)Check(Supported(slot)&&Valid(slot),
        "schema1 typed movement snapshot capability and diagnostics are published");
    Check(shared.values[466]==1&&shared.values[467]==0&&shared.values[468]==0&&shared.values[471]==2,
        "observer fault publishes schema but no invented Actor generation");
    Check(shared.values[469]==static_cast<uint32_t>(nonce)&&shared.values[470]==static_cast<uint32_t>(nonce>>32),
        "nonce low/high halves preserve all64bits without double precision loss");

    // A previously acknowledged sequence must not execute or replace its response.
    BYTE completed[sizeof(first)];memcpy(completed,reinterpret_cast<BYTE*>(&shared)+movement_tx::ResponseOffset,sizeof(completed));
    TrainerFrame();
    Check(!memcmp(completed,reinterpret_cast<BYTE*>(&shared)+movement_tx::ResponseOffset,sizeof(completed)),
        "already acknowledged typed sequence is not executed again");

    for(unsigned stale=0;stale<3;++stale) {
        auto request=acquire();queue(request);
        shared.commandIssuedAt=stale==0?0:stale==1?GetTickCount()-8000:GetTickCount()+60000;
        reject(finish(request),Reason::Expired);
        Check(!movement_tx::FindReceipt(request.clientId,request.opId),
            "new expired or future-dated packet creates no mutation receipt");
    }
    for(unsigned index=0;index<8;++index)for(double invalid :
        {1.0,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
        auto request=acquire();queue(request);shared.arguments[index]=invalid;
        reject(finish(request),Reason::InvalidRequest);
        Check(!movement_tx::FindReceipt(request.clientId,request.opId),
            "nonzero or nonfinite scalar argument cannot enter a new typed transaction");
    }
    for(unsigned heartbeat=0;heartbeat<2;++heartbeat) {
        auto request=acquire();queue(request);
        shared.hostHeartbeat=heartbeat?GetTickCount()-5001:0;
        reject(finish(request),Reason::HostExpired);
        Check(g_hostExpired&&!movement_tx::FindReceipt(request.clientId,request.opId),
            "missing or expired heartbeat blocks a new typed transaction");
    }

    // Replay the real stored ObserverFault rejection under each common pre-gate.
    const auto* stored=movement_tx::FindReceipt(q.clientId,q.opId);
    const movement_tx::Response storedFirst=stored->response;
    for(unsigned blocked=0;blocked<3;++blocked) {
        queue(q);
        if(blocked==0)shared.commandIssuedAt=GetTickCount()-9000;
        if(blocked==1)shared.hostHeartbeat=GetTickCount()-6000;
        if(blocked==2)shared.arguments[7]=std::numeric_limits<double>::quiet_NaN();
        auto replay=finish(q);reject(replay,Reason::ObserverFault,true);
        replay.requestSequence=storedFirst.requestSequence;replay.tick=storedFirst.tick;
        Check(!memcmp(&replay,&storedFirst,sizeof(replay))&&
            !memcmp(&stored->response,&storedFirst,sizeof(storedFirst)),
            "pre-rejected duplicate preserves every immutable receipt field");
    }

    // Seed ONLY a retained receipt, representing a prior already-committed result.
    // No fake lease or successful native mutation is claimed by this fixture.
    auto committedRequest=acquire();
    auto& committed=movement_tx::receipts[movement_tx::ReceiptCount-1];
    committed={};committed.used=true;committed.request=committedRequest;
    auto& prior=committed.response;prior=movement_tx::Envelope(committedRequest,0x1234);
    prior.outcome=Outcome::Applied;prior.reason=Reason::None;prior.flags=movement_tx::HasReceipt|movement_tx::IdentityKnown;
    prior.receiptOpId=committedRequest.opId;prior.actorGeneration=committedRequest.actorGeneration;
    prior.effectOwnerId=committedRequest.effectOwnerId;prior.leaseId=0x123456789ULL;prior.revision=3;
    prior.mask=prior.appliedMask=3;prior.journalState=movement_tx::State::Active;
    memcpy(prior.originalBits,committedRequest.expectedBits,sizeof(prior.originalBits));
    memcpy(prior.appliedBits,committedRequest.desiredBits,sizeof(prior.appliedBits));
    const auto immutable=prior;
    for(unsigned blocked=0;blocked<3;++blocked) {
        queue(committedRequest);
        if(blocked==0)shared.commandIssuedAt=GetTickCount()-9000;
        if(blocked==1)shared.hostHeartbeat=GetTickCount()-6000;
        if(blocked==2)shared.arguments[0]=1;
        auto replay=finish(committedRequest);
        Check(replay.outcome==Outcome::Applied&&replay.reason==Reason::None&&shared.resultCode==0,
            "expired or malformed-scalar replay acknowledges prior result rather than inventing new rejection");
        replay.requestSequence=immutable.requestSequence;replay.tick=immutable.tick;
        Check(!memcmp(&replay,&immutable,sizeof(replay))&&!memcmp(&prior,&immutable,sizeof(prior)),
            "actual frame dispatch preserves original/applied bits and all immutable prior receipt data");
    }
    auto conflict=committedRequest;conflict.desiredBits[0]=movement_tx::Bits(5.f);queue(conflict);
    shared.hostHeartbeat=0;reject(finish(conflict),Reason::RequestIdConflict);
    Check(!memcmp(&prior,&immutable,sizeof(prior)),"request-id conflict cannot rewrite a retained successful receipt");

    auto wrongSchema=acquire();++wrongSchema.schema;queue(wrongSchema);
    reject(finish(wrongSchema),Reason::UnsupportedSchema);
    auto staleBridge=acquire();++staleBridge.bridgeInstance;queue(staleBridge);
    reject(finish(staleBridge),Reason::StaleBridge);
    bool emptyLeases=true;for(const auto& lease:movement_tx::leases)if(lease.used)emptyLeases=false;
    Check(emptyLeases&&!memcmp(actorBefore,actorData,sizeof(actorBefore))&&!memcmp(statusBefore,statusData,sizeof(statusBefore)),
        "typed rejection/replay fixture executes no new lease or Actor/status write");
    Check(actor_lifetime::Status()==actor_lifetime::Fault&&
        At<uintptr_t>(actor_lifetime::kBirthSlot)==birthSlot&&At<uintptr_t>(actor_lifetime::kSoraSlot)==soraSlot&&
        At<uintptr_t>(actor_lifetime::kMickeySlot)==mickeySlot,
        "typed IPC checks preserve synthetic observer fault and never install native hooks");

    memcpy(movement_tx::receipts,savedReceipts,sizeof(savedReceipts));
    memcpy(movement_tx::leases,savedLeases,sizeof(savedLeases));movement_tx::nextLease=savedNextLease;
    actor_lifetime::observerStatus=savedObserver;actor_lifetime::bridgeInstance=savedInstance;
    g_hostExpired=savedExpired;memcpy(&shared,&savedShared,sizeof(shared));
}
unsigned positionCalls = 0;
void __fastcall FixturePosition(void* actor,const float* position) {
    ++positionCalls;
    Check(reinterpret_cast<uintptr_t>(actor)==At<uintptr_t>(0x2A105D0),"position ABI targets current actor");
    memcpy(static_cast<BYTE*>(actor)+1648,position,16);
}
void __fastcall FixtureBirth(uintptr_t,uintptr_t) {}
uintptr_t __fastcall FixtureDeath(uintptr_t,uintptr_t) { return 0; }
void ObservePositionPlayer(const TrainerContext& c) {
    using namespace actor_lifetime;
    for(const auto& p:kPins) memcpy(reinterpret_cast<void*>(g_base+p.rva),p.bytes,p.count);
    At<uintptr_t>(kActionTable)=g_base+kAction; At<uintptr_t>(kAction)=g_base+kActionVtable;
    At<uintptr_t>(0x750300)=g_base+kSoraSlot; At<uintptr_t>(0x7523B8)=g_base+kMickeySlot;
    At<uintptr_t>(kBirthSlot)=g_base+kBirth; At<uintptr_t>(kSoraSlot)=g_base+kSoraDeath;
    At<uintptr_t>(kMickeySlot)=g_base+kMickeyDeath;
    testBirth=FixtureBirth; testSoraDeath=testMickeyDeath=FixtureDeath;
    // Actual role helper and allocation pool; only native forwarding is replaced.
    constexpr uintptr_t objectTable=0x120000;
    At<uintptr_t>(0x2A25030)=g_base+objectTable; At<int>(objectTable+4)=1;
    At<WORD>(objectTable+8+76)=1; At<signed char>(objectTable+8+87)=0;
    PlayerField<uint32_t>(c.player,0)=EncodeFixture(g_base+0x750300);
    PlayerField<uint32_t>(c.player,8)=EncodeFixture(g_base+objectTable+8);
    PlayerField<unsigned>(c.player,1736)=0x1000080;
    PlayerField<int>(c.player,3552)=0; PlayerField<int>(c.status,612)=1;
    At<int>(0x2A23950)=79;
    for(int i=0;i<79;++i) At<int>(0x2A23810+i*4)=i+1;
    At<uintptr_t>(0x2A171C8)=c.player;
    g_testPlayerPosition=FixturePosition;
    Check(Install(c)&&ObserveCurrent(c)!=0,"actual lifetime observer installed on synthetic player");
}
void ReconstructPositionPlayer(const TrainerContext& c) {
    actor_lifetime::testReturnOverride=g_base+actor_lifetime::kBirthReturn;
    actor_lifetime::BirthHook(g_base+actor_lifetime::kAction,c.player);
    actor_lifetime::testReturnOverride=0;
}
void RescueTests(const TrainerContext& c) {
    using namespace rescue_features;
    BYTE saved[0x10FC0]; memcpy(saved,reinterpret_cast<void*>(g_base+0x9A98B0),sizeof(saved));
    auto command=[&](double value) { TrainerResult result{}; double args[8]{value};
        Check(RescueHandle(c,176,args,result),"rescue counter owns command176"); return result.code; };
    auto snapshot=[&]() { ZeroMemory(shared.validValues,sizeof(shared.validValues)); RescueSnapshot(c); };
    At<uint16_t>(UseCountRva)=3; At<uint16_t>(AppearCountRva)=17; At<unsigned>(0x783CA0)=123456;
    Request(1176,2); TrainerFrame();
    Check(shared.resultCode==0 && At<uint16_t>(UseCountRva)==2 && Valid(176) && shared.values[176]==2,
          "rescue edit routes through IPC and publishes the saved exponent");
    Check(At<uint16_t>(AppearCountRva)==17 && At<unsigned>(0x783CA0)==123456,
          "editing rescue exponent preserves recorded appearances and native RNG");
    BYTE before[0x10FC0]; memcpy(before,reinterpret_cast<void*>(g_base+0x9A98B0),sizeof(before));
    Check(command(999)==0 && At<uint16_t>(UseCountRva)==999,"rescue counter accepts native cap999");
    size_t differences=0;
    for(size_t i=0;i<sizeof(before);++i) if(before[i]!=At<BYTE>(0x9A98B0+i)) {
        ++differences; Check(i==UseCountRva-0x9A98B0 || i==UseCountRva-0x9A98B0+1,"rescue edits only its two SaveData bytes");
    }
    Check(differences>0 && differences<=2,"rescue edit changes no unrelated save fields");
    Check(command(0)==0 && At<uint16_t>(UseCountRva)==0,"rescue exponent can be reset to zero");
    for(double bad : {-1.0,0.5,1000.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()})
        Check(command(bad)!=0 && At<uint16_t>(UseCountRva)==0,"invalid rescue input leaves saved exponent unchanged");
    At<uint16_t>(UseCountRva)=1000; Check(command(0)!=0,"malformed existing rescue counter is rejected"); At<uint16_t>(UseCountRva)=3;
    At<uint64_t>(0x9A98B0)=0; Check(command(0)!=0,"unloaded or wrong SaveData header blocks rescue edit");
    At<uint64_t>(0x9A98B0)=0x0000003A4A32484BULL;
    PlayerField<int>(c.status,608)=4; Check(command(0)!=0,"current Mickey cannot edit the rescue counter"); PlayerField<int>(c.status,608)=1;
    PlayerField<int>(c.status,0)=0; Check(command(0)!=0,"defeated player cannot edit the rescue counter"); PlayerField<int>(c.status,0)=100;
    At<uintptr_t>(GameOverRva)=g_base+0x201000; Check(command(0)!=0,"active game-over sequence blocks rescue edit"); At<uintptr_t>(GameOverRva)=0;
    At<BYTE>(0x9006B0)=1; Check(command(0)!=0,"menu blocks rescue edit"); At<BYTE>(0x9006B0)=0;
    At<uintptr_t>(0xAC0F48)=1; Check(command(0)!=0,"event blocks rescue edit"); At<uintptr_t>(0xAC0F48)=0;
    At<uintptr_t>(0x9BA928)=1; Check(command(0)!=0,"pending transition blocks rescue edit"); At<uintptr_t>(0x9BA928)=0;
    At<int>(0x716884)=2; Check(command(0)!=0,"field pause blocks rescue edit"); snapshot();
    Check(Valid(176) && shared.values[176]==3,"field pause retains read-only rescue diagnostics"); At<int>(0x716884)=1;
    At<BYTE>(0x9BA8D0)=0; Check(command(0)!=0,"fresh scene loss blocks a stale rescue context"); At<BYTE>(0x9BA8D0)=1;
    g_gameThread=GetCurrentThreadId()+1; Check(command(0)!=0,"foreign thread blocks rescue edit"); g_gameThread=GetCurrentThreadId();
    const DWORD heartbeat=shared.hostHeartbeat; shared.hostHeartbeat=GetTickCount()-6000;
    Check(command(0)!=0,"expired host blocks rescue edit"); shared.hostHeartbeat=heartbeat;
    DWORD oldProtection=0,unused=0;
    Check(VirtualProtect(reinterpret_cast<void*>(g_base+UseCountRva),2,PAGE_READONLY,&oldProtection)!=FALSE,"rescue fixture uses an actual read-only save page");
    Check(command(0)!=0,"read-only counter page blocks edit before mutation");
    VirtualProtect(reinterpret_cast<void*>(g_base+UseCountRva),2,oldProtection,&unused);
    At<uintptr_t>(0x2AE5760)=g_base+0x202000; At<float>(0x202000+216)=0.5f; At<float>(0x202000+220)=0.1f;
    At<uintptr_t>(MissionRva)=g_base+0x2A0F8B0; At<uintptr_t>(0x2A0F8B0+8)=g_base+0x203000;
    At<uint16_t>(0x203000+4)=0x200; snapshot();
    Check(Valid(176) && Valid(177) && shared.values[177]==17 && Valid(178) && fabs(shared.values[178]-12.5)<0.0001,
          "rescue readouts separate saved counters and compute the native roll threshold");
    Check(Valid(179) && shared.values[179]==1 && Valid(180) && shared.values[180]==0 && !Valid(181) && !Valid(182) && !Valid(183),
          "mission permission does not fabricate an active game-over or selected rescue");
    At<uint16_t>(UseCountRva)=999; snapshot(); Check(fabs(shared.values[178]-10)<0.0001,"large rescue exponent reaches the native minimum threshold");
    At<uint16_t>(UseCountRva)=0; snapshot(); Check(shared.values[178]==100,"zero rescue exponent produces a full roll threshold");
    At<float>(0x202000+216)=std::numeric_limits<float>::quiet_NaN(); snapshot();
    Check(!Valid(178) && Valid(176),"invalid battle parameters suppress only the derived rescue threshold"); At<float>(0x202000+216)=0.5f;
    At<uintptr_t>(0x2A0F8B0+8)=1; snapshot(); Check(!Valid(179),"unreadable mission resource is not reported as rescue permission");
    At<uintptr_t>(MissionRva)=0; snapshot(); Check(Valid(179) && shared.values[179]==0,"no mission publishes no native rescue permission");
    At<uintptr_t>(GameOverRva)=g_base+0x201000; At<int>(0x201000)=0; At<int>(0x201000+16)=6; At<BYTE>(0x201000+20)=1;
    snapshot(); Check(Valid(180) && shared.values[180]==1 && shared.values[181]==0 && shared.values[182]==6 && shared.values[183]==1,
                      "validated game-over state reports its native type phase and chosen rescue");
    At<int>(0x201000+16)=9; snapshot(); Check(!Valid(180) && !Valid(181) && !Valid(182) && !Valid(183),"invalid game-over layout suppresses state readouts");
    At<uintptr_t>(GameOverRva)=0; At<uint64_t>(0x9A98B0)=0; snapshot();
    Check(!Valid(176) && !Valid(177) && !Valid(178) && !Valid(179) && !Valid(180),"invalid loaded save publishes no stale rescue values");
    memcpy(reinterpret_cast<void*>(g_base+0x9A98B0),saved,sizeof(saved));
    At<uintptr_t>(0x2AE5760)=0; At<uintptr_t>(MissionRva)=0; At<uintptr_t>(GameOverRva)=0;
}
}
int main() {
    g_base = reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr, kImageSize, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!g_base) return 2;
    g_shared = &shared;
    SnapshotValue(128, 128.25); SnapshotValue(511, 511.75); SupportCapability(128); SupportCapability(511);
    Check(shared.validValues[2] == 1 && shared.validValues[7] == (uint64_t(1) << 63) &&
          shared.supportedCapabilities[2] == 1 && shared.supportedCapabilities[7] == (uint64_t(1) << 63),
          "extended snapshot masks preserve independent slot banks");
    Check(shared.values[128] == 128.25 && shared.values[511] == 511.75,
          "extended snapshot stores first new bank and final slot");
    SnapshotValue(512, 123); SupportCapability(512); SnapshotValue(511, std::numeric_limits<double>::infinity());
    Check(shared.reservedTail[0] == 0 && shared.values[511] == 511.75,
          "snapshot rejects out-of-range slots and non-finite values");
    ZeroMemory(&shared, sizeof(shared));
    g_gameThread = GetCurrentThreadId();
    shared.hostHeartbeat = GetTickCount();
    TypedMovementIntegrationTests();
    Request(1122, 7); TrainerFrame();
    Check(shared.responseSequence == shared.requestSequence && shared.resultCode == 1 &&
          wcsstr(shared.resultText, L"Choose a Drive Form") != nullptr,
          "wire command routes to Drive handler and rejects an out-of-range form before native dispatch");
    Request(1131, 0); TrainerFrame();
    Check(shared.responseSequence == shared.requestSequence && shared.resultCode == 1 &&
          wcsstr(shared.resultText, L"Gummi mission") != nullptr && !shared.sceneReady,
          "Gummi command reaches its independent module guard without a Sora scene");
    Check((shared.supportedCapabilities[1] & (uint64_t(63) << 58)) == (uint64_t(63) << 58) &&
          (shared.supportedCapabilities[2] & 0xffff) == 0xffff &&
          (shared.supportedCapabilities[3] & 7) == 7,
          "bridge publishes Drive Gummi and render capabilities across protocol banks");
    for (unsigned slot = 144; slot <= 159; ++slot)
        Check(Supported(slot), "bridge publishes every implemented Audio capability");
    for (unsigned slot = 160; slot <= 170; ++slot)
        Check(Supported(slot), "bridge publishes every implemented Motion capability");
    Check(!Supported(171) && !Supported(175), "reserved slots are not advertised as implemented");
    Check((shared.supportedCapabilities[2] & (uint64_t(255) << (176 % 64))) == (uint64_t(255) << (176 % 64)),
          "rescue capabilities cover exactly the allocated protocol range");
    Check((shared.supportedCapabilities[3] & (uint64_t(0x1ffffff) << 16)) == (uint64_t(0x1ffffff) << 16) &&
          (shared.supportedCapabilities[3] & (uint64_t(0x1ff) << 48)) == (uint64_t(0x1ff) << 48) &&
          !Supported(207) && !Supported(233) && !Supported(239) && !Supported(249),
          "Mission including event setters and Camera occupy their allocated protocol ranges");
    Check((shared.supportedCapabilities[4] & (uint64_t(0x3fffff) << 16)) == (uint64_t(0x3fffff) << 16) &&
          !Supported(271) && !Supported(294),
          "Damage tuning edits and diagnostics are exposed by the integrated bridge");
    Check((shared.supportedCapabilities[4] & (uint64_t(7) << 48)) == (uint64_t(7) << 48) &&
          !Supported(303) && !Supported(307),
          "Display preview actions are exposed by the integrated bridge");
    for(unsigned slot=320;slot<=329;++slot) Check(Supported(slot),"Gummi extra capability is integrated");
    for(unsigned slot=344;slot<=347;++slot) Check(Supported(slot),"Sora movement capability is integrated");
    for(unsigned slot=352;slot<=359;++slot) Check(Supported(slot),"Loot capability is integrated");
    for(unsigned slot=360;slot<=361;++slot) Check(Supported(slot),"Gummi projectile capability is integrated");
    for(unsigned slot=368;slot<=373;++slot) Check(Supported(slot),"Targeting capability is integrated");
    for(unsigned slot=376;slot<=391;++slot) Check(Supported(slot),"Collision capability is integrated");
    for(unsigned slot=392;slot<=407;++slot) Check(Supported(slot),"Renderer diagnostic capability is integrated");
    for(unsigned slot=408;slot<=418;++slot) Check(Supported(slot),"Spatial audio capability is integrated");
    for(unsigned slot=424;slot<=430;++slot) Check(Supported(slot),"Gummi editor capability is integrated");
    for(unsigned slot=431;slot<=438;++slot) Check(Supported(slot),"Window display capability is integrated");
    for(unsigned slot=447;slot<=455;++slot) Check(Supported(slot),"MSAA policy capability is integrated");
    for(unsigned slot : {319u,330u,343u,348u,351u,362u,367u,374u,375u,419u,420u,421u,422u,423u,439u,446u}) Check(!Supported(slot),"adjacent unused slots remain reserved");
    Request(1432,0); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"renderer") && !Valid(433),"maximize dispatch rejects an absent renderer before callout");
    Request(1424,0); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Gummi") && !Valid(426),"editor reset dispatch rejects an absent editor before callout");
    Request(1425,45); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Gummi") && !Valid(427),"preview FOV dispatch rejects an absent editor before callout");
    Request(1360,0); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Gummi") && !Valid(361),"projectile clear reaches Gummi guards without a mission");
    Request(1368,2); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Sora") && !Valid(368),"targeting dispatch requires a stable Sora scene");
    Request(1376,1); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Sora") && !Valid(376),"body-separation dispatch requires a stable Sora scene");
    Request(1320,20); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Gummi") && !Valid(320),
          "Gummi extra dispatch rejects absent ship and leaves its snapshot unavailable");
    Request(1344,2); TrainerFrame();
    Check(shared.resultCode!=0 && wcsstr(shared.resultText,L"Sora") && !Valid(344),
          "movement dispatch rejects absent Sora and leaves its snapshot unavailable");
    Request(1352,500); TrainerFrame();
    Check(shared.resultCode!=0 && !Valid(352),"loot dispatch rejects absent player status and publishes no value");
    Request(1226,30); TrainerFrame();
    Check(shared.responseSequence==shared.requestSequence && shared.resultCode!=0 && !At<uintptr_t>(0x2A0FF68) && !Valid(210),
          "Mission timer command is rejected without an active mission and publishes no invented clock value");
    Request(1240,30); TrainerFrame();
    Check(shared.responseSequence==shared.requestSequence && shared.resultCode==3 && wcsstr(shared.resultText,L"free camera") && !Valid(240),
          "Camera roll IPC reaches its own held-camera guard without changing native camera state");
    Request(1243,0); TrainerFrame();
    Check(shared.resultCode==3 && !camera_extra::pending.action && !Valid(245),
          "Camera action without a valid scene never queues a native follow request");
    Check(Valid(159) && shared.values[159] == 0 && !Valid(144) && !Valid(149) && !Valid(150) && !Valid(158),
          "absent audio engine publishes unavailable state without fabricated mixer values");
    Check(Valid(160) && shared.values[160] == 1 && Valid(161) && shared.values[161] == 0 &&
          Valid(170) && !Valid(162) && !Valid(163) && !Valid(164) && !Valid(169),
          "absent Sora scene publishes Motion configuration but no fabricated animation values");
    // Native entry regions remain zeroed, so all Audio commands must stop at
    // their function/engine guard before touching the uninitialized sound lock
    // or constructing a native audio controller.
    Check(!audio_mix::FunctionsReady(), "integration fixture cannot pass native Audio code validation");
    for (LONG command = 1144; command <= 1148; ++command) {
        Request(command, 50); TrainerFrame();
        Check(shared.responseSequence == shared.requestSequence && shared.resultCode == 1 &&
              wcsstr(shared.resultText, L"Audio control needs") != nullptr,
              "Audio mix and restore commands reach their native readiness guard through IPC");
    }
    Check(!At<uintptr_t>(audio_mix::DriverRva) && !At<uintptr_t>(audio_mix::MasterRva) &&
          !At<uintptr_t>(audio_mix::ListRva), "rejected Audio routing never fabricates or mutates mixer objects");
    Request(1150, 75); TrainerFrame();
    Check(shared.responseSequence == shared.requestSequence && shared.resultCode != 0 && !Valid(150),
          "Audio readout cannot be submitted as a gain command");
    Request(1160, 2.5); TrainerFrame();
    Check(shared.responseSequence == shared.requestSequence && shared.resultCode == 0 &&
          Valid(160) && shared.values[160] == 2.5 && Valid(161) && shared.values[161] == 0 && !shared.sceneReady,
          "Motion desired rate routes and snapshots without requiring or modifying a game Actor");
    Request(1160, 0); TrainerFrame();
    Check(shared.resultCode == 2 && wcsstr(shared.resultText, L"between 0.1 and 3.0") != nullptr &&
          shared.values[160] == 2.5, "Motion invalid rate is rejected by its own handler without replacing stored rate");
    Request(1161, 1); TrainerFrame();
    Check(shared.resultCode == 3 && wcsstr(shared.resultText, L"living Sora") != nullptr &&
          !motion_features::lease.enabled && !At<uintptr_t>(motion_features::kSlot),
          "Motion enable reaches Actor/resource guard before publishing a native callback");
    Request(1161, 0); TrainerFrame();
    Check(shared.resultCode == 0 && Valid(161) && shared.values[161] == 0 &&
          Valid(170) && shared.values[170] == motion_features::Disabled,
          "Motion disable is available during scene teardown and publishes its state");
    Request(1163, 30); TrainerFrame();
    Check(shared.resultCode == 1 && wcsstr(shared.resultText, L"read-only") != nullptr && !Valid(163),
          "Motion frame readout rejects seeking through the common command router");
    Request(1160, 1.5); shared.arguments[1] = std::numeric_limits<double>::quiet_NaN(); TrainerFrame();
    Check(shared.resultCode == 2 && shared.values[160] == 2.5 && !motion_features::lease.enabled,
          "common finite-argument validation runs before Motion configuration changes");
    Check(!(shared.snapshotSequence & 1) && Supported(159) && Supported(160) && Supported(170),
          "Audio and Motion routing preserves capability bank boundary and snapshot seqlock");
    At<BYTE>(0x9BA8D0) = 1;
    At<int>(0x716884) = 1;
    At<uintptr_t>(0x716868) = reinterpret_cast<uintptr_t>(managerData);
    At<uintptr_t>(0x9BA888) = reinterpret_cast<uintptr_t>(managerData);
    At<uintptr_t>(0x2A25370) = reinterpret_cast<uintptr_t>(itemData);
    const uintptr_t actor = reinterpret_cast<uintptr_t>(actorData);
    const uintptr_t status = g_base + 0x2A17290;
    At<uintptr_t>(0x2A105D0) = actor;
    PlayerField<uintptr_t>(actor, 1472) = status;
    PlayerField<unsigned>(actor, 1736) = 0x80;
    PlayerField<uint32_t>(status, 616) = EncodeFixture(actor);
    PlayerField<unsigned>(status, 608) = 1;
    PlayerField<int>(status, 0) = 100; PlayerField<int>(status, 4) = 100;
    PlayerField<int>(status, 384) = 100; PlayerField<int>(status, 388) = 100;
    PlayerField<BYTE>(status, 431) = 1;
    PlayerField<BYTE>(status, 433) = 2;
    PlayerField<BYTE>(status, 434) = 5;
    PlayerField<float>(actor, 1648) = 10; PlayerField<float>(actor, 1652) = 20; PlayerField<float>(actor, 1656) = 30;
    const uintptr_t save = g_base + 0x9ABDA0;
    PlayerField<uint32_t>(status, 592) = EncodeFixture(save);
    PlayerField<uint32_t>(status, 620) = EncodeFixture(save);
    At<uint32_t>(0x9A98B0) = 0x4A32484B; At<uint32_t>(0x9A98B4) = 0x3A;
    TrainerContext c = MakeTrainerContext(); TrainerResult result{};
    Check(c.player == actor && c.status == status && c.sceneReady, "fresh context resolves matching backlink");
    Check(PlayerLiving(c), "stable living player accepted");
    RescueTests(c);
    const uint32_t backlink = PlayerField<uint32_t>(status, 616);
    PlayerField<uint32_t>(status, 616) = 0;
    Check(MakeTrainerContext().player == 0, "missing backlink rejects actor/status pair");
    PlayerField<uint32_t>(status, 616) = backlink;
    At<BYTE>(0x9BA8D0) = 0;
    Check(!MakeTrainerContext().sceneReady && !MakeTrainerContext().status, "scene loss invalidates object context");
    At<BYTE>(0x9BA8D0) = 1;
    PlayerField<uint32_t>(actor, 0x9B8) = 4; Check(!PlayerLiving(c), "defeated actor rejected");
    PlayerField<uint32_t>(actor, 0x9B8) = 0;
    At<uintptr_t>(0x9BA928) = 1; Check(!PlayerLiving(c), "pending transition rejects writes"); At<uintptr_t>(0x9BA928) = 0;
    At<BYTE>(0x9BA8D1) = 1; Check(!PlayerLiving(c), "event-only scene rejects writes"); At<BYTE>(0x9BA8D1) = 0;
    PlayerField<int>(status, 4) = 256; Check(!PlayerLiving(c), "non-byte-safe HP maximum rejected"); PlayerField<int>(status, 4) = 100;
    PlayerField<float>(status, 448) = std::numeric_limits<float>::quiet_NaN(); Check(!PlayerLiving(c), "NaN recharge rejected"); PlayerField<float>(status, 448) = 0;
    Check(PlayerCommand(c, 7, 3, result) && !result.code && PlayerField<BYTE>(status, 433) == 3 && PlayerField<BYTE>(status, 432) == 0, "Drive write uses bars and fraction");
    PlayerCommand(c, 7, 5, result); Check(!result.code && PlayerField<BYTE>(status, 432) == 100, "full Drive uses fraction100");
    PlayerCommand(c, 7, 6, result); Check(result.code && PlayerField<BYTE>(status, 433) == 5, "Drive beyond unlocked cap rejected");
    PlayerCommand(c, 7, 2.5, result); Check(result.code && PlayerField<BYTE>(status, 433) == 5, "fractional Drive bars rejected");
    PlayerCommand(c, 7, std::numeric_limits<double>::quiet_NaN(), result); Check(result.code, "NaN Drive rejected");
    PlayerField<BYTE>(status, 431) = 2;
    PlayerCommand(c, 7, 1, result); Check(result.code && PlayerField<BYTE>(status, 433) == 5, "Drive write does not disrupt form");
    PlayerField<float>(status, 436) = 10; PlayerField<float>(status, 440) = 100;
    PlayerCommand(c, 21, 1, result); PlayerTick(c);
    Check(!result.code && PlayerField<float>(status, 436) == 100, "form hold copies maximum without enginecall");
    PlayerField<float>(status, 436) = 5; PlayerCommand(c, 21, 0, result); PlayerTick(c);
    Check(PlayerField<float>(status, 436) == 5, "disabled form hold preserves ongoing timer");
    PlayerCommand(c, 22, 1, result); PlayerTick(c); Check(PlayerField<float>(status, 436) == 5, "summon toggle does not affect form gauge");
    PlayerField<BYTE>(status, 431) = 3; PlayerTick(c); Check(PlayerField<float>(status, 436) == 100, "summon hold affects mode3");
    PlayerField<float>(status, 440) = std::numeric_limits<float>::infinity(); PlayerField<float>(status, 436) = 5; PlayerTick(c);
    Check(PlayerField<float>(status, 436) == 5, "infinite gauge maximum is rejected");
    PlayerField<float>(status, 440) = 100; PlayerReset(c);
    Check(!g_playerEffects[2] && !g_playerEffects[4], "reset clears all continuous toggles");
    PlayerCommand(c,16,0,result); Check(result.code&&!g_bookmarkValid,"bookmark rejects unobserved lifetime");
    PlayerCommand(c,46,1,result); Check(result.code&&!g_collision.active,"collision rejects unobserved lifetime");
    ObservePositionPlayer(c);
    PlayerCommand(c, 16, 0, result); Check(!result.code && g_bookmarkValid, "bookmark stores current player instance");
    auto bookmarkGeneration=g_bookmarkGeneration;
    Check(actor_lifetime::FindLocked(bookmarkGeneration)->pins==1,"bookmark pins generation");
    PlayerField<float>(actor,1648)=99;
    PlayerCommand(c,17,0,result);
    Check(!result.code&&positionCalls==1&&PlayerField<float>(actor,1648)==10,"bookmark returns through native ABI after generation proof");
    PlayerCommand(c,16,0,result);
    Check(actor_lifetime::FindLocked(bookmarkGeneration)->pins==1,"replacing bookmark on same actor balances pin");
    ReconstructPositionPlayer(c);
    PlayerCommand(c,17,0,result);
    Check(result.code&&positionCalls==1,"same-address new actor rejects old bookmark before native call");
    PlayerTick(c);
    Check(!g_bookmarkValid&&!g_bookmarkGeneration&&!actor_lifetime::FindLocked(bookmarkGeneration),"retired bookmark drops its pin");
    PlayerCommand(c,16,0,result);
    At<BYTE>(0x717009) = 1; PlayerCommand(c, 17, 0, result);
    Check(result.code, "bookmark restore rejects changed room before nativecall");
    PlayerTick(c); Check(!g_bookmarkValid, "observed room change discards bookmark");
    PlayerField<uint32_t>(actor, 1696) = EncodeFixture(actor);
    PlayerCommand(c, 16, 0, result); Check(result.code, "attached player world bookmark rejected");
    PlayerField<uint32_t>(actor, 1696) = 0;
    PlayerCommand(c, 0, 101, result); Check(result.code && PlayerField<int>(status, 0) == 100, "HP beyond maximum rejected before nativecall");
    PlayerCommand(c, 32, -1, result); Check(result.code, "negative permanent boost rejected");
    PlayerField<BYTE>(save, 9) = 100; PlayerCommand(c, 32, 1, result);
    Check(result.code && PlayerField<BYTE>(save, 9) == 100, "capped boost rejected before nativecall");
    PlayerCommand(c, 30, 1, result); Check(result.code, "missing progression tables reject Summon EXP");
    PlayerCommand(c, 31, 1, result); Check(result.code, "missing progression tables reject Form EXP");
    PlayerField<BYTE>(status, 431) = 1;
    PlayerField<uint32_t>(actor, 292) = 0x400; PlayerField<uint32_t>(actor, 2248) = 0x200;
    PlayerField<uintptr_t>(actor, 2312) = actor;
    PlayerCommand(c, 46, 1, result);
    Check(result.code && !g_collision.active && PlayerField<uint32_t>(actor, 292) == 0x400, "collision bypass rejects native pointer override");
    PlayerField<uintptr_t>(actor, 2312) = 0;
    PlayerField<uint32_t>(actor, 292) |= 0x40;
    PlayerCommand(c, 46, 1, result); Check(result.code && !g_collision.active, "collision bypass rejects pre-existing native bit");
    PlayerField<uint32_t>(actor, 292) &= ~0x40u;
    PlayerCommand(c, 46, 0.5, result); Check(result.code, "collision bypass rejects fractional toggle");
    PlayerCommand(c, 46, 1, result);
    Check(!result.code && g_collision.active && PlayerField<uint32_t>(actor, 292) == 0x440 &&
        PlayerField<uint32_t>(actor, 2248) == 0x1200 && !PlayerField<uintptr_t>(actor, 2312), "collision bypass sets only verified bits");
    PlayerField<uint32_t>(actor, 292) |= 0x800;
    PlayerCommand(c, 46, 0, result);
    Check(!result.code && !g_collision.active && PlayerField<uint32_t>(actor, 292) == 0xC00 &&
        PlayerField<uint32_t>(actor, 2248) == 0x200, "collision restoration preserves unrelated later bits");
    PlayerCommand(c, 46, 1, result);
    PlayerField<uintptr_t>(actor, 2312) = actor;
    PlayerReset(c);
    Check(!g_collision.active && (PlayerField<uint32_t>(actor, 292) & 0x40) &&
        PlayerField<uintptr_t>(actor, 2312) == actor, "collision reset preserves a later native pointer override");
    PlayerField<uintptr_t>(actor, 2312) = 0;
    PlayerField<uint32_t>(actor, 292) &= ~0x40u; PlayerField<uint32_t>(actor, 2248) &= ~0x1000u;
    PlayerCommand(c, 46, 1, result);
    PlayerField<uint32_t>(actor, 2248) &= ~0x1000u; PlayerReset(c);
    Check(!g_collision.active && (PlayerField<uint32_t>(actor, 292) & 0x40), "partial foreign collision edit relinquishes ownership");
    PlayerField<uint32_t>(actor, 292) &= ~0x40u;
    PlayerCommand(c, 46, 1, result); At<uintptr_t>(0x2A105D0) = 0; PlayerReset(c);
    Check(g_collision.active && g_collision.releasePending && (PlayerField<uint32_t>(actor, 292) & 0x40), "collision reset retains off-current lease without writes");
    PlayerCommand(c,46,1,result);
    Check(result.code&&g_collision.releasePending,"new collision acquire cannot replace unresolved lease");
    At<uintptr_t>(0x2A105D0) = actor;
    PlayerMaintainCollision();
    Check(!g_collision.active&&!(PlayerField<uint32_t>(actor,292)&0x40),"return to same living actor completes pending collision release");
    PlayerField<uint32_t>(actor, 292) &= ~0x40u; PlayerField<uint32_t>(actor, 2248) &= ~0x1000u;
    PlayerCommand(c, 46, 1, result); At<BYTE>(0x9BA8D0) = 0; PlayerTick(MakeTrainerContext());
    Check(!g_collision.active && !(PlayerField<uint32_t>(actor, 292) & 0x40) &&
        !(PlayerField<uint32_t>(actor, 2248) & 0x1000), "unready same-instance scene safely restores owned bits");
    At<BYTE>(0x9BA8D0) = 1;
    PlayerCommand(c, 46, 1, result); At<BYTE>(0x717009) = 2; PlayerTick(c);
    Check(g_collision.active && g_collision.releasePending && (PlayerField<uint32_t>(actor, 292) & 0x40), "new room retains unresolved collision lease without writes");
    const auto oldCollisionGeneration=g_collision.generation;
    ReconstructPositionPlayer(c); PlayerMaintainCollision();
    Check(!g_collision.active&&!actor_lifetime::FindLocked(oldCollisionGeneration)&&
        (PlayerField<uint32_t>(actor,292)&0x40),"same-address construction retires collision lease without clearing new actor flags");
    PlayerField<uint32_t>(actor, 292) &= ~0x40u; PlayerField<uint32_t>(actor, 2248) &= ~0x1000u;
    Request(1007, 3); TrainerFrame();
    Check(shared.responseSequence == shared.requestSequence && shared.resultCode == 0, "bridge acknowledges completed request");
    Check(shared.values[7] == 3 && Valid(0) && Valid(7), "snapshot publishes matching HP/Drive slots");
    Check(!(shared.snapshotSequence & 1), "snapshot sequence ends even");
    Check((shared.supportedCapabilities[0] & (uint64_t(1) << 45)) != 0, "player capability bits published");
    PlayerField<BYTE>(status, 433) = 1; TrainerFrame(); Check(PlayerField<BYTE>(status, 433) == 1, "completed sequence is not executed twice");
    Request(1007, 4); shared.arguments[1] = std::numeric_limits<double>::quiet_NaN(); TrainerFrame();
    Check(shared.resultCode != 0 && PlayerField<BYTE>(status, 433) == 1, "all arguments validated before mutation");
    Request(9999, 0); TrainerFrame(); Check(shared.resultCode != 0, "unknown command acknowledged as rejection");
    Request(1018, 1); TrainerFrame(); Check(shared.resultCode == 0 && g_playerEffects[0], "bridge enables player effect");
    Request(1114, 0); TrainerFrame(); Check(shared.resultCode == 0 && !g_playerEffects[0], "DisableAll clears player effects");
    Request(1112, 0); TrainerFrame(); Check(shared.resultCode == 0 && shared.command == Show, "core Show dispatches to developer command");
    Request(1113, 0); TrainerFrame(); Check(shared.resultCode == 0 && shared.command == Hide, "core Hide dispatches to developer command");
    Check(!HostHeartbeatFresh(10000, 0), "unpublished host heartbeat is not fresh");
    Check(HostHeartbeatFresh(10000, 5000) && !HostHeartbeatFresh(10000, 4999), "heartbeat expiry boundary uses actual timestamp");
    Check(HostHeartbeatFresh(32, 0xfffffff0u), "GetTickCount wrap preserves short elapsed duration");
    Check(!HostHeartbeatFresh(10000, 10001), "future heartbeat is rejected");
    g_playerEffects[2] = true; shared.hostHeartbeat = GetTickCount() - 6001; TrainerFrame();
    Check(g_hostExpired && !g_playerEffects[2], "heartbeat loss resets persistent effects");
    Request(1007, 5); TrainerFrame(); Check(shared.resultCode != 0 && PlayerField<BYTE>(status, 433) == 1, "expired host command rejected and acknowledged");
    shared.hostHeartbeat = GetTickCount() - 5500; Request(1007, 2); TrainerFrame();
    Check(g_hostExpired && shared.resultCode != 0 && PlayerField<BYTE>(status, 433) == 1, "changed but stale heartbeat cannot revive a queued command after game suspension");
    shared.hostHeartbeat = GetTickCount(); Request(1007, 2); TrainerFrame(); Check(!g_hostExpired && shared.resultCode == 0, "fresh heartbeat permits new serialized request");
    PlayerCommand(c,46,1,result);
    const auto pendingGeneration=g_collision.generation;
    At<uintptr_t>(0x2A105D0)=0;
    shared.hostHeartbeat=GetTickCount()-6001; TrainerFrame();
    Check(g_collision.active&&g_collision.releasePending&&actor_lifetime::FindLocked(pendingGeneration)->pins==1,
        "expired host retains off-current collision lease and pin");
    At<uintptr_t>(0x2A105D0)=actor; TrainerFrame();
    Check(g_hostExpired&&!g_collision.active&&!(PlayerField<uint32_t>(actor,292)&0x40),
        "actual frame finishes pending release while host remains expired");
    shared.hostHeartbeat=GetTickCount(); TrainerFrame();
    Request(1007, 4); shared.commandIssuedAt = GetTickCount() - 9000; TrainerFrame();
    Check(shared.resultCode == 4 && shared.responseSequence == shared.requestSequence && PlayerField<BYTE>(status, 433) == 2,
        "freshly reconnected host cannot replay an expired command");
    At<BYTE>(0x9BA8D0) = 0; TrainerFrame();
    Check(!shared.sceneReady && !Valid(0) && !Valid(7), "unavailable scene clears stale object values");
    Check(Valid(18) && Valid(22), "local toggle configuration remains readable");
    Request(1018, 0); TrainerFrame(); Check(shared.resultCode == 0, "disable accepted during scene teardown");
    At<BYTE>(0x9BA8D0) = 1;
    PlayerCommand(c, 46, 1, result); g_playerEffects[0] = true;
    Fail(GameException, L"Synthetic failure for restoration test.");
    Check(g_disabled && !g_collision.active && !g_playerEffects[0] &&
        !(PlayerField<uint32_t>(actor, 292) & 0x40), "fatal bridge failure releases owned effects on game thread");
    Check(shared.status == Failed && shared.errorCode == GameException, "failure is published after best-effort reset");
    // Separate synthetic fatal scenario: normal OnFrame must remain stopped even
    // if the original Actor later returns. Do not claim deferred failure recovery.
    g_disabled=0; shared.hostHeartbeat=GetTickCount();
    PlayerCommand(c,46,1,result);
    const auto fatalGeneration=g_collision.generation;
    At<uintptr_t>(0x2A105D0)=0;
    Fail(GameException,L"Synthetic off-current fatal reset.");
    Check(g_disabled&&g_collision.active&&g_collision.releasePending&&
        actor_lifetime::FindLocked(fatalGeneration)->pins==1&&(PlayerField<uint32_t>(actor,292)&0x40),
        "fatal off-current reset retains lease and pin without actor writes");
    At<uintptr_t>(0x2A105D0)=actor;
    const LONG stoppedFrameCount=shared.frameCount;
    OnFrame(nullptr,0);
    Check(shared.frameCount==stoppedFrameCount&&g_collision.active&&g_collision.releasePending&&
        (PlayerField<uint32_t>(actor,292)&0x40),"disabled OnFrame does not promise later collision cleanup");
    // Explicit fixture cleanup only; a real failed bridge cannot resume this way.
    g_disabled=0; PlayerMaintainCollision();
    Check(!g_collision.active&&!(PlayerField<uint32_t>(actor,292)&0x40),"fixture-only cleanup after fatal scenario");
    // A broken observer must not guess that a retained Actor died or is still ours.
    g_disabled=0; shared.hostHeartbeat=GetTickCount();
    PlayerCommand(c,16,0,result); PlayerCommand(c,46,1,result);
    const auto faultGeneration=g_collision.generation;
    Check(!result.code&&actor_lifetime::FindLocked(faultGeneration)->pins==2,"bookmark and collision own independent pins");
    At<uintptr_t>(actor_lifetime::kBirthSlot)=g_base+actor_lifetime::kBirth;
    const auto callsBeforeFault=positionCalls;
    PlayerCommand(c,17,0,result);
    Check(result.code&&positionCalls==callsBeforeFault,"observer loss rejects bookmark return without native call");
    PlayerReset(c);
    Check(!g_bookmarkValid&&g_collision.active&&g_collision.releasePending&&
        actor_lifetime::FindLocked(faultGeneration)->pins==1&&(PlayerField<uint32_t>(actor,292)&0x40),
        "observer fault drops read-only bookmark but retains unresolved collision ownership without writes");
    PlayerCommand(c,46,1,result);
    Check(result.code&&g_collision.generation==faultGeneration,"faulted observer cannot acquire a replacement collision lease");
    printf("%u checks, %u failures. Synthetic memory only; no game code executed.\n", checks, failures);
    VirtualFree(reinterpret_cast<void*>(g_base), 0, MEM_RELEASE);
    return failures ? 1 : 0;
}
