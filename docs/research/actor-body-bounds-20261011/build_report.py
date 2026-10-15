"""Bounded, address-specific findings from the saved original bodies."""
import hashlib, json
from pathlib import Path
H=Path(__file__).resolve().parent
def dump(n,o): (H/n).write_text(json.dumps(o,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
e=json.loads((H/'evidence.json').read_text()); known={f['addr'] for f in e['functions']}
claims=[]
def claim(rva,finding,limits,related=()):
    a=hex(0x140000000+int(rva,16)); refs=[a,*[hex(0x140000000+int(v,16)) for v in related]]
    assert all(x in known for x in refs)
    claims.append({'addr':a,'Finding':finding,'Evidence':[f'evidence.json#functions[addr={x}]' for x in refs],'Limitations':limits})
claim('40AC20','For count0 the function zeroes the six-float output. Otherwise it initializes lower=(x-radius,y-height,z-radius) and upper=(x+radius,y+height,z+radius) from the first40-byte record after a24-byte header. For every later record, it uses MINSS at40ACF0/40AD01/40AD14 for lower coordinates and also MINSS at40AD27/40AD39/40AD50 for upper coordinates. It does not compute an enclosing union of arbitrary multiple finite records. The original three-body native probe reproduces this for12 synthetic cases, including separated centers0 and100 with radius1 producing x[-1,1] rather than[-1,101].',
      'Native probe inputs are finite, dimensions nonnegative and counts0..3. This is not a claim of malformed retail data, current player reachability, all-input floating-point behavior, or a proven gameplay defect. The intended wider engine contract is not fully established.', ['184270','184940'])
claim('184270','Writes zero to the24-byte output through three QWORD stores. The bounds helper tailcalls this path when its countDWORD is exactly zero.',
      'Zero coordinates are the native representation here; no generic empty-box sentinel or validity interpretation is inferred.', ['40AC20'])
claim('184940','Stores the first three scalar arguments from XMM1/XMM2/XMM3 at output+0/+4/+8 and the next three stack Float32 arguments at+12/+16/+20. The body is a plain six-coordinate initializer.',
      'Hex-Rays omits/mistypes floating-point arguments in the caller. ABI and stores are established from complete original ASM.', ['40AC20'])
claim('3CBFE0','When Actor+2696 is null and Actor+2560 is nonnull, calls40AC20 with output Actor+2200. Its nonnull+2696 branch instead derives a local box, transforms eight corners through Actor+64, and updates separate lower/upper coordinates using comparisons. The fallback MINSS behavior therefore does not describe every model-bound Actor path.',
      'The8-corner branch is inspected statically, not executed by the native probe. Downstream consumers of Actor+2200 and real model/resource reachability are not fully traced.', ['40AC20'])
claim('55BAF0','For nonnull Actor+1600, obtains six coordinates through40AC20, sums matching lower/upper pairs and scales by0.5 before copying to the output; it then zeroes output+8. With null+1600 it uses3B5B40 instead.',
      'The caller uses the bounds result as part of a center calculation. The complete gameplay meaning, all callers and final use of the resulting vector remain outside this study.', ['40AC20'])
claim('562C50','On its Actor+1600 branch computes a midpoint from40AC20 output before the later loop calling428710, then writes the prepared vector to each successful result+264. The null+1600 branch uses3B5B40. Thus this path also consumes the body-bound calculation outside3CBFE0.',
      'Only the selected preparation/copy relationship is claimed; the full spawning system, scene reachability and visible effect are not established.', ['40AC20'])
claim('3C9B30','Reads a signed-positive resource count at+0 and counts20-byte records starting at+64 whose byte+4 equals the requested kind. It returns that count; it does not apply the per-Actor enable-state filter here.',
      'There is no payload-size input in this body. Valid resource count/span and ordinary caller lifetime are prerequisites.')
claim('40A9E0','Counts the requested resource kind through3C9B30, returns null for zero count, otherwise allocates24+40*count bytes, stores kind at+16, initializes current record count+0 to0 and stores Actor at+8. It stores no explicit allocation capacity in those initialized header fields.',
      'This is local construction, not a full ownership/lifetime proof. Allocation failure and hostile counts are not exercised.', ['3C9B30'])
claim('3B6310','Binds Actor+2744 to the supplied resource and builds two new buffers through40A9E0: kind1 published to Actor+2560 and kind2 to Actor+1600. Earlier selected kind17 records also supply native collision radius/height values.',
      'The claim covers local binding/publication. Prior-buffer retirement, every caller and resource lifetime remain unresolved.', ['40A9E0'])
claim('40B140','Clears the current buffer count first. It rebuilds only when the owning Actor flags+2488 contain0x400, enumerating the stored kind via3B4F10 and producing40-byte output records through3C9C00. The local loop checks no stored allocation capacity.',
      'The enable-state enumerator and resource ownership are native prerequisites. No claim is made that ordinary retail execution overruns this allocation.', ['3C9C00','40A9E0'])
claim('3C9C00','The selected active branch copies signed WORD radius and height from resource+16/+18 into output+4/+8, resolves the joint/Actor matrix through3B50F0, transforms the local signed-WORD center, then subtracts signed resource+14 from resulting centerY. Radius/height are not multiplied by Actor scale here.',
      'This body is a bounded conversion from valid native resource records. Complete joint lookup, every coordinate source and all physical consequences remain outside the probe.')
claim('3CCB90','Publishes the initial Actor+64 matrix through1A94C0 at3CCFE9; after optional floor branches it conditionally rebuilds Actor+2560 via40B140 at3CD0E3, then evaluates motion root and publishes Actor+2056 through1A94C0 at3CD1B5. A hook only after this complete function returns occurs after the body-cache rebuild already ran.',
      'This is ordinary-return instruction ordering. It does not prove all threads, resource validity or which joint selectors appear in shipped records.', ['40B140'])
claim('3BFAB0','On the active branch calls3CCB90, then3C6AA0 using Actor+2056, then optional related native work, and finally rebuilds nonnull Actor+1600 through40B140. Actor+2488 is ORed with0x500 at the end. The two body buffers thus have distinct rebuild positions in this captured path.',
      'Called model helpers are not executed in this study. No guarantee is made that all other callsites share this ordering.', ['3CCB90','40B140'])
dump('claims.json',{'schema':1,'Domain':'native','claims':claims,'completeSemanticReview':False})
print(f'Wrote {len(claims)} bounded claims.')
