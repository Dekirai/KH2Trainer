// KH2 Steam build 9002b2de...49ed. Included inside the bridge namespace.
// Evidence and argument contract: work/trainer/research/progression.json.
namespace progression {
constexpr uintptr_t SaveRva = 0x9A98B0;
constexpr size_t SaveSize = 0x10FC0;
constexpr size_t Characters = 9456, CharacterSize = 276;
constexpr size_t Stock = 13696, Unique = 14016, Experience = 14048;
unsigned selectedCharacter = 1, selectedItem = 1;
struct ItemTable { uintptr_t data; unsigned count; };
struct RefreshSet { uintptr_t status[3]; unsigned count; };

unsigned CharacterIndex(unsigned id) { return id == 14 ? 1 : id == 15 ? 6 : id; }
uintptr_t Character(const TrainerContext& c, unsigned id) {
    return c.base + SaveRva + Characters + CharacterSize * (CharacterIndex(id) - 1);
}
bool SaveReady(const TrainerContext& c) {
    if (!c.sceneReady || !c.player || !c.status) return false;
    const uintptr_t save = c.base + SaveRva;
    return Writable(reinterpret_cast<void*>(save), SaveSize) &&
           *reinterpret_cast<const uint32_t*>(save) == 0x4A32484B &&
           *reinterpret_cast<const uint32_t*>(save + 4) == 0x3A;
}
bool Items(const TrainerContext& c, ItemTable& table) {
    const uintptr_t address = *reinterpret_cast<const uintptr_t*>(c.base + 0x2A25370);
    if (!Readable(reinterpret_cast<void*>(address), 8)) return false;
    const int count = *reinterpret_cast<const int*>(address + 4);
    if (count < 1 || count > 4096 || !Readable(reinterpret_cast<void*>(address + 8), size_t(count) * 24)) return false;
    table = {address + 8, static_cast<unsigned>(count)};
    return true;
}
const BYTE* FindItem(const ItemTable& table, unsigned id) {
    for (unsigned i = 0; i < table.count; ++i) {
        const BYTE* row = reinterpret_cast<const BYTE*>(table.data + i * 24);
        if (*reinterpret_cast<const uint16_t*>(row) == id) return row;
    }
    return nullptr;
}
unsigned ItemSlot(const BYTE* row) { return *reinterpret_cast<const uint16_t*>(row + 18); }
bool CountItem(const BYTE* row) {
    return row && !(row[3] & 1) && row[2] <= 17 && ItemSlot(row) < 320;
}
bool AbilityItem(const BYTE* row) {
    // Ability flag ordinal is a ushort at +4; the effect bitset is 32 bytes.
    return row && row[2] == 19 && !(row[3] & 1) &&
           *reinterpret_cast<const uint16_t*>(row + 4) < 256;
}
bool RefreshDataReady(const TrainerContext& c, const ItemTable& items) {
    const uintptr_t parameters = *reinterpret_cast<const uintptr_t*>(c.base + 0x2AE5760);
    if (!Readable(reinterpret_cast<void*>(parameters), 376)) return false;
    const uintptr_t table = *reinterpret_cast<const uintptr_t*>(c.base + 0x2AEA8A0);
    if (!Readable(reinterpret_cast<void*>(table), 8)) return false;
    const int count = *reinterpret_cast<const int*>(table + 4);
    if (count < 1 || count > 4096 || !Readable(reinterpret_cast<void*>(table + 8), size_t(count) * 16)) return false;
    unsigned previous = 0;
    for (int i = 0; i < count; ++i) {
        const BYTE* row = reinterpret_cast<const BYTE*>(table + 8 + size_t(i) * 16);
        const unsigned id = *reinterpret_cast<const uint16_t*>(row);
        const unsigned ability = *reinterpret_cast<const uint16_t*>(row + 2);
        if ((i && id <= previous) || (ability && !AbilityItem(FindItem(items, ability)))) return false;
        previous = id;
    }
    return true;
}
bool LevelRow(const TrainerContext& c, unsigned id, unsigned level, const BYTE*& row) {
    if (level < 1 || level > 99) return false;
    const uintptr_t table = *reinterpret_cast<const uintptr_t*>(c.base + 0x2AE58A8);
    if (!Readable(reinterpret_cast<void*>(table), 12)) return false;
    const int characters = *reinterpret_cast<const int*>(table + 4);
    if (characters < 2 || characters > 32 || !Readable(reinterpret_cast<void*>(table), 8 + 4 * size_t(characters))) return false;
    unsigned index = CharacterIndex(id);
    if (index >= unsigned(characters) || !*reinterpret_cast<const int*>(table + 8 + 4 * index)) index = 1;
    const int offsetWords = *reinterpret_cast<const int*>(table + 8 + 4 * index);
    if (offsetWords < 0 || offsetWords > 0x100000) return false;
    const uintptr_t levels = table + 4 * size_t(offsetWords);
    if (!Readable(reinterpret_cast<void*>(levels), 4)) return false;
    const int count = *reinterpret_cast<const int*>(levels);
    if (count < 1 || count > 99 || !Readable(reinterpret_cast<void*>(levels + 4), 16 * size_t(count))) return false;
    if (level > unsigned(count)) level = unsigned(count);
    row = reinterpret_cast<const BYTE*>(levels + 4 + 16 * (level - 1));
    return true;
}
bool CanRefresh(const TrainerContext& c, unsigned id, const ItemTable& items, RefreshSet& set) {
    set = {};
    if (!RefreshDataReady(c, items)) return false;
    const uintptr_t character = Character(c, id);
    const BYTE* data = reinterpret_cast<const BYTE*>(character);
    const BYTE* unused = nullptr;
    if (!LevelRow(c, id, data[15], unused) || data[16] > 8 || data[17] > 8 || data[18] > 8) return false;
    // Reject malformed existing equipment/abilities before any mutation or native rebuild.
    for (unsigned offset : {0u, 2u}) {
        const unsigned equipped = *reinterpret_cast<const uint16_t*>(data + offset);
        if (equipped && !FindItem(items, equipped)) return false;
    }
    for (unsigned kind = 0; kind < 2; ++kind) {
        for (unsigned i = 0; i < data[16 + kind]; ++i) {
            const unsigned equipped = *reinterpret_cast<const uint16_t*>(data + 20 + kind * 16 + i * 2);
            if (equipped && !FindItem(items, equipped)) return false;
        }
    }
    for (unsigned i = 0; i < 80; ++i) {
        const unsigned ability = *reinterpret_cast<const uint16_t*>(data + 84 + i * 2) & 0x7FFF;
        if (ability && !AbilityItem(FindItem(items, ability))) return false;
    }
    const uintptr_t actors[3] = {c.player,
        *reinterpret_cast<const uintptr_t*>(c.base + 0x2A239B0),
        *reinterpret_cast<const uintptr_t*>(c.base + 0x2A239B8)};
    for (const uintptr_t actor : actors) {
        if (!actor) continue;
        if (!Readable(reinterpret_cast<void*>(actor), 1480)) return false;
        const uintptr_t status = *reinterpret_cast<const uintptr_t*>(actor + 1472);
        if (!Readable(reinterpret_cast<void*>(status), 632)) return false;
        if (DecodePacked(*reinterpret_cast<const uint32_t*>(status + 592)) != character) continue;
        const uintptr_t driveSave = DecodePacked(*reinterpret_cast<const uint32_t*>(status + 620));
        if (!Writable(reinterpret_cast<void*>(status), 632) ||
            DecodePacked(*reinterpret_cast<const uint32_t*>(status + 616)) != actor ||
            (driveSave && driveSave != c.base + SaveRva + Characters) ||
            (id == 1 && !driveSave) ||
            CharacterIndex(*reinterpret_cast<const unsigned*>(status + 608)) != id) return false;
        // Form-specific ability/equipment data has a separate rebuild path.
        if (DecodePacked(*reinterpret_cast<const uint32_t*>(status + 596))) return false;
        bool duplicate = false;
        for (unsigned i = 0; i < set.count; ++i) duplicate |= set.status[i] == status;
        if (!duplicate) set.status[set.count++] = status;
    }
    return true;
}
void Refresh(const TrainerContext& c, const RefreshSet& set) {
    using Fn = void (__fastcall*)(uintptr_t);
    for (unsigned i = 0; i < set.count; ++i) reinterpret_cast<Fn>(c.base + 0x3C2100)(set.status[i]);
}
bool Fail(TrainerResult& result, const wchar_t* message) { result = {1, message}; return true; }
bool Success(TrainerResult& result, const wchar_t* message) { result = {0, message}; return true; }

bool AddExperienceReady(const TrainerContext& c, const ItemTable& table) {
    // Native reward handling uses messages and status parameter tables.
    for (uintptr_t rva : {uintptr_t(0x2AE5760), uintptr_t(0x2A11678)}) {
        if (!Readable(reinterpret_cast<void*>(*reinterpret_cast<const uintptr_t*>(c.base + rva)), 16)) return false;
    }
    for (unsigned id = 1; id <= 13; ++id) {
        const BYTE* character = reinterpret_cast<const BYTE*>(Character(c, id));
        if (character[15] < 1 || character[15] > 99 || character[14] > 2) return false;
        RefreshSet unused{};
        if (!CanRefresh(c, id, table, unused)) return false;
        for (unsigned level = character[15]; level <= 99; ++level) {
            const BYTE* row = nullptr;
            if (!LevelRow(c, id, level, row)) return false;
            const unsigned reward = *reinterpret_cast<const uint16_t*>(row + 8 + 2 * character[14]);
            // Base level rewards are abilities. A mod may alter the table; accept only
            // the proven reward path with a bounded ability flag ordinal.
            if (reward && !AbilityItem(FindItem(table, reward))) return false;
        }
    }
    return true;
}
}

bool ProgressionHandle(const TrainerContext& c, unsigned slot, const double args[8], TrainerResult& result) {
    using namespace progression;
    if (slot < 80 || slot > 97 || slot == 81 || slot == 89 || slot == 90 || slot == 91 || slot == 93 || slot == 95) return false;
    if (slot == 88) {
        if (!IsInteger(args[0], 1, 13)) return Fail(result, L"Choose a character slot from 1 to 13.");
        selectedCharacter = unsigned(args[0]);
        return Success(result, L"Character selection updated.");
    }
    if (slot == 92) {
        if (!IsInteger(args[0], 1, 32767)) return Fail(result, L"Choose an item ID from 1 to 32767.");
        selectedItem = unsigned(args[0]);
        return Success(result, L"Item selection updated.");
    }
    if (!SaveReady(c)) return Fail(result, L"Load a playable scene with a valid KH2 Final Mix save first.");
    BYTE* save = reinterpret_cast<BYTE*>(c.base + SaveRva);
    if (slot == 80) {
        if (!IsInteger(args[0], 0, 999999)) return Fail(result, L"Munny must be an integer from 0 to 999999.");
        *reinterpret_cast<int32_t*>(save + 9280) = int32_t(args[0]);
        return Success(result, L"Munny updated in the current save buffer.");
    }
    ItemTable table{};
    if (!Items(c, table)) return Fail(result, L"The current item table is unavailable or invalid.");
    if (slot == 82) {
        if (!IsInteger(args[0], 1, 9999999)) return Fail(result, L"Added EXP must be an integer from 1 to 9999999.");
        const int current = *reinterpret_cast<const int32_t*>(save + Experience);
        if (current < 0 || current > 9999999 || !AddExperienceReady(c, table)) return Fail(result, L"Level, reward or message data is not ready for native level-up processing.");
        const int amount = int(args[0]) < 9999999 - current ? int(args[0]) : 9999999 - current;
        if (amount) reinterpret_cast<intptr_t (__fastcall*)(int)>(c.base + 0x3ECF30)(amount);
        return Success(result, L"EXP added through the native level-up and reward handler.");
    }
    if (slot == 83) {
        if (!IsInteger(args[0], 1, 32767) || !IsInteger(args[1], 0, 99)) return Fail(result, L"Supply a valid item ID and an integer stock quantity from 0 to 99.");
        const unsigned id = unsigned(args[0]);
        const BYTE* row = FindItem(table, id);
        if (!CountItem(row)) return Fail(result, L"Only count-based consumables, boosts, equipment, synthesis items and recipes are supported here.");
        BYTE& count = save[Stock + ItemSlot(row)];
        const unsigned requested = unsigned(args[1]);
        if (count > 99) return Fail(result, L"The existing stock count is outside the supported 0..99 range.");
        if (requested < count) reinterpret_cast<char (__fastcall*)(unsigned, int)>(c.base + 0x3C4A40)(id, int(count - requested));
        else while (count < requested) {
            const unsigned before = count;
            const bool added = reinterpret_cast<char (__fastcall*)(unsigned, unsigned, unsigned char)>(c.base + 0x3C3F00)(id, 100, 0) != 0;
            if (!added || count <= before) return Fail(result, L"The native item handler stopped before reaching the requested quantity.");
        }
        selectedItem = id;
        return Success(result, L"Stock quantity updated through the native item handlers.");
    }
    if (slot == 84) {
        if (!IsInteger(args[0], 1, 32767)) return Fail(result, L"Supply a valid unlock item ID.");
        const unsigned id = unsigned(args[0]);
        const BYTE* row = FindItem(table, id);
        // Forms require additional equipment initialization; handled separately after validation.
        if (!row || !(row[3] & 1) || row[2] < 20 || row[2] > 23 || row[2] == 21 || ItemSlot(row) >= 256)
            return Fail(result, L"This action supports validated summon, map and report unlocks. Forms require their separate initialization path.");
        reinterpret_cast<char (__fastcall*)(unsigned, unsigned, unsigned char)>(c.base + 0x3C3F00)(id, 100, 0);
        selectedItem = id;
        return Success(result, L"The selected unique item has been granted.");
    }
    if (slot >= 85 && slot <= 87) {
        if (!IsInteger(args[0], 1, 13) || !IsInteger(args[1], 1, 32767) ||
            (slot != 87 && !IsInteger(args[2], 0, 1))) return Fail(result, L"Supply character 1..13, an ability ID, and enabled 0 or 1.");
        const unsigned characterId = unsigned(args[0]), abilityId = unsigned(args[1]);
        if (!AbilityItem(FindItem(table, abilityId))) return Fail(result, L"The current table does not contain this supported ability.");
        RefreshSet refresh{};
        if (!CanRefresh(c, characterId, table, refresh)) return Fail(result, L"Return to normal form and check the character's current equipment and ability data before editing.");
        uint16_t* abilities = reinterpret_cast<uint16_t*>(Character(c, characterId) + 84);
        int found = -1, freeSlot = -1;
        for (unsigned i = 0; i < 80; ++i) {
            if ((abilities[i] & 0x7FFFu) == abilityId && found < 0) found = int(i);
            if (!(abilities[i] & 0x7FFF) && freeSlot < 0) freeSlot = int(i);
        }
        if (slot == 85) {
            if (found >= 0) return Fail(result, L"This character already owns the ability. Use enable/disable to change it.");
            if (freeSlot < 0) return Fail(result, L"The character's 80 ability entries are full.");
            abilities[freeSlot] = uint16_t(abilityId | (args[2] != 0 ? 0x8000 : 0));
        } else {
            if (found < 0) return Fail(result, L"The selected character does not own this ability.");
            if (slot == 87) {
                // Journal/menu collectors stop at the first empty ID (368ED0).
                // Keep the remaining copies and their enabled bits in order.
                for (unsigned i = unsigned(found); i + 1 < 80; ++i) abilities[i] = abilities[i + 1];
                abilities[79] = 0;
            }
            else for (unsigned i = 0; i < 80; ++i) if ((abilities[i] & 0x7FFFu) == abilityId)
                abilities[i] = uint16_t(abilityId | (args[2] != 0 ? 0x8000 : 0));
        }
        Refresh(c, refresh);
        selectedCharacter = characterId;
        return Success(result, slot == 87 ? L"One copy of the ability was removed; active normal-form status was rebuilt." : L"Ability updated; active normal-form status was rebuilt.");
    }
    if (slot == 94) {
        if (!IsInteger(args[0], 0, 99)) return Fail(result, L"Consumable stock must be an integer from 0 to 99.");
        // Validate the whole preset before its first change. No story or magic items.
        for (unsigned id = 1; id <= 7; ++id) {
            const BYTE* row = FindItem(table, id);
            if (!CountItem(row) || row[2] != 0 || save[Stock + ItemSlot(row)] > 99)
                return Fail(result, L"The basic consumable preset does not match the current item table.");
        }
        for (unsigned id = 1; id <= 7; ++id) {
            double itemArgs[8] = {double(id), args[0]};
            if (!ProgressionHandle(c, 83, itemArgs, result) || result.code) return true;
        }
        return Success(result, L"Potion, Hi-Potion, Ether, Elixir and their three party variants were restocked.");
    }
    if (slot == 96 || slot == 97) {
        if (!IsInteger(args[0], 1, 13) || !IsInteger(args[1], 0, 32767) || !IsInteger(args[2], 0, 7))
            return Fail(result, L"Supply character 1..13, item ID (0 to unequip), and equipment slot 0..7.");
        const unsigned characterId = unsigned(args[0]), id = unsigned(args[1]), index = unsigned(args[2]);
        BYTE* character = reinterpret_cast<BYTE*>(Character(c, characterId));
        const unsigned kind = slot - 96, expectedType = 14 + kind;
        if (index >= character[16 + kind]) return Fail(result, L"This equipment slot is not unlocked for the selected character.");
        uint16_t& equipped = *reinterpret_cast<uint16_t*>(character + 20 + 16 * kind + 2 * index);
        if (equipped == id) return Success(result, L"The selected item is already equipped in that slot.");
        const BYTE* next = id ? FindItem(table, id) : nullptr;
        const BYTE* old = equipped ? FindItem(table, equipped) : nullptr;
        if ((id && (!CountItem(next) || next[2] != expectedType || save[Stock + ItemSlot(next)] < 1 || save[Stock + ItemSlot(next)] > 99)) ||
            (equipped && (!CountItem(old) || old[2] != expectedType || save[Stock + ItemSlot(old)] >= 99)))
            return Fail(result, L"Choose owned stock of the correct equipment type and leave room to return the old item.");
        RefreshSet refresh{};
        if (!CanRefresh(c, characterId, table, refresh)) return Fail(result, L"Return to normal form and load valid character status tables before changing equipment.");
        // Equipment is moved, not duplicated. Both counts and the destination were
        // validated before the first write; armor/accessories need no model reload.
        if (next) --save[Stock + ItemSlot(next)];
        if (old) ++save[Stock + ItemSlot(old)];
        equipped = uint16_t(id);
        Refresh(c, refresh);
        selectedCharacter = characterId;
        return Success(result, L"Equipment moved between bag and character; active normal-form status was rebuilt.");
    }
    return false;
}

void ProgressionCapabilities() {
    for (unsigned slot = 80; slot <= 97; ++slot) SupportCapability(slot);
}
void ProgressionSnapshot(const TrainerContext& c) {
    using namespace progression;
    SnapshotValue(88, selectedCharacter);
    SnapshotValue(92, selectedItem);
    if (!SaveReady(c)) return;
    const BYTE* save = reinterpret_cast<const BYTE*>(c.base + SaveRva);
    SnapshotValue(80, *reinterpret_cast<const int32_t*>(save + 9280));
    SnapshotValue(81, *reinterpret_cast<const int32_t*>(save + Experience));
    const BYTE* character = reinterpret_cast<const BYTE*>(Character(c, selectedCharacter));
    SnapshotValue(89, character[15]);
    SnapshotValue(90, *reinterpret_cast<const uint16_t*>(character));
    unsigned occupied = 0;
    for (unsigned i = 0; i < 80; ++i) occupied += (*reinterpret_cast<const uint16_t*>(character + 84 + 2 * i) & 0x7FFF) != 0;
    SnapshotValue(91, occupied);
    unsigned total = 0;
    for (unsigned i = 0; i < 320; ++i) total += save[Stock + i];
    SnapshotValue(95, total);
    ItemTable table{};
    if (!Items(c, table)) return;
    const BYTE* row = FindItem(table, selectedItem);
    if (!row) return;
    const unsigned index = ItemSlot(row);
    if ((row[3] & 1) && index < 256) SnapshotValue(93, (save[Unique + index / 8] >> (index & 7)) & 1);
    else if (row[2] != 19 && index < 320) SnapshotValue(93, save[Stock + index]);
}
void ProgressionTick(const TrainerContext&) {}
void ProgressionReset(const TrainerContext&) { /* One-shot save edits are not persistent effects. */ }
