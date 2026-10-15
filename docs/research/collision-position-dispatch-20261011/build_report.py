"""Bounded, parser-compatible claims for the selected contact dispatch chain."""
import json
from pathlib import Path
H=Path(__file__).resolve().parent
claims=[]
def add(a,finding,limits,related=(),extra=()):
    claims.append(dict(addr=hex(0x140000000+a),Finding=finding,Evidence=[f'evidence.json#functions[addr={hex(0x140000000+x)}]' for x in (a,*related)]+list(extra),Limitations=limits))
add(0x40f1c0,
 'The concrete derived constructor calls3CF830 (IDA name kh2_Attack_Construct) before storing ATTACK_OBJ vtable5CE6C0. It forwards a byte from second-argument QWORD+1472 BYTE+600 when both pointers are nonnull, otherwise0. After the base call it sets selector DWORD+200 from argument7, initializes32 float4 history records at+208 to(0,0,0,1), and stores argument5 at QWORD+720. When resource QWORD+48 BYTE+18 has neither mask0x02 nor0x08, it decodes base-produced DWORD+20, encodes that pointer+128, and assigns DWORD+40. The local body preserves base-produced fields+16/+20 and returns its input object pointer.',
 'The base constructor3CF830 is an explicit opaque boundary and is not fully captured here. Thus the exact origin/ownership/lifetime of DWORD+16 and+20 remains open. The derived class and update slot are proved, but its construction does not by itself admit any Actor receiver for live calls.',
 (0x40f610,),('evidence.json','root-xrefs-vtable-producer.json','model-results.json'))
add(0x40f610,
 'Original RTTI labels vtable5CE6C0 as YS::ATTACK_OBJ; its slot+24 at5CE6D8 contains40F610. This body treats RCX as the contact/attack object and passes exactly it to3D0BB0. It decodes object DWORD+20 for the selected geometry list and DWORD+16 for a separate gate involving DWORD+2488 mask0x04. After the initial gates it resets object DWORD+204 to0, iterates3B6250 with filter0x2040, matches entry BYTE+0 to object DWORD+200, prepares geometry via3C9C00 and calls3D08E0. At a matching entry with count below32, prior object mask0x04 and count0, it calls3D0BB0 using object+208 as the previous endpoint and a prepared stack endpoint. It stores float4 history at object+208+16*currentCount and increments count. Ordinary completion with a nonzero count ORs mask0x04; selected rejection/no-match paths call3D0EB0.',
 'This proves a concrete attack-object virtual-update caller, not a general Actor transform setter. Decode results, geometry suppliers, callbacks and list lifetime are not admitted by these local tests. Signed count branches and count reloads must not be upgraded to a reentrancy-safe capacity guarantee. Construction of object+16 is not established by this body. The second known3D0BB0 caller4376B0 remains outside the captured chain.',
 (0x3d0bb0,),('evidence.json','root-xrefs.json','root-xrefs-40f610.json'))
add(0x404eb0,
 'Original descriptor750300 points to vtable5CBA28, whose slot+216 at5CBB00 points to404EB0; RTTI names the YS::SORA specialization of PLAYER::VTABLE. The complete11-byte thunk moves incoming RDX to RCX and R8 to RDX, then tail-jumps3D63E0. Thus the selected3D1960 virtual call becomes3D63E0(first decoded record, contact object); incoming descriptor RCX is discarded.',
 'The table/slot is a concrete original-image binding. Applicability still requires the runtime decoder result to equal this descriptor with the original vptr and slot intact. No assertion is made that every contact object belongs to Sora or that dynamic class/ownership cannot change.',
 (0x3d63e0,0x3d1960),('evidence.json','model-results.json'))
add(0x4153e0,
 'Original descriptor7523B8 points to vtable5D15A0, whose slot+216 at5D1678 points to4153E0; RTTI names the YS::MICKEY specialization of PLAYER::VTABLE. This11-byte thunk performs the same two argument moves and tail-jump3D63E0 as the selected Sora thunk.',
 'Conditional original descriptor binding only. This does not prove arbitrary receiver types, all virtual overrides, runtime object lifetime or rescue-state reachability.',
 (0x3d63e0,0x3d1960),('evidence.json','model-results.json'))
add(0x1afe10,
 'Original base descriptor74AF78 points to vtable5C4F10, slot+216 at5C4FE8 pointing to1AFE10; RTTI names the YS::OBJ specialization. Its entire body is RET0 (C2 00 00), so it performs no body store or helper call and does not assign RAX. A caller must not interpret this null callback as a guaranteed Boolean-false return.',
 'Original target only; a patched vtable can choose other behavior. Preserved RAX is whatever reaches this callback, not a meaningful placement result.',
 (),('evidence.json','model-results.json'))
add(0x3d63e0,
 'For the first record argument, ORs DWORD+288 with mask0x02000000, then decrements BYTE+3444 only when it is nonzero. It calls3D4650 with the same record/contact pair, R8=0, R9D=FFFFFFFF and the original float constant-1 from623C48 as fifth argument. The ordinary callee path subsequently replaces that negative scalar by50. The function returns through3D4650 without normalizing its result. In the captured Sora/Mickey descriptor chain these are Actor reaction-state writes, not a direct contact-point-to-transform copy.',
 'Flags/counter ordering is local and tested over both concrete descriptor thunks. Native engine callees can have further effects; absence of a direct transform store in this body is not absence of movement in the full callback.',
 (0x3d4650,),('model-results.json',))
add(0x3d4650,
 'Reads contact DWORD+8. If mask0x40 is set, returns flags>>6 without calling helpers or writing a local processed marker. Otherwise decodes Actor DWORD+12 and checks record DWORD+8 for23: this branch calls403940 with the original first three arguments and returns that helper result without the ordinary processed-marker store. All other cases select the ordinary motion path via3BA9A0: default signed-negative motion code becomes43 on the true branch or41 on the false branch. It passes Actor+344 to3C86A0 and3C8310, selecting mode4 on true and0 on false, with zero scalar registers and zero fifth argument for the latter helper.',
 'The actor-state predicate, action record lifetime and internals of403940/motion routines remain opaque boundaries. The exact codes/modes and call order are proved; broad names such as collision-free placement or successful animation are not. Action23 may perform effects not covered by the ordinary path.',
 (),('model-results.json',))
add(0x3d4650,
 'In the ordinary path, a fifth-argument float below0 is replaced by50. When the resulting float is strictly greater than0, it obtains a float4 from3B56E0 and multiplies all four components by-1 via13FCC0. It passes the result and magnitude in XMM2 to3D4800 on the true predicate branch, or3D4960 on the false branch. Mode4 is requested before the direction helper in the true branch; mode0 is requested afterward in the false branch. It finally ORs contact flags mask0x40. Zero and unordered NaN skip the direction/scalar helper in the tested instruction branches. Return is whichever final opaque helper left in RAX, not a placement Boolean.',
 'Direction supplier and downstream direction/scalar helpers are explicit model stubs and are not classified as safe position setters. The model verifies float32/argument transfer and local stores, not actual velocity, knockback distance, collision safety, finite native resources or lifetime.',
 (0x13fcc0,),('model-results.json',))
add(0x3d1960,
 'The previously captured writer copies its input float4 to contact-object+180, sets category flags, and conditionally decodes object DWORD+16 and then the first DWORD of that record before virtual slot+216. For the three specifically proved original descriptors, the selected targets are base null callback1AFE10 or player thunk404EB0/4153E0. Composed original-instruction fixtures confirm the point copy precedes the actual virtual call, suppression mask0x100 avoids descriptor dispatch, and player callbacks add reaction/processed flags while the base null callback does not. This resolves concrete outcomes of the earlier open virtual slot without reclassifying contact-object+180 as Actor world position.',
 'This is an explicit re-use with a stronger bounded composition claim. The decoder token-to-descriptor mapping is a synthetic precondition, not proof of runtime contact ownership or all possible receiver classes. Optional effects are bypassed by declared fixture fields; native direction/motion callbacks remain opaque. No teleport API or live effect is approved.',
 (0x404eb0,0x4153e0,0x1afe10,0x3d63e0,0x3d4650),('model-results.json',))
out=dict(schema=1,Domain='native',title='Attack-object contact dispatch through selected Actor descriptors',originalSha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',scope='Original IDA/PE evidence and bounded models. No live actions or placement approval.',claims=claims)
(H/'report.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(len(claims),'bounded claims')
