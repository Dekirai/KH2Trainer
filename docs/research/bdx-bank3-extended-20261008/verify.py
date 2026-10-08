"""Bounded extended Bank 3 original-PE/IDA evidence verifier. Never executes KH2.
The PE parser and mnemonic aliases follow the earlier Bank 9 study.
"""
import argparse, hashlib, json, re, struct
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
        self.base=struct.unpack_from('<Q',self.raw,self.opt+24)[0];need(self.base==0x140000000,'image base')
        self.sections=[]
        for k in range(n):
            vs,va,rs,rp=struct.unpack_from('<IIII',self.raw,self.opt+sz+k*40+8)
            self.sections.append((va,vs,rs,rp))
    def read(self,a,n):
        r=a-self.base
        need(n>=0,'read size')
        for va,vs,rs,rp in self.sections:
            if va<=r and r+n<=va+rs:
                b=self.raw[rp+r-va:rp+r-va+n];need(len(b)==n,'short raw section');return b
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

def derive(pe):
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    c=load(HERE/'capture.json');need(c['domain']=='native' and c['originalSha256']==SHA,'capture domain/hash')
    spans=[]
    for r in c['spans']+c['xrefBytes']:
        b=blob(r['data']);a=int(r['addr'],16)
        need(pe.read(a,len(b))==b,'IDA data bytes '+hex(a))
        spans.append({'addr':hex(a),'size':len(b),'originalBytes':b.hex(' ')})
    aliases={'retn':'ret','jz':'je','jnz':'jne','jnbe':'ja','jnb':'jae','jna':'jbe','jnae':'jb','jnl':'jge','jng':'jle','jnge':'jl','jnle':'jg','setz':'sete','setnz':'setne','sal':'shl','mov':'movabs','xchg':'nop'}
    for prefix in ('cmov','set'):
        aliases.update({prefix+a:prefix+b for a,b in [('z','e'),('nz','ne'),('nbe','a'),('nb','ae'),('na','be'),('nae','b'),('nl','ge'),('ng','le'),('nge','l'),('nle','g')]})
    functions=[];all_ins={};all_rows={};seen=set();asm_listing=[];pseudo_listing=[];primary=0;listed=0;decompile_failures=[]
    for source in ['capture.json']:
        for f in c['functions']:
            a=int(f['addr'],16);b=blob(f['originalBytes']);z=a+len(b)
            need(a not in seen,'duplicate function');seen.add(a)
            need(len(b)==f['size'] and pe.read(a,len(b))==b,'original body '+hex(a))
            rows=f['disassembly'];pages=f['pages'];offset=0
            need(pages and pages[-1]['cursor'].get('done') is True,'final ASM cursor')
            need([r for p in pages for r in p['asm']['lines']]==rows,'page concatenation')
            for p in pages:
                need(not p.get('error') and not p.get('cursor',{}).get('cancelled'),'ASM error/cancelled')
                need(p['instruction_count']==len(p['asm']['lines']) and p['total_instructions']==len(rows),'ASM count')
                offset+=len(p['asm']['lines'])
                if offset<len(rows):need(p['cursor'].get('next')==offset and not p['cursor'].get('done'),'ASM cursor chain')
            decoded=[];covered=set()
            for r in rows:
                ia=int(r['addr'],16);need(a<=ia<z,'out-of-body ASM')
                i=next(cs.disasm(pe.read(ia,min(15,z-ia)),ia,count=1),None)
                need(i is not None and ia+i.size<=z,'instruction boundary')
                need(not (set(range(ia,ia+i.size))&covered),'overlapping instructions')
                covered.update(range(ia,ia+i.size))
                w=r['instruction'].split();m=w[0].lower()
                if m in ('rep','repe','repne','lock'):m+=' '+w[1].lower()
                need(m==i.mnemonic or aliases.get(m)==i.mnemonic,'mnemonic '+hex(ia)+' '+m+' vs '+i.mnemonic)
                need(ia not in all_ins,'duplicate global instruction')
                all_ins[ia]=i;all_rows[ia]=r['instruction']
                decoded.append({'addr':hex(ia),'size':i.size,'bytes':bytes(i.bytes).hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
            dc=f['decompile']
            if any(d.get('error') for d in dc):
                need(False,'unexpected decompiler error')
                decompile_failures.append({'addr':hex(a),'error':next(d['error'] for d in dc if d.get('error'))})
            else:
                count=0
                for d in dc:
                    need(not d.get('cursor',{}).get('cancelled') and isinstance(d.get('code'),str),'pseudocode missing')
                    count+=d['line_count']
                    if not d['cursor'].get('done'):need(d['cursor'].get('next')==count,'pseudocode cursor chain')
                need(dc[-1]['cursor'].get('done') and count==dc[-1]['total_lines'],'pseudocode complete '+hex(a))
                if dc[-1].get('truncated'):
                    proof=next(x for x in c['pseudocodeCompletion'] if int(x['addr'],16)==a)
                    need(proof['cursor'].get('done') and not proof.get('truncated') and proof['line_count']==proof['total_lines']==count,'single-page corroboration')
                    need(proof['code']=='\n'.join(d['code'] for d in dc),'paged pseudocode equals complete corroboration')
            packed={'addr':hex(a),'asm':{'start_ea':hex(a),'lines':rows},'instruction_count':len(rows),'total_instructions':len(rows),'cursor':{'done':True}}
            functions.append({'addr':hex(a),'name':f['name'],'size':len(b),'originalBytes':b.hex(' '),'source':source,'disassembly':packed,'pages':pages,'decodedInstructions':decoded,'pseudocode':dc,'listedInstructionBytes':len(covered),'unlistedPrimaryBytes':len(b)-len(covered)})
            primary+=len(b);listed+=len(covered)
            asm_listing.append('\nFUNCTION '+hex(a)+' '+f['name']+' / '+source+'\n')
            asm_listing.extend(d['addr']+' '+d['bytes']+'  '+d['mnemonic']+' '+d['operands']+'\n' for d in decoded)
            pseudo_listing.append('\nFUNCTION '+hex(a)+' '+f['name']+'\n'+'\n'.join(d.get('code') or ('DECOMPILER ERROR: '+d.get('error','unknown')) for d in dc)+'\n')
    indices=[13,14,15,16,44,97,98,99,100,101,102,103,104,105,106,107,160]
    descriptors=[]
    for d in c['descriptors']:
        a=pe.base+0x72f1a0+16*d['index'];b=pe.read(a,16);fn,flags,reserved=struct.unpack('<QII',b)
        need(int(d['addr'],16)==a and int(d['handler'],16)==fn and int(d['flags'],16)==flags and reserved==0,'descriptor identity')
        need(d['operands']==flags&0xffff and d['returns']==bool(flags&0x40000000),'descriptor contract')
        need(fn in seen,'adapter captured')
        descriptors.append({**d,'declaredOperandCount':flags&0xffff,'hasReturnSlot':bool(flags&0x40000000),'originalBytes':b.hex(' ')})
    need([d['index'] for d in descriptors]==indices,'selected descriptor scope')
    anchors=load(HERE/'semantic-anchors.json')
    for x in anchors:
        ia=int(x['addr'],16);need(all_rows[ia]==x['instruction'],'semantic ASM anchor '+x['meaning'])
    rtti=[]
    for descriptor,vt,col,td,name in [(0x72a860,0x5b52b0,0x6718b8,0x792480,'.?AV?$VTABLE@VPLAYER@gb@@@OBJ@gb@@'),(None,0x5b5e70,0x672ad0,0x792aa0,'.?AVPLAYER_STATE@gb@@'),(0x729740,0x5b4e48,0x671040,0x7921e0,'.?AVSCROLL@gb@@')]:
        if descriptor:need(struct.unpack('<Q',pe.read(pe.base+descriptor,8))[0]==pe.base+vt,'descriptor vtable')
        need(struct.unpack('<Q',pe.read(pe.base+vt-8,8))[0]==pe.base+col,'COL')
        need(struct.unpack('<I',pe.read(pe.base+col+12,4))[0]==td,'type RVA')
        need(pe.cstr(pe.base+td+16)==name,'RTTI type')
        rtti.append({'descriptor':None if descriptor is None else hex(pe.base+descriptor),'vtable':hex(pe.base+vt),'completeObjectLocator':hex(pe.base+col),'typeDescriptor':hex(pe.base+td),'decoratedName':name})
    need(struct.unpack('<Q',pe.read(pe.base+0x5b52b0,8))[0]==pe.base+0x1fbf80,'PLAYER destructor slot')
    need(struct.unpack('<Q',pe.read(pe.base+0x5b52b8,8))[0]==pe.base+0x1fc060,'PLAYER update slot')
    need(struct.unpack('<Q',pe.read(pe.base+0x72bca8,8))[0]==pe.base+0x5b5648,'vibration resource pointer')
    need(pe.cstr(pe.base+0x5b5648)=='gumibattle/vibration.bar','native resource name')
    for r,v in [(0x623a28,0.3),(0x6239f8,0.1),(0x623a80,1.0),(0x623bb4,10.0),(0x5b15b4,0.017453292519943295),(0x623a4c,0.5),(0x5b4d30,2**-32),(0x623c48,-1.0),(0x623ab0,1.5707963267948966),(0x623b78,3.141592653589793),(0x5b2e48,-1.5707963267948966)]:
        need(pe.read(pe.base+r,4)==struct.pack('<f',v),'float constant '+hex(r))
    for r,v in [(0x623cb0,(1,0,0,0)),(0x623cc0,(0,1,0,0)),(0x623ce0,(0,0,1,0)),(0x623df0,(0,0,0,1))]:
        need(pe.read(pe.base+r,16)==struct.pack('<ffff',*v),'identity matrix row')
    imports=pe.imports();byiat={int(x['addr'],16):x for x in imports};referenced=[];boundaries=[]
    for i in all_ins.values():
        for op in i.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                target=i.address+i.size+op.mem.disp
                if target in byiat:referenced.append({'site':hex(i.address),**byiat[target]})
        if i.mnemonic in ('call','jmp'):
            op=i.operands[0]
            if op.type==X86_OP_IMM:
                if op.imm not in all_ins:boundaries.append({'site':hex(i.address),'kind':'direct-unexpanded','target':hex(op.imm)})
            else:boundaries.append({'site':hex(i.address),'kind':'indirect','operand':i.op_str})
    xr=[];xrbytes={int(x['addr'],16):blob(x['data']) for x in c['xrefBytes']};xrseen=set()
    for batch in c['xrefGroups']:
      for group in batch['result']:
        need(not group.get('more') and len(group['xrefs'])==group['xref_count'],'xref response incomplete')
        to=int(group['addr'],16)
        for x in group['xrefs']:
            frm=int(x['addr'],16)
            if (frm,to) in xrseen:continue
            xrseen.add((frm,to));raw=xrbytes[frm];mode=None
            i=next(cs.disasm(raw,frm,count=1),None)
            if i:
                for op in i.operands:
                    if op.type==X86_OP_IMM and op.imm==to:mode='instruction-immediate'
                    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP and frm+i.size+op.mem.disp==to:mode='instruction-rip-relative'
            if not mode and struct.unpack_from('<Q',raw)[0]==to:mode='pointer-qword'
            if not mode and struct.unpack_from('<I',raw)[0]+pe.base==to:mode='image-rva-dword'
            er,es=struct.unpack_from('<II',pe.raw,pe.opt+136)
            if not mode and pe.base+er<=frm<pe.base+er+es and (frm-pe.base-er)%12==0 and struct.unpack_from('<I',raw,4)[0]+pe.base==to:mode='exception-directory-end-rva'
            need(mode is not None,'unverified xref '+hex(frm)+' -> '+hex(to))
            xr.append({'from':hex(frm),'to':hex(to),'kind':x['type'],'originalEncoding':mode})
    annotations=load(HERE/'annotations.json')['annotations'];byindex={d['index']:d for d in descriptors}
    need(set(annotations)=={'3:'+str(i) for i in indices},'bounded annotation scope')
    for key,a in annotations.items():
        d=byindex[a['index']]
        need(key=='3:'+str(a['index']) and a['bank']==3,'annotation identity')
        need(int(a['handlerRva'],16)+pe.base==int(d['handler'],16),'annotation handler')
        need(a['declaredOperandCount']==d['declaredOperandCount'] and a['hasReturnSlot']==d['hasReturnSlot'],'annotation ABI')
        for field in ['name','summary','notes','evidence']:need(isinstance(a[field],str) and a[field],'annotation text')
        for match in re.findall(r'#functions\[addr=(0x[0-9a-fA-F]+)\]',a['evidence']):need(int(match,16) in seen,'annotation helper evidence')
        need(all(pe.base+int(rva,16) in seen for rva in a['helperRvas']),'annotation helper RVAs')
    claims=load(HERE/'claims.json')['claims'];need(load(HERE/'report.json')['claims']==claims,'report/claims agreement')
    for claim in claims:
        need(int(claim['addr'],16) in seen,'claim body');need(claim['evidence'],'claim reference')
        for ref in claim['evidence']:
            need(ref.startswith('docs/research/bdx-bank3-extended-20261008/'),'own evidence reference')
            if '#functions[addr=' in ref:
                addr=ref.split('#functions[addr=')[1].rstrip(']');need(int(addr,16) in seen,'claim reference target')
    from model import run
    model=run()
    evidence={'schema':1,'domain':'native','date':'2026-10-08','originalSha256':SHA,'imageBase':hex(pe.base),'sourceSha256':{'capture.json':digest((HERE/'capture.json').read_bytes())},'functions':functions,'descriptors':descriptors,'spans':spans,'rtti':rtti,'imports':referenced,'verifiedXrefs':xr,'unexpandedCallBoundaries':boundaries,'limits':'Fresh full selected bodies and 17 semantic annotations. No whole-bank completion, dynamic lifetime lease, native bank index bound, global scheduler/thread exclusion, or execution of KH2 is claimed.'}
    v={'success':True,'originalSha256':SHA,'functions':len(functions),'instructions':len(all_ins),'primaryByteSpanTotal':primary,'listedInstructionByteTotal':listed,'unlistedPrimaryBytes':primary-listed,'spans':len(spans),'descriptors':len(descriptors),'annotations':len(annotations),'claims':len(claims),'semanticAnchors':len(anchors),'rttiTypes':len(rtti),'verifiedXrefs':len(xr),'referencedImportSites':len(referenced),'pseudocodeSinglePageCorroborations':len(c['pseudocodeCompletion']),'models':model,'gameExecuted':False}
    return {'evidence.json':encoded(evidence),'native-listings.txt':''.join(asm_listing).encode(),'pseudocode.txt':''.join(pseudo_listing).encode(),'verification.json':encoded(v)},v

def main():
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,default=DEFAULT);p.add_argument('--check',action='store_true');a=p.parse_args()
    files,v=derive(PE(a.original))
    if a.check:
        for name,data in files.items():need((HERE/name).read_bytes()==data,'stale derived '+name)
        m=load(HERE/'manifest.json')['files']
        need(set(m)=={f.name for f in HERE.iterdir() if f.is_file() and f.name!='manifest.json'},'manifest coverage')
        for name,info in m.items():need((HERE/name).stat().st_size==info['bytes'] and digest((HERE/name).read_bytes())==info['sha256'],'manifest '+name)
    else:
        for name,data in files.items():(HERE/name).write_bytes(data)
    print(json.dumps(v))
if __name__=='__main__':main()
