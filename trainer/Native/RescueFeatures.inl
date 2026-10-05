// Native Mickey rescue selection and recorded statistics.
// Evidence: work/trainer/research/retry_gameover_evidence.json.
// Counter edits are one-time SaveData changes. No actor creation or RNG call.
namespace rescue_features {
constexpr uintptr_t UseCountRva=0x9AD660, AppearCountRva=0x9AD662;
constexpr uintptr_t GameOverRva=0x2AE8050, MissionRva=0x2A0FF68;
template<class T> T Field(uintptr_t object,SIZE_T offset) { return *reinterpret_cast<const T*>(object+offset); }
bool Range(uintptr_t object,SIZE_T bytes) { return object && Readable(reinterpret_cast<void*>(object),bytes); }
bool ContextReady(const TrainerContext& c) {
    return g_base && c.base==g_base && !g_disabled && g_gameThread==GetCurrentThreadId() &&
        g_shared && g_shared->hostHeartbeat && static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000 &&
        c.sceneReady && At<BYTE>(0x9BA8D0)==1 && !At<BYTE>(0x9BA8D1) && !At<uintptr_t>(0x9BA928) &&
        (At<int>(0x716884)==1 || At<int>(0x716884)==2) && Range(At<uintptr_t>(0x716868),72) &&
        Range(c.base+0x9A98B0,0x10FC0) && At<uint64_t>(0x9A98B0)==0x0000003A4A32484BULL;
}
bool MayChangeCount(const TrainerContext& c) {
    return ContextReady(c) && At<int>(0x716884)==1 && !At<BYTE>(0x9006B0) &&
        !At<uintptr_t>(0xAC0F48) && !At<uintptr_t>(GameOverRva) &&
        At<uintptr_t>(0x2A105D0)==c.player && Range(c.player,0xDE4) && Range(c.status,632) &&
        Field<uintptr_t>(c.player,1472)==c.status && DecodePacked(Field<uint32_t>(c.status,616))==c.player &&
        PlayerLiving(c) && Field<int>(c.status,608)==1 && At<uint16_t>(UseCountRva)<=999 &&
        Writable(reinterpret_cast<void*>(c.base+UseCountRva),sizeof(uint16_t));
}
}
bool RescueHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace rescue_features;
    if(slot!=176) return false;
    if(!IsInteger(args[0],0,999)) {
        result={1,L"Choose a whole Mickey rescue-use count from 0 to 999."}; return true;
    }
    if(!MayChangeCount(c)) {
        result={1,L"Changing the rescue-use count requires living Sora in stable gameplay, with no game-over sequence."}; return true;
    }
    At<uint16_t>(UseCountRva)=static_cast<uint16_t>(args[0]);
    result={0,L"Mickey rescue-use count changed. Native mission and party conditions still apply; saving can retain this value."};
    return true;
}
void RescueCapabilities() { for(unsigned slot=176;slot<=183;++slot) SupportCapability(slot); }
void RescueSnapshot(const TrainerContext& c) {
    using namespace rescue_features;
    if(!ContextReady(c)) return;
    const unsigned used=At<uint16_t>(UseCountRva), appearances=At<uint16_t>(AppearCountRva);
    if(used<=999) SnapshotValue(176,used);
    if(appearances<=999) SnapshotValue(177,appearances);
    const uintptr_t parameters=At<uintptr_t>(0x2AE5760);
    if(used<=999 && Range(parameters,224)) {
        const float decay=Field<float>(parameters,216), minimum=Field<float>(parameters,220);
        if(isfinite(decay) && decay>=0 && decay<=1 && isfinite(minimum) && minimum>=0 && minimum<=1)
            SnapshotValue(178,static_cast<double>(fmaxf(powf(decay,static_cast<float>(used)),minimum))*100);
    }
    const uintptr_t mission=At<uintptr_t>(MissionRva);
    if(!mission) SnapshotValue(179,0);
    else if(mission==c.base+0x2A0F8B0 && Range(mission,16)) {
        const uintptr_t resource=Field<uintptr_t>(mission,8);
        if(Range(resource,6)) SnapshotValue(179,(Field<uint16_t>(resource,4)&0x200)?1:0);
    }
    const uintptr_t gameOver=At<uintptr_t>(GameOverRva);
    if(!gameOver) { SnapshotValue(180,0); return; }
    if(!Range(gameOver,136)) return;
    const int kind=Field<int>(gameOver,0), phase=Field<int>(gameOver,16);
    const BYTE rescue=Field<BYTE>(gameOver,20);
    if(kind<0 || kind>3 || phase<0 || phase>8 || rescue>1) return;
    SnapshotValue(180,1); SnapshotValue(181,kind); SnapshotValue(182,phase); SnapshotValue(183,rescue);
}
