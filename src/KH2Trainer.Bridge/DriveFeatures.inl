// Forced native Drive transitions. Evidence: research archive (see README): drive_forced.*
// Included after ProgressionFeatures.inl inside TrainerBridge.cpp's anonymous
// namespace; reuses its audited read-only status-rebuild guards. No form-ID writes.
#include "PlayerRoleSupport.inl"
namespace drive_features {
constexpr BYTE kBeginBytes[] = {0x48,0x89,0x5c,0x24,0x10,0x57,0x48,0x83,0xec,0x20,0x8b,0xfa,0x48,0x8b,0xd9,0xe8,0xac,0xd8,0xfa,0xff,0x0f,0xb6,0x05,0x59,0xff,0x59,0x00,0x3b,0xf8,0x74,0x7c,0xb9};
using BeginFn = void (__fastcall *)(uintptr_t,int);
#ifdef KH2_DRIVE_TESTS
BeginFn testBegin = nullptr;
#endif
template<class T> const T& Field(uintptr_t p, SIZE_T offset) {
    return *reinterpret_cast<const T*>(p + offset);
}
bool Range(uintptr_t p, SIZE_T size) { return p && Readable(reinterpret_cast<const void*>(p), size); }
bool CodeReady() {
    return g_base && Range(g_base+0x40CE60,sizeof(kBeginBytes)) &&
        !memcmp(reinterpret_cast<const void*>(g_base+0x40CE60),kBeginBytes,sizeof(kBeginBytes));
}
bool AllowedThread() {
    return !g_disabled && g_shared && g_gameThread && g_gameThread==GetCurrentThreadId() &&
        g_shared->hostHeartbeat && static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000;
}
struct Table { uintptr_t rows=0; unsigned count=0, stride=0; };
bool ReadTable(uintptr_t pointer, unsigned stride, unsigned limit, Table& out) {
    if (!Range(pointer,8)) return false;
    const int count=Field<int>(pointer,4);
    if (count<1 || static_cast<unsigned>(count)>limit || !Range(pointer,8+static_cast<SIZE_T>(count)*stride)) return false;
    out={pointer+8,static_cast<unsigned>(count),stride}; return true;
}
uintptr_t FindWord(const Table& table, uint16_t id) {
    uintptr_t found=0;
    for (unsigned i=0;i<table.count;++i) {
        const uintptr_t row=table.rows+static_cast<SIZE_T>(i)*table.stride;
        if (Field<uint16_t>(row,0)==id) { if (found) return 0; found=row; }
    }
    return found;
}
bool ObjectAvailable(unsigned id) {
    if (!id) return false;
    // 3DFEB0 treats these IDs as context-sensitive aliases, not direct models.
    for(unsigned alias : {566u,567u,568u,571u,572u,573u,575u,576u,704u,793u,794u,1006u,1578u,1579u})
        if(id==alias) return false;
    for (unsigned t=0;t<3;++t) {
        const uintptr_t pointer=At<uintptr_t>(0x2A25030+t*sizeof(uintptr_t));
        if (!pointer) continue;
        Table objects;
        if (!ReadTable(pointer,96,65536,objects)) return false;
        unsigned previous=0;
        bool found=false, valid=false;
        for (unsigned i=0;i<objects.count;++i) {
            const uintptr_t row=objects.rows+static_cast<SIZE_T>(i)*96;
            const unsigned current=Field<unsigned>(row,0);
            if (i && current<=previous) return false;
            previous=current;
            if (current==id) { found=true; valid=Field<BYTE>(row,8)!=0 && memchr(reinterpret_cast<const void*>(row+8),0,32)!=nullptr; }
        }
        if (found) return valid;
    }
    return false;
}
bool ResourceAvailable(unsigned form) {
    // 405190 reads the room's form model table; base Sora uses world costume.
    unsigned index=form+11;
    if (!form) {
        const unsigned world=At<BYTE>(0x717008);
        if (world>=19) return false;
        const unsigned costume=At<BYTE>(0x9ACDE4+4*world)&31;
        if (costume>=18) return false;
        index=costume+8;
    }
    const unsigned id=At<uint16_t>(0x2A252F0+2*index);
    if(!ObjectAvailable(id)) return false;
    // Native selection is not a character-type check. A replaced model table
    // must not construct Roxas/another class as a requested Sora Drive form.
    for(unsigned t=0;t<3;++t) {
        const uintptr_t table=At<uintptr_t>(0x2A25030+t*sizeof(uintptr_t));
        if(!table) continue;
        Table objects; if(!ReadTable(table,96,65536,objects)) return false;
        for(unsigned i=0;i<objects.count;++i) {
            const uintptr_t row=objects.rows+static_cast<SIZE_T>(i)*96;
            if(Field<unsigned>(row,0)==id)
                return Field<uint16_t>(row,76)==1 && Field<signed char>(row,87)==static_cast<int>(form);
        }
    }
    return false;
}
#include "DriveWeaponSupport.inl"
bool CurrentCostumesReady() {
    const unsigned world=At<BYTE>(0x717008);
    if(world>=19) return false;
    for(unsigned i=0;i<4;++i) {
        const unsigned costume=At<BYTE>(0x9ACDE4+4*world+i)&31;
        if(costume==18) continue;
        if(costume>=18 || !ObjectAvailable(At<uint16_t>(0x2A25300+2*costume))) return false;
    }
    return true;
}
bool StatusPoolReady(const TrainerContext& c) {
    constexpr uintptr_t pool=0x2A17290;
    if(c.status<g_base+pool || c.status>=g_base+pool+80*632 || (c.status-g_base-pool)%632) return false;
    const int freeCount=At<int>(0x2A23950);
    if(freeCount<0 || freeCount>80) return false;
    bool free[80]{};
    for(int i=0;i<freeCount;++i) {
        const int index=At<int>(0x2A23810+4*i);
        if(index<0 || index>=80 || free[index]) return false;
        free[index]=true;
    }
    for(unsigned i=0;i<80;++i) {
        const uintptr_t status=g_base+pool+632*i;
        if(!free[i] && Field<int>(status,608)==1)
            return status==c.status && Field<int>(status,612)>0 && Field<int>(status,612)<0x7fffffff;
    }
    return false;
}
bool FormRecordReady(unsigned form,const progression::ItemTable& items,bool prepareWeapon=false) {
    if(!form) return true;
    const uintptr_t record=g_base+0x9ABDA0+3588+56*(form-1);
    const unsigned level=Field<BYTE>(record,2), weapon=Field<uint16_t>(record,0);
    const bool canReplace=prepareWeapon && (form==1 || form==4 || form==5);
    if(level>7 || (!canReplace && weapon && !progression::FindItem(items,weapon))) return false;
    uint16_t replacement=0;
    if(prepareWeapon && !PlanFormWeapon(form,items,replacement)) return false;
    for(unsigned i=0;i<24;++i) {
        const unsigned ability=Field<uint16_t>(record,8+2*i)&0x7fff;
        if(ability && !progression::AbilityItem(progression::FindItem(items,ability))) return false;
    }
    return true;
}
bool RebuildReady(const TrainerContext& c,unsigned requested) {
    progression::ItemTable items{};
    if(!progression::SaveReady(c) || !progression::Items(c,items) || !progression::RefreshDataReady(c,items) || !StatusPoolReady(c)) return false;
    const uintptr_t save=g_base+0x9ABDA0;
    const unsigned form=static_cast<unsigned>(Field<int>(c.player,3552));
    const uintptr_t expectedForm=form ? save+3588+56*(form-1) : 0;
    if(DecodePacked(Field<uint32_t>(c.status,592))!=save || DecodePacked(Field<uint32_t>(c.status,620))!=save ||
        DecodePacked(Field<uint32_t>(c.status,596))!=expectedForm) return false;
    const BYTE* level=nullptr;
    if(!progression::LevelRow(c,1,Field<BYTE>(save,15),level)) return false;
    for(unsigned offset : {0u,2u}) {
        const unsigned item=Field<uint16_t>(save,offset);
        if(item && !progression::FindItem(items,item)) return false;
    }
    for(unsigned kind=0;kind<2;++kind) {
        const unsigned count=Field<BYTE>(save,16+kind);
        if(count>8) return false;
        for(unsigned i=0;i<count;++i) {
            const unsigned item=Field<uint16_t>(save,20+kind*16+i*2);
            if(item && !progression::FindItem(items,item)) return false;
        }
    }
    for(unsigned i=0;i<80;++i) {
        const unsigned ability=Field<uint16_t>(save,84+2*i)&0x7fff;
        if(ability && !progression::AbilityItem(progression::FindItem(items,ability))) return false;
    }
    return FormRecordReady(form,items) && FormRecordReady(requested,items,true);
}
bool TimerReady(unsigned form) {
    if(!form) return true;
    const uintptr_t params=At<uintptr_t>(0x2AE5760);
    if(!Range(params,144)) return false;
    const float factor=Field<float>(params,104);
    int gauge=Field<BYTE>(g_base+0x9ABDA0+3588+56*(form-1),2)+3;
    if(form==6) {
        const int anti=Field<int>(params,140);
        if(anti<0 || anti>254) return false;
        gauge=anti+1;
    }
    return isfinite(factor) && factor>0 && isfinite(factor*static_cast<float>(gauge)) && factor*static_cast<float>(gauge)>0;
}
bool MessageText(uintptr_t text) {
    for(unsigned i=0;i<4096;++i) {
        if(!Range(text+i,1)) return false;
        if(!Field<BYTE>(text,i)) return true;
    }
    return false;
}
bool FindMessage(uintptr_t pointer,unsigned id,bool& found) {
    found=false; Table messages;
    if(!ReadTable(pointer,8,65536,messages)) return false;
    unsigned previous=0;
    for(unsigned i=0;i<messages.count;++i) {
        const uintptr_t row=messages.rows+8*i;
        const unsigned current=Field<uint16_t>(row,0);
        if(i && current<=previous) return false;
        previous=current;
        if(current==id) {
            const unsigned offset=Field<unsigned>(row,4);
            if(offset<8+8*messages.count || offset>0x1000000 || !MessageText(pointer+offset)) return false;
            found=true;
        }
    }
    return true;
}
bool FormMessageReady(unsigned form) {
    // Every new Sora clears message29; Anti copies it into one of six slots.
    Table commands;
    if(!ReadTable(At<uintptr_t>(0x2A11498),64,4096,commands)) return false;
    unsigned previous=0;
    for(unsigned i=0;i<commands.count;++i) {
        const unsigned id=Field<uint16_t>(commands.rows+64*i,0);
        if(i && id<=previous) return false;
        previous=id;
    }
    const uintptr_t row=FindWord(commands,29);
    if(!row || Field<BYTE>(row,36)>=6 || !Writable(reinterpret_cast<void*>(row),64) ||
        !Writable(reinterpret_cast<void*>(g_base+0x2A114A0),384)) return false;
    if(form!=6) return true;
    for(unsigned i=0;i<3;++i) {
        const uintptr_t pointer=At<uintptr_t>(0x2A11668+16*i);
        if(!pointer) continue;
        bool found=false;
        if(!FindMessage(pointer,50255&0x7fff,found)) return false;
        if(found) return true;
    }
    bool fallback=false;
    return FindMessage(At<uintptr_t>(0x2A11678),0xADC,fallback) && fallback;
}
bool ActorListReady(uintptr_t player) {
    uintptr_t seen[2048]{}; unsigned count=0; bool found=false;
    uintptr_t node=At<uintptr_t>(0x2A171C8);
    while(node) {
        if(count==2048 || !Range(node,2708)) return false;
        for(unsigned i=0;i<count;++i) if(seen[i]==node) return false;
        seen[count++]=node; found|=node==player;
        node=DecodePacked(Field<uint32_t>(node,2704));
    }
    return found;
}
bool LiveScene(const TrainerContext& c) {
    if(!AllowedThread() || player_role::Inspect(c).role!=player_role::Sora) return false;
    if (!AllowedThread() || c.base!=g_base || !c.sceneReady || !c.player || !c.status ||
        !At<BYTE>(0x9BA8D0) || At<BYTE>(0x9BA8D1) || At<int>(0x716884)!=1 ||
        At<uintptr_t>(0x9BA928) || At<BYTE>(0x9006B0) || At<uintptr_t>(0xAC0F48) ||
        At<BYTE>(0xABAC58) || At<BYTE>(0xABAC59) || At<BYTE>(0xABADE0) ||
        (At<unsigned>(0x2A11400)&0x20) || (At<unsigned>(0x2A10504)&2) || At<unsigned>(0x2A24EDC) ||
        At<uintptr_t>(0x2AE9FA8) || At<uintptr_t>(0x2A105D0)!=c.player ||
        !Writable(reinterpret_cast<void*>(c.player),3608) || !Writable(reinterpret_cast<void*>(c.status),632)) return false;
    if (Field<uintptr_t>(c.player,1472)!=c.status || DecodePacked(Field<uint32_t>(c.status,616))!=c.player ||
        Field<int>(c.status,608)!=1 || DecodePacked(Field<uint32_t>(c.player,0))!=g_base+0x750300 ||
        (Field<unsigned>(c.player,1736)&0x1000080)!=0x1000080 ||
        (Field<unsigned>(c.player,288)&0x10080100) || (Field<unsigned>(c.player,2488)&4) ||
        Field<uintptr_t>(c.player,3400) || Field<uint32_t>(c.player,1696) ||
        Field<int>(c.status,0)<=0 || Field<int>(c.status,0)>Field<int>(c.status,4) ||
        Field<int>(c.status,4)>255 || Field<BYTE>(c.status,433)>Field<BYTE>(c.status,434) ||
        Field<BYTE>(c.status,434)>9 || Field<int>(c.status,384)<0 || Field<int>(c.status,384)>Field<int>(c.status,388) ||
        Field<int>(c.status,388)>255 || !isfinite(Field<float>(c.status,436)) || !isfinite(Field<float>(c.status,440)) ||
        !isfinite(Field<float>(c.status,444)) || !isfinite(Field<float>(c.status,448)) ||
        Field<float>(c.status,444)<0 || Field<float>(c.status,444)>15300 || Field<float>(c.status,448)<0 || Field<float>(c.status,448)>15300 ||
        !Range(Field<uintptr_t>(c.player,3536),3048) ||
        !Range(DecodePacked(Field<uint32_t>(c.player,8)),96) ||
        !Range(DecodePacked(Field<uint32_t>(c.player,12)),16) ||
        !Range(Field<uintptr_t>(c.player,344),8)) return false;
    const int form=Field<int>(c.player,3552);
    if (form<0 || form>6 || At<BYTE>(0x9ACDD4)!=form) return false;
    const uintptr_t heap=At<uintptr_t>(0x9BA920);
    if (!Range(heap,8) || !Range(Field<uintptr_t>(heap,0),16) ||
        !Range(At<uintptr_t>(0x716868),72) || !Range(At<uintptr_t>(0x2A17180),72)) return false;
    const uintptr_t area=At<uintptr_t>(0x2A0FF68);
    if (area && (!Range(area,1708) || !Range(Field<uintptr_t>(area,8),16) || !isfinite(Field<float>(area,1704)))) return false;
    const int partyCount=At<int>(0x2AE9790);
    if (partyCount<0 || partyCount>2 || At<BYTE>(0x717008)>=19) return false;
    for (int i=0;i<partyCount;++i) {
        const int id=At<int>(0x2AE9788+4*i);
        if(id<0 || id>=18) return false;
        const unsigned object=At<uint16_t>(0x2A25300+2*id);
        if(object && !ObjectAvailable(object)) return false;
    }
    for (unsigned i=0;i<2;++i) {
        const uintptr_t ally=At<uintptr_t>(0x2A239B0+i*8);
        if (ally && (!Range(ally,2492) || !Range(DecodePacked(Field<uint32_t>(ally,8)),96))) return false;
    }
    return CodeReady() && ActorListReady(c.player) && CurrentCostumesReady();
}
void NativeBegin(uintptr_t actor,unsigned form) {
#ifdef KH2_DRIVE_TESTS
    if(testBegin) testBegin(actor,static_cast<int>(form));
#else
    // Native AL is not a success result. Confirm the queued context separately.
    reinterpret_cast<BeginFn>(g_base+0x40CE60)(actor,static_cast<int>(form));
#endif
}
enum Phase : unsigned { Idle=0,WaitingForBase=1,WaitingForForm=2,WaitingForRevert=3 };
enum Outcome : unsigned { None=0,Queued=1,Completed=2,Cancelled=3,SceneChanged=4,HostExpired=5,TimedOut=6,SafetyRejected=7,NativeQueueFailed=8 };
struct Queue {
    Phase phase=Idle; unsigned target=0; Outcome outcome=None;
    DWORD started=0; uintptr_t sourceActor=0,nativeContext=0,nativeTask=0,heap=0,fieldScheduler=0,actorScheduler=0;
    unsigned nativeForm=0;
    BYTE room[10]{};
} queue{};
constexpr DWORD kTimeout=30000;
void Finish(Outcome outcome) { queue.phase=Idle; queue.outcome=outcome; }
bool SameScene(const TrainerContext& c) {
    return c.base==g_base && c.sceneReady && At<BYTE>(0x9BA8D0) && !At<uintptr_t>(0x9BA928) &&
        !At<BYTE>(0x9BA8D1) && !At<BYTE>(0xABAC58) && !At<BYTE>(0xABAC59) &&
        At<uintptr_t>(0x9BA920)==queue.heap && At<uintptr_t>(0x716868)==queue.fieldScheduler &&
        At<uintptr_t>(0x2A17180)==queue.actorScheduler &&
        !memcmp(reinterpret_cast<const void*>(g_base+0x717008),queue.room,10);
}
bool CanStart(const TrainerContext& c,unsigned form) {
    return LiveScene(c) && RebuildReady(c,form) && ResourceAvailable(form) && FormSkeletonReady(c,form) && TimerReady(form) && FormMessageReady(form) &&
        // Direct400B20 may append two suspended partners; the fixed array is two.
        (!form || At<int>(0x2AE9790)==0);
}
bool Begin(const TrainerContext& c,unsigned form,Phase phase) {
    // The form's second weapon must exist before the asynchronous loader runs.
    // Re-plan after Revert using the new base actor's current equipment.
    // CanStart rechecks the bounded attachment row before any weapon write.
    progression::ItemTable items{}; uint16_t replacement=0;
    if(!CanStart(c,form) || !progression::Items(c,items) || !PlanFormWeapon(form,items,replacement)) {
        Finish(SafetyRejected); return false;
    }
    const uintptr_t weaponSlot=form ? g_base+0x9ABDA0+3588+56*(form-1) : 0;
    uint16_t previous=0;
    if(replacement) {
        if(!Writable(reinterpret_cast<void*>(weaponSlot),sizeof(uint16_t))) { Finish(SafetyRejected); return false; }
        previous=Field<uint16_t>(weaponSlot,0);
        *reinterpret_cast<uint16_t*>(weaponSlot)=replacement;
    }
    const uintptr_t source=c.player;
    NativeBegin(source,form);
    const uintptr_t native=At<uintptr_t>(0x2AE9FA8);
    if(!Range(native,56) || Field<uintptr_t>(native,0)!=source || Field<int>(native,8)!=static_cast<int>(form) ||
        !Range(Field<uintptr_t>(native,40),24)) {
        // With no native context, no asynchronous loader owns the assignment.
        // An unexpected live context keeps the valid weapon for engine cleanup.
        if(!native && replacement && Field<uint16_t>(weaponSlot,0)==replacement)
            *reinterpret_cast<uint16_t*>(weaponSlot)=previous;
        Finish(NativeQueueFailed); return false;
    }
    queue.sourceActor=source; queue.nativeContext=native; queue.nativeTask=Field<uintptr_t>(native,40);
    queue.nativeForm=form; queue.phase=phase; queue.outcome=Queued; return true;
}
void CaptureScene(const TrainerContext& c,unsigned requested) {
    queue={}; queue.target=requested; queue.started=GetTickCount();
    queue.heap=At<uintptr_t>(0x9BA920); queue.fieldScheduler=At<uintptr_t>(0x716868);
    queue.actorScheduler=At<uintptr_t>(0x2A17180);
    memcpy(queue.room,reinterpret_cast<const void*>(c.base+0x717008),10);
}
}

bool DriveHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace drive_features;
    if(slot!=122 && slot!=123 && slot!=126) return false;
    if(!AllowedThread()) { result={1,L"Drive requests require the game thread and a connected trainer."}; return true; }
    if(slot==126) {
        Finish(Cancelled);
        result={0,L"Pending trainer steps cancelled. A native transition already running will finish normally."}; return true;
    }
    if(slot==122 && !IsInteger(args[0],1,6)) { result={1,L"Choose a Drive Form from Valor through Antiform (1..6)."}; return true; }
    if(queue.phase!=Idle) { result={1,L"A Drive switch is already queued. Cancel its pending steps before another request."}; return true; }
    const unsigned target=slot==122?static_cast<unsigned>(args[0]):0;
    const auto role=player_role::Inspect(c).role;
    if(role==player_role::Roxas || role==player_role::Mickey || role==player_role::Other) {
        result={1,L"Drive Forms are available only for normal Sora. Roxas, Mickey and special player classes cannot use this transition."}; return true;
    }
    if(!LiveScene(c)) { result={1,L"Drive needs living, unattached Sora in a stable scene without a cutscene, summon, pause or transition."}; return true; }
    const unsigned current=static_cast<unsigned>(Field<int>(c.player,3552));
    if(!target && !current) { queue.target=0; Finish(Completed); result={0,L"Sora is already in base form."}; return true; }
    // Check requested resources before the first step, then revalidate everything
    // against the actual new Base Actor before the second step.
    if(!RebuildReady(c,target) || !ResourceAvailable(target) || !FormSkeletonReady(c,target) || !TimerReady(target) || !FormMessageReady(target) ||
        (current && !CanStart(c,0)) || (!current && !CanStart(c,target))) {
        Finish(SafetyRejected); result={1,L"The requested form's native actor, status, model or message data is not ready."}; return true;
    }
    CaptureScene(c,target);
    const unsigned first=current?0:target;
    const Phase phase=current?(target?WaitingForBase:WaitingForRevert):WaitingForForm;
    if(!Begin(c,first,phase)) { result={2,L"The native form transition was not queued; no automatic retry was made."}; return true; }
    result={0,current&&target ? L"Switch queued: Revert, then selected form. Missing second Keyblades use Sora's main weapon; unlocks and Drive bars are unchanged." :
        target ? L"Selected form queued. Missing second Keyblades use Sora's main weapon; no Drive cost or unlock change." : L"Native Revert queued."};
    return true;
}
void DriveTick(const TrainerContext& c) {
    using namespace drive_features;
    if(queue.phase==Idle) return;
    if(!AllowedThread()) { Finish(HostExpired); return; }
    if(!SameScene(c)) { Finish(SceneChanged); return; }
    if(static_cast<DWORD>(GetTickCount()-queue.started)>=kTimeout) { Finish(TimedOut); return; }
    const uintptr_t pending=At<uintptr_t>(0x2AE9FA8);
    if(pending) {
        // The engine can replace its in-flight context. Never follow somebody
        // else's transition with a trainer-owned second step.
        if(pending!=queue.nativeContext || !Range(pending,56) || Field<uintptr_t>(pending,0)!=queue.sourceActor ||
            Field<int>(pending,8)!=static_cast<int>(queue.nativeForm) || Field<uintptr_t>(pending,40)!=queue.nativeTask)
            Finish(SafetyRejected);
        return;
    }
    // A native Drive allocates the new Actor before deleting the old one.
    // Neither the Save form byte alone nor a cleared task pointer is completion.
    if(!c.player || c.player==queue.sourceActor || !c.status || !Range(c.player,3608) || !Range(c.status,632)) return;
    if(player_role::Inspect(c).role!=player_role::Sora) { Finish(SafetyRejected); return; }
    const unsigned expected=queue.phase==WaitingForForm?queue.target:0;
    if(Field<int>(c.player,3552)!=static_cast<int>(expected) || At<BYTE>(0x9ACDD4)!=expected) return;
    if(!LiveScene(c) || !RebuildReady(c,expected)) { Finish(SafetyRejected); return; }
    if(queue.phase==WaitingForBase) {
        if(!CanStart(c,queue.target)) { Finish(SafetyRejected); return; }
        Begin(c,queue.target,WaitingForForm);
    } else {
        if(expected && (Field<BYTE>(c.status,431)!=2 || Field<float>(c.status,436)<=0)) { Finish(SafetyRejected); return; }
        Finish(Completed);
    }
}
void DriveCapabilities() { for(unsigned slot=122;slot<=127;++slot) SupportCapability(slot); }
void DriveSnapshot(const TrainerContext&) {
    SnapshotValue(124,drive_features::queue.target); SnapshotValue(125,drive_features::queue.phase); SnapshotValue(127,drive_features::queue.outcome);
}
void DriveReset(const TrainerContext&) {
    using namespace drive_features;
    if(queue.phase!=Idle) Finish(AllowedThread()?Cancelled:HostExpired);
    // Never cancel/free the engine's active fiber, refund gauges or edit form IDs.
}
