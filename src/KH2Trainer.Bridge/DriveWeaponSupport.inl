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
bool WeaponTableSpans(WeaponSpan& mapping, WeaponSpan& motions) {
    mapping={}; motions={};
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
        const unsigned tag=Field<unsigned>(entry,4);
        WeaponSpan* span=nullptr; uintptr_t installed=0;
        if(tag==0x746e6577 && !mapping.data) { span=&mapping; installed=At<uintptr_t>(0x2AE5A38); }
        else if(tag==0x74736d77 && !motions.data) { span=&motions; installed=At<uintptr_t>(0x2AE5A40); }
        if(!span) continue;
        const uintptr_t data=DecodePacked(Field<uint32_t>(entry,8));
        const unsigned size=Field<unsigned>(entry,12);
        // Link flags do not alter native First-Match semantics. Every accepted
        // cell must belong to this entry and this loaded container allocation.
        if(!size || data!=installed || data<bar || data-bar<tableEnd ||
            data-bar>bytes || size>bytes-(data-bar)) return false;
        *span={data,size};
        if(mapping.data && motions.data) return true;
    }
    return false;
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
    if(!object || (Field<uint16_t>(object,76)!=1 && Field<uint16_t>(object,76)!=14) ||
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
