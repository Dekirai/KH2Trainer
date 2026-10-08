"""Reproduce bounded registry evidence from frozen IDA capture and original PE.

--check compares derived files and the manifest without writing.
No game process, target assembly execution, or IDA mutation is used.
"""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

HERE=Path(__file__).resolve().parent
TARGET=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def digest(b): return hashlib.sha256(b).hexdigest()
def encoded(x): return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def number(s): return int(s,16) if isinstance(s,str) else s
class PE:
    def __init__(self,path):
        self.raw=path.read_bytes();assert digest(self.raw)==SHA,'Wrong original PE'
        p=struct.unpack_from('<I',self.raw,0x3c)[0];assert self.raw[p:p+4]==b'PE\0\0'
        n=struct.unpack_from('<H',self.raw,p+6)[0];z=struct.unpack_from('<H',self.raw,p+20)[0]
        self.opt=p+24;assert struct.unpack_from('<H',self.raw,self.opt)[0]==0x20b
        self.base=struct.unpack_from('<Q',self.raw,self.opt+24)[0];self.sections=[]
        for i in range(n):
            s=self.opt+z+i*40
            name=self.raw[s:s+8].split(b'\0')[0].decode()
            vs,va,rs,rp=struct.unpack_from('<IIII',self.raw,s+8)
            flags=struct.unpack_from('<I',self.raw,s+36)[0]
            self.sections.append((name,va,vs,rs,rp,flags))
    def read(self,addr,size):
        rva=addr-self.base
        for name,va,vs,rs,rp,flags in self.sections:
            if va<=rva and rva+size<=va+max(vs,rs):
                delta=rva-va;stored=max(0,min(size,rs-delta))
                return self.raw[rp+delta:rp+delta+stored]+bytes(size-stored),size-stored
        raise AssertionError(('unmapped',hex(addr),size))
    def cstr(self,rva):
        result=bytearray()
        for i in range(1000):
            b=self.read(self.base+rva+i,1)[0][0]
            if not b:return result.decode('ascii')
            result.append(b)
        raise AssertionError('unterminated string')
    def imports(self):
        rva,size=struct.unpack_from('<II',self.raw,self.opt+112+8)
        result={};offset=0
        while True:
            d=struct.unpack('<5I',self.read(self.base+rva+offset,20)[0]);offset+=20
            if not any(d):break
            oft,_,_,name,iat=d;dll=self.cstr(name);index=0
            while True:
                value=struct.unpack('<Q',self.read(self.base+(oft or iat)+index*8,8)[0])[0]
                if not value:break
                symbol=('#'+str(value&0xffff)) if value>>63 else self.cstr(value+2)
                result[self.base+iat+index*8]=(dll,symbol);index+=1
        return result

def build():
    pe=PE(TARGET);e=json.loads((HERE/'capture.json').read_text())
    assert e['originalSha256']==SHA and number(e['imageBase'])==pe.base
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    ins_by_addr={};functions=[];total_ins=0;total_code=0;total_padding=0
    evidence=copy.deepcopy(e)
    for f in evidence['functions']:
        addr=number(f['addr']);size=f['size'];raw,zero=pe.read(addr,size);assert zero==0
        assert raw==bytes(int(x,16) for x in f['idaBytes'].split())
        assert f['cursor']['done'] and f['instruction_count']==f['total_instructions']==len(f['asm']['lines'])
        assert len(f['asm']['lines'])==sum(len(p['asm']['lines']) for p in f['pages'])
        assert all(p['instruction_count']==len(p['asm']['lines']) for p in f['pages'])
        assert f['pseudocode']['cursor']['done']
        assert sum(p['line_count'] for p in f['pseudocode']['pages'])==f['pseudocode']['pages'][0]['total_lines']
        cover=set();fn_ins=[]
        for row in f['asm']['lines']:
            a=number(row['addr']);offset=a-addr;assert 0<=offset<size
            i=next(cs.disasm(raw[offset:offset+15],a,count=1),None)
            assert i and not cover.intersection(range(offset,offset+i.size))
            cover.update(range(offset,offset+i.size));ins_by_addr[a]=i
            fn_ins.append({'addr':hex(a),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str,'idaInstruction':row['instruction']})
        missing=sorted(set(range(size))-cover)
        if addr==0x14041b400:
            assert missing==list(range(0x11a1,0x1288))
            assert raw[0x11a1:0x11a4]==b'\x0f\x1f\x00'
            tail={'paddingBytes':3,'switchTableBytes':228,'start':hex(addr+0x11a1),'scope':'3-byte NOP followed by five original switch tables; not executable instructions.'}
        else:
            assert all(raw[o] in (0x90,0xcc) for o in missing),(f['addr'],missing)
            tail={'paddingBytes':len(missing),'switchTableBytes':0}
        f['originalBytes']=raw.hex(' ');f['idaMatchesOriginal']=True;f['decodedInstructions']=fn_ins;f['nonInstructionTail']=tail
        total_ins+=len(fn_ins);total_code+=len(cover);total_padding+=len(missing)
        functions.append({'addr':f['addr'],'size':size,'instructions':len(fn_ins),'sha256':digest(raw),'unlistedBytes':len(missing)})
    data=[];unique={(number(d['addr']),d['size']):d for d in evidence['data']}
    for key,d in sorted(unique.items()):
        b,z=pe.read(*key);assert b==bytes(int(x,16) for x in d['idaBytes'].split())
        d['originalBytes']=b.hex(' ');d['idaMatchesOriginal']=True;d['originalFileBytes']=len(b)-z;d['loaderZeroFillBytes']=z;data.append(d)
    evidence['data']=data
    imports=pe.imports();verified_imports=[]
    for i in e['imports']['data']:
        dll,name=imports[number(i['addr'])]
        assert dll.lower().removesuffix('.dll')==i['declaringDll'].lower().removesuffix('.dll')
        if not name.startswith('#'):assert name==i['imported_name'],(i,name)
        verified_imports.append({**i,'originalDeclaringDll':dll,'originalImportedNameOrOrdinal':name,
            'idaNameProvenByPe':not name.startswith('#')})
    evidence['imports']={'data':verified_imports,'next_offset':None,'scope':'Original PE import identity inventory; no claim that every imported body was analyzed.'}
    assert len(verified_imports)==len(imports)
    xref_sites=set();data_xref_sites=set()
    for group in e['xrefs']+e['globalXrefs']+e['registrySlotXrefs']+e['bank9RecordXrefs']:
        assert group['next_offset'] is None and len(group.get('data',[]))==group['total']
        for x in group.get('data',[]):
            a=number(x['from']);target=number(x['to'])
            if x['type']=='data' and x.get('fn'):
                b,z=pe.read(a,15);assert not z;i=next(cs.disasm(b,a,count=1))
                targets=[op.imm for op in i.operands if op.type==X86_OP_IMM]
                targets.extend(i.address+i.size+op.mem.disp for op in i.operands if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP)
                assert target in targets,(hex(a),i.mnemonic,i.op_str,hex(target),targets)
                data_xref_sites.add((a,target))
            if x['type']!='code' or (a,target) in xref_sites:continue
            b,z=pe.read(a,15);assert not z;i=next(cs.disasm(b,a,count=1))
            assert i.mnemonic in ('call','jmp') and int(i.op_str,16)==target,(hex(a),i.mnemonic,i.op_str,hex(target))
            xref_sites.add((a,target))
    anchors={
        0x1403e1720:('movsxd','rax, ecx'),0x1403e172a:('mov','qword ptr [rcx + rax*8], rdx'),
        0x1403e1710:('mov','qword ptr [rip + 0x371d91], rcx'),
        0x14041c4af:('movzx','eax, di'),0x14041c4b2:('shr','rax, 6'),0x14041c4b6:('mov','rdi, qword ptr [rcx + rax*8]'),
        0x14041c4c2:('movzx','eax, word ptr [r9 + r10*2 + 0x12]'),0x14041c4c8:('shl','rax, 4'),0x14041c4cc:('add','rdi, rax'),
        0x14041c4cf:('movzx','edx, word ptr [rdi + 8]'),0x14041c4fa:('call','qword ptr [rdi]'),0x14041c4fc:('test','dword ptr [rdi + 8], 0x40000000'),
    }
    for a,v in anchors.items():
        i=ins_by_addr[a];assert (i.mnemonic,i.op_str)==v,(hex(a),i.mnemonic,i.op_str,v)
    expected_calls={0x14026acc9:0x1403e1720,0x14026acd2:0x1403e1620,
        0x14026aceb:0x1403e16b0,0x14026ad00:0x1403e1720,
        0x1401f9a86:0x1403e1710,0x1401f9a8f:0x1403e1620,
        0x1401f9aac:0x1403e16b0,0x1401f9abc:0x1403e1710,
        0x140243962:0x14019ffd0,0x1402439de:0x14026acc0,0x1402439f4:0x1402513d0,
        0x140243b0a:0x14019ffd0,0x140243b8b:0x14026acc0,0x140243ba1:0x1402513d0,
        0x1403e142b:0x14041b320,0x1403e1440:0x14041b400,0x1403e1658:0x1403e1410,
        0x140243bf0:0x1402513e0,0x140243d5f:0x14026ace0}
    for a,target in expected_calls.items():
        i=ins_by_addr[a];assert i.mnemonic in ('call','jmp') and int(i.op_str,16)==target
    for addr in (0x140753490,0x14073d080,0x14072f1a0):
        matches=[s for s in pe.sections if s[1]<=addr-pe.base<s[1]+s[2]]
        assert len(matches)==1 and matches[0][0]=='.data' and matches[0][5]&0x80000000
    original_banks=list(struct.unpack('<11Q',pe.read(0x140753490,88)[0]))
    assert original_banks==[0x140752e00,0x140755370,0x140756b60,0,0x140757250,0x140789be0,0x140787e80,0x1407883f0,0x140787530,0,0x140787070]
    assert struct.unpack('<Q',pe.read(0x1407534e8,8)[0])[0]==0x142b047d0
    bank9=[]
    for n in range(41):
        handler,flags,pad=struct.unpack('<QII',pe.read(0x14073d080+n*16,16)[0]);assert 0x140001000<=handler<0x140578000 and pad==0
        bank9.append({'index':n,'addr':hex(0x14073d080+n*16),'handler':hex(handler),'flags':hex(flags),'operandCount':flags&0xffff,'writesReturnOperand':bool(flags&0x40000000)})
    assert int(bank9[-1]['handler'],16)==0x1402885d0
    assert struct.unpack('<2Q',pe.read(0x14073d310,16)[0])==(0x60,0x2000000001300000)
    hole=pe.read(0x140752ea0,16)[0];assert hole==bytes(16)
    assert struct.unpack('<Q',pe.read(0x140752e90,8)[0])[0] and struct.unpack('<Q',pe.read(0x140752eb0,8)[0])[0]
    snapshot={'schemaVersion':1,'Domain':'native','originalSha256':SHA,'root':'0x140753490','structuralSlotCount':11,'countIsRuntimeGuard':False,'countEvidence':'Original data cluster before independent adjacent object7534E8 consumed by02B6B0. No array length or bank-limit check exists in the captured dispatcher/setters; IDA has no authoritative C array extent.','entries':[{'bank':n,'slot':hex(0x140753490+n*8),'originalTable':hex(v) if v else None,'installedVariant':('0x14072f1a0' if n==3 else '0x14073d080' if n==9 else None)} for n,v in enumerate(original_banks)],'bank9':{'table':'0x14073d080','structuralDescriptorCount':41,'endExclusive':'0x14073d310','countIsRuntimeGuard':False,'descriptorBytes':16,'records':bank9,'boundary':'Next bytes form the independent initialized data family containing73D340 and73D3E0. No terminal NULL descriptor is present.','allocation':'Static writable image .data; installed pointer changes, table storage is not allocated/freed by registration.'},'nullCounterexample':{'bank':0,'index':10,'addr':'0x140752ea0','bytes':hole.hex(),'neighborIndices':[9,11],'conclusion':'A NULL descriptor is an interior hole, not a universal terminating sentinel.'}}
    verification={'schemaVersion':1,'success':True,'originalSha256':SHA,'functions':len(functions),'listedInstructions':total_ins,'originalFunctionBytes':sum(f['size'] for f in functions),'instructionBytes':total_code,'nonInstructionBytes':total_padding,'dataSpans':len(data),'dataFileBytes':sum(d['originalFileBytes'] for d in data),'dataLoaderZeroFillBytes':sum(d['loaderZeroFillBytes'] for d in data),'verifiedImportIdentities':len(verified_imports),'verifiedDirectCodeXrefs':len(xref_sites),'verifiedDirectDataXrefs':len(data_xref_sites),'semanticInstructionAnchors':len(anchors),'orderedCallAnchors':len(expected_calls),'functionChecks':functions,'scope':'Byte equality and bounded instruction/data relationships. Does not establish runtime contents, context exclusion, all indirect writers, or native index safety.'}
    listing=[]
    for f in evidence['functions']:
        listing.append(f"\n{f['addr']} {f['name']} — {f['size']} bytes / {len(f['asm']['lines'])} listed instructions")
        listing.extend(f"{x['addr']}: {x['instruction']}" for x in f['asm']['lines'])
        listing.extend(['\nIDA pseudocode (assembly authoritative):',f['pseudocode']['code']])
    return {'evidence.json':encoded(evidence),'registry-snapshot.json':encoded(snapshot),'verification.json':encoded(verification),'listings.txt':('\n'.join(listing)+'\n').encode('utf-8')},verification

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    derived,result=build()
    for name,data in derived.items():
        if args.check:assert (HERE/name).read_bytes()==data,name+' changed'
        else:(HERE/name).write_bytes(data)
    report=json.loads((HERE/'report.json').read_text())
    known={f['addr'] for f in json.loads(derived['evidence.json'])['functions']}
    for claim in report['claims']:
        assert claim['addr'] in known
        for reference in claim['Evidence']:
            path,_,fragment=reference.partition('#')
            assert (HERE.parents[2]/path).is_file(),reference
            if fragment:
                assert fragment.startswith('functions[addr=') and fragment.endswith(']')
                assert fragment[len('functions[addr='):-1] in known,reference
    files=[]
    for p in sorted(HERE.iterdir()):
        if p.is_file() and p.name!='manifest.json':
            b=p.read_bytes();files.append({'file':p.name,'bytes':len(b),'sha256':digest(b)})
    manifest=encoded({'schemaVersion':1,'date':'2026-10-08','frozen':True,'staticOnly':True,'originalSha256':SHA,'files':files})
    if args.check:assert (HERE/'manifest.json').read_bytes()==manifest,'manifest changed'
    else:(HERE/'manifest.json').write_bytes(manifest)
    print(json.dumps({k:v for k,v in result.items() if k!='functionChecks'}))
if __name__=='__main__':main()
