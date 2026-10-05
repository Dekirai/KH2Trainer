// Compile the production branches without executing or linking game code.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <string.h>
namespace {
struct TrainerContext { uintptr_t base,player,status;bool sceneReady; };
struct TrainerResult { LONG code;const wchar_t* text; };
struct Shared { DWORD hostHeartbeat; };
uintptr_t g_base=0,g_selectedVtable=0;DWORD g_gameThread=0;LONG g_disabled=0;Shared* g_shared=nullptr;
bool Readable(const void*,SIZE_T) { return false; }
bool Writable(const void*,SIZE_T) { return false; }
bool IsInteger(double v,double a,double b) { return isfinite(v)&&v>=a&&v<=b&&floor(v)==v; }
void SnapshotValue(unsigned,double) {}
void SupportCapability(unsigned) {}
#include "../../../trainer/Native/DisplayFeatures.inl"
}
