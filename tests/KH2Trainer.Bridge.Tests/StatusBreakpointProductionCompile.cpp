#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../src/KH2Trainer.Bridge/StatusBreakpointRouter.h"

// Compile the real MEM_IMAGE-only path without private-memory test overrides.
// This translation unit is never linked or executed by the test runner.
status_breakpoint::Error CompileResidentStatusEntryPath(
    status_breakpoint::Router& router,
    const status_breakpoint::Candidate (&candidate)[status_breakpoint::EntryCount]) noexcept {
    const auto prepared=router.Prepare(candidate);
    if(prepared!=status_breakpoint::Error::None)return prepared;
    const auto committed=router.Commit();
    if(committed!=status_breakpoint::Error::None)return committed;
    return router.Verify() && router.Status()==status_breakpoint::State::Resident &&
        router.PatchedMask()==((1u<<status_breakpoint::EntryCount)-1)
        ?status_breakpoint::Error::None:status_breakpoint::Error::Changed;
}
