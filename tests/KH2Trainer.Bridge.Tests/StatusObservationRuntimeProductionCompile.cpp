#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../src/KH2Trainer.Bridge/StatusObservationRuntime.h"

// Compile-only: instantiate the real components and wrappers without starting,
// loading, patching, suspending, or calling into any game process.
bool CompileStatusRuntimeStart(uintptr_t module,uintptr_t pool,uint64_t instance,DWORD confirmedGameThread) {
    return status_observation::RetailRuntime::Start(module,pool,instance,confirmedGameThread);
}
status_observation::Diagnostic CompileStatusRuntimeTick(unsigned budget) {
    return status_observation::RetailRuntime::Tick(budget);
}
status_observation::Diagnostic CompileStatusRuntimeDiagnostic() {
    return status_observation::RetailRuntime::InspectOnOwner();
}
