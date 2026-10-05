// Optional keyboard shortcuts, evaluated on the same game thread as commands.
// No global keyboard hook or key suppression is installed.
namespace shortcuts {
bool enabled = false, observed = false, previousForeground = false;
unsigned previousKeys = 0;
DWORD previousTime = 0;
uint32_t eventSequence = 0;
unsigned lastCommand = 0;
LONG lastResult = 0;

void Reset() {
    enabled = false; observed = false; previousKeys = 0; previousForeground = false;
}
// All function keys are tracked even while modifiers are released, so pressing
// Ctrl while already holding a function key cannot issue a command.
unsigned Select(unsigned keys, bool control, bool foreground, bool liveHost, DWORD now) {
    const bool armed = enabled && liveHost && foreground && previousForeground && observed &&
        static_cast<DWORD>(now - previousTime) < 500;
    const unsigned edges = keys & ~previousKeys;
    previousKeys = keys; previousForeground = foreground; previousTime = now; observed = true;
    if (!armed || !control || !edges || (edges & (edges - 1))) return 0;
    switch (edges) {
    case 1: return 1114; // Ctrl+F5: release effects, including these shortcuts.
    case 2: return 1006; // Ctrl+F6: HP and MP.
    case 4: return 1016; // Ctrl+F7: position bookmark.
    case 8: return 1017; // Ctrl+F8: return to bookmark.
    case 16: return 1079; // Ctrl+F9: actor/effect freeze.
    case 64: return 1116; // Ctrl+F11: field simulation pause.
    case 128: return 1117; // Ctrl+F12: one field update.
    default: return 0;
    }
}
}

bool ShortcutHandle(unsigned slot, const double args[8], TrainerResult& result) {
    if (slot != 118) return false;
    if (!IsInteger(args[0], 0, 1)) { result = {2, L"Keyboard shortcuts must be zero or one."}; return true; }
    shortcuts::Reset();
    shortcuts::enabled = args[0] != 0;
    result = {0, shortcuts::enabled ?
        L"Hold Ctrl: F5 disable effects, F6 heal, F7 bookmark, F8 return, F9 freeze, F11 field pause, F12 step." :
        L"Training shortcuts disabled. F10 remains available while the trainer is connected."};
    return true;
}
void ShortcutSnapshot() {
    SnapshotValue(118, shortcuts::enabled ? 1 : 0);
    SnapshotValue(119, shortcuts::lastCommand);
    SnapshotValue(120, shortcuts::lastResult);
    SnapshotValue(121, shortcuts::eventSequence);
}
