// One-time native window requests. Include after DisplayFeatures and RendererDiagnostics.
// Evidence: research archive (see README): renderer_round6_contract.* and renderer_round7_window_*.
namespace window_display {
constexpr unsigned First=431,Last=438;
constexpr SIZE_T ResizeOffset=31432;
// Full original bodies; generated from the byte-verified read-only IDA evidence.
constexpr BYTE SetterCode[]={0x48,0x8b,0xc4,0x55,0x57,0x41,0x54,0x41,0x56,0x41,0x57,0x48,0x8d,0x6c,0x24,0xa0,0x48,0x81,0xec,0x60,0x01,0x00,0x00,0x48,0xc7,0x44,0x24,0x30,0xfe,0xff,0xff,0xff,0x48,0x89,0x58,0x10,0x48,0x89,0x70,0x18,0x48,0x8b,0x05,0xe9,0x41,0x63,0x00,0x48,0x33,0xc4,0x48,0x89,0x45,0x50,0x45,0x8b,0xf0,0x48,0x8b,0xf2,0x48,0x8b,0xf9,0x4c,0x8d,0xa1,0xc8,0x7a,0x00,0x00,0x4c,0x89,0x64,0x24,0x38,0x48,0x8d,0x05,0x8e,0x40,0x48,0x00,0x48,0x89,0x44,0x24,0x40,0x49,0x8b,0xcc,0xff,0x15,0x98,0x62,0x45,0x00,0x90,0xc6,0x87,0x01,0x04,0x00,0x00,0x00,0x32,0xc9,0x41,0x83,0xfe,0x01,0x0f,0x85,0xf1,0x00,0x00,0x00,0x48,0x8b,0x9f,0x40,0x04,0x00,0x00,0x48,0x89,0x5c,0x24,0x28,0xf3,0x0f,0x10,0x0e,0x0f,0x57,0xc0,0x45,0x33,0xc9,0x48,0x8b,0xcf,0x0f,0x2f,0xc1,0x72,0x23,0x45,0x8b,0xc6,0x48,0x8d,0x54,0x24,0x20,0xe8,0xf1,0x78,0xff,0xff,0xf3,0x0f,0x2c,0x4c,0x24,0x24,0xf3,0x0f,0x2c,0x44,0x24,0x20,0x89,0x44,0x24,0x20,0x89,0x4c,0x24,0x24,0xeb,0x7e,0xf3,0x44,0x0f,0x2c,0xf9,0x44,0x89,0x7c,0x24,0x20,0xf3,0x0f,0x2c,0x76,0x04,0x89,0x74,0x24,0x24,0x41,0xb8,0x20,0x00,0x00,0x00,0x48,0x8d,0x54,0x24,0x50,0xe8,0xb8,0x78,0xff,0xff,0x4c,0x63,0xc8,0x85,0xc0,0x7e,0x30,0x33,0xd2,0x0f,0x1f,0x40,0x00,0x66,0x66,0x66,0x0f,0x1f,0x84,0x00,0x00,0x00,0x00,0x00,0xf3,0x44,0x0f,0x2c,0x44,0xd4,0x54,0xf3,0x0f,0x2c,0x4c,0xd4,0x50,0x44,0x3b,0xf9,0x75,0x05,0x41,0x3b,0xf0,0x74,0x2c,0x48,0xff,0xc2,0x49,0x3b,0xd1,0x7c,0xe1,0x83,0xf8,0x01,0x7c,0x16,0xf3,0x0f,0x2c,0x44,0x24,0x50,0x89,0x44,0x24,0x20,0xf3,0x0f,0x2c,0x44,0x24,0x54,0x89,0x44,0x24,0x24,0xeb,0x09,0x48,0xc7,0x44,0x24,0x20,0x00,0x00,0x00,0x00,0x48,0x8b,0x44,0x24,0x20,0x48,0x89,0x87,0x40,0x04,0x00,0x00,0x3b,0xd8,0x75,0x17,0x8b,0x87,0x44,0x04,0x00,0x00,0x39,0x44,0x24,0x2c,0x75,0x0b,0x32,0xc9,0x48,0x8b,0x87,0x1c,0x04,0x00,0x00,0xeb,0x61,0xb1,0x01,0x48,0x8b,0x87,0x1c,0x04,0x00,0x00,0xeb,0x56,0x45,0x85,0xf6,0x75,0x58,0xf3,0x0f,0x10,0x1e,0x0f,0x28,0xd3,0xf3,0x0f,0x10,0x25,0x63,0x4b,0x48,0x00,0xf3,0x0f,0x59,0xd4,0xf3,0x0f,0x10,0x4e,0x04,0x0f,0x28,0xc1,0xf3,0x0f,0x59,0x05,0x57,0xea,0x4f,0x00,0x0f,0x2f,0xd0,0x72,0x06,0xf3,0x0f,0x5e,0xc4,0xeb,0x0e,0x0f,0x28,0xca,0xf3,0x0f,0x59,0x0d,0x19,0x4b,0x48,0x00,0x0f,0x28,0xc3,0xf3,0x0f,0x2c,0xc0,0x89,0x44,0x24,0x20,0xf3,0x0f,0x2c,0xc1,0x89,0x44,0x24,0x24,0x48,0x8b,0x44,0x24,0x20,0x48,0x89,0x87,0x08,0x04,0x00,0x00,0x41,0x83,0xfe,0x01,0x0f,0x94,0xc0,0x88,0x87,0x02,0x04,0x00,0x00,0x44,0x89,0xb7,0x04,0x04,0x00,0x00,0xc7,0x87,0x10,0x04,0x00,0x00,0x00,0x00,0x00,0x00,0x84,0xc9,0x75,0x31,0x3a,0x87,0x16,0x04,0x00,0x00,0x75,0x29,0x44,0x3b,0xb7,0x18,0x04,0x00,0x00,0x75,0x20,0x8b,0x87,0x1c,0x04,0x00,0x00,0x39,0x87,0x08,0x04,0x00,0x00,0x75,0x12,0x8b,0x87,0x20,0x04,0x00,0x00,0x39,0x87,0x0c,0x04,0x00,0x00,0x75,0x04,0x32,0xc0,0xeb,0x02,0xb0,0x01,0x88,0x87,0x00,0x04,0x00,0x00,0x49,0x8b,0xcc,0xff,0x15,0xca,0x60,0x45,0x00,0x48,0x8b,0x4d,0x50,0x48,0x33,0xcc,0xe8,0x4e,0x48,0x31,0x00,0x4c,0x8d,0x9c,0x24,0x60,0x01,0x00,0x00,0x49,0x8b,0x5b,0x38,0x49,0x8b,0x73,0x40,0x49,0x8b,0xe3,0x41,0x5f,0x41,0x5e,0x41,0x5c,0x5f,0x5d,0xc3};
constexpr BYTE CookieCode[]={0x48,0x3b,0x0d,0x91,0xf7,0x31,0x00,0xf2,0x75,0x12,0x48,0xc1,0xc1,0x10,0x66,0xf7,0xc1,0xff,0xff,0xf2,0x75,0x02,0xf2,0xc3,0x48,0xc1,0xc9,0x10,0xe9,0x53,0x06,0x00,0x00};
using SetterFn=void (__fastcall*)(void*,const float*,int);
using CriticalFn=void (WINAPI*)(LPCRITICAL_SECTION);
bool faulted=false;
#ifdef KH2_WINDOW_DISPLAY_TESTS
SetterFn testSetter=nullptr;
CriticalFn testEnter=nullptr,testLeave=nullptr;
bool testSystemRuntime=true;
#endif
void Latch() { faulted=display_preview::faulted=renderer_diagnostics::faulted=true; }
struct Lease {
    display_preview::Lease display{};
    HWND window=nullptr;
    DWORD windowThread=0;
    CriticalFn enter=nullptr,leave=nullptr;
};
bool Runtime(Lease& l) {
    using namespace display_preview;
    if(!Range(g_base+0x57B2D0,16))return false;
#ifdef KH2_WINDOW_DISPLAY_TESTS
    if(!testSystemRuntime)return false;
    l.enter=testEnter;l.leave=testLeave;
#else
    const HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    if(!kernel)return false;
    l.enter=reinterpret_cast<CriticalFn>(GetProcAddress(kernel,"EnterCriticalSection"));
    l.leave=reinterpret_cast<CriticalFn>(GetProcAddress(kernel,"LeaveCriticalSection"));
#endif
    return l.enter && l.leave && Field<uintptr_t>(g_base+0x57B2D8)==reinterpret_cast<uintptr_t>(l.enter) &&
        Field<uintptr_t>(g_base+0x57B2D0)==reinterpret_cast<uintptr_t>(l.leave);
}
bool Ready(const TrainerContext& c,Lease& l) {
    using namespace display_preview;
    if(faulted || renderer_diagnostics::faulted || !display_preview::Ready(c,l.display) ||
        !Code(0x124FE0,SetterCode) || !Code(0x439A60,CookieCode) ||
        !Range(g_base+0x7591F8,8) || !Field<uint64_t>(g_base+0x7591F8) ||
        (Field<uint64_t>(g_base+0x7591F8)>>48)!=0 ||
        !Range(g_base+0x5A9CBC,4) || Field<float>(g_base+0x5A9CBC)!=9.0f ||
        !Range(g_base+0x623BC4,4) || Field<float>(g_base+0x623BC4)!=16.0f ||
        !Range(g_base+0x5A9C9C,4) || Field<float>(g_base+0x5A9C9C)!=0.0625f ||
        !Range(l.display.object,ResizeOffset+sizeof(CRITICAL_SECTION)) ||
        !Writable(reinterpret_cast<void*>(l.display.object+1024),20) ||
        !Writable(reinterpret_cast<void*>(l.display.object+ResizeOffset),sizeof(CRITICAL_SECTION)) || !Runtime(l))return false;
    l.window=Field<HWND>(l.display.object,1008);
    DWORD process=0;
    l.windowThread=l.window?GetWindowThreadProcessId(l.window,&process):0;
    // The native window thread need not be the application-update thread.
    return l.window && IsWindow(l.window) && l.windowThread && process==GetCurrentProcessId();
}
bool Same(const Lease& a,const Lease& b) {
    return display_preview::Same(a.display,b.display) && a.window==b.window &&
        a.windowThread==b.windowThread && a.enter==b.enter && a.leave==b.leave;
}
struct State {
    int width=0,height=0,mode=0,requestedWidth=0,requestedHeight=0;
    bool pending=false;
};
bool Dimension(int v) { return v>=1 && v<=16384; }
bool CopyState(uintptr_t object,State& s) {
    using namespace display_preview;
    // Caller holds outer presentation mutex and the native resize CS.
    const BYTE pending=Field<BYTE>(object,1024),active=Field<BYTE>(object,1044);
    const BYTE requestedFullscreen=Field<BYTE>(object,1026),fullscreen=Field<BYTE>(object,1046);
    const int requestedMode=Field<int>(object,1028);
    const float retry=Field<float>(object,1040);
    const int transition=Field<int>(object,1072);
    s.width=Field<int>(object,8);s.height=Field<int>(object,12);s.mode=Field<int>(object,1048);
    s.requestedWidth=Field<int>(object,1032);s.requestedHeight=Field<int>(object,1036);
    if(pending>1 || active>1 || requestedFullscreen>1 || fullscreen>1 ||
        Field<BYTE>(object,1025)>1 || Field<BYTE>(object,1045)>1 ||
        requestedMode<0 || requestedMode>2 || s.mode<0 || s.mode>2 ||
        !isfinite(retry) || retry<0 || retry>60.0f || transition<0 || transition>3 ||
        !Dimension(s.width) || !Dimension(s.height) ||
        !Dimension(s.requestedWidth) || !Dimension(s.requestedHeight) ||
        !Dimension(Field<int>(object,1052)) || !Dimension(Field<int>(object,1056)))return false;
    // Native119E90 clears the retry to zero when its subtraction crosses zero.
    // +1064 suppresses the native WndProc size handler; do not compete with it.
    s.pending=pending!=0 || active!=0 || retry>0 || transition!=0 || Field<int>(object,1064)!=0;
    return true;
}
struct Plan { int mode=0;float dimensions[2]{}; };
bool Arguments(unsigned slot,const double* args,Plan& p) {
    if(slot==432) { p.mode=2;return true; }
    if(slot!=431 || !args || !IsInteger(args[0],640,7680) || !IsInteger(args[1],360,4320))return false;
    p.mode=0;p.dimensions[0]=static_cast<float>(args[0]);p.dimensions[1]=static_cast<float>(args[1]);return true;
}
void Set(uintptr_t object,const Plan& p) {
#ifdef KH2_WINDOW_DISPLAY_TESTS
    testSetter(reinterpret_cast<void*>(object),p.dimensions,p.mode);
#else
    reinterpret_cast<SetterFn>(g_base+0x124FE0)(reinterpret_cast<void*>(object),p.dimensions,p.mode);
#endif
}
bool Locked(const TrainerContext& c,const Lease& before,const Plan* plan,State& copied,TrainerResult& result) {
    Lease current{};
    if(!Ready(c,current) || !Same(before,current)) {
        result={1,L"The renderer or window changed while waiting. No request was queued."};return false;
    }
    auto* const cs=reinterpret_cast<LPCRITICAL_SECTION>(before.display.object+ResizeOffset);
    if(!TryEnterCriticalSection(cs)) {
        result={1,L"A native window request is busy. Try again after the resize finishes."};return false;
    }
    bool valid=false,completed=false;
    __try {
        Lease latest{};
        if(!Ready(c,latest) || !Same(before,latest) || !CopyState(latest.display.object,copied))
            result={1,L"The current native window state is unavailable. No request was queued."};
        else if(plan && copied.pending)
            result={1,L"A resize or display retry is already pending. Wait for it to finish."};
        else {
            if(plan) {
                // Mode0/2 have no callbacks, COM work or GPU waits. They only
                // recurse into this same Windows CS, copy a request, then leave.
                // Holding our outer recursion prevents a competing WndProc request
                // between the final pending check and the single native setter.
                Set(latest.display.object,*plan);
                result={0,L"Window request queued once. The game applies it on a later render frame; actual dimensions may be smaller."};
                // No old native pointer or request-field read after the call.
            }
            valid=true;
        }
        completed=true;
    } __finally {
        if(!completed)Latch();
        bool released=false;
        __try {
            // Release only the single recursion this module acquired. A failed
            // native call may have left a further recursion; never guess/retry.
            before.leave(cs);released=true;
        } __finally { if(!released)Latch(); }
    }
    return valid;
}
bool Execute(const TrainerContext& c,const Plan* plan,State& copied,TrainerResult& result) {
    Lease before{};
    bool valid=false;
    __try {
        if(!Ready(c,before)) {
            result={1,L"Window controls need the live game renderer, window and normal application update."};
            return false;
        }
        void* const mutex=reinterpret_cast<void*>(before.display.object+display_preview::MutexOffset);
        if(before.display.lock(mutex)!=0) {
            result={1,L"The native presentation mutex could not be acquired."};return false;
        }
        bool completed=false,released=false;
        __try { valid=Locked(c,before,plan,copied,result);completed=true; }
        __finally {
            if(!completed)Latch();
            __try { released=before.display.unlock(mutex)==0; }
            __finally { if(!released)Latch(); }
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { Latch(); }
    if(faulted) {
        result={2,L"A native window call or unlock failed. Renderer controls are disabled until the game is restarted."};
        return false;
    }
    return valid;
}
}
bool WindowDisplayHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace window_display;
    if(slot<431 || slot>432)return false;
    if(faulted || display_preview::faulted || renderer_diagnostics::faulted) {
        result={2,L"Renderer controls are disabled after a native fault. Restart the game before trying again."};return true;
    }
    Plan plan{};
    if(!Arguments(slot,args,plan)) {
        result={1,L"Choose whole-pixel width 640 to 7680 and height 360 to 4320. The game fits the result to 16:9."};return true;
    }
    State copied{};Execute(c,&plan,copied,result);return true;
}
void WindowDisplaySnapshot(const TrainerContext& c) {
    using namespace window_display;
    State copied{};TrainerResult result{};
    if(!Execute(c,nullptr,copied,result))return;
    SnapshotValue(433,copied.width);SnapshotValue(434,copied.height);SnapshotValue(435,copied.mode);
    SnapshotValue(436,copied.pending?1:0);SnapshotValue(437,copied.requestedWidth);SnapshotValue(438,copied.requestedHeight);
}
void WindowDisplayCapabilities() { for(unsigned s=431;s<=438;++s)SupportCapability(s); }
void WindowDisplayReset(const TrainerContext&) {} // no undo, auto replay, or fault-latch reset
void WindowDisplayFailureReset(const TrainerContext&) { window_display::Latch(); }
