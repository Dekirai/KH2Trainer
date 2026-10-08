"""Materialize the bounded findings and selected instruction anchors."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def save(name,data): (HERE/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
e=load(HERE/'evidence.json')
by_addr={int(i['addr'],16):i for f in e['functions'] for i in f['decodedInstructions']}
groups={
 'radius and substep arithmetic':[0x14017532C,0x1401753A7,0x1401754B3,0x1401754B7,0x1401754BC,0x140175516],
 'persistent context filters':[0x1401745C5,0x1401745CB,0x1401745CE,0x1401745D2,0x140172913,0x140172922,0x14017292D,0x140172938],
 'candidate filter and special mode':[0x1401742A9,0x1401742AC,0x1401742B3,0x1401742BA,0x1401742C1,0x1401742CC,0x1401742D5,0x1401742E3],
 'category switch':[0x1401742E7,0x1401742EA,0x1401742F6,0x140174301,0x140174303,0x140174308,0x14017430D,0x140174312,0x140174314,0x140174318,0x140174320,0x140174325],
 'capacity and child decoding':[0x14017435A,0x14017435F,0x140174362,0x140174367,0x14017436D,0x1401743A5,0x1401743A9,0x1401743AB,0x1401743C1],
 'signed box overlap':[0x1401842D7,0x1401842E0,0x1401842EA,0x1401842F4,0x1401842FE,0x140184308],
 'ray facing and endpoints':[0x14018B515,0x14018B519,0x14018B53C,0x14018B541,0x14018B548,0x14018B54A,0x14018B54D],
 'polygon edge tolerance':[0x14018B7F0,0x14018B88B,0x14018B88E],
 'off-plane projection scalar omitted by decompiler':[0x14017916A,0x140179194],
 'quantization is not a symmetric saturation':[0x14018498B,0x140184995,0x1401849C7,0x1401849DD,0x1401849E1],
 'floor acceptance threshold':[0x1401727CA,0x1401727D0,0x1401727D6,0x1401727EA,0x1401727F3,0x1401727FE],
 'unordered side classifier':[0x14018B3EB,0x14018B3EE,0x14018B3FB,0x14018B402],
}
anchors=[]
for meaning,addresses in groups.items():
 for addr in addresses:
  i=by_addr[addr]
  anchors.append(dict(addr=i['addr'],mnemonic=i['mnemonic'],operands=i['operands'],meaning=meaning))
save('semantic-anchors.json',dict(schema=1,anchors=anchors))

findings={
 '16fec0':'Clears state+116 bit2 and sets contact WORDs+98/+100 to FFFF sentinels, queries moving and static collision contexts, then tests floor candidates. The static context comes from ABD448 without a null check. A chosen moving candidate can cause another static correction. The 136-byte local query is not an isolated pure operation because callees change shared context filters.',
 '1638f0':'Traverses the ABCCC0 moving list through encoded DWORD+20 links. Skips node flags+16 mask2, matching state+128 identity, mask1 and contexts whose tested basis length is too small. A nonzero correction updates state movement+16 to result+48 minus start. No cycle or generation check is present in this loop.',
 '163750':'Traverses the same moving list but omits the mask1 skip used by 1638F0. Among candidates with state+116 bit0 clear, saves the strictly lowest result Y below initial 10000000 and restores the saved 136-byte state. Other hits can reduce the separately returned height. This is an ordered selection rule, not proof that the retained pointer remains live.',
 '163690':'Copies the query state at offsets0..95 as six 16-byte vectors, WORDs96/98/100/102, DWORDs104/108/112/116, QWORD120 and DWORDs128/132: 136 bytes total, including a borrowed moving-object pointer.',
 '173ef0':'Tests squared XYZ lengths of context basis vectors+100/+116/+132 against binary32 0.01 and returns true if one is strictly smaller. This does not establish matrix invertibility or finite components in every case.',
 '1752e0':'Reads state+32 as the collision sphere radius, subtracts state+108 from start Y, derives displacement and computes CVTTSS2SI(length/radius)+1 substeps without a finite/radius bound. Transforms endpoints when context+229 is zero, builds quantized candidate bounds, sets shared filters92=15/96=4/228=1/231=0, and performs bounded correction retries. BDX1:367 writes its stepped scalar to this radius field; it is not merely a movement-distance parameter.',
 '1745c0':'Writes shared collision context DWORD+92 mask, DWORD+96 comparison value, BYTE+228 equality/inverse selector and BYTE+231 special flag. No prior value is saved or restored by this function.',
 '1741c0':'Recursively collects polygons from 32-byte nodes and 20-byte active leaf records using inclusive signed-WORD AABB overlap, attribute filtering and a category switch. Stores at most1023 WORD indices from a zero initial count. ChildFFFF ends the child list; other child WORDs are sign-extended before recursion. No node count, cycle or ownership validation appears. The recorded extent includes a64-byte switch table and3-byte padding after RET, separately verified as data.',
 '174640':'Applies sphere-face and edge/vertex correction passes selected by state flags and polygon attributes. Attribute mask0x100000 skips a polygon. State+32 supplies radius-dependent offsets; alternate branches use state+36 and+108. With mode bit0 clear, a correction count reaching10 takes the -1 fallback. Input polygon count and resource indices rely on upstream data, and no universal malformed-input safety is established.',
 '175190':'Increments the retry counter, invokes174640 again, restores the supplied previous point on -1 and copies the sphere center on zero. A further retry is made only while the incremented counter is at most5. This bound limits this correction recursion, not arbitrary hierarchy traversal.',
 '172840':'Constructs a Y-directed floor segment from state result+48, absolute movementY+20 and offset+108, with an additional0..100 clamp for category0. Writes the same shared filters as1752E0, calls173B30, records hit height or10000000, updates state+116 bit1 and calls172640 to decide result acceptance.',
 '172640':'Invalid polygonFFFF sets state+116 bit0 and polygon96FFFF. With mode bit0 clear, an ordered contact above (offset108-dimension36)+(startY+positiveMovementY)+field132-1 sets bit0 without copying; the other branch copies the contact. With mode bit0 set, a plane-side classifier and low-nibble attribute2 affect acceptance. An exact620/ABB920==3 special case also exists. Bit0 is therefore not a universal query-success flag.',
 '173b30':'Builds a segment AABB, inherits shared context filters, collects up to1023 candidates, resolves triangle/quad vertex pointers, and tests directed intersections. Chooses only a strictly smaller squared XYZ distance than the current binary32 threshold, initially1e14; equal hits keep the first. Returns false and polygonFFFF when no candidate qualifies. No separate output initialization on that miss is established.',
 '18b4d0':'For ordered finite scalars, rejects nonnegative plane-direction dot products, computes intersection fraction and accepts the inclusive0..1 interval before polygon-edge testing. COMISS/JAE and COMISS/JA do not reject unordered NaNs when SSE invalid exceptions are masked; downstream behavior remains data-dependent. The routine is not a finite-input validator.',
 '18b760':'Checks cyclic triangle order1,2,0 or quad order1,2,3,0, rejecting an edge when dot(cross(point-vertex,next-vertex),normal)>binary32 0.01. The current caller provides3 or4 vertices. The helper itself accepts nonpositive counts immediately and does not bound arbitrary larger counts or normalize the normal.',
 '1795d0':'Computes dot(sphereCenter,planeXYZ)+planeW and stores it through the third argument, then tests it between zero and sphere radius+16. Geometry interpretation requires the expected plane normalization; this helper does not normalize it.',
 '179150':'Reads the distance through R9 into XMM2 before1A8F90, projects center minus scaled plane normal, stores the result and calls18B760. Hex-Rays omits the implicit XMM2 scalar argument in its rendered1A8F90 call; assembly establishes it.',
 '178cb0':'Implements sphere-to-polygon edge/vertex proximity fallback and uses a compiler-style one-time initialization path involving ABE780 and439F50/4399B0/439EF0. The full CRT initialization, teardown and concurrency closure is outside this study; the path cannot be described as global-state-free math.',
 '184970':'Quantizes a six-float AABB using indexed margin values1/10/20/100 and scales1/0.1/0.05/0.01. It only applies the lower clamp branch to lower endpoints and the upper clamp branch to upper endpoints, converts with CVTTSS2SI and stores low16 bits. The signed input index and nonfinite/out-of-range values are not validated by this helper; this is not symmetric saturation.',
 '1842d0':'Performs all six AABB separation comparisons as signed16-bit JL/JG tests. Touching faces count as overlap. Unsigned-looking decompiler types do not change these signed native comparisons.',
 '18b3b0':'Classifies dot(vertex-point,normal) as1 below binary32 -0.001,2 within the inclusive tolerance band, otherwise0 for ordered values. Masked unordered COMISS takes both JBE branches and returns2. This is not a NaN-rejecting plane test.',
 '1729d0':'Builds a temporary polygon from context+32 vertex storage using WORD vertex indices1/2/3 and optional4. Fourth indexFFFF chooses count3; otherwise count4. No index extent or lifetime validation is present.',
 '183990':'Passes the two adjacent 16-byte segment endpoints to184850 and returns the output AABB pointer.',
 '184850':'For ordered finite endpoint coordinates, writes XYZ component minima at0/4/8 and maxima at12/16/20 to form a six-float segment AABB. It does not validate pointers or sanitize nonfinite coordinates.'
}
claims=[]
for rva,finding in findings.items():
 addr=hex(0x140000000+int(rva,16))
 assert any(f['addr'].lower()==addr for f in e['functions'])
 claims.append(dict(addr=addr,Finding=finding,Evidence=[f'evidence.json#functions[addr={addr}]'],Limitations='Bounded static claim for the pinned executable. Complete recorded bytes do not imply complete semantics, validated resource ownership, live reachability or successful game execution.'))
save('claims.json',dict(schema=1,Domain='native',claims=claims))
upstream=load(HERE.parent/'bdx-actor-query-20261008/annotations.json')['annotations']['1:367']
annotation=dict(upstream)
annotation.update(name='Run expanding Actor collision query',summary='Decodes wrapper+4 Actor and copies its136-byte collision state. Operand1 advances by100 to a float limit and sets state+32, consumed as a collision sphere radius, plus field+40. Movement starts at zero; each retained result seeds the next iteration. Operand2 controls a mode bit and an optional flag break. Returns shared buffer RVA0x756B48 as @ADR, discarding the helper result.',notes='This call also changes shared static/moving collision-context filters; copying Actor state does not make it a pure query. Radius units and the independent meaning of field+40 remain unassigned. Missing or stale Actor/collision resources are unchecked. The result can be stale on nonpositive/NaN input or an early flag break, and1:147 overwrites the same buffer. With masked SSE exceptions and nearest-even rounding, limits above2^31 or positive infinity can stall the outer scalar loop if helpers return and no flag break applies. Helpers trust geometry indices, hierarchy acyclicity and matrix/radius inputs; the1023-candidate cap is not a traversal bound.',evidence='actor-query-collision-20261008/evidence.json + actor-query-collision-20261008/report.txt + bdx-actor-query-20261008/evidence.json + bdx-actor-query-20261008/model.json')
annotation['summary']='Decodes wrapper+4 Actor and copies its 136-byte collision state. A local scalar advances by 100 toward operand1 as the float limit and sets state+32, consumed as a collision sphere radius, plus field+40. Movement starts at zero; each retained result seeds the next iteration. Operand2 controls a mode bit and an optional flag break. Returns shared buffer RVA 0x756B48 as @ADR, discarding the helper result.'
annotation['notes']=upstream['notes'].replace('Geometry semantics, units, transitive effects and retail reachability remain open.', 'The query changes shared static/moving collision-context filters; copying Actor state does not make it a pure query. Radius units and the independent meaning of field+40 remain unassigned. Geometry indices, hierarchy acyclicity, resource lifetimes and matrix/radius inputs are trusted. The 1023-candidate cap is not a traversal bound. Retail reachability of extreme inputs remains open.')
save('annotations.json',dict(schema=1,originalSha256=e['originalSha256'],annotations={'1:367':annotation}))
print(json.dumps(dict(claims=len(claims),anchors=len(anchors),annotations=1)))
