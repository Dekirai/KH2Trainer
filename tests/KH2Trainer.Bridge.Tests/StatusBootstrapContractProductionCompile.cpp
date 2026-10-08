#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../src/KH2Trainer.Bridge/StatusBootstrapContract.h"
bool CompileStatusBootstrapContract(status_bootstrap::Contract& contract,uintptr_t module,
    status_bootstrap::Range (&roots)[status_bootstrap::RootCount]) noexcept {
    return contract.Prepare(module) && contract.Verify(status_bootstrap::EntryMode::Original) &&
        contract.Verify(status_bootstrap::EntryMode::FiveGates) && contract.RootRanges(roots);
}
