#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define KH2_GUMMI_EDITOR_TESTS
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <limits>
#include <vector>
#include <initializer_list>
namespace {
uintptr_t g_base=0; DWORD g_gameThread=0; volatile LONG g_disabled=0;
struct TrainerContext { uintptr_t base,player,status; bool sceneReady; };
struct TrainerResult { LONG code; const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; double values[512]; uint64_t valid[8],supported[8]; } shared{};
Shared* g_shared=&shared;
template<class T>T& At(uintptr_t rva){return *reinterpret_cast<T*>(g_base+rva);}
bool afterCall=false, destroyAfterCall=false; unsigned postCallReads=0,calls=0;
uintptr_t watchRead=0; unsigned watchOrdinal=0,watchSeen=0; void(*onRead)()=nullptr;
bool Readable(const void* p,size_t count) {
    if(afterCall)++postCallReads;
    const uintptr_t start=reinterpret_cast<uintptr_t>(p);
    if(onRead && start==watchRead && ++watchSeen==watchOrdinal){auto f=onRead;onRead=nullptr;f();}
    if(!start || count>UINTPTR_MAX-start)return false;
    uintptr_t cursor=start;
    while(cursor<start+count) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m))||m.State!=MEM_COMMIT||
           (m.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return false;
        const DWORD protection=m.Protect&0xff;
        if(protection!=PAGE_READONLY && protection!=PAGE_READWRITE && protection!=PAGE_WRITECOPY &&
           protection!=PAGE_EXECUTE_READ && protection!=PAGE_EXECUTE_READWRITE && protection!=PAGE_EXECUTE_WRITECOPY)return false;
        const uintptr_t next=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
        if(next<=cursor)return false;cursor=next;
    }
    return true;
}
bool Writable(const void* p,size_t count) {
    if(!Readable(p,count))return false;
    uintptr_t cursor=reinterpret_cast<uintptr_t>(p),end=cursor+count;
    while(cursor<end) {
        MEMORY_BASIC_INFORMATION m{};
        if(!VirtualQuery(reinterpret_cast<const void*>(cursor),&m,sizeof(m)))return false;
        const DWORD protection=m.Protect&0xff;
        if(protection!=PAGE_READWRITE && protection!=PAGE_WRITECOPY && protection!=PAGE_EXECUTE_READWRITE && protection!=PAGE_EXECUTE_WRITECOPY)return false;
        cursor=reinterpret_cast<uintptr_t>(m.BaseAddress)+m.RegionSize;
    }
    return true;
}
uintptr_t DecodePacked(uint32_t value){return value?g_base+value:0;}
void SnapshotValue(unsigned s,double n){shared.values[s]=n;shared.valid[s/64]|=uint64_t(1)<<(s%64);}
void SupportCapability(unsigned s){shared.supported[s/64]|=uint64_t(1)<<(s%64);}
#include "../../src/KH2Trainer.Bridge/GummiEditorFeatures.inl"
#include "../../src/KH2Trainer.Bridge/GummiHistorySupport.inl"
constexpr uintptr_t Work=0xC00000, Editor=0xD80000, Camera=0xD90000, Cursor=0xDA0000;
constexpr uintptr_t Manager=0xDB0000, Objects=0xDB1000, Heap=0xDB2000, PartHeap=0xDB3000;
constexpr uintptr_t EditTask=0xDC0000, WorkTask=0xDC1000, CameraTask=0xDC2000, CursorTask=0xDC3000, Fiber=0xDC4000, Extra=0xDC5000;
constexpr size_t Allocation=0x3000000;
unsigned checks=0,failures=0,resetCalls=0,fovCalls=0;uintptr_t calledObject=0;int calledInt=-1;float calledAngle=0;
TrainerContext host{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
void FinishCall(){if(destroyAfterCall){At<uintptr_t>(0xAFBEF0)=0;At<uintptr_t>(0xAFC118)=0;}afterCall=true;}
void Node(uintptr_t rva,uintptr_t manager,uintptr_t previous,uintptr_t next,int priority,uintptr_t fn,uintptr_t cleanup,uintptr_t data,unsigned flags,uintptr_t fiber=0) {
    At<uintptr_t>(rva)=g_base+fn;At<uintptr_t>(rva+24)=g_base+data;At<uintptr_t>(rva+88)=g_base+manager;
    At<unsigned>(rva+96)=flags;At<int>(rva+100)=priority;At<uintptr_t>(rva+104)=g_base+cleanup;
    At<uintptr_t>(rva+112)=fiber?g_base+fiber:0;At<uintptr_t>(rva+120)=next?g_base+next:0;At<uintptr_t>(rva+128)=previous?g_base+previous:0;
}
void Ready(bool preview=false,bool tiny=false) {
    memset(reinterpret_cast<void*>(g_base),0,Allocation);memset(&shared,0,sizeof(shared));
    g_shared=&shared;g_disabled=0;g_gameThread=GetCurrentThreadId();shared.hostHeartbeat=GetTickCount();
    host={g_base,0,0,false};afterCall=destroyAfterCall=false;postCallReads=calls=resetCalls=fovCalls=0;onRead=nullptr;watchSeen=0;calledObject=0;calledInt=-1;calledAngle=0;
    At<uintptr_t>(gummi_editor::Module)=g_base+gummi_editor::ModuleVtable;At<uintptr_t>(gummi_editor::Module+8)=g_base+Manager;
    At<int>(gummi_editor::Module+16)=71;At<int>(gummi_editor::Module+36)=1;At<uintptr_t>(0x8EC5D8)=g_base+gummi_editor::Module;
    At<uintptr_t>(0xAFBEF0)=g_base+Work;At<uintptr_t>(0xAFC118)=g_base+Editor;
    At<uintptr_t>(0xAF9F08)=g_base+Manager;At<uintptr_t>(0xAFA700)=g_base+Objects;
    At<uintptr_t>(0xAFB420)=At<uintptr_t>(0x9A8800)=g_base+Heap;At<uintptr_t>(0xAFBA60)=g_base+PartHeap;
    At<BYTE>(0xAFC0C0)=tiny?1:0;At<int>(0xAFBEE8)=1;
    At<uintptr_t>(Work)=g_base+0x5B7330;At<uintptr_t>(Editor)=g_base+(tiny?0x5B7920:0x5B78D0);
    At<uintptr_t>(0x5B78D0+16)=At<uintptr_t>(0x5B7920+16)=g_base+0x26CBB0;
    At<BYTE>(Editor+8)=1;At<int>(Editor+12272)=1;At<int>(Editor+12276)=preview?4:1;
    At<uintptr_t>(Work+1414552)=g_base+Camera;At<uintptr_t>(Work+1414568)=g_base+Cursor;
    At<uintptr_t>(Work+1414576)=g_base+Editor+12016;At<uintptr_t>(Work+1414584)=g_base+Editor+1456;
    At<uintptr_t>(Camera)=g_base+0x5B7D48;At<uintptr_t>(Cursor)=g_base+0x5B7AC0;At<uintptr_t>(0x5B7D50)=g_base+0x290D00;
    At<uintptr_t>(Cursor+1344)=At<uintptr_t>(Cursor+2824)=g_base+Camera;At<unsigned>(Cursor+16)=1;At<int>(Cursor+2840)=1;
    At<int>(Camera+2356)=preview?1:0;At<float>(Camera+80)=1;At<float>(Camera+84)=At<float>(Camera+88)=At<float>(Camera+2592)=gummi_editor::Pi*.25f;
    At<float>(Camera+2596)=At<float>(Camera+2600)=gummi_editor::Pi*.25f;
    At<float>(Camera+92)=512;At<float>(Camera+96)=416;At<float>(Camera+2448)=.3f;At<float>(Camera+2452)=1;
    At<float>(Camera+2468)=gummi_editor::Pi*.5f;
    At<float>(0x73DD10)=-gummi_editor::Pi*.125f;At<float>(0x73DD14)=gummi_editor::Pi*.5f;
    At<float>(0x73DCD8)=gummi_editor::Pi*.25f;At<float>(0x73DCD4)=gummi_editor::Pi*(89.f/180.f);
    At<float>(Work+16)=At<float>(Work+20)=At<float>(Work+24)=16;
    At<uintptr_t>(Manager+16)=g_base+EditTask;At<uintptr_t>(Manager+24)=g_base+CameraTask;
    Node(EditTask,Manager,0,WorkTask,1000,0x2745A0,0x2745B0,Editor,0x80000,Fiber);
    Node(WorkTask,Manager,EditTask,CameraTask,43400,0x25E190,0x25E1A0,Work,2);
    Node(CameraTask,Manager,WorkTask,0,65000,0x272070,0x272090,Camera,0);
    At<uintptr_t>(Fiber)=g_base+Fiber+64;At<BYTE>(Fiber+24)=1;
    At<uintptr_t>(Objects+16)=At<uintptr_t>(Objects+24)=g_base+CursorTask;
    Node(CursorTask,Objects,0,0,20010,0x24C180,0x24C360,Cursor,2);
    At<int>(0x73EB50)=79;unsigned j=0;for(unsigned i=0;i<80;++i)if(i!=7)At<int>(0x73EA10+4*j++)=i;
    At<uintptr_t>(0x73DD90+7*40)=g_base+Camera;strcpy_s(reinterpret_cast<char*>(g_base+0x73DD90+7*40+8),32,"work area camera");
    for(const auto& sig:gummi_editor::signatures)memcpy(reinterpret_cast<void*>(g_base+sig.rva),sig.bytes,sig.size);
}
constexpr uintptr_t Cells=0xE00008, Indices=0xE10000, Scratch=0xE20008, Params=0xE30000;
constexpr uintptr_t Part0=0xE40000,Part1=0xE41000,PartTask0=0xE60000,PartTask1=0xE60100,ToolTask0=0xE70000,ToolTask1=0xE70100;
using gummi_history::Direction;using gummi_history::Error;using gummi_history::Snapshot;
uintptr_t Cell(unsigned i){return Cells+208*i;}
uintptr_t Hist(int slot=0,unsigned group=0,unsigned row=0){return Work+6256+352064*slot+64+176000*group+176*row;}
void Matrix(uintptr_t p){for(unsigned i=0;i<16;++i)At<float>(p+4*i)=(i%5==0)?1.f:0.f;}
void Record(uintptr_t p,unsigned id=20,unsigned anchor=0,bool decoration=false) {
    At<float>(p+12)=1;for(unsigned i=0;i<4;++i)At<float>(p+16+4*i)=1;Matrix(p+32);
    At<float>(p+96)=At<float>(p+100)=At<float>(p+104)=10;
    At<uint32_t>(p+112)=0x20;At<unsigned>(p+116)=id;At<uintptr_t>(p+120)=g_base+Camera;
    At<BYTE>(p+129)=2;At<BYTE>(p+131)=decoration?1:0;At<uintptr_t>(p+144)=g_base+Cell(anchor);
}
void MakePart(uintptr_t p,unsigned id,unsigned anchor,unsigned row,bool decoration) {
    At<uintptr_t>(p)=g_base+0x5B6FB0;At<unsigned>(p+16)=1;At<uintptr_t>(p+1344)=g_base+Camera;
    At<uintptr_t>(p+2264)=g_base+Params+128*row;At<unsigned>(p+2272)=0x20;
    At<unsigned>(p+2528)=anchor;At<unsigned>(p+2544)=id;Matrix(p+1448);
    for(unsigned i=0;i<4;++i)At<float>(p+1104+4*i)=1;
    At<float>(p+1672)=At<float>(p+1676)=At<float>(p+1680)=10;
    At<uint16_t>(Params+128*row)=static_cast<uint16_t>(id);At<BYTE>(Params+128*row+8)=decoration?4:0;
    At<BYTE>(Params+128*row+9)=At<BYTE>(Params+128*row+10)=At<BYTE>(Params+128*row+11)=1;
    At<uint16_t>(Params+128*row+12)=5;
    At<uintptr_t>(Cell(anchor)+(decoration?24:32))=g_base+p;
    At<uint16_t>(Indices+2*(anchor+(decoration?0:8)))=0x4005;
}
void Fixture(bool tiny=false) {
    Ready(false,tiny);At<unsigned>(Cursor+16)=5;At<int>(Cursor+2840)=19;At<int>(Cursor+2848)=19;
    At<int>(Work+112)=At<int>(Work+116)=At<int>(Work+120)=2;
    At<float>(Work+16)=At<float>(Work+20)=At<float>(Work+24)=10;
    At<uintptr_t>(Work+1414536)=g_base+Cells;At<uintptr_t>(Work+1414544)=g_base+Indices;At<uintptr_t>(Work+1414560)=g_base+Scratch;
    At<uint64_t>(Cells-8)=8;At<uint64_t>(Scratch-8)=16;
    for(unsigned i=0;i<8;++i) {
        unsigned x=i%2,y=(i/2)%2,z=i/4;At<int>(Cell(i)+16)=i;At<float>(Cell(i))=float(x)*10-5;At<float>(Cell(i)+4)=float(y)*10-5;At<float>(Cell(i)+8)=float(z)*10-5;At<float>(Cell(i)+12)=1;
        unsigned ns[]={y?i-2:i,y?i:i+2,x?i-1:i,x?i:i+1,z?i-4:i,z?i:i+4};
        for(unsigned j=0;j<6;++j)At<uintptr_t>(Cell(i)+56+8*j)=g_base+Cell(ns[j]);
    }
    At<int>(0x2B58B00)=2;At<uintptr_t>(0x2B58B08)=g_base+Params;
    MakePart(Part0,20,0,0,false);MakePart(Part1,21,7,1,true);
    At<uintptr_t>(0xAFBF40)=g_base+Part0;At<uintptr_t>(0xAFBF48)=g_base+Part1;At<uint32_t>(Part0+1444)=DWORD(Part1);
    At<uintptr_t>(0xAFA780)=g_base+Cursor;At<uintptr_t>(0xAFA788)=g_base+Part1;
    At<uint32_t>(Cursor+40)=DWORD(Part0);At<uint32_t>(Part0+40)=DWORD(Part1);
    At<uintptr_t>(Objects+16)=g_base+PartTask0;At<uintptr_t>(Objects+24)=g_base+CursorTask;
    Node(PartTask0,Objects,0,PartTask1,20000,0x24C180,0x24C360,Part0,2);
    Node(PartTask1,Objects,PartTask0,CursorTask,20000,0x24C180,0x24C360,Part1,2);
    Node(CursorTask,Objects,PartTask1,0,20010,0x24C180,0x24C360,Cursor,2);
    At<int>(Work+1414648)=1;At<int>(Work+1414652)=0;
    At<int>(Work+6256+28)=At<int>(Work+6256+32)=1;At<int>(Work+6256+352052)=1;
    Record(Hist(0,0));Record(Hist(0,1));
}
void Tool(int mode=11,bool fullBox=false) {
    At<int>(Editor+12276)=6;At<int>(Editor+12280)=1;At<unsigned>(Cursor+16)=1;At<int>(Cursor+2840)=At<int>(Cursor+2848)=mode;
    At<uintptr_t>(Cursor+2736)=g_base+Cell(0);
    if(fullBox){At<uintptr_t>(Cursor+2744)=g_base+Cell(0);At<uintptr_t>(Cursor+2752)=g_base+Cell(7);}
    At<uintptr_t>(0xAFCA38)=g_base+ToolTask0;At<uintptr_t>(0xAFCA40)=g_base+ToolTask1;
    Node(WorkTask,Manager,EditTask,ToolTask1,43400,0x25E190,0x25E1A0,Work,2);
    Node(ToolTask1,Manager,WorkTask,ToolTask0,46001,0x27F700,0,Cursor,0);At<uintptr_t>(ToolTask1+104)=0;
    Node(ToolTask0,Manager,ToolTask1,CameraTask,49000,0x27F8A0,0,Cursor,0);At<uintptr_t>(ToolTask0+104)=0;
    Node(CameraTask,Manager,ToolTask0,0,65000,0x272070,0x272090,Camera,0);
}
bool Capture(Snapshot& s,Direction d=Direction::Undo){Error e{};bool ok=gummi_history::Capture(d,s,e);if(!ok && s.valid)Check(false,"failure clears validity");return ok;}
void Reject(const char* name,Direction d=Direction::Undo){Snapshot s;Check(!Capture(s,d)&&!s.valid,name);}
void Accept(const char* name,Direction d=Direction::Undo){Snapshot s;Check(Capture(s,d)&&s.valid,name);}
}
int main() {
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,Allocation,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    for(bool tiny:{false,true}){Fixture(tiny);Snapshot a,b;Check(Capture(a)&&Capture(b)&&gummi_history::Same(a,b),"two complete equal menu snapshots");Check(a.parts.count==2&&a.cells.count==8&&a.history.count==2,"deep graph counts");}
    for(int mode=0;mode<27;++mode)for(bool box:{false,true}) {
        Fixture();Tool(mode,box);Snapshot s;
        const bool expected=(mode==2||mode==3||mode==4||mode==11||mode==13||mode==17||mode==19||mode==21||(mode==15&&!box));
        Check(Capture(s)==expected,"actual native mode matrix including mode15 completed box");
    }
    for(int phase:{-1,0,2,3,4,5,7,8,9,10,99}){Fixture();At<int>(Editor+12276)=phase;Reject("non-dispatch editor phase");}
    for(int previous:{1,2,3}){Fixture();Tool();At<int>(Editor+12280)=previous;Accept("main/list/palette return routes");}
    for(int previous:{0,4,6,9}){Fixture();Tool();At<int>(Editor+12280)=previous;Reject("invalid cursor return route");}
    Fixture();At<BYTE>(0xAFD1D8)=1;Reject("global input lock");
    Fixture();At<unsigned>(Editor+9072)=1;Reject("help overlay intercepts dispatch");
    Fixture();At<BYTE>(Editor+9073)=0x55;Accept("help gate is one byte, adjacent state is not a lock");
    Fixture();Tool();At<unsigned>(Cursor+2272)=2;Reject("cursor rotation in progress");
    Fixture();Tool();At<unsigned>(Cursor+2976)=8;Reject("special cursor menu");
    Fixture();Tool();At<int>(Cursor+2848)=13;Reject("pending mode commit");
    for(unsigned off:{2833u,2834u}){Fixture();Tool();At<BYTE>(Cursor+off)=1;Reject("button/initialization latch");}
    Fixture();Tool();At<unsigned>(Camera+2612)=0x10;Reject("camera suppresses cursor history input");
    Fixture();At<unsigned>(Camera+2612)=0x10;Accept("menu branch does not use cursor camera gate");
    Fixture();At<unsigned>(Cursor+16)=1;Reject("menu requires completed cursor exit");
    Fixture();At<unsigned>(Cursor+16)|=8;Reject("hidden cursor has pending activation");
    Fixture();Tool();At<unsigned>(Cursor+16)|=8;Reject("visible cursor pending activation");
    Fixture();Tool();At<uintptr_t>(Cursor+2752)=g_base+Cell(0);At<int>(Cursor+2840)=At<int>(Cursor+2848)=15;Accept("mode15 one-null corner accepted");
    for(auto global:{0xAFCA38u,0xAFCA40u}){Fixture();Tool();At<uintptr_t>(global)=0;Reject("missing transient owner");}
    for(auto task:{ToolTask0,ToolTask1})for(auto off:{0u,24u,88u,104u,112u}){Fixture();Tool();At<uintptr_t>(task+off)=g_base+Extra;Reject("transient task tuple");}
    Fixture();Tool();At<uintptr_t>(0xAFCA40)=g_base+ToolTask0;Reject("transient task alias");
    Fixture();At<uintptr_t>(0xAFCA38)=g_base+ToolTask0;Reject("menu exit did not retire transient task");
    for(auto o:{2736u,2744u,2752u,2760u}){Fixture();Tool();At<uintptr_t>(Cursor+o)=g_base+Cell(0)+1;Reject("unaligned cursor grid handle");}
    Fixture();At<uintptr_t>(Cursor+2744)=UINTPTR_MAX;Accept("hidden cursor may retain obsolete selection");
    Fixture();Tool();At<uintptr_t>(Cursor+2736)=0;Reject("visible cursor needs current cell");
    for(auto off:{112u,116u,120u})for(int bad:{0,-1,32769,INT32_MAX}){Fixture();At<int>(Work+off)=bad;Reject("dimension product bounded by packed root index");}
    Fixture();At<int>(Work+112)=32768;Reject("dimension product overflow boundary");
    for(auto addr:{Cells-8,Scratch-8}){Fixture();At<uint64_t>(addr)=0;Reject("native allocation count header");}
    for(auto off:{1414536u,1414544u,1414560u}){Fixture();At<uintptr_t>(Work+off)=0;Reject("released grid storage");}
    Fixture();At<uintptr_t>(Work+1414544)=g_base+Cells;Reject("grid storage overlap");
    for(unsigned cell=0;cell<8;++cell)for(unsigned n=0;n<6;++n){Fixture();At<uintptr_t>(Cell(cell)+56+8*n)=0;Reject("every exact clamped neighbor");}
    for(unsigned cell=0;cell<8;++cell){Fixture();At<int>(Cell(cell)+16)=8;Reject("cell index mismatch");}
    for(auto addr:{Work+16,Work+20,Work+24})for(float value:{0.f,-1.f,std::numeric_limits<float>::infinity()}){Fixture();At<float>(addr)=value;Reject("invalid cell scale");}
    Fixture();At<float>(Work+16)=std::numeric_limits<float>::max();Reject("finite scale dimension multiplication overflow");
    Fixture();At<float>(Cell(3))=std::numeric_limits<float>::quiet_NaN();Reject("nonfinite cell position");
    Fixture();At<uintptr_t>(Cell(1)+48)=g_base+Cells+1;Reject("noncell root pointer");
    Fixture();At<uintptr_t>(Cell(1)+48)=g_base+Cell(2);Reject("root has no owner");
    Fixture();At<uintptr_t>(Cell(1)+32)=g_base+Part0;Reject("part cannot own two anchors");
    Fixture();At<uint16_t>(Indices+2)=0x8000;Reject("nonzero empty-cell encoding");
    Fixture();At<uint16_t>(Indices+16)=0;Reject("anchor cost encoding mismatch");
    Fixture();At<BYTE>(Cell(0)+202)=1;Reject("anchor paint mismatch");
    Fixture();At<unsigned>(Part0+2272)=0;At<uint16_t>(Indices+16)=5;At<uintptr_t>(Cell(0)+48)=g_base+Cell(0);At<uintptr_t>(Cell(1)+48)=g_base+Cell(0);At<uint16_t>(Indices+18)=0x8000;Accept("multicell root graph");
    At<uint16_t>(Indices+18)=0x8002;Reject("covered cell root encoding");
    Fixture();At<unsigned>(Part0+2272)=0;At<uint16_t>(Indices+16)=5;At<uintptr_t>(Cell(0)+48)=g_base+Cell(0);At<uintptr_t>(Cell(7)+48)=g_base+Cell(0);At<uint16_t>(Indices+30)=0x8000;Reject("detached coverage island would survive native recursive clear");
    Fixture();At<uintptr_t>(Cell(0)+48)=g_base+Cell(0);Reject("single-cell special part cannot carry coverage root");
    for(auto global:{0xAFBF40u,0xAFBF48u,0xAFA780u,0xAFA788u}){Fixture();At<uintptr_t>(global)=0;Reject("list head/tail mismatch");}
    for(auto node:{Cursor,Part0,Part1}){Fixture();At<uint32_t>(node+40)=DWORD(node);Reject("cyclic object list");}
    Fixture();At<uint32_t>(Part0+1444)=DWORD(Part0);Reject("cyclic placed list");
    Fixture();At<uintptr_t>(0xAFA7A0)=At<uintptr_t>(0xAFA7A8)=g_base+Part0;Reject("placed object scheduled for deletion");
    Fixture();At<uintptr_t>(0xAFA7A0)=At<uintptr_t>(0xAFA7A8)=g_base+Extra;At<uint32_t>(Extra+52)=DWORD(Extra);Reject("deletion queue cycle");
    Fixture();At<uintptr_t>(0xAFA7A0)=At<uintptr_t>(0xAFA7A8)=g_base+Extra;Accept("unrelated deferred deletion retained in snapshot");
    for(auto p:{Part0,Part1}) {
        for(auto off:{0u,1344u,2264u}){Fixture();At<uintptr_t>(p+off)=0;Reject("part class/camera/parameter identity");}
        Fixture();At<unsigned>(p+16)|=2;Reject("part pending destruction");
        Fixture();At<unsigned>(p+2272)|=0x100;Reject("preview ghost on placed list");
        Fixture();At<unsigned>(p+2528)=8;Reject("part anchor out of grid");
        Fixture();At<unsigned>(p+2556)=32;Reject("part palette out of span");
        Fixture();At<unsigned>(p+2544)=9999;Reject("missing part parameter");
        for(auto off:{1072u,1104u,1448u,1672u}){Fixture();At<float>(p+off)=std::numeric_limits<float>::infinity();Reject("part transform finite");}
    }
    Fixture();At<BYTE>(Params+8)=4;Reject("parameter type changes material layer");
    Fixture();At<uint16_t>(Params+128)=20;At<unsigned>(Part1+2544)=20;Reject("first matching parameter row has priority");
    for(auto off:{0u,24u,104u,112u}){Fixture();At<uintptr_t>(PartTask0+off)=g_base+Extra;Reject("part owner task contract");}
    Fixture();At<int>(PartTask0+100)=19999;Reject("part priority changed");
    Fixture();At<int>(0x2B58B00)=0;Reject("parameter table empty");
    Fixture();At<uintptr_t>(0x2B58B08)=0;Reject("parameter table missing");
    for(int begin:{-1,4,INT32_MAX}){Fixture();At<int>(Work+1414644)=begin;Reject("history begin bounds");}
    for(int end:{-1,0,5,INT32_MAX}){Fixture();At<int>(Work+1414648)=end;Reject("history end bounds");}
    for(int current:{-2,1,INT32_MAX}){Fixture();At<int>(Work+1414652)=current;Reject("history current bounds");}
    for(unsigned group=0;group<2;++group)for(int count:{-1,1001,INT32_MAX}){Fixture();At<int>(Work+6256+28+4*group)=count;Reject("history group capacity");}
    Fixture();At<int>(Work+6256+352052)=0;Reject("history side does not match current position");
    Fixture();Reject("redo unavailable at newest transaction",Direction::Redo);
    Fixture();At<int>(Work+1414652)=-1;At<int>(Work+6256+352052)=0;Accept("redo before first transaction",Direction::Redo);Reject("undo unavailable before first");
    Fixture();At<int>(Work+1414648)=0;At<int>(Work+1414652)=-1;Accept("empty history can be structurally captured",Direction::Inspect);Reject("empty history no undo");
    Fixture();At<uintptr_t>(Hist(0,0)+144)=g_base+Cell(3);Accept("inspection does not treat an old addition group as today's removal",Direction::Inspect);
    Fixture();At<int>(Work+1414644)=3;At<int>(Work+1414648)=7;At<int>(Work+1414652)=4;
    for(int logical=3;logical<7;++logical){auto slot=Work+6256+352064*(logical%4);At<int>(slot+28)=At<int>(slot+32)=0;At<int>(slot+352052)=logical<=4?1:0;}
    Accept("wrapped four-slot undo");Accept("wrapped four-slot redo",Direction::Redo);
    for(unsigned group=0;group<2;++group) {
        for(auto off:{0u,16u,32u,96u}){Fixture();At<float>(Hist(0,group)+off)=std::numeric_limits<float>::quiet_NaN();Reject("history numeric fields");}
        Fixture();At<unsigned>(Hist(0,group)+116)=10000;Reject("history parameter lookup avoids native fallback");
        Fixture();At<uintptr_t>(Hist(0,group)+120)=g_base+Extra;Reject("history camera belongs to old work area");
        Fixture();At<uintptr_t>(Hist(0,group)+144)=g_base+Cell(8);Reject("history handle outside current grid");
        for(auto off:{131u,133u,137u}){Fixture();At<BYTE>(Hist(0,group)+off)=2;Reject("history boolean fields");}
        Fixture();At<BYTE>(Hist(0,group)+136)=32;Reject("history palette outside32");
    }
    Fixture();At<int>(Work+6256+32)=2;Record(Hist(0,1,1));Reject("selected removal repeats same anchor");
    Fixture();At<uintptr_t>(Hist(0,1)+144)=g_base+Cell(3);Reject("selected removal no owner");
    Fixture();At<int>(Work+6256+28)=1000;for(unsigned i=1;i<1000;++i)Record(Hist(0,0,i));Accept("native snapshot capacity1000 structurally readable; insertion plan remains separate");
    Fixture();Snapshot a,b;Check(Capture(a),"baseline snapshot");At<float>(Part0+1072)=1;Check(Capture(b)&&!gummi_history::Same(a,b),"fresh copy detects part state change");
    Fixture();Check(Capture(a),"palette baseline");At<uint32_t>(Editor+1456)=0x12345678;Check(Capture(b)&&!gummi_history::Same(a,b),"fresh copy detects palette change");
    Fixture();Check(Capture(a),"history baseline");At<BYTE>(Hist()+132)=1;Check(Capture(b)&&!gummi_history::Same(a,b),"fresh copy detects history change");
    Fixture();Check(Capture(a),"task group baseline");At<unsigned>(PartTask0+96)=3;Check(Capture(b)&&!gummi_history::Same(a,b),"fresh copy detects task group change");
    Fixture();Error stableError{};Check(gummi_history::CaptureStable(Direction::Undo,a,b,stableError),"stable helper captures two independent snapshots");
    Check(!gummi_history::CaptureStable(Direction::Undo,a,a,stableError)&&!a.valid,"aliased snapshot buffers rejected");
    Fixture();watchRead=g_base+Params;watchOrdinal=2;onRead=[](){At<BYTE>(Hist()+132)=1;};Check(!gummi_history::CaptureStable(Direction::Undo,a,b,stableError)&&!a.valid&&!b.valid,"two-pass history drift rejects entire result");
    Fixture();Check(Capture(a),"complete memory baseline");std::vector<BYTE> old(Allocation);memcpy(old.data(),reinterpret_cast<const void*>(g_base),Allocation);Check(Capture(b)&&!memcmp(old.data(),reinterpret_cast<const void*>(g_base),Allocation),"no game/global/save memory writes");
    Fixture();shared.hostHeartbeat=0;Reject("zero host heartbeat");Fixture();shared.hostHeartbeat=GetTickCount()-5001;Reject("expired host heartbeat");
    Fixture();g_gameThread++;Reject("foreign worker thread");Fixture();g_disabled=1;Reject("disabled bridge");
    Fixture();Tool();watchRead=g_base+Params;watchOrdinal=1;onRead=[](){At<int>(Cursor+2848)=13;};Reject("phase changes during graph capture");
    Fixture();watchRead=g_base+Params;watchOrdinal=1;onRead=[](){At<uintptr_t>(0xAFBEF0)=0;};Reject("owner disappears during graph capture");
    Fixture();DWORD oldProtect=0,temp=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base+Part0),0x1000,PAGE_NOACCESS,&oldProtect)!=0,"protect part fixture");Reject("unreadable placed part");Check(VirtualProtect(reinterpret_cast<void*>(g_base+Part0),0x1000,oldProtect,&temp)!=0,"restore fixture protection");
    gummi_history::Buffer<gummi_history::Cell> buffer;Check(!buffer.Resize(SIZE_MAX),"host buffer multiplication overflow");
    printf("GummiHistoryGuardTests: %u checks, %u failures\n",checks,failures);VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);return failures?1:0;
}
