// Native display previews, issued once on the verified application thread.
// Evidence: research archive (see README): render_controls_deep.* / display_implementation.*.
// The presentation thread shares this opaque MSVCP mutex. Never reinterpret it
// as a CRITICAL_SECTION, call a flush here, or write loaded configuration.
namespace display_preview {
constexpr uintptr_t ObjectRva=0x8A0970, VtableRva=0x5A9028, EpochRva=0x8AEEF0;
constexpr uintptr_t AppRva=0x79CF00, FieldsRva=0x715364, MutexOffset=30848;
constexpr BYTE BrightnessCode[]={0x0f,0xbf,0xc1,0x66,0x0f,0x6e,0xc0,0x0f,0x5b,0xc0,0xf3,0x0f,0x5e,0x05,0x7a,0xf1,0x0a,0x00,0xe9,0x09,0x07,0xc2,0xff};
constexpr BYTE ColorCode[]={0x0f,0xb7,0xc2,0x66,0x85,0xc9,0x75,0x0d,0x33,0xc0,0x0f,0xbf,0xc9,0x0f,0xbf,0xd0,0xe9,0xfb,0xfa,0xc1,0xff,0x66,0x83,0xf8,0x01,0x7d,0x10,0xb8,0x01,0x00,0x00,0x00,0x0f,0xbf,0xc9,0x0f,0xbf,0xd0,0xe9,0xe5,0xfa,0xc1,0xff,0x66,0x83,0xf8,0x0a,0x7e,0x05,0xb8,0x0a,0x00,0x00,0x00,0x0f,0xbf,0xd0,0x0f,0xbf,0xc9,0xe9,0xcf,0xfa,0xc1,0xff};
constexpr BYTE GammaCode[]={0x48,0x83,0xec,0x38,0x0f,0x29,0x74,0x24,0x20,0x0f,0x28,0xf0,0xe8,0x7f,0x58,0xff,0xff,0xf3,0x0f,0x10,0x0d,0xdb,0x33,0x48,0x00,0xf3,0x0f,0x11,0xb0,0xcc,0x02,0x00,0x00,0xf3,0x0f,0x58,0xf1,0xf3,0x0f,0x5e,0xce,0x0f,0x28,0x74,0x24,0x20,0xf3,0x0f,0x11,0x88,0x40,0x5b,0x00,0x00,0x48,0x83,0xc4,0x38,0xc3};
constexpr BYTE ColorSetterCode[]={0x48,0x89,0x5c,0x24,0x08,0x57,0x48,0x83,0xec,0x20,0x8b,0xfa,0x8b,0xd9,0xe8,0x3d,0x64,0xff,0xff,0x89,0x98,0x44,0x5b,0x00,0x00,0x48,0x8b,0x5c,0x24,0x30,0x89,0xb8,0x48,0x5b,0x00,0x00,0x48,0x83,0xc4,0x20,0x5f,0xc3};
constexpr BYTE GetterCode[]={0x40,0x53,0x48,0x83,0xec,0x30,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff,0x8b,0x0d,0x03,0xda,0x9d,0x02,0x65,0x48,0x8b,0x04,0x25,0x58,0x00,0x00,0x00,0xba,0x10,0x00,0x00,0x00,0x48,0x8b,0x0c,0xc8,0x8b,0x04,0x0a,0x39,0x05,0x70,0x2d,0x79,0x00,0x7f,0x0d,0x48,0x8d,0x05,0xe7,0x47,0x78,0x00,0x48,0x83,0xc4,0x30,0x5b,0xc3,0x48,0x8d,0x0d,0x5a,0x2d,0x79,0x00,0xe8,0xb5,0xdd,0x31,0x00,0x83,0x3d,0x4e,0x2d,0x79,0x00,0xff,0x75,0xde,0x48,0x8d,0x1d,0xc5,0x47,0x78,0x00,0x48,0x8b,0xcb,0xe8,0xbd,0xe0,0xfe,0xff,0x48,0x8d,0x0d,0xc6,0x60,0x45,0x00,0xe8,0xf1,0xd7,0x31,0x00,0x90,0x48,0x8d,0x0d,0x29,0x2d,0x79,0x00,0xe8,0x24,0xdd,0x31,0x00,0x48,0x8b,0xc3,0x48,0x83,0xc4,0x30,0x5b,0xc3};
constexpr BYTE LockCode[]={0xff,0x25,0x4e,0x07,0x14,0x00};
constexpr BYTE UnlockCode[]={0xff,0x25,0x40,0x07,0x14,0x00};
using MutexFn=int (__cdecl*)(void*);
using BrightnessFn=void (__fastcall*)(int16_t);
using ColorFn=void (__fastcall*)(int16_t,int16_t);
bool faulted=false; // an unsuccessful unlock leaves ownership uncertain
#ifdef KH2_DISPLAY_TESTS
MutexFn testLock=nullptr, testUnlock=nullptr;
BrightnessFn testBrightness=nullptr; ColorFn testColor=nullptr;
bool testRuntimeAvailable=true;
#endif
template<class T> T Field(uintptr_t p,SIZE_T offset=0) { return *reinterpret_cast<const T*>(p+offset); }
bool Range(uintptr_t p,SIZE_T size) { return p && Readable(reinterpret_cast<const void*>(p),size); }
template<SIZE_T N> bool Code(uintptr_t rva,const BYTE (&bytes)[N]) {
    return Range(g_base+rva,N) && !memcmp(reinterpret_cast<const void*>(g_base+rva),bytes,N);
}
bool ThreadReady(const TrainerContext& c) {
    return g_base && c.base==g_base && !g_disabled && !faulted && g_shared && g_gameThread &&
        GetCurrentThreadId()==g_gameThread && g_shared->hostHeartbeat &&
        static_cast<DWORD>(GetTickCount()-g_shared->hostHeartbeat)<=5000;
}
bool CodeReady() {
    return Code(0x5061A0,BrightnessCode) && Code(0x5061F0,ColorCode) &&
        Code(0x1268C0,GammaCode) && Code(0x125D00,ColorSetterCode) &&
        Code(0x11C150,GetterCode) && Code(0x43AD04,LockCode) && Code(0x43AD0A,UnlockCode) &&
        Range(g_base+0x5B532C,4) && Field<float>(g_base+0x5B532C)==50.0f &&
        Range(g_base+0x5A9CB4,4) && Field<float>(g_base+0x5A9CB4)==2.2f;
}
bool Runtime(MutexFn& lock,MutexFn& unlock) {
    if(!Range(g_base+0x57B450,16)) return false;
#ifdef KH2_DISPLAY_TESTS
    if(!testRuntimeAvailable) return false;
    lock=testLock; unlock=testUnlock;
#else
    // Use the runtime already referenced by the game's import table, not our
    // statically linked CRT. Resolve exact exports before trusting the IAT.
    const HMODULE runtime=GetModuleHandleW(L"MSVCP140.dll");
    if(!runtime) return false;
    lock=reinterpret_cast<MutexFn>(GetProcAddress(runtime,"_Mtx_lock"));
    unlock=reinterpret_cast<MutexFn>(GetProcAddress(runtime,"_Mtx_unlock"));
#endif
    return lock && unlock && Field<uintptr_t>(g_base+0x57B458)==reinterpret_cast<uintptr_t>(lock) &&
        Field<uintptr_t>(g_base+0x57B450)==reinterpret_cast<uintptr_t>(unlock);
}
struct Lease {
    uintptr_t object=0,app=0,device=0,root=0;
    HANDLE appThread=nullptr,timingThread=nullptr;
    MutexFn lock=nullptr,unlock=nullptr;
};
bool Ready(const TrainerContext& c,Lease& l) {
    if(!ThreadReady(c) || !CodeReady() || !Range(g_base+AppRva,8) ||
        !Range(g_base+EpochRva,4) || !g_selectedVtable) return false;
    const int epoch=Field<int>(g_base+EpochRva);
    if(epoch==0 || epoch==-1) return false; // uninitialized / construction in progress
    l.object=g_base+ObjectRva;
    if(!Range(l.object,MutexOffset+80) || Field<uintptr_t>(l.object)!=g_base+VtableRva ||
        !Writable(reinterpret_cast<void*>(l.object+716),4) ||
        !Writable(reinterpret_cast<void*>(l.object+23360),12) ||
        !Writable(reinterpret_cast<void*>(l.object+MutexOffset),80)) return false;
    l.app=Field<uintptr_t>(g_base+AppRva);
    l.device=Field<uintptr_t>(l.object,736); l.root=Field<uintptr_t>(l.object,1144);
    l.appThread=Field<HANDLE>(l.object,784); l.timingThread=Field<HANDLE>(l.object,792);
    DWORD timingExit=0;
    return Range(l.app,4756) && Field<uintptr_t>(l.app)==g_selectedVtable &&
        Field<uintptr_t>(l.object,1000)==l.app && Field<int>(l.app,4752)<0 &&
        Field<int>(l.object,808)==0 && Range(l.device,8) && Range(l.root,8) &&
        l.appThread && l.timingThread && l.appThread!=l.timingThread &&
        GetThreadId(l.appThread)==g_gameThread && GetThreadId(l.timingThread)!=0 &&
        GetThreadId(l.timingThread)!=g_gameThread &&
        GetProcessIdOfThread(l.timingThread)==GetCurrentProcessId() &&
        GetExitCodeThread(l.timingThread,&timingExit) && timingExit==STILL_ACTIVE &&
        Runtime(l.lock,l.unlock);
}
bool Same(const Lease& a,const Lease& b) {
    return a.object==b.object && a.app==b.app && a.device==b.device && a.root==b.root &&
        a.appThread==b.appThread && a.timingThread==b.timingThread &&
        a.lock==b.lock && a.unlock==b.unlock;
}
bool ColorPair(int type,int severity) {
    return type>=0 && type<=3 && (type==0?severity==0:(severity>=1&&severity<=10));
}
bool CurrentColor(uintptr_t object,int& type,int& severity) {
    type=Field<int32_t>(object,23364); severity=Field<int32_t>(object,23368);
    return ColorPair(type,severity);
}
struct Plan {
    bool brightness=false,color=false;
    int16_t level=0,type=0,severity=0;
    bool compare=false,restoring=false;
    int16_t expectedType=0,expectedSeverity=0;
};
bool Arguments(unsigned slot,const double* args,Plan& p) {
    if(slot!=305 && !args) return false;
    if(slot==304) {
        if(!IsInteger(args[0],-50,50)) return false;
        p.brightness=true; p.level=static_cast<int16_t>(args[0]);
    } else if(slot==306) {
        if(!IsInteger(args[0],0,3) || !IsInteger(args[1],1,10)) return false;
        p.color=true; p.type=static_cast<int16_t>(args[0]);
        p.severity=p.type?static_cast<int16_t>(args[1]):0;
    } else if(slot==464) {
        if(!IsInteger(args[0],0,1) || !IsInteger(args[1],0,3) || !IsInteger(args[2],0,10) ||
            !IsInteger(args[3],0,3) || !IsInteger(args[4],0,10)) return false;
        p.expectedType=static_cast<int16_t>(args[1]); p.expectedSeverity=static_cast<int16_t>(args[2]);
        p.type=static_cast<int16_t>(args[3]); p.severity=static_cast<int16_t>(args[4]);
        if(!ColorPair(p.expectedType,p.expectedSeverity) || !ColorPair(p.type,p.severity)) return false;
        p.compare=p.color=true; p.restoring=args[0]==1;
    }
    return true;
}
bool Loaded(Plan& p) {
    // Same SET- header as the existing audio restore contract. Copy all fields
    // before either setter, so the action never rereads a partially changed UI.
    if(!Range(g_base+0x715350,40) || memcmp(reinterpret_cast<const void*>(g_base+0x715350),"SET-",4) ||
        Field<unsigned>(g_base+0x715354)!=8 || Field<unsigned>(g_base+0x715358)!=508) return false;
    const int16_t level=Field<int16_t>(g_base+FieldsRva,12);
    const int16_t type=Field<int16_t>(g_base+FieldsRva,16);
    const int16_t severity=Field<int16_t>(g_base+FieldsRva,18);
    if(level < -50 || level>50 || type<0 || type>3 || (type && (severity<1 || severity>10))) return false;
    p={true,true,level,type,type?severity:int16_t(0)};
    return true;
}
void Brightness(int16_t level) {
#ifdef KH2_DISPLAY_TESTS
    testBrightness(level);
#else
    reinterpret_cast<BrightnessFn>(g_base+0x5061A0)(level);
#endif
}
void Color(int16_t type,int16_t severity) {
#ifdef KH2_DISPLAY_TESTS
    testColor(type,severity);
#else
    reinterpret_cast<ColorFn>(g_base+0x5061F0)(type,severity);
#endif
}
}
bool DisplayHandle(const TrainerContext& c,unsigned slot,const double args[8],TrainerResult& result) {
    using namespace display_preview;
    if((slot<304 || slot>306) && slot!=464) return false;
    Plan plan{};
    if(!Arguments(slot,args,plan)) {
        result={1,L"Use integer display arguments. Color pairs must be Off (0,0), or mode 1 to 3 with severity 1 to 10."}; return true;
    }
    Lease before{};
    if(!Ready(c,before)) { result={1,L"Display preview needs a live renderer and its normal application update."}; return true; }
    void* const mutex=reinterpret_cast<void*>(before.object+MutexOffset);
    if(before.lock(mutex)!=0) { result={1,L"The native display mutex could not be acquired."}; return true; }
    int unlockResult=0;
    __try {
        Lease current{};
        if(!Ready(c,current) || !Same(before,current))
            result={1,L"The display lifetime changed while waiting; no preview was applied."};
        else if(slot==305 && !Loaded(plan))
            result={1,L"The loaded display settings are invalid; no preview was applied."};
        else if(plan.compare) {
            int type=0,severity=0;
            if(!CurrentColor(current.object,type,severity))
                result={1,L"The current native color pair is invalid; no color change was applied."};
            else if(type!=plan.expectedType || severity!=plan.expectedSeverity)
                result={plan.restoring?0:1,plan.restoring?
                    L"The color filter changed after the effect. It was preserved; no restore was applied.":
                    L"The color filter changed before application. Read the current pair and retry."};
            else {
                // Compare and call on the application thread under the same presentation
                // mutex. Never reset brightness or loaded settings as a side effect.
                Color(plan.type,plan.severity);
                result={0,L"The matching color pair was replaced. Brightness and loaded settings were not changed."};
            }
        } else {
            // Both setters are pinned leaf-like native previews: no script,
            // scene replacement, save or resource-creation path is entered.
            if(plan.brightness) Brightness(plan.level);
            if(plan.color) Color(plan.type,plan.severity);
            result={0,slot==305?L"Loaded display settings applied. Configuration was not changed.":
                L"Display preview applied once. Later game settings can replace it."};
        }
    } __finally {
        // Captured and verified before locking; do not reread a possibly changed IAT.
        unlockResult=before.unlock(mutex);
    }
    if(unlockResult!=0) {
        faulted=true;
        result={2,L"The native display mutex reported an unlock error. Display previews are disabled until restart."};
    }
    return true;
}
void DisplayCapabilities() {
    for(unsigned slot=304;slot<=306;++slot) SupportCapability(slot);
    SupportCapability(464); SupportCapability(465);
}
void DisplaySnapshot(const TrainerContext& c) {
    using namespace display_preview;
    Lease before{};
    if(!Ready(c,before)) return;
    void* const mutex=reinterpret_cast<void*>(before.object+MutexOffset);
    if(before.lock(mutex)!=0) return;
    bool valid=false,colorValid=false; double value=0,colorValue=0; int unlockResult=0;
    __try {
        Lease current{};
        if(Ready(c,current) && Same(before,current)) {
            const float adjustment=Field<float>(current.object,716);
            if(isfinite(adjustment) && adjustment>=-1.0f && adjustment<=1.0f) {
                value=static_cast<double>(adjustment)*50.0; valid=true;
            }
            int type=0,severity=0;
            colorValid=CurrentColor(current.object,type,severity);
            if(colorValid) colorValue=type*16+severity;
        }
    } __finally { unlockResult=before.unlock(mutex); }
    if(unlockResult!=0) faulted=true;
    else {
        if(valid) SnapshotValue(304,value);
        if(colorValid) SnapshotValue(465,colorValue);
    }
}
void DisplayTick(const TrainerContext&) {} // one-time actions; no persistent override
void DisplayReset(const TrainerContext&) {} // deliberately does not undo completed previews
