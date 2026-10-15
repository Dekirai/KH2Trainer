// Reviewer-owned synthetic executable: no KH2 test defines, no game process,
// no DLL injection, no executable module memory and no replacement WinAPI.
#include "../../src/KH2Trainer.Bridge/TrainerBridge.cpp"
#include <stdio.h>
#include <limits.h>
namespace review {
unsigned checks=0,failures=0,frames=0;
SharedState state{};
BYTE* module=nullptr;
void check(bool ok,const char* why) {++checks;if(!ok){++failures;printf("FAIL %s\n",why);}}
bool valid(unsigned n){return (state.validValues[n/64]>>(n%64))&1;}
bool supported(unsigned n){return (state.supportedCapabilities[n/64]>>(n%64))&1;}
void protect(DWORD flags) {DWORD old=0;check(VirtualProtect(module,kImageSize,flags,&old)!=FALSE,"synthetic module protection");}
void counters(int free,int interval,BYTE inhibit) {
 protect(PAGE_READWRITE);
 *reinterpret_cast<int*>(module+0xad9390)=free;
 *reinterpret_cast<int*>(module+0xad93c4)=interval;
 module[0xad93c0]=inhibit;
 protect(PAGE_READONLY);
}
void reset() {
 ZeroMemory(&state,sizeof(state));g_shared=&state;g_base=reinterpret_cast<uintptr_t>(module);
 g_disabled=0;g_gameThread=GetCurrentThreadId();state.hostHeartbeat=GetTickCount();
 g_hostExpired=false;g_initialized=false;g_pendingVisibility=false;g_desiredVisible=false;
}
bool snapshot() {
 __try {AudioRequestSnapshot({g_base,0,0,false});return true;}
 __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
bool frame() {
 __try {TrainerFrame();++frames;return true;}
 __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
void empty(const char* why) {check(!valid(482)&&!valid(483)&&!valid(484),why);}
void values(int free,int interval,unsigned limits) {
 check(valid(482)&&valid(483)&&valid(484),"all three sample validity bits");
 check(state.values[482]==free && state.values[483]==interval && state.values[484]==limits,"copied values and reason set");
}
void changedByte(size_t rva) {protect(PAGE_READWRITE);module[rva]^=1;protect(PAGE_READONLY);}
}
int main() {
 using namespace review;
 module=static_cast<BYTE*>(VirtualAlloc(nullptr,kImageSize,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
 if(!module)return 2;
 for(const auto& s:audio_request_signatures::Writers)memcpy(module+s.rva,s.bytes,s.size);
 // This full-size image is synthetic. All unrelated objects and scene globals
 // remain zero; no engine implementation can execute from PAGE_READONLY memory.
 protect(PAGE_READONLY);reset();
 unsigned masks=0;
 for(int free=0;free<=80;++free)for(int interval=0;interval<=25;++interval)for(BYTE inhibit=0;inhibit<2;++inhibit) {
  counters(free,interval,inhibit);reset();
  unsigned expected=0;
  if(inhibit==1)expected+=1;
  if(free<17)expected+=2;
  if(interval==25)expected+=4;
  masks|=1u<<expected;
  check(snapshot(),"real helper did not fault on non-executable readonly module");values(free,interval,expected);
 }
 check(masks==255,"all eight reason sets visited");
 const int freeInvalid[]={INT_MIN,-1,81,INT_MAX};
 for(int f:freeInvalid){counters(f,0,0);reset();check(snapshot(),"invalid free no fault");empty("invalid signed free rejected");}
 const int intervalInvalid[]={INT_MIN,-1,26,INT_MAX};
 for(int i:intervalInvalid){counters(80,i,0);reset();check(snapshot(),"invalid interval no fault");empty("invalid signed interval rejected");}
 for(unsigned v=2;v<256;++v){counters(80,0,static_cast<BYTE>(v));reset();check(snapshot(),"invalid inhibit no fault");empty("noncanonical inhibit rejected");}
 counters(17,24,0);reset();g_gameThread=GetCurrentThreadId()+1;check(snapshot(),"wrong thread no fault");empty("wrong thread rejected");
 reset();g_gameThread=0;check(snapshot(),"unset thread no fault");empty("unset thread rejected");
 reset();g_disabled=1;check(snapshot(),"disabled no fault");empty("disabled rejected");
 reset();state.hostHeartbeat=0;check(snapshot(),"missing host no fault");empty("missing host rejected");
 reset();state.hostHeartbeat=GetTickCount()-5001;check(snapshot(),"stale host no fault");empty("stale host rejected");
 reset();state.hostHeartbeat=GetTickCount()+100;check(snapshot(),"future host no fault");empty("future host rejected");
 reset();g_shared=nullptr;check(snapshot(),"null shared no fault");empty("null shared rejected");
 reset();g_base=0;check(snapshot(),"null base no fault");empty("null base rejected");
 reset();AudioRequestSnapshot({g_base+1,0,0,false});empty("mismatched base rejected");
 reset();g_base=UINTPTR_MAX-1;check(snapshot(),"wrapped address rejected without fault");empty("wrapped address invalid");
 reset();
 for(const auto& s:audio_request_signatures::Writers){
  // First/last and interior corruption independently; entire-body checking.
  for(size_t off:{size_t(0),s.size/2,s.size-1}) {
   changedByte(s.rva+off);reset();check(snapshot(),"changed signature no fault");empty("changed native body rejected");changedByte(s.rva+off);
  }
 }
 // Actual VirtualQuery accessibility, not a fake span predicate.
 DWORD old=0;
 check(VirtualProtect(module+0xad9000,4096,PAGE_NOACCESS,&old)!=FALSE,"deny scalar page");
 reset();check(snapshot(),"inaccessible scalar page no fault");empty("inaccessible scalar page rejected");
 check(VirtualProtect(module+0xad9000,4096,PAGE_READONLY,&old)!=FALSE,"restore scalar page");
 check(VirtualProtect(module+0x1dd000,4096,PAGE_NOACCESS,&old)!=FALSE,"deny writer page");
 reset();check(snapshot(),"inaccessible writer page no fault");empty("inaccessible writer page rejected");
 check(VirtualProtect(module+0x1dd000,4096,PAGE_READONLY,&old)!=FALSE,"restore writer page");
 // Invoke the actual production TrainerFrame. The entire synthetic game module
 // stays readonly and non-executable: any accidental module write/call faults.
 for(unsigned mask=0;mask<8;++mask){
  int f=(mask&2)?16:17,i=(mask&4)?25:24;BYTE inhibit=(mask&1)?1:0;
  counters(f,i,inhibit);reset();
  check(frame(),"production TrainerFrame runs with readonly non-executable module");
  values(f,i,mask);check(supported(482)&&supported(483)&&supported(484),"production capabilities publish all three slots");
  check(state.sceneReady==0&&!(state.snapshotSequence&1)&&state.snapshotSequence==2,"global observation outside scene under snapshot sequence");
 }
 for(LONG command=1482;command<=1484;++command){
  counters(80,0,0);reset();state.commandId=command;state.commandIssuedAt=GetTickCount();state.requestSequence=1;
  for(double& v:state.arguments)v=42;
  check(frame(),"production readonly command dispatch no fault");
  check(state.responseSequence==1 && state.resultCode==1 && wcsstr(state.resultText,L"read-only"),"1482-1484 reject explicitly before generic fallback");
  values(80,0,0);
 }
 counters(17,24,0);reset();check(frame(),"initial valid production frame");values(17,24,0);
 changedByte(0x1dd510);check(frame(),"invalid signature next frame");empty("production frame clears previous validity");
 check(state.values[482]==0&&state.values[483]==0&&state.values[484]==0,"production frame clears previous numerical data");changedByte(0x1dd510);
 counters(17,24,0);reset();check(frame(),"host-loss baseline frame");state.hostHeartbeat=GetTickCount()-5001;
 check(frame(),"host-loss production frame");empty("host-loss clears observation");
 // Early OnFrame gates run without entering keyboard/foreground code.
 reset();OnFrame(nullptr,1);check(state.snapshotSequence==0,"unsuccessful Update does not sample");
 reset();g_disabled=1;OnFrame(nullptr,0);check(state.snapshotSequence==0,"disabled OnFrame does not sample");
 reset();OnFrame(reinterpret_cast<void*>(1),0);check(state.snapshotSequence==0&&g_disabled,"wrong app OnFrame fails before observation");
 reset();
 uintptr_t app[1]={123};protect(PAGE_READWRITE);*reinterpret_cast<void**>(module+kAppGlobalRva)=app;protect(PAGE_READONLY);
 g_selectedVtable=123;g_gameThread=GetCurrentThreadId()+1;OnFrame(app,0);
 check(state.snapshotSequence==0&&g_disabled,"wrong thread OnFrame fails before observation");
 printf("Independent production route: %u checks, %u failures, %u actual TrainerFrame calls; zero test defines.\n",checks,failures,frames);
 VirtualFree(module,0,MEM_RELEASE);return failures?1:0;
}
