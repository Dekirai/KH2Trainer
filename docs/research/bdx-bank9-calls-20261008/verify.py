"""Verify the bounded Bank 9 study against original on-disk bytes; never load/execute KH2.
PE parsing and instruction-alias comparison adapted from the frozen system-call verifier.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
DEFAULT=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(b):return hashlib.sha256(b).hexdigest()
def encoded(x):return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode()
def blob(s):return bytes(int(x,16) for x in s.split()) if '0x' in s else bytes.fromhex(s)
def need(v,m):
    if not v:raise AssertionError(m)
class PE:
    def __init__(self,path):
        self.raw=path.read_bytes();need(digest(self.raw)==SHA,'Original SHA')
        p=struct.unpack_from('<I',self.raw,0x3c)[0];need(self.raw[p:p+4]==b'PE\0\0','PE')
        n=struct.unpack_from('<H',self.raw,p+6)[0];sz=struct.unpack_from('<H',self.raw,p+20)[0];self.opt=p+24
        need(struct.unpack_from('<H',self.raw,self.opt)[0]==0x20b,'PE32+')
        self.base=struct.unpack_from('<Q',self.raw,self.opt+24)[0];self.sections=[]
        for k in range(n):
            vs,va,rs,rp=struct.unpack_from('<IIII',self.raw,self.opt+sz+k*40+8)
            self.sections.append((va,vs,rs,rp))
    def read(self,a,n):
        r=a-self.base
        for va,vs,rs,rp in self.sections:
            if va<=r and r+n<=va+rs:return self.raw[rp+r-va:rp+r-va+n]
        raise AssertionError(('not original stored bytes',hex(a),n))
    def cstr(self,a):
        b=bytearray()
        for k in range(1024):
            c=self.read(a+k,1)
            if c==b'\0':return b.decode('ascii')
            b.extend(c)
        raise AssertionError('unterminated string')
    def imports(self):
        rva,_=struct.unpack_from('<II',self.raw,self.opt+120);out=[];off=0
        while True:
            oft,_,_,name,iat=struct.unpack('<IIIII',self.read(self.base+rva+off,20));off+=20
            if not any((oft,name,iat)):break
            dll=self.cstr(self.base+name);k=0
            while True:
                thunk=struct.unpack('<Q',self.read(self.base+(oft or iat)+k*8,8))[0]
                if not thunk:break
                symbol='#'+str(thunk&0xffff) if thunk>>63 else self.cstr(self.base+thunk+2)
                out.append({'addr':hex(self.base+iat+k*8),'declaringDll':dll,'symbol':symbol});k+=1
        return out

def derive(pe,requests_only=False):
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    captures=['ida-capture.json','helper-capture.json','closure-capture.json','semantic-closure-capture.json','lifetime-capture.json','callback-capture.json','last-closure-capture.json','import-capture.json','task-boundary-capture.json','vm-retirement-capture.json']
    capture=load(HERE/'ida-capture.json');additional=load(HERE/'additional-bytes.json')
    regions=capture['spans']+additional['spans']+load(HERE/'import-capture.json')['spans']
    if (HERE/'external-chunks.json').exists():regions+=load(HERE/'external-chunks.json')['spans']
    extra={int(r['addr'],16):blob(r['data']) for r in regions}
    for a,b in extra.items():need(pe.read(a,len(b))==b,'captured data '+hex(a))
    sources={p:digest((HERE/p).read_bytes()) for p in captures+['additional-bytes.json']}
    models=[(p,f) for p in captures for f in load(HERE/p)['functions']]
    aliases={'retn':'ret','jz':'je','jnz':'jne','jnbe':'ja','jnb':'jae','jna':'jbe','jnae':'jb','jnl':'jge','jng':'jle','jnge':'jl','jnle':'jg','setz':'sete','setnz':'setne','sal':'shl','mov':'movabs','xchg':'nop'}
    for prefix in ('cmov','set'):
        aliases.update({prefix+a:prefix+b for a,b in [('z','e'),('nz','ne'),('nbe','a'),('nb','ae'),('na','be'),('nae','b'),('nl','ge'),('ng','le'),('nge','l'),('nle','g')]})
    functions=[];requests=[];all_ins={};seen=set();listing=[];primary_bytes=0;instruction_bytes=0
    for source,f in models:
        start=int(f['addr'],16);need(start not in seen,'duplicate function');seen.add(start)
        raw=blob(f['originalBytes']);need(len(raw)==f['size'] and pe.read(start,len(raw))==raw,'original body '+f['addr'])
        rows=f['disassembly'];pages=f['pages']
        need(pages[-1]['cursor'].get('done') and len(rows)==pages[-1]['total_instructions'],'complete pagination '+f['addr'])
        need([r for p in pages for r in p['asm']['lines']]==rows,'page concatenation '+f['addr'])
        for p in pages:need(len(p['asm']['lines'])==p['instruction_count'],'clipped page')
        decoded=[];spans=[]
        for r in rows:
            a=int(r['addr'],16);i=next(cs.disasm(pe.read(a,15),a,count=1),None);need(i is not None,'decode '+hex(a))
            words=r['instruction'].split();m=words[0].lower()
            if m in ('rep','repe','repne','lock'):m+=' '+words[1].lower()
            need(m==i.mnemonic or aliases.get(m)==i.mnemonic,'mnemonic '+hex(a)+' '+r['instruction']+' vs '+i.mnemonic)
            all_ins[a]=i
            if spans and spans[-1][1]==a:spans[-1][1]=a+i.size
            else:spans.append([a,a+i.size])
            decoded.append({'addr':hex(a),'size':i.size,'bytes':bytes(i.bytes).hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
        chunks=[]
        for a,z in spans:
            b=pe.read(a,z-a);inside=start<=a and z<=start+len(raw)
            if not inside and extra.get(a)!=b:requests.append({'addr':hex(a),'size':len(b)})
            chunks.append({'addr':hex(a),'size':len(b),'originalBytes':b.hex(' '),'idaProof':'primary' if inside else 'additional IDA chunk'})
            instruction_bytes+=len(b)
        # Preserve the original list/pages separately. Combined counts below come only from verified complete page coverage.
        asm={'addr':hex(start),'asm':{'start_ea':hex(start),'lines':rows},'instruction_count':len(rows),'total_instructions':len(rows),'cursor':{'done':True}}
        functions.append({'addr':hex(start),'size':len(raw),'originalBytes':raw.hex(' '),'source':source,'disassembly':asm,'pages':pages,'decodedInstructions':decoded,'instructionChunks':chunks,'pseudocode':f['decompile']})
        primary_bytes+=len(raw)
        listing.append('\nFUNCTION '+hex(start)+' / '+source+'\n')
        listing.extend(d['addr']+' '+d['bytes']+'  '+d['mnemonic']+' '+d['operands']+'\n' for d in decoded)
    if requests_only:return requests
    need(not requests,'Need additional IDA chunks '+str(requests))
    descriptors=[]
    for d in capture['descriptors']:
        a=pe.base+0x73d080+16*d['index'];b=pe.read(a,16);fn,flags,reserved=struct.unpack('<QII',b)
        need(int(d['addr'],16)==a and int(d['handler'],16)==fn and int(d['flags'],16)==flags and reserved==0,'descriptor identity')
        need(d['operandCount']==flags&0xffff and d['writesReturnOperand']==bool(flags&0x40000000),'descriptor contract')
        descriptors.append({**d,'declaredOperandCount':flags&0xffff,'hasReturnSlot':bool(flags&0x40000000),'originalBytes':b.hex(' ')})
    need([d['index'] for d in descriptors]==list(range(41)),'all 41 structural rows')
    imports=pe.imports();byiat={int(x['addr'],16):x for x in imports};referenced=[]
    for i in all_ins.values():
        for op in i.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                target=i.address+i.size+op.mem.disp
                if target in byiat:referenced.append({'site':hex(i.address),**byiat[target]})
    anchors=load(HERE/'semantic-anchors.json') if (HERE/'semantic-anchors.json').exists() else []
    meanings=load(HERE/'anchor-meanings.json') if (HERE/'anchor-meanings.json').exists() else {}
    need({a['addr']:a['meaning'] for a in anchors}==meanings,'anchor meaning coverage')
    for a in anchors:
        i=all_ins[int(a['addr'],16)];need(i.mnemonic==a['mnemonic'] and i.op_str==a['operands'],'semantic anchor '+a['meaning'])
    for rva,bits in [(0x623a4c,0x3f000000),(0x5b138c,0x43d00000),(0x5b1390,0x44000000),(0x623bb4,0x41200000),(0x5a9ca8,0x3f7d70a4)]:
        need(pe.read(pe.base+rva,4)==struct.pack('<I',bits),'numeric constant '+hex(rva))
    rtti=[]
    for vt,col,td,name in [(0x5b7970,0x675320,0x793580,'OBJ3D'),(0x5b7590,0x674f38,0x793768,'CAMERA'),(0x5b7d98,0x675868,0x7939f8,'VM_THREAD'),(0x5b72d8,0x674b30,0x793630,'SELECTBODY'),(0x5b7a78,0x675448,0x7938c8,'MOTION')]:
        need(struct.unpack('<Q',pe.read(pe.base+vt-8,8))[0]==pe.base+col,'COL')
        need(struct.unpack('<I',pe.read(pe.base+col+12,4))[0]==td,'type RVA')
        need(pe.cstr(pe.base+td+16)=='.?AV'+name+'@gm@@','RTTI type')
        rtti.append({'vtable':hex(pe.base+vt),'completeObjectLocator':hex(pe.base+col),'typeDescriptor':hex(pe.base+td),'name':'gm::'+name})
    verified_xrefs=[];xref_seen=set()
    for result in additional['xrefs']['result']:
        need(result.get('next_offset') is None and len(result['data'])==result['total'],'xref pagination')
        for x in result['data']:
            frm=int(x['from'],16);to=int(x['to'],16);key=(frm,to,x['type'])
            if key in xref_seen:continue
            xref_seen.add(key);raw=pe.read(frm,15);mode=None;i=next(cs.disasm(raw,frm,count=1),None)
            if i:
                for op in i.operands:
                    if op.type==X86_OP_IMM and op.imm==to:mode='instruction-immediate'
                    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP and frm+i.size+op.mem.disp==to:mode='instruction-rip-relative'
            if not mode and struct.unpack_from('<Q',raw)[0]==to:mode='pointer-qword'
            if not mode and struct.unpack_from('<I',raw)[0]+pe.base==to:mode='image-rva-dword'
            er,es=struct.unpack_from('<II',pe.raw,pe.opt+136)
            if not mode and pe.base+er<=frm<pe.base+er+es and (frm-pe.base-er)%12==0 and struct.unpack_from('<I',raw,4)[0]+pe.base==to:mode='exception-directory-end-rva'
            need(mode is not None,'xref '+str(key));verified_xrefs.append({'from':hex(frm),'to':hex(to),'kind':x['type'],'originalEncoding':mode})
    annotations=load(HERE/'annotations.json')['annotations'] if (HERE/'annotations.json').exists() else {}
    reuse=load(HERE/'reused-evidence.json');reused=[]
    for path,sha in reuse['files'].items():need(digest((ROOT/path).read_bytes())==sha,'reused evidence hash '+path)
    prior=load(ROOT/'docs/research/bdx-trap-registry-20261008/evidence.json')
    for f in prior['functions']:
        if f['addr'].lower() in reuse['functions']:
            b=blob(f['originalBytes']);need(pe.read(int(f['addr'],16),len(b))==b and len(b)==f['size'],'reused original body')
            reused.append(f['addr'].lower())
    need(set(reused)==set(reuse['functions']),'reused function selection')
    if annotations:
        need(set(annotations)=={'9:'+str(i) for i in range(41)},'all annotation keys')
        for key,a in annotations.items():
            d=descriptors[a['index']]
            need(a['bank']==9 and key=='9:'+str(a['index']),'annotation identity')
            need(a['declaredOperandCount']==d['declaredOperandCount'] and a['hasReturnSlot']==d['hasReturnSlot'],'annotation contract')
            need(all(isinstance(a[s],str) and a[s] for s in ['name','summary','notes','evidence']),'annotation text')
    evidence={'schema':1,'domain':'native','date':'2026-10-08','originalSha256':SHA,'imageBase':hex(pe.base),'sourceSha256':sources,'functions':functions,'descriptors':descriptors,'spans':[{'addr':hex(a),'size':len(b),'originalBytes':b.hex(' ')} for a,b in extra.items()],'rtti':rtti,'imports':referenced,'verifiedXrefs':verified_xrefs,'limits':'Complete captures for the selected bodies; bounded semantic closure, not a complete program/allocator/scheduler/resource proof. Descriptor range is structural, not a native guard.'}
    v={'success':True,'originalSha256':SHA,'functions':len(functions),'instructions':sum(len(f['decodedInstructions']) for f in functions),'primaryByteSpanTotal':primary_bytes,'listedInstructionByteTotal':instruction_bytes,'spans':len(extra),'descriptors':len(descriptors),'annotations':len(annotations),'semanticAnchors':len(anchors),'rttiTypes':len(rtti),'verifiedXrefs':len(verified_xrefs),'referencedImportSites':len(referenced),'separatelyRecheckedRegistryBodies':reused,'gameExecuted':False}
    return {'evidence.json':encoded(evidence),'listings.txt':''.join(listing).encode(),'verification.json':encoded(v)},v
def main():
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,default=DEFAULT);p.add_argument('--capture-requests',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args();pe=PE(a.original)
    if a.capture_requests:print(json.dumps(derive(pe,True)));return
    files,v=derive(pe)
    if a.check:
        for name,data in files.items():need((HERE/name).read_bytes()==data,'stale derived '+name)
        manifest=load(HERE/'manifest.json')['files']
        need(set(manifest)=={f.name for f in HERE.iterdir() if f.is_file() and f.name!='manifest.json'},'manifest coverage')
        for name,info in manifest.items():need((HERE/name).stat().st_size==info['bytes'] and digest((HERE/name).read_bytes())==info['sha256'],'manifest '+name)
    else:
        for name,data in files.items():(HERE/name).write_bytes(data)
    print(json.dumps(v))
if __name__=='__main__':main()
