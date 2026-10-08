// Included inside drive_features, after ObjectAvailable/ResourceAvailable.
// Read-only preparation for the native second-weapon load/constructor path.
// Evidence: drive_locked_crash_native_evidence.json (3E0CC0, 3EF8B0,
// 3EF910, 3E0660, 3A7A40) and drive_locked_crash_review_evidence.json.
// The caller owns scene/thread/save gates and commits only the returned ushort
// immediately before NativeBegin. No inventory ownership or unlock is required.

bool WeaponAddress(uintptr_t base, uint64_t offset, SIZE_T size, uintptr_t& out) {
    out=0;
    if(!base || offset>UINTPTR_MAX-base) return false;
    const uintptr_t address=base+static_cast<uintptr_t>(offset);
    if(size>UINTPTR_MAX-address || !Range(address,size)) return false;
    out=address; return true;
}

struct WeaponSpan { uintptr_t data=0; SIZE_T size=0; };
bool WeaponSpanAddress(const WeaponSpan& span, uint64_t offset, SIZE_T size, uintptr_t& out) {
    out=0;
    return offset<=span.size && size<=span.size-static_cast<SIZE_T>(offset) &&
        WeaponAddress(span.data,offset,size,out);
}
bool SystemTableSpan(unsigned wantedTag, uintptr_t installedRva, WeaponSpan& span) {
    span={};
    // 3F4C30 publishes the fixed system BAR and installs went/wmst from its
    // first type2/tag matches. 3E6010's preceding allocation header records
    // the loaded, 64-byte-rounded size, magic 0x23234141 and allocation kind1.
    const uintptr_t bar=At<uintptr_t>(0x2AE5E50);
    if(bar<16 || !Range(bar-16,32) || Field<unsigned>(bar-16,4)!=0x23234141 ||
        Field<unsigned>(bar-16,8)!=1 || (Field<unsigned>(bar,0)&0x00ffffff)!=0x00524142 ||
        DecodePacked(Field<uint32_t>(bar,8))!=bar) return false;
    const unsigned bytes=Field<unsigned>(bar-16,0);
    const int count=Field<int>(bar,4);
    if(bytes<16 || (bytes&63) || count<=0 ||
        uint64_t(count)*16+16>bytes || !Range(bar,bytes)) return false;
    const SIZE_T tableEnd=16+static_cast<SIZE_T>(count)*16;
    for(int i=0;i<count;++i) {
        const uintptr_t entry=bar+16+static_cast<SIZE_T>(i)*16;
        if(Field<uint16_t>(entry,0)!=2) continue;
        if(Field<unsigned>(entry,4)!=wantedTag) continue;
        const uintptr_t installed=At<uintptr_t>(installedRva);
        const uintptr_t data=DecodePacked(Field<uint32_t>(entry,8));
        const unsigned size=Field<unsigned>(entry,12);
        // Link flags do not alter native First-Match semantics. Every accepted
        // cell must belong to this entry and this loaded container allocation.
        if(!size || data!=installed || data<bar || data-bar<tableEnd ||
            data-bar>bytes || size>bytes-(data-bar)) return false;
        span={data,size}; return true;
    }
    return false;
}
bool WeaponTableSpans(WeaponSpan& mapping, WeaponSpan& motions) {
    mapping={}; motions={};
    return SystemTableSpan(0x746e6577,0x2AE5A38,mapping) &&
        SystemTableSpan(0x74736d77,0x2AE5A40,motions);
}

// Full bodies for the mirrored key/row/installation contract. This does not
// claim to pin every later constructor, asset parser or allocator.
constexpr BYTE kSkeletonKeyBytes[]={0x48,0x83,0xec,0x28,0x8b,0x49,0x08,0xe8,0x54,0x76,0x0f,0x00,0x0f,0xb6,0x40,0x07,0x48,0x83,0xc4,0x28,0xc3};
constexpr BYTE kSkeletonJointBytes[]={0x40,0x53,0x48,0x83,0xec,0x20,0x48,0x63,0xda,0xe8,0xe2,0xe5,0xfd,0xff,0x8b,0xc8,0xe8,0xab,0x34,0x01,0x00,0x0f,0xbf,0x44,0x58,0x04,0x48,0x83,0xc4,0x20,0x5b,0xc3};
constexpr BYTE kSkeletonCompareBytes[]={0x2b,0x0a,0x8b,0xc1,0xc3};
constexpr BYTE kSkeletonFindBytes[]={0x48,0x83,0xec,0x38,0x48,0x8b,0x15,0xad,0xac,0x6f,0x02,0x48,0x8d,0x05,0xde,0xff,0xff,0xff,0x48,0x63,0xc9,0x41,0xb9,0x08,0x00,0x00,0x00,0x48,0x89,0x44,0x24,0x20,0x4c,0x63,0x42,0x04,0x48,0x83,0xc2,0x08,0xff,0x15,0x72,0x10,0x19,0x00,0x48,0x83,0xc4,0x38,0xc3};
constexpr BYTE kSkeletonInstallBytes[]={0x48,0x89,0x0d,0x71,0xac,0x6f,0x02,0xc3};
struct SkeletonCodePin { uintptr_t rva; const BYTE* bytes; SIZE_T size; };
constexpr SkeletonCodePin kSkeletonPins[]={
    {0x3B5C10,kSkeletonKeyBytes,sizeof(kSkeletonKeyBytes)},
    {0x3D7620,kSkeletonJointBytes,sizeof(kSkeletonJointBytes)},
    {0x3EAAD0,kSkeletonCompareBytes,sizeof(kSkeletonCompareBytes)},
    {0x3EAAE0,kSkeletonFindBytes,sizeof(kSkeletonFindBytes)},
    {0x3EAB20,kSkeletonInstallBytes,sizeof(kSkeletonInstallBytes)}
};
bool SkeletonCodeReady() {
    for(const auto& pin:kSkeletonPins)
        if(!Range(g_base+pin.rva,pin.size) ||
            memcmp(reinterpret_cast<const void*>(g_base+pin.rva),pin.bytes,pin.size)) return false;
    return true;
}

bool WeaponSkeletonReady(uintptr_t formObject) {
    WeaponSpan skeleton;
    if(!Range(formObject,96) || !SkeletonCodeReady() ||
        !SystemTableSpan(0x746c6b73,0x2AE5798,skeleton) || skeleton.size<8) return false;
    const int count=Field<int>(skeleton.data,4);
    if(count<=0 || uint64_t(count)*8+8>skeleton.size) return false;
    // 3B5C10 uses object BYTE+7; weapon mapping instead uses WORD+78.
    const unsigned key=Field<BYTE>(formObject,7);
    unsigned previous=0; bool found=false;
    for(int i=0;i<count;++i) {
        const uintptr_t row=skeleton.data+8+static_cast<SIZE_T>(i)*8;
        const unsigned current=Field<unsigned>(row,0);
        if(i && current<=previous) return false;
        previous=current;
        // 3EAAD0 subtracts DWORD keys. Its signed comparison must agree with
        // this table's ordering for the selected BYTE key (no wrap inversion).
        if(current>key && uint64_t(current)-key>0x80000000ull) return false;
        if(current==key) found=true;
    }
    // A complete row contains both signed joints. Negative values are not
    // rejected: their model-specific encoding has not been established here.
    return found;
}

uintptr_t WeaponObjectRow(unsigned id) {
    // ObjectAvailable validates sorted tables, the first matching model name,
    // and excludes native context-dependent aliases. Preserve its precedence.
    if(!ObjectAvailable(id)) return 0;
    for(unsigned t=0;t<3;++t) {
        const uintptr_t pointer=At<uintptr_t>(0x2A25030+t*sizeof(uintptr_t));
        if(!pointer) continue;
        Table objects;
        if(!ReadTable(pointer,96,65536,objects)) return 0;
        for(unsigned i=0;i<objects.count;++i) {
            const uintptr_t row=objects.rows+static_cast<SIZE_T>(i)*96;
            if(Field<unsigned>(row,0)==id) return row;
        }
    }
    return 0;
}

bool FormWeaponAvailable(uintptr_t formObject, const progression::ItemTable& items, uint16_t item,
    const WeaponSpan& mapping, const WeaponSpan& motions) {
    if(!item || !Range(formObject,96)) return false;
    const BYTE* row=progression::FindItem(items,item);
    if(!row || row[2]!=2) return false; // Item type2 is a Keyblade.
    const unsigned group=Field<uint16_t>(formObject,78);
    if(!group) return false;

    // Native 3EF8B0: went[group] + WORD(item+4) is an index in DWORDs.
    // Spans come from the owning BAR, not a guessed item/model index limit.
    uintptr_t groupCell=0, modelCell=0;
    if(!WeaponSpanAddress(mapping,uint64_t(group)*4,4,groupCell)) return false;
    const unsigned first=Field<unsigned>(groupCell,0);
    if(!first) return false;
    const unsigned index=*reinterpret_cast<const uint16_t*>(row+4);
    if(!WeaponSpanAddress(mapping,(uint64_t(first)+index)*4,4,modelCell) ||
        !ObjectAvailable(Field<unsigned>(modelCell,0))) return false;

    // Native 3EF910/3EF750: slot1 uses wmst[1+2*group], 32-byte names.
    // An empty row skips loading, motion linking and weapon attachment. A dual
    // form needs a real offhand animation name, not merely a model-table hit.
    uintptr_t motionName=0;
    if(!WeaponSpanAddress(motions,(uint64_t(group)*2+1)*32,32,motionName)) return false;
    return Field<BYTE>(motionName,0)!=0 &&
        memchr(reinterpret_cast<const void*>(motionName),0,32)!=nullptr;
}

bool PlanFormWeapon(unsigned form, const progression::ItemTable& items, uint16_t& replacement) {
    replacement=0;
    if(form>6) return false;
    if(form!=1 && form!=4 && form!=5) return true;
    if(!items.data || !items.count || items.count>4096 ||
        !Range(items.data,static_cast<SIZE_T>(items.count)*24)) return false;

    const uintptr_t object=WeaponObjectRow(At<uint16_t>(0x2A252F0+2*(form+11)));
    if(!object || Field<uint16_t>(object,76)!=1 ||
        Field<int8_t>(object,87)!=static_cast<int>(form)) return false;
    WeaponSpan mapping, motions;
    if(!WeaponTableSpans(mapping,motions)) return false;
    // 3E0CC0 selects the form record using object+87; require the record being
    // planned to be exactly the one the native asynchronous loader will read.
    const uintptr_t record=g_base+0x9ABDA0+3588+56*(form-1);
    if(!Range(record,sizeof(uint16_t)) || !Range(g_base+0x9ABDA0,sizeof(uint16_t))) return false;
    if(FormWeaponAvailable(object,items,Field<uint16_t>(record,0),mapping,motions)) return true;
    const uint16_t primary=At<uint16_t>(0x9ABDA0);
    if(!FormWeaponAvailable(object,items,primary,mapping,motions)) return false;
    replacement=primary; return true;
}

bool WeaponHandNeedsSkeleton(unsigned group, unsigned hand, uint16_t item,
    const progression::ItemTable& items, bool& needed) {
    needed=false;
    // Native 3E0CC0/3EF8B0 skip construction for group/item/offset/model zero.
    if(!group || !item) return true;
    WeaponSpan mapping; uintptr_t cell=0;
    if(!SystemTableSpan(0x746e6577,0x2AE5A38,mapping) ||
        !WeaponSpanAddress(mapping,uint64_t(group)*4,4,cell)) return false;
    const unsigned first=Field<unsigned>(cell,0);
    if(!first) return true;
    const BYTE* row=progression::FindItem(items,item);
    if(!row || !WeaponSpanAddress(mapping,(uint64_t(first)+*reinterpret_cast<const uint16_t*>(row+4))*4,4,cell)) return false;
    if(!Field<unsigned>(cell,0)) return true;
    // 3EF750 skips this particular attachment lookup if the selected name is
    // empty. It still constructs the weapon; this is not an asset safety claim.
    WeaponSpan motions;
    if(!SystemTableSpan(0x74736d77,0x2AE5A40,motions) ||
        !WeaponSpanAddress(motions,(uint64_t(group)*2+hand)*32,32,cell)) return false;
    needed=Field<BYTE>(cell,0)!=0;
    return !needed || memchr(reinterpret_cast<const void*>(cell),0,32)!=nullptr;
}

bool FormSkeletonReady(const TrainerContext& c,unsigned form) {
    if(form>6) return false;
    unsigned index=form+11;
    if(!form) {
        const unsigned world=At<BYTE>(0x717008);
        if(world>=19) return false;
        const unsigned costume=At<BYTE>(0x9ACDE4+4*world)&31;
        if(costume>=18) return false;
        index=costume+8;
    }
    const uintptr_t object=WeaponObjectRow(At<uint16_t>(0x2A252F0+2*index));
    if(!object || Field<uint16_t>(object,76)!=1 || Field<int8_t>(object,87)!=static_cast<int>(form)) return false;
    progression::ItemTable items{}; uint16_t replacement=0;
    if(!progression::Items(c,items) || !PlanFormWeapon(form,items,replacement)) return false;
    const unsigned group=Field<uint16_t>(object,78);
    bool mainNeeds=false,offhandNeeds=false;
    if(!WeaponHandNeedsSkeleton(group,0,At<uint16_t>(0x9ABDA0),items,mainNeeds)) return false;
    if(form) {
        const uint16_t offhand=replacement ? replacement : At<uint16_t>(0x9ABDA0+3588+56*(form-1));
        if(!WeaponHandNeedsSkeleton(group,1,offhand,items,offhandNeeds)) return false;
    }
    return (!mainNeeds && !offhandNeeds) || WeaponSkeletonReady(object);
}
