#pragma once
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

// Fixed retail normal-call contract, not a hook installer or a whole-process
// integrity proof. Prepare resolves and pins API modules before any suspension.
// Verify does not resolve/load modules. Serialize all calls on the installer
// thread and retain this object for process lifetime. External thread control,
// arbitrary callbacks, transient foreign code/data changes and inline changes
// to the trusted Windows/CRT APIs remain outside the supported native contract.
namespace status_bootstrap {
static_assert(sizeof(uintptr_t)==8,"Retail Win64 contract");
struct BodyPin { uint32_t rva;size_t size;int root;const unsigned char* bytes; };
struct ImportPin { uint32_t rva;const wchar_t* module;const char* name; };
#include "StatusBootstrapPins.inl"
constexpr unsigned BodyCount=sizeof(Bodies)/sizeof(Bodies[0]),ImportCount=sizeof(Imports)/sizeof(Imports[0]),RootCount=5;
constexpr uint32_t DispatchSlot=0x57bca0,DispatchThunk=0x5669f0,CookieSlot=0x7591f8;
constexpr uint32_t EventSlot=0x2af9b50,SleepSlot=0x2af9b58,WakeSlot=0x2af9b60;
static_assert(BodyCount==26 && ImportCount==6,"Exact researched closure and import boundary");
enum class Phase { Empty,Prepared,Gated,Fault };
enum class EntryMode { Original,FiveGates };
enum class Error { None,State,Module,Read,Header,Body,Import,Dispatch,Resolve,Configuration };
struct Range { uintptr_t begin=0,end=0; };
struct ApiTargets { uintptr_t imports[ImportCount]{};uintptr_t sleep=0,wake=0; };
struct Configuration { uintptr_t event=0,cookie=0,sleep=0,wake=0; };
using Read=bool (*)(void*,uintptr_t,void*,size_t,bool) noexcept;
struct Reader { Read read=nullptr;void* context=nullptr; };
inline uint64_t RotateRight(uint64_t value,unsigned bits) noexcept {
    bits&=63;return bits?((value>>bits)|(value<<(64-bits))):value;
}
inline uintptr_t Decode(uintptr_t encoded,uintptr_t cookie) noexcept {
    return RotateRight(encoded^cookie,static_cast<unsigned>(cookie&63));
}
inline bool Same(const Configuration& a,const Configuration& b) noexcept {
    return a.event==b.event && a.cookie==b.cookie && a.sleep==b.sleep && a.wake==b.wake;
}
inline bool NativeRead(void* context,uintptr_t address,void* output,size_t size,bool code) noexcept {
    const uintptr_t base=reinterpret_cast<uintptr_t>(context);
    if(!base || ImageSize>UINTPTR_MAX-base || address<base || address>=base+ImageSize || !size || size>base+ImageSize-address)return false;
    const uintptr_t end=address+size;uintptr_t cursor=address;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION mbi{};
        if(VirtualQuery(reinterpret_cast<const void*>(cursor),&mbi,sizeof(mbi))!=sizeof(mbi) ||
            mbi.AllocationBase!=reinterpret_cast<void*>(base) || mbi.Type!=MEM_IMAGE || mbi.State!=MEM_COMMIT ||
            (mbi.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return false;
        const DWORD access=mbi.Protect&255;
        const bool executable=access==PAGE_EXECUTE_READ || access==PAGE_EXECUTE_READWRITE || access==PAGE_EXECUTE_WRITECOPY;
        const bool readable=executable || access==PAGE_READONLY || access==PAGE_READWRITE || access==PAGE_WRITECOPY;
        if(!readable || (code && !executable))return false;
        const uintptr_t start=reinterpret_cast<uintptr_t>(mbi.BaseAddress);
        if(!mbi.RegionSize || mbi.RegionSize>UINTPTR_MAX-start || start>cursor || start+mbi.RegionSize<=cursor)return false;
        cursor=start+mbi.RegionSize;
    }
    SIZE_T copied=0;
    return ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const void*>(address),output,size,&copied) && copied==size;
}
inline bool PinAddress(uintptr_t address,bool code) noexcept {
    if(!address)return false;
    MEMORY_BASIC_INFORMATION mbi{};
    if(VirtualQuery(reinterpret_cast<const void*>(address),&mbi,sizeof(mbi))!=sizeof(mbi) ||
        mbi.Type!=MEM_IMAGE || mbi.State!=MEM_COMMIT || (mbi.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return false;
    const DWORD access=mbi.Protect&255;
    if(code && access!=PAGE_EXECUTE_READ && access!=PAGE_EXECUTE_READWRITE && access!=PAGE_EXECUTE_WRITECOPY)return false;
    HMODULE owner=nullptr;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
        reinterpret_cast<LPCWSTR>(address),&owner)!=FALSE;
}
// Only call before suspension and outside DllMain/metadata locks. Forwarders and
// API-set redirection are resolved by the trusted Windows loader. Both declaring
// module and actual export owner stay loaded. Mapping/protection is not an OS
// code authenticity proof; API inline hooks are outside this contract.
inline bool ResolveApis(ApiTargets& result,bool needConditionVariables) noexcept {
    ApiTargets candidate{};
    for(unsigned i=0;i<ImportCount;++i) {
        HMODULE module=LoadLibraryExW(Imports[i].module,nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!module)return false;
        const uintptr_t target=reinterpret_cast<uintptr_t>(GetProcAddress(module,Imports[i].name));
        const bool valid=target && PinAddress(reinterpret_cast<uintptr_t>(module),false) && PinAddress(target,true);
        FreeLibrary(module);
        if(!valid)return false;
        candidate.imports[i]=target;
    }
    if(needConditionVariables) {
        // Match the native initializer's module preference exactly. A reference
        // is acquired before export lookup, so the handle cannot be recycled.
        HMODULE module=nullptr;
        if(!GetModuleHandleExW(0,L"api-ms-win-core-synch-l1-2-0.dll",&module) &&
           !GetModuleHandleExW(0,L"kernel32.dll",&module))return false;
        candidate.sleep=reinterpret_cast<uintptr_t>(GetProcAddress(module,"SleepConditionVariableCS"));
        candidate.wake=reinterpret_cast<uintptr_t>(GetProcAddress(module,"WakeAllConditionVariable"));
        const bool valid=PinAddress(reinterpret_cast<uintptr_t>(module),false) &&
            PinAddress(candidate.sleep,true) && PinAddress(candidate.wake,true);
        FreeLibrary(module);
        if(!valid)return false;
    }
    result=candidate;return true;
}
class Contract {
    uintptr_t base=0;
    Reader reader{};ApiTargets targets{};Configuration originalConfig{};
    Phase phase=Phase::Empty;Error error=Error::None;
    bool Fail(Error why) noexcept {if(phase!=Phase::Fault)error=why;phase=Phase::Fault;return false;}
    bool ReadAt(uint32_t rva,void* output,size_t bytes,bool code=false) const noexcept {
        return reader.read && rva<ImageSize && bytes<=ImageSize-rva &&
            reader.read(reader.context,base+rva,output,bytes,code);
    }
    template<class T> bool Scalar(uint32_t rva,T& value) const noexcept {return ReadAt(rva,&value,sizeof(value));}
    bool Header() noexcept {
        IMAGE_DOS_HEADER dos{};IMAGE_NT_HEADERS64 nt{};
        if(!Scalar(0,dos) || !Scalar(PeOffset,nt))return Fail(Error::Read);
        return (dos.e_magic==IMAGE_DOS_SIGNATURE && static_cast<DWORD>(dos.e_lfanew)==PeOffset && nt.Signature==IMAGE_NT_SIGNATURE &&
            nt.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64 && nt.FileHeader.TimeDateStamp==TimeStamp &&
            nt.FileHeader.SizeOfOptionalHeader==sizeof(IMAGE_OPTIONAL_HEADER64) &&
            nt.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC && nt.OptionalHeader.SizeOfImage==ImageSize &&
            nt.OptionalHeader.DllCharacteristics==DllCharacteristics) || Fail(Error::Header);
    }
    bool Config(Configuration& value) noexcept {
        Configuration a{},b{};
        for(unsigned attempt=0;attempt<2;++attempt) {
            auto& c=attempt?b:a;
            if(!Scalar(EventSlot,c.event))return Fail(Error::Read);
            // Both pinned helpers test this handle before reading encoded slots.
            // Event mode never gives those unused slots a semantic meaning.
            if(!c.event && (!Scalar(CookieSlot,c.cookie) || !Scalar(SleepSlot,c.sleep) || !Scalar(WakeSlot,c.wake)))return Fail(Error::Read);
        }
        if(!Same(a,b))return Fail(Error::Configuration);
        if(!a.event && (!targets.sleep || !targets.wake || Decode(a.sleep,a.cookie)!=targets.sleep || Decode(a.wake,a.cookie)!=targets.wake))return Fail(Error::Configuration);
        value=a;return true;
    }
    bool Check(EntryMode mode,Configuration& config) noexcept {
        if(!Header())return false;
        unsigned char bytes[2048]{};
        for(const auto& body:Bodies) {
            if(body.size>sizeof(bytes) || !ReadAt(body.rva,bytes,body.size,true))return Fail(Error::Read);
            const unsigned char first=mode==EntryMode::FiveGates && body.root>=0?0xcc:body.bytes[0];
            if(bytes[0]!=first || memcmp(bytes+1,body.bytes+1,body.size-1))return Fail(Error::Body);
        }
        uintptr_t pointer=0;
        if(!Scalar(DispatchSlot,pointer))return Fail(Error::Read);
        if(pointer!=base+DispatchThunk)return Fail(Error::Dispatch);
        for(unsigned i=0;i<ImportCount;++i) {
            if(!Scalar(Imports[i].rva,pointer))return Fail(Error::Read);
            if(!targets.imports[i] || pointer!=targets.imports[i])return Fail(Error::Import);
        }
        return Config(config);
    }
    bool Initialize(uintptr_t module,Reader source,const ApiTargets& apis) noexcept {
        if(!module || ImageSize>UINTPTR_MAX-module || !source.read)return Fail(Error::Module);
        base=module;reader=source;targets=apis;
        Configuration config{};
        if(!Check(EntryMode::Original,config))return false;
        originalConfig=config;phase=Phase::Prepared;return true;
    }
public:
    Contract()=default;Contract(const Contract&)=delete;Contract& operator=(const Contract&)=delete;
    bool Prepare(uintptr_t module) noexcept {
        if(phase!=Phase::Empty)return Fail(Error::State);
        if(!module || module!=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr)) || ImageSize>UINTPTR_MAX-module)return Fail(Error::Module);
        base=module;reader={NativeRead,reinterpret_cast<void*>(module)};
        if(!Header() || !PinAddress(module,false))return Fail(Error::Module);
        uintptr_t event=0;if(!Scalar(EventSlot,event))return Fail(Error::Read);
        ApiTargets apis{};
        if(!ResolveApis(apis,event==0))return Fail(Error::Resolve);
        return Initialize(module,reader,apis);
    }
    // The sole forward transition is Prepared/Original -> Gated/FiveGates.
    // Original remains useful during preparation; after publication it can
    // never reauthorize removed gates. An observed failure is permanent.
    bool Verify(EntryMode mode) noexcept {
        if((phase!=Phase::Prepared && phase!=Phase::Gated) ||
            (mode!=EntryMode::Original && mode!=EntryMode::FiveGates) ||
            (phase==Phase::Gated && mode!=EntryMode::FiveGates))return Fail(Error::State);
        Configuration config{};
        if(!Check(mode,config))return false;
        if(!Same(config,originalConfig))return Fail(Error::Configuration);
        if(mode==EntryMode::FiveGates)phase=Phase::Gated;
        return true;
    }
    bool RootRanges(Range (&result)[RootCount]) const noexcept {
        if(phase!=Phase::Prepared && phase!=Phase::Gated)return false;
        for(unsigned i=0;i<RootCount;++i)result[i]={base+Bodies[i].rva,base+Bodies[i].rva+Bodies[i].size};
        return true;
    }
    Phase Status() const noexcept {return phase;}
    Error Failure() const noexcept {return error;}
#ifdef KH2_STATUS_BOOTSTRAP_CONTRACT_TESTS
    bool TestPrepare(uintptr_t module,Reader source,const ApiTargets& apis) noexcept {
        if(phase!=Phase::Empty)return Fail(Error::State);
        return Initialize(module,source,apis);
    }
#endif
};
} // namespace status_bootstrap
