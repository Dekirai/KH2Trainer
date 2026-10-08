// Player contracts are documented in research archive (see README): player_combat.json.
// This file is included inside TrainerBridge.cpp's anonymous namespace.
bool g_playerEffects[5]{}; // Auto heal, full MP, full Drive, form timer, summon timer.
uintptr_t g_bookmarkActor = 0;
uintptr_t g_bookmarkStatus = 0;
float g_bookmarkPosition[4]{};
bool g_bookmarkValid = false;
uint64_t g_bookmarkGeneration = 0;
uintptr_t g_bookmarkScheduler = 0;
BYTE g_bookmarkRoom[10]{};
struct PlayerCollisionLease {
    bool active, releasePending;
    uintptr_t actor, status, scheduler;
    uint64_t generation;
    BYTE room[10];
} g_collision{};

void PlayerClearBookmark() {
    actor_lifetime::Unpin(g_bookmarkGeneration);
    g_bookmarkGeneration = 0;
    g_bookmarkValid = false;
}
#ifdef KH2_PLAYER_POSITION_TESTS
void (__fastcall* g_testPlayerPosition)(void*,const float*) = nullptr;
#endif
void PlayerApplyPosition(const TrainerContext& c,const float* position) {
#ifdef KH2_PLAYER_POSITION_TESTS
    g_testPlayerPosition(reinterpret_cast<void*>(c.player),position);
#else
    reinterpret_cast<void (__fastcall*)(void*, const float*)>(c.base + 0x3B6100)(
        reinterpret_cast<void*>(c.player), position);
#endif
}

template<class T> T& PlayerField(uintptr_t object, SIZE_T offset) {
    return *reinterpret_cast<T*>(object + offset);
}
bool PlayerLiving(const TrainerContext& c) {
    return c.sceneReady && c.player && c.status &&
        At<int>(0x716884) == 1 && !At<BYTE>(0x9BA8D1) && !At<uintptr_t>(0x9BA928) &&
        Writable(reinterpret_cast<void*>(c.status), 632) &&
        !(PlayerField<uint32_t>(c.player, 0x9B8) & 4) &&
        !(PlayerField<uint32_t>(c.player, 0x120) & 0x10080000) &&
        PlayerField<int>(c.status, 0) > 0 &&
        PlayerField<int>(c.status, 4) > 0 && PlayerField<int>(c.status, 4) <= 255 &&
        PlayerField<int>(c.status, 0) <= PlayerField<int>(c.status, 4) &&
        PlayerField<int>(c.status, 388) >= 0 && PlayerField<int>(c.status, 388) <= 255 &&
        PlayerField<int>(c.status, 384) >= 0 &&
        PlayerField<int>(c.status, 384) <= PlayerField<int>(c.status, 388) &&
        isfinite(PlayerField<float>(c.status, 444)) && isfinite(PlayerField<float>(c.status, 448));
}
uintptr_t PlayerSave(const TrainerContext& c) {
    if (!c.status) return 0;
    const uintptr_t save = DecodePacked(PlayerField<uint32_t>(c.status, 592));
    return Readable(reinterpret_cast<void*>(save), 276) ? save : 0;
}
uintptr_t PlayerFormSave(const TrainerContext& c) {
    if (!c.status || !c.player) return 0;
    const int form = PlayerField<int>(c.player, 3552);
    if (form < 1 || form > 5) return 0;
    const uintptr_t record = DecodePacked(PlayerField<uint32_t>(c.status, 596));
    const uintptr_t expected = c.base + 0x9ABDA0 + 3588 + 56 * (form - 1);
    return record == expected && Readable(reinterpret_cast<void*>(record), 56) ? record : 0;
}
bool PlayerPosition(const TrainerContext& c, float out[4], bool requireUnattached) {
    if (!c.player || !c.sceneReady) return false;
    const bool attached = PlayerField<uint32_t>(c.player, 1696) != 0;
    if (requireUnattached && attached) return false;
    const SIZE_T offset = attached ? 112 : 1648;
    for (unsigned i = 0; i < 3; ++i) {
        out[i] = PlayerField<float>(c.player, offset + i * sizeof(float));
        if (!isfinite(out[i]) || fabsf(out[i]) > 1000000.0f) return false;
    }
    out[3] = 1.0f;
    return true;
}
bool PlayerCollisionIdentity() {
    if (!g_collision.active || At<uintptr_t>(0x2A105D0) != g_collision.actor ||
        actor_lifetime::Resolve(g_collision.generation) != g_collision.actor ||
        At<uintptr_t>(0x716868) != g_collision.scheduler ||
        memcmp(reinterpret_cast<void*>(g_base + 0x717008), g_collision.room, sizeof(g_collision.room)) ||
        !Writable(reinterpret_cast<void*>(g_collision.actor), 0xDE4) ||
        !Readable(reinterpret_cast<void*>(g_collision.status), 632)) return false;
    const TrainerContext current{g_base,g_collision.actor,g_collision.status,false};
    return actor_lifetime::ObserveCurrent(current) == g_collision.generation;
}
bool PlayerCollisionProfile() {
    return PlayerCollisionIdentity() &&
        (PlayerField<uint32_t>(g_collision.actor, 292) & 0x40) &&
        (PlayerField<uint32_t>(g_collision.actor, 2248) & 0x1000) &&
        PlayerField<uintptr_t>(g_collision.actor, 2312) == 0;
}
void PlayerForgetCollision() {
    actor_lifetime::Unpin(g_collision.generation);
    g_collision = {};
}
void PlayerMaintainCollision() {
    if (!g_collision.active) return;
    if (actor_lifetime::IsRetired(g_collision.generation)) {
        PlayerForgetCollision(); return;
    }
    // Off-current, absent or unresolved Actors may still be alive. Retain the
    // pinned lease without dereferencing them or changing a replacement Actor.
    if (!g_collision.releasePending || !PlayerCollisionIdentity()) return;
    // 3CC3B0 consists only of these masked clears and a zero pointer store.
    // The pointer is already zero. Never clear a native/cutscene override.
    if (PlayerCollisionProfile()) {
        PlayerField<uint32_t>(g_collision.actor, 292) &= ~0x40u;
        PlayerField<uint32_t>(g_collision.actor, 2248) &= ~0x1000u;
    }
    PlayerForgetCollision();
}
void PlayerReleaseCollision() {
    if (g_collision.active) g_collision.releasePending = true;
    PlayerMaintainCollision();
}
#include "PlayerHealthSupport.inl"
bool PlayerHeal(const TrainerContext& c) {
    return player_health::SetHp(c,PlayerField<int>(c.status,4));
}
bool PlayerFullMp(const TrainerContext& c) {
    return player_health::FullMp(c);
}
bool PlayerGaugeValid(const TrainerContext& c) {
    const float current = PlayerField<float>(c.status, 436);
    const float maximum = PlayerField<float>(c.status, 440);
    return isfinite(current) && isfinite(maximum) && current >= 0 &&
        maximum > 0 && maximum <= 1000000.0f && current <= maximum;
}
bool PlayerProgressionTables() {
    const uintptr_t level = At<uintptr_t>(0x2AE5708);
    if (!Readable(reinterpret_cast<void*>(level), 8)) return false;
    const int count = PlayerField<int>(level, 4);
    if (count < 1 || count > 256 || !Readable(reinterpret_cast<void*>(level), 8 + 8 * count)) return false;
    int previous = -1;
    for (int i = 0; i < count; ++i) {
        const int key = PlayerField<BYTE>(level, 8 + 8 * i);
        if (key <= previous) return false;
        previous = key;
    }
    return true;
}
bool PlayerHasLevelRow(unsigned key) {
    const uintptr_t table = At<uintptr_t>(0x2AE5708);
    const int count = PlayerField<int>(table, 4);
    for (int i = 0; i < count; ++i)
        if (PlayerField<BYTE>(table, 8 + 8 * i) == key) return true;
    return false;
}
bool PlayerRewardDataReady(const TrainerContext& c) {
    progression::ItemTable items{};
    if (!progression::SaveReady(c) || !progression::Items(c, items) ||
        !progression::RefreshDataReady(c, items)) return false;
    const unsigned character = PlayerField<unsigned>(c.status, 608);
    if (character != 1 && character != 14) return false;
    const uintptr_t save = PlayerSave(c);
    if (save != progression::Character(c, character) ||
        DecodePacked(PlayerField<uint32_t>(c.status, 620)) != c.base + 0x9ABDA0) return false;
    const BYTE* levelRow = nullptr;
    if (!progression::LevelRow(c, character, PlayerField<BYTE>(save, 15), levelRow)) return false;
    for (unsigned offset : {0u, 2u}) {
        const unsigned item = PlayerField<WORD>(save, offset);
        if (item && !progression::FindItem(items, item)) return false;
    }
    for (unsigned kind = 0; kind < 2; ++kind) {
        const unsigned count = PlayerField<BYTE>(save, 16 + kind);
        if (count > 8) return false;
        for (unsigned index = 0; index < count; ++index) {
            const unsigned item = PlayerField<WORD>(save, 20 + kind * 16 + index * 2);
            if (item && !progression::FindItem(items, item)) return false;
        }
    }
    for (unsigned i = 0; i < 80; ++i) {
        const unsigned id = PlayerField<WORD>(save, 84 + 2 * i) & 0x7fff;
        if (id && !progression::AbilityItem(progression::FindItem(items, id))) return false;
    }
    const uintptr_t form = DecodePacked(PlayerField<uint32_t>(c.status, 596));
    if (form) {
        if (PlayerFormSave(c) != form) return false;
        const unsigned weapon = PlayerField<WORD>(form, 0);
        if (weapon && !progression::FindItem(items, weapon)) return false;
        for (unsigned i = 0; i < 24; ++i) {
            const unsigned id = PlayerField<WORD>(form, 8 + 2 * i) & 0x7fff;
            if (id && !progression::AbilityItem(progression::FindItem(items, id))) return false;
        }
    }
    const uintptr_t table = At<uintptr_t>(0x2AE5708);
    const int count = PlayerField<int>(table, 4);
    for (int i = 0; i < count; ++i) {
        const unsigned reward = PlayerField<WORD>(table, 8 + 8 * i + 2);
        if (reward && !progression::AbilityItem(progression::FindItem(items, reward))) return false;
        const unsigned key = PlayerField<BYTE>(table, 8 + 8 * i);
        const unsigned formId = key >> 4;
        if (formId >= 1 && formId <= 5) {
            const unsigned growth = PlayerField<BYTE>(table, 8 + 8 * i + 1);
            if (growth < 1 || growth > 4 || (key & 15) < 1 || (key & 15) > 7) return false;
        }
    }
    return Readable(At<void*>(0x2A11678), 16);
}
bool PlayerExpAllowed() {
    const uintptr_t map = At<uintptr_t>(0x2A0FF68);
    if (!map) return true; // Matches 3A3C40.
    if (!Readable(reinterpret_cast<void*>(map), 16)) return false;
    const uintptr_t data = PlayerField<uintptr_t>(map, 8);
    return Readable(reinterpret_cast<void*>(data), 6) && !(PlayerField<WORD>(data, 4) & 0x400);
}
void PlayerReset(const TrainerContext&) {
    ZeroMemory(g_playerEffects, sizeof(g_playerEffects));
    PlayerClearBookmark();
    PlayerReleaseCollision();
}
void PlayerTick(const TrainerContext& c) {
    PlayerMaintainCollision();
    if (g_collision.active && (!PlayerLiving(c) || c.player != g_collision.actor ||
        c.status != g_collision.status || !PlayerCollisionProfile() ||
        PlayerField<uint32_t>(c.player, 1696))) PlayerReleaseCollision();
    if (g_bookmarkValid && (!c.sceneReady || c.player != g_bookmarkActor || c.status != g_bookmarkStatus ||
        actor_lifetime::Resolve(g_bookmarkGeneration) != c.player ||
        actor_lifetime::ObserveCurrent(c) != g_bookmarkGeneration ||
        At<int>(0x716884) != 1 || At<BYTE>(0x9BA8D1) || At<uintptr_t>(0x9BA928) ||
        At<uintptr_t>(0x716868) != g_bookmarkScheduler ||
        memcmp(reinterpret_cast<void*>(c.base + 0x717008), g_bookmarkRoom, sizeof(g_bookmarkRoom))))
        PlayerClearBookmark();
    if (!PlayerLiving(c)) return;
    if (g_playerEffects[0]) PlayerHeal(c);
    if (g_playerEffects[1] &&
        (PlayerField<int>(c.status, 384) < PlayerField<int>(c.status, 388) ||
         PlayerField<float>(c.status, 448) > 0.0f)) PlayerFullMp(c);
    const BYTE mode = PlayerField<BYTE>(c.status, 431);
    const BYTE maxDrive = PlayerField<BYTE>(c.status, 434);
    if (g_playerEffects[2] && mode == 1 && maxDrive >= 1 && maxDrive <= 9) {
        PlayerField<BYTE>(c.status, 433) = maxDrive;
        PlayerField<BYTE>(c.status, 432) = 100;
    }
    if (((g_playerEffects[3] && mode == 2) || (g_playerEffects[4] && mode == 3)) &&
        PlayerGaugeValid(c))
        PlayerField<float>(c.status, 436) = PlayerField<float>(c.status, 440);
}
bool PlayerHandle(const TrainerContext& c, unsigned slot, const double args[8], TrainerResult& result) {
    if (slot >= 48) return false;
    const bool implemented = slot == 0 || (slot >= 4 && slot <= 7) ||
        (slot >= 13 && slot <= 22) || (slot >= 30 && slot <= 35) || slot == 44 || slot == 46;
    if (!implemented) return false;
    result = {10, L"Load a save and enter a playable scene with a living player."};
    if (slot == 46) {
        if (!IsInteger(args[0], 0, 1)) { result = {11, L"Use 0 or 1 for this toggle."}; return true; }
        if (args[0] == 0) {
            PlayerReleaseCollision();
            result = {0, g_collision.active ? L"Collision release is pending until its original player instance can be verified." :
                L"Movement collision override released where still owned."}; return true;
        }
    }
    // Disable is always accepted, including teardown and character changes.
    if (slot >= 18 && slot <= 22) {
        if (!IsInteger(args[0], 0, 1)) { result = {11, L"Use 0 or 1 for this toggle."}; return true; }
        if (args[0] == 0) { g_playerEffects[slot - 18] = false; result = {0, L"Effect disabled."}; return true; }
    }
    if (!PlayerLiving(c)) return true;
    if (slot == 46) {
        if (g_collision.active) {
            if (!g_collision.releasePending && c.player == g_collision.actor && c.status == g_collision.status && PlayerCollisionProfile()) {
                result = {0, L"Movement collision bypass is already active."}; return true;
            }
            PlayerReleaseCollision();
            if (g_collision.active) {
                result = {18, L"The previous collision override is still waiting for its original player instance."}; return true;
            }
        }
        if (!Writable(reinterpret_cast<void*>(c.player), 0xDE4) ||
            PlayerField<uint32_t>(c.player, 1696) ||
            (PlayerField<uint32_t>(c.player, 292) & 0x40) ||
            (PlayerField<uint32_t>(c.player, 2248) & 0x1000) ||
            PlayerField<uintptr_t>(c.player, 2312)) {
            result = {18, L"The player is attached or already has a native movement/collision override."}; return true;
        }
        const uint64_t generation = actor_lifetime::ObserveCurrent(c);
        if (!generation || !actor_lifetime::Pin(generation)) {
            result = {18, L"Collision bypass requires a verified player lifetime."}; return true;
        }
        g_collision.active = true; g_collision.generation = generation;
        g_collision.actor = c.player; g_collision.status = c.status;
        g_collision.scheduler = At<uintptr_t>(0x716868);
        memcpy(g_collision.room, reinterpret_cast<void*>(c.base + 0x717008), sizeof(g_collision.room));
        // Exact field effects of 3CBFC0(Actor,null), with pre-existing flags rejected.
        PlayerField<uint32_t>(c.player, 292) |= 0x40u;
        PlayerField<uint32_t>(c.player, 2248) |= 0x1000u;
        result = {0, L"Movement collision bypass enabled for this player and scene. It does not grant flight or invulnerability."};
        return true;
    }
    if (slot >= 18 && slot <= 22) {
        g_playerEffects[slot - 18] = true;
        result = {0, L"Effect enabled; it pauses when its player or gauge is unavailable."};
        return true;
    }
    if (slot == 0) {
        if (!IsInteger(args[0], 1, PlayerField<int>(c.status, 4))) {
            result = {11, L"HP must be an integer between 1 and the current maximum."}; return true;
        }
        if(!player_health::SetHp(c,static_cast<int>(args[0]))) {
            result={19,L"HP changes are waiting for a verified player and available HP display resources."}; return true;
        }
    } else if (slot == 4) {
        if(!PlayerHeal(c)) { result={19,L"Healing is waiting for a verified player and available HP display resources."}; return true; }
    } else if (slot == 5) {
        if(!PlayerFullMp(c)) { result={19,L"MP restore is waiting for a verified player and MP state."}; return true; }
    } else if (slot == 6) {
        // Validate both paths before either resource is changed.
        if(!player_health::HpReady(c,PlayerField<int>(c.status,4)) || !player_health::MpReady(c)) {
            result={19,L"Full restore is waiting for verified HP, MP and display resources."}; return true;
        }
        if(!PlayerHeal(c) || !PlayerFullMp(c)) { result={19,L"Player resources changed during restore."}; return true; }
    }
    else if (slot == 7) {
        const int maximum = PlayerField<BYTE>(c.status, 434);
        if (PlayerField<BYTE>(c.status, 431) != 1 || maximum < 1 || maximum > 9 ||
            !IsInteger(args[0], 0, maximum)) {
            result = {11, L"Drive bars require the normal Drive gauge and a value within its current maximum."};
            return true;
        }
        PlayerField<BYTE>(c.status, 433) = static_cast<BYTE>(args[0]);
        PlayerField<BYTE>(c.status, 432) = args[0] == maximum ? 100 : 0;
    } else if (slot >= 13 && slot <= 17) {
        float position[4]{};
        if (!PlayerPosition(c, position, true) || !Writable(reinterpret_cast<void*>(c.player), 0xDE4)) {
            result = {12, L"World-position changes require an unattached player with valid coordinates."}; return true;
        }
        if (slot == 16) {
            const uint64_t generation = actor_lifetime::ObserveCurrent(c);
            if (!generation || !actor_lifetime::Pin(generation)) {
                result = {13, L"A position bookmark requires a verified player lifetime."}; return true;
            }
            PlayerClearBookmark();
            g_bookmarkGeneration = generation;
            memcpy(g_bookmarkPosition, position, sizeof(position));
            g_bookmarkActor = c.player; g_bookmarkStatus = c.status; g_bookmarkValid = true;
            g_bookmarkScheduler = At<uintptr_t>(0x716868);
            memcpy(g_bookmarkRoom, reinterpret_cast<void*>(c.base + 0x717008), sizeof(g_bookmarkRoom));
            result = {0, L"Position bookmark saved for this player instance."}; return true;
        }
        if (slot == 17) {
            if (!g_bookmarkValid || g_bookmarkActor != c.player || g_bookmarkStatus != c.status ||
                actor_lifetime::Resolve(g_bookmarkGeneration) != c.player ||
                actor_lifetime::ObserveCurrent(c) != g_bookmarkGeneration ||
                At<uintptr_t>(0x716868) != g_bookmarkScheduler ||
                memcmp(reinterpret_cast<void*>(c.base + 0x717008), g_bookmarkRoom, sizeof(g_bookmarkRoom))) {
                result = {13, L"No bookmark is valid for the current scene/player instance."}; return true;
            }
            memcpy(position, g_bookmarkPosition, sizeof(position));
        } else {
            if (!isfinite(args[0]) || fabs(args[0]) > 1000000.0) {
                result = {11, L"Position must be finite and within -1000000 to 1000000."}; return true;
            }
            position[slot - 13] = static_cast<float>(args[0]);
        }
        PlayerApplyPosition(c,position);
    } else if (slot >= 32 && slot <= 35) {
        const uintptr_t save = PlayerSave(c);
        static constexpr unsigned offsets[]{9, 10, 11, 8};
        static constexpr uintptr_t calls[]{0x3C09D0, 0x3C0E30, 0x3C0A50, 0x3C0950};
        const unsigned index = slot - 32;
        if (!save || !Writable(reinterpret_cast<void*>(save), 276) ||
            !progression::SaveReady(c) || save != progression::Character(c, PlayerField<unsigned>(c.status, 608)) ||
            !IsInteger(args[0], 1, 100) || PlayerField<BYTE>(save, offsets[index]) > 100) {
            result = {11, L"A valid character save and an integer boost amount from 1 to 100 are required."}; return true;
        }
        if (PlayerField<BYTE>(save, offsets[index]) == 100) {
            result = {14, L"This saved boost is already at the game's limit of 100."}; return true;
        }
        const unsigned actual = static_cast<unsigned>(args[0]) < 100u - PlayerField<BYTE>(save, offsets[index]) ?
            static_cast<unsigned>(args[0]) : 100u - PlayerField<BYTE>(save, offsets[index]);
        if (PlayerField<WORD>(c.status, 392 + index * 2) > 65535u - actual ||
            PlayerField<WORD>(c.status, 400 + index * 2) > 65535u - actual) {
            result = {15, L"The current runtime stat is outside a safe boost range."}; return true;
        }
        reinterpret_cast<void (__fastcall*)(void*, int)>(c.base + calls[index])(
            reinterpret_cast<void*>(c.status), static_cast<int>(args[0]));
        result = {0, L"Saved character boost increased, capped at 100. This change is permanent when saved."}; return true;
    } else if (slot == 30 || slot == 31) {
        if (!IsInteger(args[0], 1, 10000) || !PlayerProgressionTables() || !PlayerExpAllowed() ||
            !PlayerRewardDataReady(c)) {
            result = {11, L"Experience requires an integer from 1 to 10000 and valid progression data in an eligible scene."}; return true;
        }
        if (slot == 30) {
            const uintptr_t summons = At<uintptr_t>(0x2AE55E8);
            if (!Readable(reinterpret_cast<void*>(summons), 8)) { result = {15, L"Summon definitions are unavailable."}; return true; }
            const int count = PlayerField<int>(summons, 4);
            if (count != 4 || !Readable(reinterpret_cast<void*>(summons), 8 + 64 * count) ||
                At<BYTE>(0x9ACDD6) < 1 || At<BYTE>(0x9ACDD6) > 7 ||
                At<uint32_t>(0x9ACF94) > 0x7fffffffu - static_cast<unsigned>(args[0])) {
                result = {15, L"Summon level or experience data is outside the supported range."}; return true;
            }
            for (unsigned level = 1; level <= 7; ++level) if (!PlayerHasLevelRow(level)) {
                result = {15, L"The summon level table is incomplete."}; return true;
            }
            reinterpret_cast<void (__fastcall*)(int)>(c.base + 0x40D530)(static_cast<int>(args[0]));
        } else {
            const uintptr_t form = PlayerFormSave(c);
            const int id = PlayerField<int>(c.player, 3552);
            if (!form || !Writable(reinterpret_cast<void*>(form), 56) ||
                PlayerField<BYTE>(form, 2) < 1 || PlayerField<BYTE>(form, 2) > 7 ||
                PlayerField<uint32_t>(form, 4) > 0x7fffffffu - static_cast<unsigned>(args[0])) {
                result = {16, L"Enter a standard leveled Drive form before adding form experience."}; return true;
            }
            // The engine dereferences the next level row while awarding growth abilities.
            for (unsigned level = 1; level <= 7; ++level) if (!PlayerHasLevelRow(id * 16 + level)) {
                result = {15, L"The form level table is incomplete."}; return true;
            }
            reinterpret_cast<void (__fastcall*)(void*, int)>(c.base + 0x3E8380)(
                reinterpret_cast<void*>(c.player), static_cast<int>(args[0]));
        }
        result = {0, L"Experience processed by the game, including its level cap and rewards."}; return true;
    } else if (slot == 44) {
        const BYTE mode = PlayerField<BYTE>(c.status, 431);
        if ((mode != 2 && mode != 3) || !PlayerGaugeValid(c)) {
            result = {17, L"An active form or summon gauge is required."}; return true;
        }
        PlayerField<float>(c.status, 436) = PlayerField<float>(c.status, 440);
    }
    result = {0, L"Player command completed."};
    return true;
}
void PlayerCapabilities() {
    for (unsigned slot = 0; slot <= 46; ++slot) SupportCapability(slot);
}
void PlayerSnapshot(const TrainerContext& c) {
    for (unsigned i = 0; i < 5; ++i) SnapshotValue(18 + i, g_playerEffects[i] ? 1 : 0);
    SnapshotValue(16, g_bookmarkValid ? 1 : 0);
    SnapshotValue(46, g_collision.active ? 1 : 0);
    if (!c.status || !c.player) return;
    SnapshotValue(0, PlayerField<int>(c.status, 0));
    SnapshotValue(1, PlayerField<int>(c.status, 4));
    SnapshotValue(2, PlayerField<int>(c.status, 384));
    SnapshotValue(3, PlayerField<int>(c.status, 388));
    SnapshotValue(7, PlayerField<BYTE>(c.status, 433));
    SnapshotValue(8, PlayerField<BYTE>(c.status, 434));
    SnapshotValue(9, PlayerField<BYTE>(c.status, 431));
    SnapshotValue(10, PlayerField<float>(c.status, 436));
    SnapshotValue(11, PlayerField<float>(c.status, 440));
    SnapshotValue(12, PlayerField<int>(c.player, 3552));
    SnapshotValue(23, PlayerField<float>(c.status, 444));
    for (unsigned i = 0; i < 4; ++i) SnapshotValue(24 + i, PlayerField<WORD>(c.status, 392 + 2 * i));
    SnapshotValue(28, At<BYTE>(0x9ACDD6));
    SnapshotValue(29, At<uint32_t>(0x9ACF94));
    SnapshotValue(41, PlayerField<int>(c.status, 608));
    SnapshotValue(45, PlayerField<BYTE>(c.status, 432));
    float position[4]{};
    if (PlayerPosition(c, position, false))
        for (unsigned i = 0; i < 3; ++i) SnapshotValue(13 + i, position[i]);
    const uintptr_t save = PlayerSave(c);
    if (save) {
        static constexpr unsigned offsets[]{9, 10, 11, 8};
        for (unsigned i = 0; i < 4; ++i) SnapshotValue(36 + i, PlayerField<BYTE>(save, offsets[i]));
        SnapshotValue(40, PlayerField<BYTE>(save, 15));
    }
    const uintptr_t form = PlayerFormSave(c);
    if (form) {
        SnapshotValue(42, PlayerField<BYTE>(form, 2));
        SnapshotValue(43, PlayerField<uint32_t>(form, 4));
    }
}
