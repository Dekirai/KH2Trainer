"""Build bounded catalog metadata from captured descriptors and reviewed native semantics."""
from pathlib import Path
import json, struct
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=0x140000000
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
ev=load(HERE/'evidence.json')
reg=load(HERE.parent/'bdx-trap-registry-20261008/registry-snapshot.json')
banks=[dict(bank=b['bank'],state=1 if b['originalTable'] else 2,tableRva=int(b['originalTable'] or b['installedVariant'],16)-BASE) for b in reg['entries']]
rows=[]
for d in ev['descriptors']:
    rows.append(dict(bank=0,index=d['index'],descriptorRva=0x752e00+16*d['index'],handlerRva=int(d['addr'],16)-BASE if int(d['addr'],16) else 0,flags=d['flags']))
for d in reg['bank9']['records']:
    rows.append(dict(bank=9,index=d['index'],descriptorRva=int(d['addr'],16)-BASE,handlerRva=int(d['handler'],16)-BASE if int(d['handler'],16) else 0,flags=int(d['flags'],16)))
# These selected descriptors are independently checked against the pinned original file by verify.py.
for bank,index,table,handler,flags in [(1,3,0x755370,0x42b230,0x40000000),(1,6,0x755370,0x42e220,12),(2,9,0x756b60,0x431a70,3),(2,95,0x756b60,0x431aa0,2)]:
    rows.append(dict(bank=bank,index=index,descriptorRva=table+16*index,handlerRva=handler,flags=flags))
ann={}
def a(bank,index,name,summary,notes='',evidence='bdx-trap-catalog-20261008/evidence.json + helpers.json'):
    ann[bank,index]=dict(name=name,summary=summary,notes=notes,evidence=evidence)
nan='The adapter replaces NaN components in the referenced input vector(s) with zero before calculating the result. This writes to the input memory.'
ptr='Arguments are encoded native pointers; valid allocation and lifetime are required.'
for i in (0,1,2,8,24,25,26,60):a(0,i,'No-op adapter','The captured native adapter returns immediately without reading its declared operands. The VM still consumes the declared operand count.')
a(0,3,'Read native tick factor','Returns the float at RVA 0x717480 as @FLT. No operands.')
a(0,4,'Add vectors','Adds all four components of operand 0 and operand 1. Returns @ADR to shared result storage at RVA 0x2AEA798.',nan+' A later invocation overwrites the result. '+ptr)
a(0,5,'Subtract vectors','Subtracts operand 1 from operand 0, across all four components. Returns @ADR to shared result storage at RVA 0x2AEA7B0.',nan+' A later invocation overwrites the result. '+ptr)
a(0,6,'Vector length','Returns sqrt(x*x + y*y + z*z) as @FLT; w is ignored.',ptr+' This adapter does not sanitize NaN values.')
a(0,7,'Normalize vector and retain length','Normalizes the input xyz components when the computed length is nonzero. Stores the original length in w and returns that length as @FLT.',ptr+' This changes the input vector and does not sanitize NaN values. A zero-length vector keeps xyz unchanged and writes zero to w.')
a(0,16,'Random integer','Updates the shared DWORD seed at RVA 0x7535C0 by multiplying it by 69069 modulo 2^32. For unsigned n > 0, returns seed / ceil(2^32 / n) as @INT.', 'n = 0 reaches an integer divide fault after updating the seed and the return tag. This describes the native path, not a recommended call.')
a(0,17,'Random float scaled','Updates the same shared seed, converts the unsigned 32-bit result to float, multiplies by 2^-32 and by operand 0, and returns @FLT.','Float rounding can produce a fraction of 1.0. The decompiler shows a misleading signed cast; the instructions zero-extend through EDX before CVTSI2SS from RDX.')
a(0,18,'Random float between','Updates the shared seed and calculates a + (b - a) * (float(seed) * 2^-32) using scalar float instructions. Returns @FLT.','The seed conversion is unsigned. Float rounding can reach an endpoint; no strictly open upper interval is promised.')
a(0,21,'Horizontal angle difference','Returns the wrapped difference atan2(b.x, b.z) - atan2(a.x, a.z) as @FLT.',ptr+' This adapter does not include the vector NaN sanitization loop.')
a(0,22,'Integer absolute value','Calculates a 32-bit absolute value using CDQ, XOR and SUB, then returns @INT.','INT_MIN wraps to the same bit pattern 0x80000000.')
a(0,23,'Float absolute value','Converts float to double, clears the double sign bit and converts back to float, returning @FLT.','NaN payloads and signaling behavior follow those floating-point conversions; this is not a raw float-bit sign mask.')
a(0,27,'Write native timing scalar','Copies operand 0 as float to RVA 0x717424 through the shared tail at RVA 0x1545B0.','The adapter performs no value-range validation. This does not establish all consumers of that global.')
a(0,35,'Scale vector in place','Multiplies all four components of operand 0 by float operand 1 in place. No VM return slot.',ptr+' No NaN sanitization loop.')
a(0,36,'Scale vector','Multiplies all four components of operand 0 by float operand 1. Returns @ADR to shared result storage at RVA 0x2AEA7C8.',nan+' A later invocation overwrites the result. '+ptr)
a(0,37,'Divide vector','Multiplies all four components by the float reciprocal of operand 1. Returns @ADR to shared result storage at RVA 0x2AEA7E0.',ptr+' No zero-divisor check or NaN sanitization loop. A later invocation overwrites the result.')
a(0,42,'Horizontal vector angle','Returns atan2(x, z) as @FLT.',nan+' '+ptr)
a(0,43,'Wrap angle','For a finite float, calls the angle wrapper at RVA 0x3B6F20. For a non-finite float, returns zero. Result tag @FLT.','The helper uses separate positive and nonpositive branches with fmodf and float approximations of pi and 2*pi.')
a(0,45,'Advance along direction','Normalizes a copy of operand 1, scales it by float operand 2 and the global tick factor at RVA 0x717480, then adds all four resulting components to operand 0.',nan+' '+ptr+' The copied w component also participates in scale and add.')
a(0,57,'Set global bit','Sets bit (index & 31) in the DWORD array at RVA 0x9ABCB0, indexed by unsigned index >> 5.','No bounds check is present in the adapter or its shared tail.')
a(0,58,'Clear global bit','Clears bit (index & 31) in the DWORD array at RVA 0x9ABCB0, indexed by unsigned index >> 5.','No bounds check is present in the adapter or its shared tail.')
a(0,59,'Read global bit','Reads bit (index & 31) from the DWORD array at RVA 0x9ABCB0, indexed by unsigned index >> 5. Returns @INT.','No bounds check is present in the captured helper.')
a(0,78,'Interpolate vectors','Returns a*(1-t) + b*t across all four components, with a=operand 0, b=operand 1 and t=float operand 2. Returns @ADR to RVA 0x7535C8.',nan+' The result buffer is shared with other vector calls, including 0:82, 0:83 and 0:102. '+ptr)
a(0,82,'Vector cross product','Returns the xyz cross product of operand 0 and operand 1 with w=0, as @ADR to shared storage at RVA 0x7535C8.',nan+' This storage is reused by other vector calls. '+ptr)
a(0,84,'Angle from vector dot product','Calculates the xyz dot product without normalizing the vectors, then returns 0 for dot >= 1, pi for dot <= -1, otherwise acos(dot), as @FLT.',nan+' With masked floating-point exceptions, an unordered/NaN dot product reaches acosf; unmasked COMISS can fault before that. '+ptr)
a(0,86,'Write object field +8','Writes the low 32 bits of operand 1 to decoded operand 0 plus 8. No VM return slot.',ptr+' No object-type or null guard is present in this adapter.')
for index,offset in [(92,9),(93,10),(94,11),(96,8)]:a(0,index,'Add object byte +'+str(offset),f'Adds the low byte of operand 1 to decoded operand 0 plus {offset}, with byte wraparound. No VM return slot.',ptr+' The semantic object type is not established.')
a(0,95,'Write object byte +14','Writes the low byte of operand 1 to decoded operand 0 plus 14. No VM return slot.',ptr+' The semantic object type is not established.')
a(0,91,'Dot product of normalized vectors','Sanitizes input vectors, normalizes local copies of xyz and returns their xyz dot product as @FLT.',nan+' Normalization acts on copies after sanitization. '+ptr)
a(0,102,'Direction to angles','Produces (atan2(-y, sqrt(x*x+z*z)), atan2(x,z), 0, 1). Returns @ADR to shared storage at RVA 0x7535C8.',nan+' Other vector calls overwrite the same storage. '+ptr)
a(1,3,'Current Actor pointer','Returns the current Actor pointer through RVA 0x3B3E80, encoded as @ADR.','No operand. A returned address does not establish a stable Actor lifetime.','actor-scale-contract-20261007/evidence.json#functions[addr=0x14042b230]')
a(1,6,'Register movement entry','The descriptor declares 12 operands, but adapter RVA 0x42E220 also reads low DWORDs from scratch slots 12, 13, 14 and 15. Callee RVA 0x3CA0E0 uses the values from slots 12 through 14.','These reads remain within the native 16-slot scratch buffer. The dispatcher only initializes the 12 declared slots for this call; the additional values are uninitialized scratch contents or values left by an earlier native call. This is not proof of a live crash.','bdx-rebind-operands-20261008/ida-capture.json')
for index,handler,target,count in [(9,0x431a70,0x411350,3),(95,0x431aa0,0x4112b0,2)]:
    a(2,index,'Actor STATUS rebind',f'Adapter RVA 0x{handler:X} calls RVA 0x{target:X}. Operand 0 encodes a wrapper whose +4 field encodes an Actor; operand 1 supplies the parameter ID. No return-value slot.',('The third declared operand is unused by this adapter. ' if count==3 else '')+'The selected retail event-0 paths initialize this wrapper, conditional on successful native setup. General runtime argument validity and object lifetime remain unproved.','actor-rebind-context-20261008 + bdx-rebind-operands-20261008')
for r in rows:
    r.update(ann.get((r['bank'],r['index']),dict(name='',summary='',notes='',evidence='bdx-trap-registry-20261008/registry-snapshot.json' if r['bank']==9 else 'bdx-trap-catalog-20261008/evidence.json')))
rows.sort(key=lambda r:(r['bank'],r['index']))
out=dict(schema=1,originalSha256=ev['originalSha256'],banks=banks,descriptors=rows)
write(HERE/'catalog-data.json',out)
write(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json',out)
print({'descriptors':len(rows),'annotated':len(ann),'nullHandlers':sum(r['handlerRva']==0 for r in rows)})
