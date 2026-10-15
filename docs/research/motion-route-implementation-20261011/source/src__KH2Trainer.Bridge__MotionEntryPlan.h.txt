// Exact-build Motion entry planning. No allocation, installation or game call.
// Evidence: docs/research/motion-resource-binding-20261011/evidence.json, 3C8CD0.
// Original PE SHA256: 9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed.
// Caller supplies a readable source span and private output storage. Source-module
// lifetime, thread admission, bootstrap, rollback and publication belong to its owner.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace motion_entry_plan {
enum class Kind : unsigned { NormalBind, Count };
enum class Error : unsigned { None, InvalidKind, InvalidAddress, InputSpan, Fingerprint, RelayRange, Alias };
enum class Relocation : unsigned { Outside, Boundary, InvalidInterior };
constexpr size_t ImageSize=80, UnwindOffset=32, RuntimeOffset=64;
struct RuntimeFunction { uint32_t BeginAddress,EndAddress,UnwindData; };
static_assert(sizeof(RuntimeFunction)==12,"Windows AMD64 runtime entry");
struct Definition {
    uintptr_t rva;
    const unsigned char* original;
    size_t originalSize;
    unsigned char prefixSize;
    unsigned char boundaries[4]; // Includes the continuation boundary.
    unsigned char boundaryCount;
    unsigned char unwind[12];
    unsigned char unwindSize;
};
// Complete 287-byte body; SHA256 7be995bb4bd05f399acb2ff1b0553ef2b36eeb5ed642a742a51432c7b458be1f.
// Original .pdata at RVA2BB80E8: [3C8CD0,3C8DEF), unwind RVA6E6434.
// Original UNWIND_INFO: 01 22 0a 00 22 78 02 00 14 68 03 00
//                       0f 64 0b 00 0f 34 0a 00 0f 72 0b 70.
inline constexpr unsigned char Body3C8CD0[] = {
    0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xec, 0x40, 0x0f,
    0x29, 0x74, 0x24, 0x30, 0x48, 0x8b, 0xf9, 0x48, 0x8b, 0x09, 0x0f, 0x28, 0xf2, 0x0f, 0x29, 0x7c,
    0x24, 0x20, 0x8b, 0xf2, 0x0f, 0x28, 0xfb, 0xe8, 0xf4, 0x4a, 0x04, 0x00, 0x84, 0xc0, 0x74, 0x03,
    0x0f, 0x57, 0xf6, 0x48, 0x8b, 0x47, 0x10, 0x33, 0xdb, 0x48, 0x83, 0xe8, 0x80, 0x48, 0x89, 0x87,
    0x48, 0x01, 0x00, 0x00, 0x48, 0x89, 0x9f, 0x58, 0x01, 0x00, 0x00, 0x48, 0x89, 0x9f, 0x60, 0x01,
    0x00, 0x00, 0x85, 0xf6, 0x78, 0x26, 0x48, 0x39, 0x1f, 0x74, 0x21, 0x48, 0x8b, 0x4f, 0x08, 0x48,
    0x85, 0xc9, 0x74, 0x0c, 0x8b, 0xd6, 0xe8, 0x65, 0x4a, 0x04, 0x00, 0x48, 0x85, 0xc0, 0x75, 0x0f,
    0x48, 0x8b, 0x0f, 0x8b, 0xd6, 0xe8, 0x56, 0x4a, 0x04, 0x00, 0xeb, 0x03, 0x48, 0x8b, 0xc3, 0x0f,
    0x28, 0xdf, 0x0f, 0x28, 0xd6, 0x48, 0x8b, 0xd0, 0x48, 0x8b, 0xcf, 0xe8, 0xe0, 0xfc, 0xff, 0xff,
    0x84, 0xc0, 0x74, 0x71, 0x48, 0x8b, 0x0f, 0x89, 0x77, 0x2c, 0xe8, 0x61, 0x4a, 0x04, 0x00, 0x84,
    0xc0, 0x75, 0x07, 0xb8, 0xff, 0xff, 0xff, 0xff, 0xeb, 0x10, 0x8b, 0xc6, 0x25, 0x03, 0x00, 0x00,
    0x80, 0x7d, 0x07, 0xff, 0xc8, 0x83, 0xc8, 0xfc, 0xff, 0xc0, 0x89, 0x47, 0x30, 0x85, 0xc0, 0x75,
    0x0f, 0x48, 0x8b, 0x47, 0x10, 0x81, 0x88, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x90,
    0x48, 0x85, 0xdb, 0x75, 0x09, 0x48, 0x8b, 0x9f, 0xd8, 0x00, 0x00, 0x00, 0xeb, 0x0e, 0x8b, 0x8b,
    0xe8, 0x00, 0x00, 0x00, 0xe8, 0xb7, 0x44, 0x0e, 0x00, 0x48, 0x8b, 0xd8, 0x48, 0x85, 0xdb, 0x74,
    0x12, 0x0f, 0x28, 0xdf, 0x0f, 0x28, 0xd6, 0x8b, 0xd6, 0x48, 0x8b, 0xcb, 0xe8, 0xff, 0xfe, 0xff,
    0xff, 0xeb, 0xcd, 0xb0, 0x01, 0x48, 0x8b, 0x5c, 0x24, 0x50, 0x48, 0x8b, 0x74, 0x24, 0x58, 0x0f,
    0x28, 0x74, 0x24, 0x30, 0x0f, 0x28, 0x7c, 0x24, 0x20, 0x48, 0x83, 0xc4, 0x40, 0x5f, 0xc3,
};
static_assert(sizeof(Body3C8CD0)==287,"complete normal binding body");
inline constexpr Definition Definitions[] = {
    // Prefix: MOV [RSP+8],RBX. No relative operands, stack allocation or branch.
    // The relocated prefix has no stack adjustment: RBX's saved slot is RSP+8.
    // Version1, no handler, UWOP_SAVE_NONVOL(RBX) at completed offset5, scaled slot1.
    {0x3C8CD0,Body3C8CD0,sizeof(Body3C8CD0),5,{0,5,0,0},2,
        {1,5,2,0,5,0x34,1,0},8}
};
static_assert(sizeof(Definitions)/sizeof(Definitions[0])==static_cast<unsigned>(Kind::Count),"exact entries");
struct Plan {
    alignas(16) unsigned char image[ImageSize]{};
    unsigned char entryPatch[10]{};
    uintptr_t entry=0,trampoline=0,relay=0;
    unsigned char prefixSize=0,codeSize=0,unwindSize=0,boundaryCount=0,patchSize=0;
    unsigned char boundaries[4]{};
    bool valid=false;
};
inline const Definition* Get(Kind kind) {
    const auto i=static_cast<unsigned>(kind);
    return i<static_cast<unsigned>(Kind::Count)?&Definitions[i]:nullptr;
}
inline bool Span(uintptr_t p,size_t n) { return p && n && n<=UINTPTR_MAX-p; }
inline bool Overlap(uintptr_t a,size_t an,uintptr_t b,size_t bn) {
    return a<b+bn && b<a+an; // Inputs already passed Span.
}
inline bool Relative32(uintptr_t next,uintptr_t target,int32_t& result) {
    if(target>=next) {
        const auto d=target-next;if(d>INT32_MAX)return false;result=static_cast<int32_t>(d);
    } else {
        const auto d=next-target;if(d>uint64_t(INT32_MAX)+1)return false;
        result=d==uint64_t(INT32_MAX)+1?INT32_MIN:-static_cast<int32_t>(d);
    }
    return true;
}
// Failure leaves out unchanged. The relay is distinct from the original-call
// trampoline. The installer supplies its body; this function plans bytes only.
inline Error BuildPlan(Kind kind,uintptr_t moduleBase,const void* liveBody,size_t liveSize,
    uintptr_t trampolineAddress,uintptr_t entryRelayAddress,Plan& out,bool breakpoint) {
    const auto* d=Get(kind);if(!d)return Error::InvalidKind;
    if(!moduleBase || d->rva>UINTPTR_MAX-moduleBase)return Error::InvalidAddress;
    const uintptr_t entry=moduleBase+d->rva;
    if(!Span(entry,d->originalSize) || !Span(trampolineAddress,ImageSize) ||
       (trampolineAddress&15) || (!breakpoint && !Span(entryRelayAddress,14)) ||
       (breakpoint && entryRelayAddress))return Error::InvalidAddress;
    if(!liveBody || liveSize<d->originalSize ||
       !Span(reinterpret_cast<uintptr_t>(liveBody),d->originalSize))return Error::InputSpan;
    if(Overlap(entry,d->originalSize,trampolineAddress,ImageSize) ||
       (!breakpoint && Overlap(entry,d->originalSize,entryRelayAddress,14)) ||
       (!breakpoint && Overlap(trampolineAddress,ImageSize,entryRelayAddress,14)) ||
       Overlap(reinterpret_cast<uintptr_t>(liveBody),d->originalSize,reinterpret_cast<uintptr_t>(&out),sizeof(out)))
        return Error::Alias;
    if(memcmp(liveBody,d->original,d->originalSize))return Error::Fingerprint;
    int32_t distance=0;
    if(!breakpoint && !Relative32(entry+5,entryRelayAddress,distance))return Error::RelayRange;
    Plan next{};
    next.entry=entry;next.trampoline=trampolineAddress;next.relay=entryRelayAddress;
    next.prefixSize=d->prefixSize;next.codeSize=static_cast<unsigned char>(d->prefixSize+13);
    next.unwindSize=d->unwindSize;next.boundaryCount=d->boundaryCount;
    memcpy(next.boundaries,d->boundaries,sizeof(next.boundaries));
    memcpy(next.image,d->original,d->prefixSize);
    unsigned char* jump=next.image+d->prefixSize;
    // R11 is Win64-volatile. The complete pinned body has no R11 read or write;
    // its first call is at +39, after restoring the original argument flow.
    // A mod11 JMP avoids Windows' mod00-indirect-JMP epilog recognition, which
    // could otherwise skip the prefix's saved-register unwind.
    jump[0]=0x49;jump[1]=0xbb; // MOV R11,imm64.
    const uint64_t continuation=entry+d->prefixSize;
    memcpy(jump+2,&continuation,sizeof(continuation));
    jump[10]=0x41;jump[11]=0xff;jump[12]=0xe3; // JMP R11.
    memcpy(next.image+UnwindOffset,d->unwind,d->unwindSize);
    const RuntimeFunction runtime{0,next.codeSize,static_cast<uint32_t>(UnwindOffset)};
    memcpy(next.image+RuntimeOffset,&runtime,sizeof(runtime));
    if(breakpoint) { next.entryPatch[0]=0xcc;next.patchSize=1; }
    else {
        memset(next.entryPatch,0x90,d->prefixSize);next.entryPatch[0]=0xe9;
        memcpy(next.entryPatch+1,&distance,sizeof(distance));next.patchSize=d->prefixSize;
    }
    next.valid=true;out=next;return Error::None;
}
inline Error Build(Kind kind,uintptr_t moduleBase,const void* liveBody,size_t liveSize,
    uintptr_t trampolineAddress,uintptr_t entryRelayAddress,Plan& out) {
    return BuildPlan(kind,moduleBase,liveBody,liveSize,trampolineAddress,entryRelayAddress,out,false);
}
// Plans a one-byte permanent entry breakpoint plus the same original-call image.
// This establishes no VEH route, observed thread, drained entry or resource lease.
inline Error BuildBreakpoint(Kind kind,uintptr_t moduleBase,const void* liveBody,size_t liveSize,
    uintptr_t trampolineAddress,Plan& out) {
    return BuildPlan(kind,moduleBase,liveBody,liveSize,trampolineAddress,0,out,true);
}
// Map only complete instruction boundaries inside the copied prefix. The original
// continuation stays in place. Pass an unchanged Plan produced by this planner.
inline Relocation MapSuspendedInstruction(const Plan& p,uintptr_t ip,uintptr_t& mapped) {
    if(!p.valid || p.prefixSize!=5 || p.boundaryCount!=2 || p.boundaries[0]!=0 || p.boundaries[1]!=5)
        return Relocation::InvalidInterior;
    if(ip<p.entry || ip-p.entry>=p.prefixSize)return Relocation::Outside;
    if(ip==p.entry) { mapped=p.trampoline;return Relocation::Boundary; }
    return Relocation::InvalidInterior;
}
} // namespace motion_entry_plan
