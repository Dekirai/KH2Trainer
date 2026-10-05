#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <limits>
#include <initializer_list>
namespace {
uintptr_t g_base=0;DWORD g_gameThread=0;
struct TrainerContext {uintptr_t base,player,status;bool sceneReady;};
struct Snapshot {double values[512];uint64_t valid[8],supported[8];} snapshot{};
bool Readable(const void* p,size_t count){
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p);
    if(!cursor||count>UINTPTR_MAX-cursor)return false;
    const uintptr_t end=cursor+count;
    while(cursor<end){MEMORY_BASIC_INFORMATION info{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&info,sizeof(info))||info.State!=MEM_COMMIT||
           (info.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return false;
        const DWORD protection=info.Protect&0xff;
        if(protection!=PAGE_READONLY&&protection!=PAGE_READWRITE&&protection!=PAGE_WRITECOPY&&
           protection!=PAGE_EXECUTE_READ&&protection!=PAGE_EXECUTE_READWRITE&&protection!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(info.BaseAddress)+info.RegionSize;
        if(next<=cursor)return false;cursor=next;
    }return true;
}
void SnapshotValue(unsigned slot,double value){snapshot.values[slot]=value;snapshot.valid[slot/64]|=uint64_t(1)<<(slot%64);}
void SupportCapability(unsigned slot){snapshot.supported[slot/64]|=uint64_t(1)<<(slot%64);}
#include "../../../trainer/Native/RenderFeatures.inl"
template<class T>T& Field(size_t offset){return *reinterpret_cast<T*>(g_base+renderstats::ObjectRva+offset);}
unsigned checks=0,failures=0;
TrainerContext c{};
void Check(bool ok,const char* label){++checks;if(!ok){++failures;printf("FAIL %s\n",label);}}
void Clear(){memset(snapshot.valid,0,sizeof(snapshot.valid));memset(snapshot.values,0,sizeof(snapshot.values));}
bool Valid(unsigned slot){return (snapshot.valid[slot/64]&(uint64_t(1)<<(slot%64)))!=0;}
bool None(){for(unsigned s=184;s<=194;++s)if(Valid(s))return false;return true;}
void Ready(){g_gameThread=GetCurrentThreadId();c={g_base,0,0,true};
    Field<uintptr_t>(0)=g_base+renderstats::VtableRva;Field<uintptr_t>(736)=g_base+0x1000;Field<uintptr_t>(1144)=g_base+0x2000;
    Field<uint32_t>(816)=1234;Field<int32_t>(96)=12;Field<int32_t>(108)=5;
    Field<uint32_t>(58244)=234;Field<uint32_t>(58232)=567;Field<uint32_t>(58236)=890;
    Field<int32_t>(22944)=1;Field<BYTE>(640)=1;Field<float>(23360)=1.25f;
    Field<uint32_t>(23364)=2;Field<uint32_t>(23368)=6;Clear();
}
void Unavailable(const char* label){Clear();RenderSnapshot(c);Check(None(),label);}
}
int main(){
    constexpr SIZE_T bytes=0x900000;
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,bytes,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    Ready();BYTE before[58248];memcpy(before,reinterpret_cast<const void*>(g_base+renderstats::ObjectRva),sizeof(before));
    RenderSnapshot(c);bool all=true;for(unsigned s=184;s<=194;++s)all&=Valid(s);Check(all,"all eleven diagnostics available for valid renderer");
    const double expected[]={1234,12,5,234,567,890,1,1,1.25,2,6};
    for(unsigned i=0;i<11;++i)Check(snapshot.values[184+i]==expected[i],"each diagnostic reads its verified offset and type");
    Check(memcmp(before,reinterpret_cast<const void*>(g_base+renderstats::ObjectRva),sizeof(before))==0,"snapshot makes no renderer writes");
    Field<uintptr_t>(0)=0;Unavailable("missing renderer vtable rejected");Ready();
    Field<uintptr_t>(0)=g_base+renderstats::VtableRva+8;Unavailable("foreign renderer vtable rejected");Ready();
    Field<uintptr_t>(736)=0;Unavailable("device teardown rejected");Ready();
    Field<uintptr_t>(1144)=0;Unavailable("presentation teardown rejected");Ready();
    c.sceneReady=false;Unavailable("unavailable main field scene omitted");Ready();
    c.base+=0x1000;Unavailable("foreign context base rejected");Ready();
    g_gameThread=0;Unavailable("unset engine thread rejected");Ready();
    ++g_gameThread;Unavailable("foreign thread rejected");Ready();
    DWORD old=0;
    const uintptr_t tail=(g_base+renderstats::ObjectRva+58244)&~uintptr_t(4095);
    VirtualProtect(reinterpret_cast<void*>(tail),4096,PAGE_NOACCESS,&old);
    Unavailable("unreadable final object page rejected before any sample");
    VirtualProtect(reinterpret_cast<void*>(tail),4096,old,&old);Ready();
    for(int value:{-1,48}){Field<int32_t>(96)=value;Clear();RenderSnapshot(c);Check(!Valid(185)&&Valid(184)&&Valid(186),"invalid program omitted without losing adjacent fields");}Ready();
    for(int value:{-1,6}){Field<int32_t>(108)=value;Clear();RenderSnapshot(c);Check(!Valid(186)&&Valid(185)&&Valid(187),"invalid target omitted individually");}Ready();
    for(int value:{-1,2}){Field<int32_t>(22944)=value;Clear();RenderSnapshot(c);Check(!Valid(190)&&Valid(189)&&Valid(191),"invalid boolean word omitted individually");}Ready();
    Field<BYTE>(640)=2;Clear();RenderSnapshot(c);Check(!Valid(191)&&Valid(190)&&Valid(192),"invalid boolean byte omitted individually");Ready();
    for(float value:{-1.f,0.f,10001.f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}){
        Field<float>(23360)=value;Clear();RenderSnapshot(c);Check(!Valid(192)&&Valid(191)&&Valid(193),"invalid scale is not published as zero or NaN");}Ready();
    Field<uint32_t>(23364)=4;Clear();RenderSnapshot(c);Check(!Valid(193)&&Valid(192)&&Valid(194),"invalid mode omitted individually");Ready();
    Field<uint32_t>(23368)=11;Clear();RenderSnapshot(c);Check(!Valid(194)&&Valid(193),"invalid quality omitted individually");Ready();
    Field<int32_t>(96)=47;Field<int32_t>(108)=5;Field<float>(23360)=10000;Field<uint32_t>(23364)=3;Field<uint32_t>(23368)=10;
    Clear();RenderSnapshot(c);Check(Valid(185)&&Valid(186)&&Valid(192)&&Valid(193)&&Valid(194),"inclusive upper policy bounds published");Ready();
    Field<int32_t>(96)=0;Field<int32_t>(108)=0;Field<int32_t>(22944)=0;Field<BYTE>(640)=0;Field<uint32_t>(23364)=0;Field<uint32_t>(23368)=0;
    Clear();RenderSnapshot(c);Check(Valid(185)&&Valid(186)&&Valid(190)&&Valid(191)&&Valid(193)&&Valid(194),"zero selectors and false flags remain valid values");Ready();
    for(size_t offset:{size_t(816),size_t(58244),size_t(58232),size_t(58236)})Field<uint32_t>(offset)=UINT32_MAX;
    Clear();RenderSnapshot(c);Check(snapshot.values[184]==4294967295.0&&snapshot.values[187]==4294967295.0&&snapshot.values[188]==4294967295.0&&snapshot.values[189]==4294967295.0,"unsigned counters retain full range without signed wrap");
    Field<uintptr_t>(0)=0;Clear();RenderSnapshot(c);Check(None(),"fresh snapshot does not retain values after renderer loss");
    RenderCapabilities();bool supported=true;for(unsigned s=184;s<=194;++s)supported&=(snapshot.supported[s/64]&(uint64_t(1)<<(s%64)))!=0;
    Check(supported,"implementation capabilities remain static while renderer unavailable");
    Check((snapshot.supported[183/64]&(uint64_t(1)<<(183%64)))==0&&(snapshot.supported[195/64]&(uint64_t(1)<<(195%64)))==0,"adjacent unowned slots remain unsupported");
    printf("RenderGuardTests: %u checks, %u failures\n",checks,failures);
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
