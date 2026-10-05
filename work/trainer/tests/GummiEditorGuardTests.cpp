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
#include "../../../trainer/Native/GummiEditorFeatures.inl"
constexpr uintptr_t Work=0xC00000, Editor=0xD80000, Camera=0xD90000, Cursor=0xDA0000;
constexpr uintptr_t Manager=0xDB0000, Objects=0xDB1000, Heap=0xDB2000, PartHeap=0xDB3000;
constexpr uintptr_t EditTask=0xDC0000, WorkTask=0xDC1000, CameraTask=0xDC2000, CursorTask=0xDC3000, Fiber=0xDC4000, Extra=0xDC5000;
constexpr size_t Allocation=0x1000000;
unsigned checks=0,failures=0,resetCalls=0,fovCalls=0;uintptr_t calledObject=0;int calledInt=-1;float calledAngle=0;
TrainerContext host{};
void Check(bool ok,const char* name){++checks;if(!ok){++failures;printf("FAIL %s\n",name);}}
void FinishCall(){if(destroyAfterCall){At<uintptr_t>(0xAFBEF0)=0;At<uintptr_t>(0xAFC118)=0;}afterCall=true;}
void __fastcall NativeReset(void* camera,int duration) {
    ++calls;++resetCalls;calledObject=reinterpret_cast<uintptr_t>(camera);calledInt=duration;
    *reinterpret_cast<int*>(calledObject+2604)=duration*2;*reinterpret_cast<int*>(calledObject+2608)=duration*2;
    *reinterpret_cast<unsigned*>(calledObject+2612)|=0x10;FinishCall();
}
void __fastcall NativeFov(void* projection,float angle,int axis) {
    ++calls;++fovCalls;calledObject=reinterpret_cast<uintptr_t>(projection);calledInt=axis;calledAngle=angle;
    float* p=static_cast<float*>(projection);const float x=(512.f/p[19])*.5f,y=(416.f/p[20])*.5f;
    p[16]=x/tanf(angle*.5f);p[17]=angle;p[18]=2.f*atanf(y/p[16]);FinishCall();
}
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
TrainerResult Command(unsigned slot=424,double value=45){double args[8]{value};TrainerResult r{};Check(GummiEditorHandle(host,slot,args,r),"known action routes");return r;}
void Rejected(const char* why,unsigned slot=424,double value=45){auto old=calls;auto r=Command(slot,value);Check(r.code!=0&&calls==old,why);}
bool Valid(unsigned s){return (shared.valid[s/64]&(uint64_t(1)<<(s%64)))!=0;}
void Observe(){memset(shared.valid,0,sizeof(shared.valid));GummiEditorSnapshot(host);}
void ProtectReject(uintptr_t rva,DWORD protection,const char* why,unsigned slot=424){DWORD old=0,temp=0;Check(VirtualProtect(reinterpret_cast<void*>(g_base+rva),0x1000,protection,&old)!=0,"protect fixture");Rejected(why,slot);Check(VirtualProtect(reinterpret_cast<void*>(g_base+rva),0x1000,old,&temp)!=0,"restore fixture");}
void Drift(void(*change)()){watchRead=g_base+0x290900;watchOrdinal=1;watchSeen=0;onRead=change;}
}
int main(){
    g_base=reinterpret_cast<uintptr_t>(VirtualAlloc(nullptr,Allocation,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));if(!g_base)return 2;
    gummi_editor::testReset=NativeReset;gummi_editor::testFov=NativeFov;
    for(bool tiny:{false,true})for(bool preview:{false,true}) {
        Ready(preview,tiny);Observe();Check(Valid(426)&&shared.values[426]==(preview?4:1),"both editor identities/phase snapshots");
        Check(Valid(427)&&fabs(shared.values[427]-45)<.001&&Valid(428)&&Valid(429)&&Valid(430),"five numeric readouts");
        auto r=Command();Check(!r.code&&calls==1&&resetCalls==1&&!fovCalls&&calledObject==g_base+Camera&&calledInt==10,"reset exact ABI and single call");
        Check(At<int>(Camera+2604)==20&&At<int>(Camera+2608)==20&&(At<unsigned>(Camera+2612)&16),"native mock receives transition contract");
        Check(!postCallReads,"reset no post-call dereference");
    }
    for(double degrees:{20.,20.25,45.,89.75,90.}){
        Ready(true);auto r=Command(425,degrees);Check(!r.code&&calls==1&&!resetCalls&&fovCalls==1&&calledObject==g_base+Camera+16&&calledInt==0,"FOV exact projection and axis ABI");
        Check(fabs(calledAngle-degrees*(3.141592653589793/180))<1e-6&&isfinite(At<float>(Camera+80))&&At<float>(Camera+80)>0,"FOV radians and finite projection");Check(!postCallReads,"FOV no post-call dereference");
    }
    Ready();Rejected("FOV requires native preview phase",425);
    for(unsigned action:{424u,425u}) {
        Ready(true);destroyAfterCall=true;auto r=Command(action);Check(!r.code&&calls==1&&!postCallReads,"teardown during native call causes no stale read");
        Ready(true);shared.hostHeartbeat=0;Rejected("zero heartbeat",action);
        Ready(true);shared.hostHeartbeat=GetTickCount()-5001;Rejected("expired heartbeat",action);
        Ready(true);shared.hostHeartbeat=GetTickCount()+1000;Rejected("future heartbeat",action);
        Ready(true);g_gameThread++;Rejected("foreign thread",action);
        Ready(true);g_gameThread=0;Rejected("missing thread",action);
        Ready(true);g_disabled=1;Rejected("disabled",action);
        Ready(true);g_shared=nullptr;Rejected("shared state missing",action);
        Ready(true);host.base=0;Rejected("wrong base",action);
        Ready(true);At<int>(gummi_editor::Module+36)=2;Rejected("paused module",action);Observe();Check(Valid(426),"paused module still diagnostic");
        Ready(true);At<BYTE>(0xAFD1D8)=1;Rejected("global input lock",action);
        Ready(true);At<int>(Camera+2604)=1;Rejected("pending transition",action);Observe();Check(Valid(430)&&shared.values[430]==1,"transition still diagnostic");
        Ready(true);At<unsigned>(Camera+2612)=0x20;Rejected("camera owns input lock",action);
        Ready(true);At<unsigned>(Camera+2612)=0x10;auto q=Command(action);Check(!q.code&&calls==1,"idle preview latch0x10 is not a lock");
        Ready(true);At<BYTE>(Editor+8)=0;Rejected("editor inactive",action);
        Ready(true);At<unsigned>(Camera+2352)=1;Rejected("camera deletion pending",action);
        Ready(true);At<unsigned>(Cursor+16)|=2;Rejected("cursor deletion pending",action);
        Ready(true);ProtectReject(Camera,PAGE_READONLY,"read-only camera",action);
        Ready(true);ProtectReject(Work,PAGE_NOACCESS,"unreadable owner",action);
        Ready(true);ProtectReject(Cursor,PAGE_NOACCESS,"unreadable cursor",action);
        Ready(true);Drift([](){At<uintptr_t>(0xAFBEF0)=0;});Rejected("owner loss before second validation",action);
        Ready(true);Drift([](){At<BYTE>(0xAFD1D8)=1;});Rejected("input lock before dispatch",action);
        Ready(true);Drift([](){shared.hostHeartbeat=0;});Rejected("host lost during preflight",action);
        Ready(true);Drift([](){At<unsigned>(Camera+2612)=0x20;});Rejected("camera transition ownership changes",action);
        Ready(true);Drift([](){At<uintptr_t>(CursorTask)=0;});Rejected("cursor task retired between preflights",action);
    }
    for(int phase:{-1,0,2,3,5,6,7,8,9,10,99}){Ready();At<int>(Editor+12276)=phase;Rejected("non-editor/modal phase");}
    for(int state:{-1,0,3,99}){Ready();At<int>(gummi_editor::Module+36)=state;Rejected("inactive/foreign module state");}
    for(auto rva:{0xAFBEF0u,0xAFC118u,0xAF9F08u,0xAFA700u,0xAFB420u,0x9A8800u,0xAFBA60u}){Ready();At<uintptr_t>(rva)=0;Rejected("released global owner");}
    for(auto rva:{Work,Editor,Camera,Cursor}){Ready();At<uintptr_t>(rva)=0;Rejected("foreign object vtable");}
    Ready();At<uintptr_t>(gummi_editor::Module)=0;Rejected("foreign module vtable");
    Ready();At<int>(gummi_editor::Module+16)=70;Rejected("wrong module identifier");
    Ready();At<uintptr_t>(0x8EC5D8)=0;Rejected("module unlisted");
    Ready();At<uint32_t>(gummi_editor::Module+20)=DWORD(gummi_editor::Module);Rejected("cyclic module list");
    Ready();At<uintptr_t>(gummi_editor::Module+8)=g_base+Objects;Rejected("global manager alias mismatch");
    Ready();At<uintptr_t>(0xAFA700)=g_base+Manager;Rejected("cursor manager cannot be module manager");
    Ready();At<BYTE>(0xAFC0C0)=1;Rejected("main/tiny class mismatch");
    Ready();At<BYTE>(0xAFC0C0)=2;Rejected("invalid editor kind");
    Ready();At<int>(0xAFBEE8)=2;Rejected("invalid material mode");
    Ready();At<int>(Editor+12272)=0;Rejected("material owner mismatch");
    Ready();At<int>(Camera+2356)=1;Rejected("phase/camera mode mismatch");
    Ready();At<uintptr_t>(0x5B7D50)=0;Rejected("foreign camera update");
    Ready();At<uintptr_t>(0x5B78D0+16)=0;Rejected("foreign editor fiber vcall");
    for(auto off:{1414552u,1414568u,1414576u,1414584u}){Ready();At<uintptr_t>(Work+off)=0;Rejected("workarea backlink missing");}
    for(auto off:{1344u,2824u}){Ready();At<uintptr_t>(Cursor+off)=0;Rejected("cursor camera backlink missing");}
    for(auto manager:{Manager,Objects}){
        Ready();At<uintptr_t>(manager+16)=At<uintptr_t>(manager+24)=0;Rejected("empty owner scheduler");
        Ready();At<uintptr_t>(manager+24)=0;Rejected("manager tail mismatch");
        Ready();At<uintptr_t>(manager+32)=g_base+EditTask;Rejected("dispatching scheduler");
    }
    for(auto task:{EditTask,WorkTask,CameraTask,CursorTask})for(auto off:{0u,24u,88u,104u}){Ready();At<uintptr_t>(task+off)=0;Rejected("task ownership tuple");}
    for(auto task:{EditTask,WorkTask,CameraTask,CursorTask}){
        Ready();At<uintptr_t>(task+120)=g_base+task;Rejected("task self cycle");
        Ready();At<uintptr_t>(task+128)=g_base+task;Rejected("bad previous link");
        Ready();At<unsigned>(task+96)^=8;Rejected("wrong task group");
        Ready();At<int>(task+100)++;Rejected("wrong task priority");
    }
    Ready();At<uintptr_t>(EditTask+112)=0;Rejected("editor lacks fiber");
    Ready();At<BYTE>(Fiber+24)=0;Rejected("unstarted editor fiber");
    Ready();At<uintptr_t>(Fiber)=0;Rejected("released native fiber");
    for(auto task:{WorkTask,CameraTask,CursorTask}){Ready();At<uintptr_t>(task+112)=g_base+Fiber;Rejected("wrong fiber kind");}
    Ready();At<uintptr_t>(CameraTask+32)=g_base+Extra;Rejected("foreign camera clear pointer");
    Ready();Node(Extra,Objects,CursorTask,0,20010,0x24C180,0x24C360,Cursor,2);At<uintptr_t>(CursorTask+120)=g_base+Extra;At<uintptr_t>(Objects+24)=g_base+Extra;Rejected("duplicate cursor owner");
    Ready();Node(Extra,Manager,CameraTask,0,65000,0x272070,0x272090,Camera,0);At<uintptr_t>(CameraTask+120)=g_base+Extra;At<uintptr_t>(Manager+24)=g_base+Extra;Rejected("duplicate camera owner");
    Ready();Node(Extra,Manager,CameraTask,0,65001,0x111111,0,Extra+160,0);At<uintptr_t>(CameraTask+120)=g_base+Extra;At<uintptr_t>(Manager+24)=g_base+Extra;auto r=Command();Check(!r.code&&calls==1,"unrelated valid scheduler tasks allowed");
    Ready();At<int>(0x73EB50)=-1;Rejected("negative registry free count");
    Ready();At<int>(0x73EB50)=81;Rejected("registry free count overflow");
    for(int index:{-1,80,INT32_MAX}){Ready();At<int>(0x73EA10)=index;Rejected("free index bounds");}
    Ready();At<int>(0x73EA10+4)=At<int>(0x73EA10);Rejected("duplicate registry free index");
    Ready();At<uintptr_t>(0x73DD90)=g_base+Camera;Rejected("free registry record retains pointer");
    Ready();At<uintptr_t>(0x73DD90+7*40)=0;Rejected("named camera pointer mismatch");
    Ready();memset(reinterpret_cast<void*>(g_base+0x73DD90+7*40+8),'x',32);Rejected("unterminated registry name");
    Ready();At<int>(0x73EB50)=78;const int used=At<int>(0x73EA10+78*4);At<uintptr_t>(0x73DD90+40*used)=g_base+Camera;strcpy_s(reinterpret_cast<char*>(g_base+0x73DD90+40*used+8),32,"work area camera");Rejected("duplicate camera name");
    const float nan=std::numeric_limits<float>::quiet_NaN(),inf=std::numeric_limits<float>::infinity(),large=std::numeric_limits<float>::max();
    for(auto off:{80u,84u,88u,92u,96u,2592u})for(float bad:{0.f,-1.f,nan,inf}){Ready();At<float>(Camera+off)=bad;Rejected("invalid projection state");}
    Ready(true);At<float>(Camera+92)=std::numeric_limits<float>::denorm_min();Rejected("projection division overflows",425);
    Ready(true);At<float>(Camera+96)=std::numeric_limits<float>::denorm_min();Rejected("vertical projection overflow",425);
    for(auto off:{2448u,2452u,2456u,2464u,2468u,2472u,2480u,2484u,2488u})for(float bad:{nan,inf,100000000.f}){Ready();At<float>(Camera+off)=bad;Rejected("angle normalization cannot diverge");}
    Ready();At<float>(Camera+2484)=gummi_editor::Turn*1.5f;r=Command();Check(!r.code&&calls==1,"previous yaw accepts native one-turn normalization extension");
    Ready();At<float>(0x73DD10)=nan;Rejected("invalid native defaults");
    Ready();At<float>(0x73DCD8)=0;Rejected("invalid pitch snap threshold");
    for(int plane:{-1,3,INT32_MAX}){Ready();At<int>(Work+6240)=plane;Rejected("grid plane is bounded");}
    for(auto off:{16u,20u,24u,32u,36u,40u,6168u,6172u,6176u,6200u,6204u,6208u}){Ready();At<float>(Work+off)=nan;Rejected("nonfinite focus inputs");}
    for(auto off:{1072u,1076u,1080u,1120u,1124u,1128u}){Ready();At<float>(Cursor+off)=nan;Rejected("nonfinite cursor input");}
    Ready();At<float>(Cursor+1072)=large;At<float>(Cursor+1120)=large;Rejected("cursor translation float overflow");
    Ready();At<float>(Cursor+1072)=large*.5f;Rejected("transition weighted sum float overflow");
    Ready();At<unsigned>(Cursor+16)|=4;At<int>(Work+6240)=99;r=Command();Check(!r.code&&calls==1,"hidden cursor uses only work center");
    Ready();At<int>(Cursor+2840)=0;At<int>(Work+6240)=99;r=Command();Check(!r.code&&calls==1,"empty cursor focus uses center");
    Ready();At<unsigned>(Camera+2612)|=1;At<int>(Work+6240)=99;r=Command();Check(!r.code&&calls==1,"focus-disabled native path avoids unused grid data");
    Ready();At<unsigned>(Cursor+2976)|=4;At<float>(Work+16)=nan;r=Command();Check(!r.code&&calls==1,"unsnapped cursor path avoids unused cell vector");
    for(double bad:{-1.,0.,19.99,90.01,1e20,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}){Ready(true);Rejected("FOV argument native range",425,bad);}
    for(const auto& sig:gummi_editor::signatures)for(size_t index:{size_t(0),sig.size-1}){Ready();At<BYTE>(sig.rva+index)^=1;Rejected("full native body pin rejects first/last byte corruption");}
    Ready();Drift([](){At<float>(Cursor+1072)=std::numeric_limits<float>::infinity();});Rejected("second preflight repeats cursor numeric checks");
    Ready(true);Drift([](){At<float>(Camera+92)=0;});Rejected("second preflight repeats viewport arithmetic",425);
    Ready();Drift([](){memcpy(reinterpret_cast<void*>(g_base+Extra),reinterpret_cast<void*>(g_base+CameraTask),152);At<uintptr_t>(WorkTask+120)=g_base+Extra;At<uintptr_t>(Manager+24)=g_base+Extra;});Rejected("valid task replacement loses lifetime identity");
    Ready();GummiEditorCapabilities();for(unsigned s=424;s<=430;++s)Check((shared.supported[s/64]&(uint64_t(1)<<(s%64)))!=0,"capability includes action and five diagnostics");
    Check(!Valid(424)&&!Valid(425),"one-shot controls do not publish fictitious saved values");
    double args[8]{};TrainerResult result{};Check(!GummiEditorHandle(host,423,args,result)&&!GummiEditorHandle(host,431,args,result),"unrelated slots are unhandled");
    Ready();Check(GummiEditorHandle(host,424,nullptr,result)&&result.code&&!calls,"missing argument vector rejected");
    Ready();args[7]=std::numeric_limits<double>::quiet_NaN();Check(GummiEditorHandle(host,424,args,result)&&result.code&&!calls,"nonfinite unused argument rejected");
    Ready();shared.hostHeartbeat=0;Observe();Check(!Valid(426)&&!Valid(430),"snapshot rejects expired host");
    Ready();g_gameThread++;Observe();Check(!Valid(426),"snapshot rejects foreign thread");
    Ready();g_disabled=1;Observe();Check(!Valid(426),"snapshot respects disabled bridge");
    Ready();At<float>(Work+6180)=nan;r=Command();Check(!r.code&&calls==1,"unused fourth grid plane component does not overconstrain reset");
    for(bool hidden:{false,true}){Ready();if(hidden)At<unsigned>(Cursor+16)|=4;else At<int>(Cursor+2840)=0;At<float>(Work+32)=large;Rejected("fallback center weighted transition overflow");}
    Ready();At<unsigned>(Camera+2612)|=1;At<float>(Camera+2560)=large;Rejected("retained focus cannot overflow during new transition");
    Ready(true);At<float>(Camera+92)=1;At<float>(Camera+84)=std::numeric_limits<float>::min();At<float>(Camera+2592)=2e-36f;Rejected("current projection endpoint must also remain finite");
    for(auto off:{2596u,2600u}){Ready();At<float>(Camera+off)=nan;Rejected("edit reset preserves and validates existing FOV interpolation endpoints");}
    Ready();At<unsigned>(Cursor+16)|=4;At<float>(Work+44)=large;Rejected("fallback homogeneous component cannot overflow interpolation");
    Ready();At<float>(Work+6212)=large;Rejected("grid homogeneous component cannot overflow interpolation");
    for(auto off:{2572u,2588u}){Ready();At<unsigned>(Camera+2612)|=1;At<float>(Camera+off)=large;Rejected("retained homogeneous component cannot overflow interpolation");}
    Ready();At<float>(Cursor+1084)=At<float>(Cursor+1132)=large;r=Command();Check(!r.code&&calls==1,"discarded cursor homogeneous sum does not restrict reset");
    VirtualFree(reinterpret_cast<void*>(g_base),0,MEM_RELEASE);printf("GummiEditorGuardTests: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
