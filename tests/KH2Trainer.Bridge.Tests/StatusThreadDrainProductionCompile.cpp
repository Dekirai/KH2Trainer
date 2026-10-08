#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../src/KH2Trainer.Bridge/StatusThreadDrain.h"

// Compile-only: exercise shipping branches without injected resume failures.
bool CompileStatusThreadDrain(status_thread_drain::Drain& drain,
    const status_thread_drain::Range (&roots)[status_thread_drain::RootCount],
    status_thread_drain::GateCheck gates,void* context) noexcept {
    if(!drain.Begin(roots,gates,context))return drain.Close();
    const auto result=drain.Poll();
    if(drain.ResumePending())return false;
    return result.phase==status_thread_drain::Phase::Drained && drain.Ready() && drain.Close();
}
