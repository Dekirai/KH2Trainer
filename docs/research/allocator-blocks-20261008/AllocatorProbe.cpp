// Private-process execution of verified retail bodies with recorded dependencies.
// No game process, native loader, real engine callbacks, or real semaphore.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <vector>
#include <set>
#include "NativeBodies.h"

using U = uintptr_t;
unsigned checks=0, failures=0;
unsigned waits=0, releases=0, creates=0, frees=0, sweeps=0, closes=0;
DWORD waitResult=WAIT_OBJECT_0;
bool createFails=false;
U image=0, dummy=0, lastWait=0, lastRelease=0, lastFreed=0, sweepStart=0, sweepEnd=0;
LONG initialCount=0, maximumCount=0;
U closeArgs[16]{};
template<class T=U> T& At(U p, size_t offset=0) { return *reinterpret_cast<T*>(p+offset); }
template<class T> T Fn(unsigned rva) { return reinterpret_cast<T>(image+rva); }
void Check(bool ok, const char* label) {
    ++checks; if(!ok) { ++failures; std::printf("FAIL %s\n", label); }
}
void Require(bool ok,const char* label) { Check(ok,label); if(!ok) std::exit(2); }
U __fastcall CreateStub(LONG initial,LONG maximum) {
    ++creates; initialCount=initial; maximumCount=maximum;
    return createFails ? 0 : dummy;
}
DWORD __fastcall WaitStub(U p) { ++waits; lastWait=p; return waitResult; }
BOOL __fastcall ReleaseStub(U p) { ++releases; lastRelease=p; return TRUE; }
void __fastcall FreeStub(U p) { ++frees; lastFreed=p; }
void __fastcall SweepStub(U first,U last) { ++sweeps; sweepStart=first; sweepEnd=last; }
BOOL WINAPI CloseStub(HANDLE h) { if(closes<16)closeArgs[closes]=reinterpret_cast<U>(h);++closes;return TRUE; }

void Jump(unsigned rva,U target) {
    const BYTE prefix[6]={0xff,0x25,0,0,0,0};
    std::memcpy(reinterpret_cast<void*>(image+rva),prefix,sizeof(prefix));
    At<U>(image+rva,6)=target;
}
void SetupImage() {
    image=reinterpret_cast<U>(VirtualAlloc(nullptr,0xC00000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    Require(image!=0,"private image allocation"); dummy=image+0x900000;
    std::set<U> codePages;
    for(const auto& b:nativeBodies) {
        std::memcpy(reinterpret_cast<void*>(image+b.rva),b.bytes,b.size);
        for(U page=(image+b.rva)&~U(4095);page<image+b.rva+b.size;page+=4096)codePages.insert(page);
    }
    const struct {unsigned rva;U target;} stubs[]={
        {0xFD9C0,reinterpret_cast<U>(CreateStub)}, {0xFDD90,reinterpret_cast<U>(WaitStub)},
        {0xFDC90,reinterpret_cast<U>(ReleaseStub)}, {0x4390A0,reinterpret_cast<U>(FreeStub)},
        {0x3A08F0,reinterpret_cast<U>(SweepStub)}};
    for(const auto& s:stubs) { Jump(s.rva,s.target);codePages.insert((image+s.rva)&~U(4095)); }
    const unsigned vtable[]={0x19C0C0,0x19C2B0,0x19C470,0x19C510,0x19C520,0x19C6E0,0x66F970,0x19C0AC};
    for(unsigned i=0;i<8;++i)At<U>(image+0x5B2BB0,8*i)=image+vtable[i];
    At<U>(image+0x57B368)=reinterpret_cast<U>(CloseStub); // original CloseHandle IAT, fixture import
    for(U page:codePages) { DWORD old=0;Require(VirtualProtect(reinterpret_cast<void*>(page),4096,PAGE_EXECUTE_READ,&old)!=FALSE,"code page RX"); }
    Require(FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(image),0xC00000)!=FALSE,"flush private instruction cache");
    for(const auto& b:nativeBodies)Check(!std::memcmp(reinterpret_cast<void*>(image+b.rva),b.bytes,b.size),"executed body equals verified capture");
}
void ResetFixture() {
    std::memset(reinterpret_cast<void*>(image+0x800000),0xcc,0x20000);
    At<U>(image+0xAC0FD8)=0;At<U>(image+0xAC0FD0)=0;
    At<U>(dummy,8)=0xCAFE;
    waits=releases=creates=frees=sweeps=closes=0;
    lastWait=lastRelease=lastFreed=sweepStart=sweepEnd=0;
    waitResult=WAIT_OBJECT_0;createFails=false;
}
U Init(size_t size=4096,unsigned misalignment=0) {
    return Fn<U(__fastcall*)(U,size_t)>(0x19C3A0)(image+0x800000+misalignment,size);
}
U Allocate(U arena,size_t size) { return Fn<U(__fastcall*)(U,size_t)>(0x19C2B0)(arena,size); }
void Free(U arena,U p) { Fn<void(__fastcall*)(U,U)>(0x19C470)(arena,p); }
U Used(U arena) { return Fn<U(__fastcall*)(U)>(0x19C520)(arena); }
U Capacity(U arena) { return Fn<U(__fastcall*)(U)>(0x19C510)(arena); }
void Poison(U header,unsigned size) {
    for(unsigned i=0;i<size;i+=4)Check(At<uint32_t>(header,i)==(i==8||i==12?0:0xEFACCAFEu),"freed block poison with zero predecessor field");
}

void BoundaryCases() {
    ResetFixture();Check(Init(176)==0 && creates==0,"constructor rejects strict 176-byte boundary");
    U a=Init(177);Require(a!=0,"177-byte arena accepted");
    Check(Capacity(a)==49 && Used(a)==0,"capacity excludes 128-byte allocator prefix");
    Check(Allocate(a,1)==0,"accepted arena can be too small for one minimum block");
    Check(waits==1 && releases==1,"failed allocation releases");
    for(unsigned shift=0;shift<16;++shift) {
        ResetFixture();a=Init(512,shift);Require(a!=0,"unaligned arena initializes");
        const U input=image+0x800000+shift;
        Check(a==((input+15)&~U(15)),"arena base aligns up to 16");
        Check(At<U>(a,64)==a+128 && At<U>(a,72)==input+512,"original end and aligned start");
        Check(Capacity(a)==input+512-a-128,"alignment reduces usable capacity");
        Check(creates==1 && initialCount==1 && maximumCount==1 && At<U>(image+0xAC0FD8)==dummy,"constructor creates shared binary semaphore");
        Check(At<U>(a,96)==At<U>(a,72) && At<U>(a,104)==0 && At<uint32_t>(a,112)==32 && At<U>(a,120)==a,"sentinel fields initialized");
    }
    for(unsigned n=1;n<=80;++n) {
        ResetFixture();a=Init();U p=Allocate(a,n);Require(p!=0,"small allocation exists");
        unsigned rounded=(n+15)&~15u, block=rounded+48;
        Check(p==a+160 && !(p&15),"first payload after prefix and 32-byte header");
        Check(At<uint32_t>(p-32,16)==block && At<U>(p-32,24)==a && Used(a)==block,"size includes rounded payload and 48-byte overhead");
        Check(At<U>(p,rounded)==0xDEADBEEFDEADBEEFULL && At<U>(p,rounded+8)==0x0123456787654321ULL,"both trailer markers");
        Check(lastWait==dummy && lastRelease==dummy && waits==1 && releases==1,"allocation semaphore calls balanced");
        Free(a,p);
        Check(sweeps==1 && sweepStart==p-32 && sweepEnd==p-32+block,"free passes exact block bounds to dependency stub");
        Check(Used(a)==0 && At<U>(a,88)==a+96 && At<U>(a,96)==At<U>(a,72),"free removes block and moves recent cursor to sentinel");
        Poison(p-32,block);
        Check(Allocate(a,n)==p,"freed address immediately reused without allocation generation");
    }
    ResetFixture();a=Init(512);Check(Allocate(a,0)==0 && Allocate(a,1024)==0,"zero and over-capacity requests fail");
    Free(a,0);Check(waits==3 && releases==3 && sweeps==0,"null locked free still waits and releases");
    waitResult=WAIT_FAILED;U p=Allocate(a,1);Require(p!=0,"native allocator ignores failed wait result");
    Free(a,p);Check(Used(a)==0 && waits==5 && releases==5,"native free also ignores failed wait result");
    ResetFixture();a=Init();p=Allocate(a,~size_t(0));Require(p!=0,"maximum-size request wraps to a 48-byte block");
    Check(Used(a)==48 && At<uint32_t>(p-32,16)==48 && At<U>(p)==0xDEADBEEFDEADBEEFULL,"wrapped size has zero rounded payload");
    Free(a,p);Check(Used(a)==0,"wrapped 48-byte block can be freed in fixture");
    ResetFixture();createFails=true;a=Init();Check(a!=0 && At<U>(image+0xAC0FD8)==0,"constructor publishes object even if semaphore helper returns null");
    p=Allocate(a,1);Check(p!=0 && lastWait==0 && lastRelease==0,"dependency failure behavior is unchecked with recording stubs");
}

void OrderingAndReset() {
    ResetFixture();U a=Init(512),p1=Allocate(a,16),p2=Allocate(a,16),p3=Allocate(a,16);
    Require(p1&&p2&&p3,"three blocks allocated");Free(a,p1);
    U p4=Allocate(a,16);Check(p4==p3+64,"cached recent block is preferred to an earlier free hole");
    Fn<void(__fastcall*)(U)>(0x19C6E0)(a);unsigned before=waits;
    Check(At<U>(a,88)==0 && Used(a)==192 && waits==before,"reset-last only clears cursor; getters are unlocked");
    U p5=Allocate(a,16);Check(p5==p1,"first-fit scan starts from sentinel after cursor reset");
    Free(a,p2);Check(At<U>(p3-32,8)==p5-32 && At<U>(p5-32)==p3-32,"middle removal repairs both links");
    // Capacity is the whole arena span, not free bytes or the largest free hole.
    Check(Capacity(a)==384 && Used(a)==192,"capacity is invariant under frees");
    U large=Allocate(a,129);Check(large==0,"aggregate free space does not imply a large contiguous allocation");
    std::memset(reinterpret_cast<void*>(p3),0x5a,16);before=sweeps;unsigned calls=waits;
    Fn<void(__fastcall*)(U)>(0x19C530)(a);
    Check(Used(a)==0 && At<U>(a,88)==0 && At<U>(a,96)==At<U>(a,72),"reset drops list and accounting");
    Check(sweeps==before && waits==calls && At<BYTE>(p3)==0x5a,"reset does not invoke free callback, wait, or poison payload");
    Check(Allocate(a,16)==p1,"reset makes old block addresses available again");
    p2=Allocate(a,16);calls=waits;before=releases;
    Fn<void(__fastcall*)(U,U)>(0x19C230)(a,p2);
    Check(waits==calls && releases==before && Used(a)==64,"unlocked free-like body has same unlink without semaphore");
    Poison(p2-32,64);before=sweeps;
    Fn<void(__fastcall*)(U,U)>(0x19C230)(a,0);Check(sweeps==before && waits==calls,"unlocked null free-like path has no dependency call");
}

void Destructors() {
    for(unsigned flag=0;flag<4;++flag) {
        ResetFixture();U a=Init();At<U>(a,16)=0x1111;At<U>(a,32)=0x2222;At<uint32_t>(a,56)=123;
        U result=Fn<U(__fastcall*)(U,unsigned)>(0x19C0C0)(a,flag);
        Check(result==a && At<U>(a)==image+0x5B13B0 && At<U>(a,8)==image+0x585700,"scalar dtor returns this and resets both vtables");
        Check(At<U>(image+0xAC0FD8)==0 && closes==3 && closeArgs[0]==0xCAFE && closeArgs[1]==0x2222 && closeArgs[2]==0x1111,"global semaphore and two thread handles closed in order");
        Check(At<U>(a,16)==0 && At<U>(a,32)==0 && At<uint32_t>(a,56)==0,"thread handle and ID fields cleared");
        Check(frees==((flag&1)?2u:1u) && lastFreed==((flag&1)?a:dummy),"only low flag bit adds allocator free to semaphore-wrapper free");
        Check(waits==0 && releases==0,"destructor does not acquire allocator semaphore");
    }
    ResetFixture();U a=Init();Fn<void(__fastcall*)(U)>(0x19C050)(a);
    Check(frees==1 && lastFreed==dummy && closes==1,"nondeleting destructor only releases wrapper");
    Fn<void(__fastcall*)(U)>(0x19C050)(a);Check(frees==1 && closes==1,"repeat nondeleting dtor sees cleared handles");
    ResetFixture();a=Init();U result=Fn<U(__fastcall*)(U,unsigned)>(0x19C0AC)(a+8,1);
    Check(result==a && frees==2 && lastFreed==a,"secondary-vtable adjustor subtracts eight before deleting dtor");
    ResetFixture();a=Init();At<U>(image+0xAC0FD0)=a;
    Fn<void(__fastcall*)(U,size_t)>(0x19C560)(image+0x810000,512);
    U next=At<U>(image+0xAC0FD0);
    Check(next==image+0x810000 && frees==2 && lastFreed==a && creates==2,"replacement destroys old global allocator before constructing and publishing new one");
    Fn<void(__fastcall*)(U,size_t)>(0x19C560)(image+0x800000,176);
    Check(At<U>(image+0xAC0FD0)==0 && At<U>(image+0xAC0FD8)==0 && frees==4,"failed replacement has already destroyed old global allocator");
    ResetFixture();a=Init();
    U other=Fn<U(__fastcall*)(U,size_t)>(0x19C3A0)(image+0x810000,512);
    Require(other!=0,"second independent arena initializes");
    Check(creates==1 && At<U>(image+0xAC0FD8)==dummy,"distinct arenas share one global semaphore wrapper");
    Fn<void(__fastcall*)(U)>(0x19C050)(a);
    Check(At<U>(image+0xAC0FD8)==0 && frees==1,"one arena destructor clears shared semaphore without instance reference count");
    U p=Allocate(other,1);
    Check(p!=0 && lastWait==0 && lastRelease==0,"remaining arena passes null semaphore to fixture dependencies after peer destruction");
}

struct Live {U p;unsigned requested,rounded;BYTE fill;};
void AllocationSequence() {
    ResetFixture();U a=Init(4096);std::vector<Live> live;uint32_t random=0xCAFE1234;
    for(unsigned step=0;step<1200;++step) {
        random=random*1664525u+1013904223u;
        if(!live.empty() && (random&3)==0) {
            size_t index=(random>>8)%live.size();Live b=live[index];Free(a,b.p);
            Poison(b.p-32,b.rounded+48);live.erase(live.begin()+index);
        } else {
            unsigned size=(random>>8)%257+1;U p=Allocate(a,size);
            if(p) {Live b{p,size,(size+15)&~15u,static_cast<BYTE>(step)};std::memset(reinterpret_cast<void*>(p),b.fill,size);live.push_back(b);}
        }
        std::sort(live.begin(),live.end(),[](const Live& left,const Live& right){return left.p<right.p;});
        U total=0,prev=a+96;
        for(const auto& b:live) {
            Check(At<U>(prev)==b.p-32 && At<U>(b.p-32,8)==prev,"sequence list links agree with independent sorted live intervals");
            Check(b.p>=a+160 && !(b.p&15) && b.p+b.rounded+16<=At<U>(a,72),"sequence interval stays aligned within arena");
            Check(At<U>(b.p-32,24)==a && At<uint32_t>(b.p-32,16)==b.rounded+48,"sequence owner and rounded extent");
            Check(At<U>(b.p,b.rounded)==0xDEADBEEFDEADBEEFULL && At<U>(b.p,b.rounded+8)==0x0123456787654321ULL,"sequence trailer markers intact");
            bool intact=true;for(unsigned i=0;i<b.requested;++i)intact&=At<BYTE>(b.p,i)==b.fill;
            Check(intact,"unrelated allocations and frees preserve survivor payload");
            if(prev!=a+96)Check(prev+At<uint32_t>(prev,16)<=b.p-32,"live intervals never overlap");
            prev=b.p-32;total+=b.rounded+48;
        }
        Check(At<U>(prev)==At<U>(a,72) && Used(a)==total,"sequence end sentinel and independent accounting");
        Check(Capacity(a)==3968 && waits==releases,"sequence fixed capacity and balanced helper calls");
    }
    for(const auto& b:live)Free(a,b.p);
    Check(Used(a)==0 && At<U>(a,96)==At<U>(a,72),"all sequence survivors removed");
}
int main() {
    SetupImage();BoundaryCases();OrderingAndReset();Destructors();AllocationSequence();
    Require(VirtualFree(reinterpret_cast<void*>(image),0,MEM_RELEASE)!=FALSE,"release private image");
    std::printf("AllocatorProbe checks=%u failures=%u\n",checks,failures);
    return failures?1:0;
}
