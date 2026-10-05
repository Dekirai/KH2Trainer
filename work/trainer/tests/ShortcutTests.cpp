#define KH2DEV_PAYLOAD_TESTS
#include "../../../trainer/Native/TrainerBridge.cpp"
#include <stdio.h>
#include <limits>
unsigned checks = 0, failures = 0;
void Check(bool value, const char* name) { ++checks; if (!value) { ++failures; printf("FAIL %s\n", name); } }
int main() {
    using shortcuts::Select;
    TrainerResult result{};
    double args[8]{1};
    Check(!ShortcutHandle(117, args, result), "unowned slot is not consumed");
    ShortcutHandle(118, args, result);
    Check(!result.code && shortcuts::enabled, "shortcuts enable explicitly");
    Check(!Select(2, true, true, true, 1000), "held key on first observation is ignored");
    Check(!Select(2, true, true, true, 1016), "key hold does not repeat");
    Select(0, true, true, true, 1032);
    Check(Select(2, true, true, true, 1048) == 1006, "fresh Ctrl F6 heals");
    Select(0, false, true, true, 1064);
    Check(!Select(4, false, true, true, 1080), "F7 alone is ignored");
    Check(!Select(4, true, true, true, 1096), "pressing Ctrl on held F7 is ignored");
    Select(0, true, true, true, 1112);
    Check(Select(4, true, true, true, 1128) == 1016, "fresh Ctrl F7 bookmarks");
    Select(0, true, false, true, 1144);
    Check(!Select(8, true, false, true, 1160), "shortcut outside game is ignored");
    Check(!Select(8, true, true, true, 1176), "focus return with held key is ignored");
    Select(0, true, true, true, 1192);
    Check(Select(8, true, true, true, 1208) == 1017, "fresh Ctrl F8 returns");
    Select(0, true, true, true, 1224);
    Check(!Select(16, true, true, false, 1240), "expired host cannot issue hotkeys");
    Select(0, true, true, true, 1256);
    Check(Select(16, true, true, true, 1272) == 1079, "fresh Ctrl F9 toggles freeze");
    Select(0, true, true, true, 1288);
    Check(!Select(6, true, true, true, 1304), "simultaneous shortcut edges rejected");
    Select(0, true, true, true, 1320);
    Check(!Select(8, true, true, true, 3000), "long frame gap rearms instead of triggering");
    Select(0, true, true, true, 3016);
    Check(Select(1, true, true, true, 3032) == 1114, "Ctrl F5 releases effects");
    Select(0, true, true, true, 3040);
    Check(Select(64, true, true, true, 3041) == 1116, "Ctrl F11 toggles field pause");
    Select(0, true, true, true, 3042);
    Check(Select(128, true, true, true, 3043) == 1117, "Ctrl F12 steps field update");
    Select(0, true, true, true, 3044);
    Check(!Select(32, true, true, true, 3045), "F10 is left to the developer desktop handler");
    shortcuts::Reset(); Select(0, true, true, true, 3048);
    Check(!Select(2, true, true, true, 3064), "disabled shortcuts ignored");
    args[0] = std::numeric_limits<double>::quiet_NaN(); ShortcutHandle(118, args, result);
    Check(result.code && !shortcuts::enabled, "NaN toggle rejected");
    args[0] = .5; ShortcutHandle(118, args, result);
    Check(result.code && !shortcuts::enabled, "fractional toggle rejected");
    SharedState shared{}; g_shared = &shared;
    shortcuts::lastCommand = 1016; shortcuts::lastResult = 3; shortcuts::eventSequence = 17;
    ShortcutSnapshot();
    Check(shared.values[118] == 0 && shared.values[119] == 1016 && shared.values[120] == 3 && shared.values[121] == 17,
        "shortcut result snapshot preserves command/result/event");
    printf("%u shortcut checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
