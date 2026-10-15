"""Bounded canonical claims for the frozen capture/model scope."""
import json
from pathlib import Path
H=Path(__file__).resolve().parent
claims=[]
def add(rva,finding,limits,related=(),models=False):
    refs=[f'evidence.json#functions[addr={hex(0x140000000+x)}]' for x in (rva,*related)]
    if models:refs.append('model-results.json')
    claims.append(dict(addr=hex(0x140000000+rva),Finding=finding,Evidence=refs,Limitations=limits))
add(0x1752e0,
    'Consumes a state record: float4 start+0, float4 displacement+16, radius float+32, Y offset float+108, mode/category DWORD+112, result point+48 and status DWORD+116. It subtracts the Y offset from start, adds displacement, forces endpoint W=1, and conditionally transforms endpoint and adjusted start by context matrix+164 when context BYTE+229 is zero. Local XYZ length/radius is truncated with CVTTSS2SI then incremented for the signed-positive step loop. Radius is passed unchanged to the correction sphere; matrix scaling does not rescale it here. It collects a single candidate set using the union of the adjusted start point and the target expanded by1.5*radius, then uses per-step expanded bounds. Empty candidates copies target to result, conditionally transforms via matrix+100, adds Y offset and returns0. With candidates, -1 correction restores the previous substep and marks status mask0x04; positive correction enters the existing retry helper. Except category6, a final directed segment hit restores the original start and returns0 without adding Y offset again. Otherwise return is existing status+116 mask0x04 and Y offset is added. This body does not clear that bit. Category6 rewrites mode bits via AND FFFFFFFD / OR4 and skips the final segment test.',
    'Fresh byte-identical recapture of a previously recorded body; these are stronger dataflow/return assertions, not a new-body claim. Model boundary stubs supply candidate/correction/final-query results; this is not full volume-geometry simulation. Radius0, finite values, affine inverse pairs, valid table topology/capacity and retained ownership are not checked locally. One synthetic radius0/candidate case skips the signed-positive loop and retains old output coordinates. Collector exhaustion and the earlier body-bound MINSS finding remain separate limits. No collision-free placement approval follows from return0.',
    (0x140f50,0x13f900,0x183a50,0x183920,0x175190,0x174640,0x173b30),True)
add(0x16fec0,
    'Clears state+116 mask0x04 and writes DWORD FFFFFFFF across the two WORD IDs at+98/+100 before invoking1638F0 on the same state. It then invokes1752E0 with global pointer ABD448 and combines correction returns with OR. It clears QWORD+120 before163750. A true163750 result computes state+16=result+48 minus start+0 as float4 and invokes the static1752E0 again; otherwise172840 is invoked and its nonzero return clears+120 again. A changed float measurement from initial1e7 clears status mask0x02 and writes float+104 independently of the combined return.',
    'Ordinary-return sequencing and explicit model effect stubs only. The internals/lifetime of163750 and172840 remain outside this study. The10 direct caller addresses in root-ida-xrefs-16fec0.json are next targets, not a complete initialization/owner proof.',
    (0x1638f0,0x1752e0,0x13fd20,0x1a8e60),True)
add(0x1638f0,
    'Starts from global list head ABCCC0 and follows each node DWORD+20 through4AD270. It skips node flags+16 mask0x02, node DWORD+0 equal to state DWORD+128, node flags mask0x01, and contexts whose173EF0 check is nonzero. For eligible nodes it passes node QWORD+8 as context and the same input state to1752E0. A nonzero result sets its aggregate return to1 and replaces state+16 with state result+48 minus start+0 before continuing through later nodes.',
    'Fresh complete local path, manually read. Its list traversal was not instruction-modeled in this study. No linked-node lease, acyclicity, stable global head or atomic matrix snapshot is established. Existing173EF0 is retained as a reused dependency, not expanded to a full resource validator.',
    (0x1752e0,0x173ef0,0x13fd20,0x1a8e60))
add(0x3d1960,
    'Consumes object RCX, polygon index low16 RDX, point pointer R8, and pointer-to-node-pointer R9. With null node it obtains polygon normal/category from global static context via170AC0/170910; otherwise both come from node QWORD+8 through173500/173300. Category low-nibble1 selects OR16 into object DWORD+8 and effect mask256; other categories select OR8 and mask2. It then copies the full float4 to object+180. After that store, optional native calls depend on decoded object DWORD+40, resource QWORD+48 BYTE+11, and decoded object DWORD+20 flags+1736 mask0x40. Resource byte11 controls a masked-x64 shift of1<<32 by(byte-1) for the optional effect argument. Unless object flags mask0x100 is set, the final path decodes DWORD+16, decodes the DWORD at that result, and calls virtual slot+216 with(receiver, first decoded record, object). With mask0x100 set, RAX is flags>>8; otherwise RAX is whatever the final virtual call returns. It exposes no uniform Boolean placement-success contract.',
    'The only direct point store established here is object+180, whose meaning must not be upgraded to Actor world position. Optional callees and virtual implementations may have broader side effects. Tests replace compressed-pointer decoding and opaque callees with explicit fixtures. No allocation, ownership, callback identity, concurrency or safe teleport API is established.',
    (0x170ac0,0x170910,0x173500,0x173300,0x1a8e60),True)
add(0x173500,
    'Resolves the normal using context QWORD+24 polygon table,16-byte polygon stride, unsigned WORD polygon+10, context QWORD+48 normal table and16-byte normal stride. Copies float4, then forces W=1. If context BYTE+229 is zero, copies the first three16-byte rows of matrix+100 into a temporary matrix and supplies final row(0,0,0,1), transforms the normal and normalizes XYZ through142080. Stores the float4 to the caller output and returns that output pointer. Translation is excluded from this temporary matrix.',
    'No polygon/normal table extent checks or inverse-transpose operation are present. Zero-length input stays zero through the reused normalizer. The demonstrated direction-transform behavior is not a guarantee for arbitrary nonuniform scaling or malformed data.',
    (0x13f900,0x142080,0x1a8e60),True)
add(0x173300,
    'Returns context QWORD+40 plus4*unsigned WORD(polygon+14), where polygon is context QWORD+24 plus16*unsigned16 input index. This supplies the attribute DWORD read by3D1960 and170910.',
    'A borrowed table-cell pointer, not a lifetime token. No table-size or index validation is local.',(0x3d1960,0x170910),True)
add(0x170ac0,
    'Selects global ABD450 only when its byte selector is nonzero and that pointer is nonnull; otherwise selects ABD448. Invokes173500 for the supplied WORD polygon index and output.3D1960 passes selector0, therefore takes ABD448.',
    'No root-retention or global-snapshot guarantee. Model cases exercise the selector0 call from3D1960.',(0x173500,0x3d1960),True)
add(0x170910,
    'Uses the same selector rule between ABD450 and ABD448, passes unsigned16 polygon index to173300, reads its attribute DWORD and returns only the low nibble.3D1960 passes selector0.',
    'This is category extraction, not validation of the polygon or its owner.',(0x173300,0x3d1960),True)
add(0x3d0bb0,
    'The previously captured category4 line-query caller invokes3D1960 only after a query hit and then writes AL=1 itself. Its absent-hit exits write AL=0. The new composed fixture returns AL=1 even when3D1960 final virtual callback returns0. Thus its Boolean reports the local hit/ordinary call path, not verified placement by3D1960.',
    'Reused byte-identical body;171090 is an explicit result-effect stub in the composed case. An exception/nonreturning writer is not modeled as success. No actual Actor movement is proved.',(0x3d1960,),True)
add(0x175190,
    'Reused retry helper increments the caller counter before re-entering174640. Result-1 restores the supplied previous point; result0 copies the current sphere-center float4; positive result retries only when incremented counter<=5. In the composed1752E0 model, one substep with always-positive corrector results makes six total corrector invocations and marks state+116 mask0x04.',
    'Only this correction recursion is bounded. The outer step count, collector topology and callee duration are not bounded by this retry count. Actual collision corrections are supplied by the declared model stub.',(0x1752e0,0x174640),True)
out=dict(schema=1,Domain='native',title='Collision state correction and contact-result writer boundaries',originalSha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',scope='Fresh read-only IDA views and original-byte synthetic interpretation; no game or placement API approval.',claims=claims)
(H/'report.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(len(claims),'bounded claims')
