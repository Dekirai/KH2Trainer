"""Verify bounded system-call evidence against the original PE; never executes it."""
import argparse, hashlib, json, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
DEFAULT=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(b): return hashlib.sha256(b).hexdigest()
def encoded(x): return (json.dumps(x,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
def blob(s): return bytes(int(x,16) for x in s.split()) if '0x' in s else bytes.fromhex(s)
def need(v,message):
    if not v: raise AssertionError(message)
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

def source_functions():
    c=load(HERE/'ida-capture.json');out=[];sources={}
    def add(path,selected=None):
        j=load(ROOT/path);sources[path]=digest((ROOT/path).read_bytes())
        for f in j['functions']:
            if selected is None or int(f['addr'],16) in selected:
                d=f.get('disassembly',f.get('asm'))
                lines=d if isinstance(d,list) else d.get('asm',d)['lines']
                pages=f['pages'];need(pages[-1]['cursor'].get('done'),'last page '+f['addr'])
                need(sum(p['instruction_count'] for p in pages)==len(lines),'pagination '+f['addr'])
                for p in pages:need(len(p['asm']['lines'])==p['instruction_count'],'clipped page '+f['addr'])
                need(len(lines)==pages[-1]['total_instructions'],'full listing '+f['addr'])
                out.append({'source':path,'capture':f,'lines':lines})
    add(str((HERE/'ida-capture.json').relative_to(ROOT)).replace('\\','/'))
    add('docs/research/bdx-trap-catalog-20261008/evidence.json',{int(d['addr'],16) for d in c['selectedDescriptors']})
    add('docs/research/bdx-inspection-20261008/evidence.json',{0x1403e1240,0x14041b320})
    add('docs/research/bdx-trap-registry-20261008/evidence.json',{0x1403e1410})
    add('docs/research/allocator-ownership-20261008/evidence.json',{0x140152680})
    return c,out,sources

def derive(pe,request_only=False):
    capture,models,sources=source_functions();cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    extras=load(HERE/'additional-bytes.json') if (HERE/'additional-bytes.json').exists() else {'regions':[]}
    extra={int(r['addr'],16):blob(r['data']) for r in extras['regions']}
    for a,b in extra.items():need(pe.read(a,len(b))==b,'extra IDA bytes '+hex(a))
    requests=[];functions=[];all_ins={};listing=[];fresh=0;count=0;primary_bytes=0;chunk_bytes=0
    for model in models:
        f=model['capture'];start=int(f['addr'],16);raw=blob(f['originalBytes']);size=f['size']
        need(len(raw)==size and pe.read(start,size)==raw,'primary original bytes '+f['addr'])
        spans=[];decoded=[]
        for row in model['lines']:
            a=int(row['addr'],16);i=next(cs.disasm(pe.read(a,15),a,count=1),None);need(i is not None,'decode '+hex(a))
            ida_mnemonic=row['instruction'].split()[0].lower()
            aliases={'retn':'ret','jz':'je','jnz':'jne','jnbe':'ja','jnb':'jae','jna':'jbe','jnae':'jb','jnl':'jge','jng':'jle','jnge':'jl','jnle':'jg','setz':'sete','setnz':'setne','sal':'shl','mov':'movabs','xchg':'nop'}
            aliases.update({'cmov'+a:'cmov'+b for a,b in [('z','e'),('nz','ne'),('nbe','a'),('nb','ae'),('na','be'),('nae','b'),('nl','ge'),('ng','le'),('nge','l'),('nle','g')]})
            aliases.update({'set'+a:'set'+b for a,b in [('z','e'),('nz','ne'),('nbe','a'),('nb','ae'),('na','be'),('nae','b'),('nl','ge'),('ng','le'),('nge','l'),('nle','g')]})
            need(ida_mnemonic==i.mnemonic or aliases.get(ida_mnemonic)==i.mnemonic,'IDA/Capstone mnemonic '+hex(a)+' '+row['instruction']+' / '+i.mnemonic)
            if spans and spans[-1][1]==a:spans[-1][1]=a+i.size
            else:spans.append([a,a+i.size])
            decoded.append({'addr':hex(a),'size':i.size,'bytes':bytes(i.bytes).hex(),'mnemonic':i.mnemonic,'operands':i.op_str})
            all_ins[a]=i
        chunks=[]
        for a,z in spans:
            b=pe.read(a,z-a)
            if start<=a and z<=start+size:need(raw[a-start:z-start]==b,'primary chunk');proof='primary'
            else:
                if extra.get(a)!=b:requests.append({'addr':hex(a),'size':z-a})
                proof='additional IDA chunk'
            chunks.append({'addr':hex(a),'size':z-a,'originalBytes':b.hex(' '),'idaProof':proof});chunk_bytes+=len(b)
        dc=f.get('decompile',f.get('pseudocode',f.get('pc')))
        functions.append({'addr':hex(start),'size':size,'source':model['source'],'originalBytes':raw.hex(' '),'asm':model['lines'],'decodedInstructions':decoded,'instructionChunks':chunks,'pseudocode':dc})
        count+=len(decoded);primary_bytes+=size;fresh+=model['source'].endswith('/ida-capture.json')
        listing.append('\nFUNCTION '+hex(start)+' | '+model['source']+' | primary bytes '+str(size)+'\n')
        listing.extend(d['addr']+' '+d['bytes']+'  '+d['mnemonic']+' '+d['operands']+'\n' for d in decoded)
    if request_only:return sorted({r['addr']:r for r in requests}.values(),key=lambda x:int(x['addr'],16))
    need(not requests,'Missing IDA external instruction chunks '+str(requests))
    spans=[]
    for r in capture['spans']+extras['regions']:
        a=int(r['addr'],16);b=blob(r['data']);need(pe.read(a,len(b))==b,'captured data '+r['addr']);spans.append({'addr':hex(a),'size':len(b),'originalBytes':b.hex(' ')})
    descriptors=[]
    for d in capture['selectedDescriptors']:
        a=pe.base+0x752e00+16*d['index'];b=pe.read(a,16);fn,flags,reserved=struct.unpack('<QII',b)
        need(fn==int(d['addr'],16) and flags==d['flags'] and reserved==d['reserved'],'descriptor '+str(d['index']))
        descriptors.append(dict(d,descriptorAddr=hex(a),originalBytes=b.hex(' '),declaredOperandCount=flags&0xffff,hasReturnSlot=bool(flags&0x40000000)))
    need(len(descriptors)==33,'selected descriptor count')
    constants={0x5b18f4:'0000803f',0x623b18:'00000040',0x623a80:'0000803f',0x5b4c98:'00028038'}
    for rva,b in constants.items():need(pe.read(pe.base+rva,4).hex()==b,'numeric constant')
    need(pe.cstr(pe.base+0x5abbe0)=='SslSePlay : bank=%d no=%d id=%d -> ','sound diagnostic')
    anchors=load(HERE/'semantic-anchors.json') if (HERE/'semantic-anchors.json').exists() else []
    for a in anchors:
        i=all_ins[int(a['addr'],16)];need(i.mnemonic==a['mnemonic'] and i.op_str==a['operands'],'semantic anchor '+a['meaning'])
    imports=pe.imports();byiat={int(x['addr'],16):x for x in imports};referenced=[]
    for i in all_ins.values():
        for op in i.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                target=i.address+i.size+op.mem.disp
                if target in byiat:referenced.append({'site':hex(i.address),**byiat[target]})
    annotations=load(HERE/'annotations.json') if (HERE/'annotations.json').exists() else {'annotations':{}}
    byindex={d['index']:d for d in descriptors}
    for key,a in annotations['annotations'].items():
        need(key=='0:'+str(a['index']) and a['bank']==0 and a['index'] in byindex,'annotation identity')
        need(a['declaredOperandCount']==byindex[a['index']]['declaredOperandCount'] and a['hasReturnSlot']==byindex[a['index']]['hasReturnSlot'],'annotation descriptor contract')
        need(all(isinstance(a[s],str) and a[s] for s in ['name','summary','notes','evidence']),'annotation text')
    verified_xrefs=[];seen=set()
    for query in capture['xrefQueries']:
        for result in query['result']:
            for x in result.get('data',[]):
                frm=int(x['from'],16);to=int(x['to'],16);key=(frm,to,x['type'])
                if key in seen:continue
                seen.add(key);raw=pe.read(frm,15);mode=None
                i=next(cs.disasm(raw,frm,count=1),None)
                if i:
                    for op in i.operands:
                        if op.type==X86_OP_IMM and op.imm==to:mode='instruction-immediate'
                        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP and frm+i.size+op.mem.disp==to:mode='instruction-rip-relative'
                if not mode and struct.unpack_from('<Q',raw)[0]==to:mode='pointer-qword'
                if not mode and struct.unpack_from('<I',raw)[0]+pe.base==to:mode='image-rva-dword'
                exception_rva,exception_size=struct.unpack_from('<II',pe.raw,pe.opt+136)
                if not mode and pe.base+exception_rva<=frm<pe.base+exception_rva+exception_size and (frm-pe.base-exception_rva)%12==0 and struct.unpack_from('<I',raw,4)[0]+pe.base==to:mode='exception-directory-end-rva'
                need(mode is not None,'xref original encoding '+str(key))
                verified_xrefs.append({'from':hex(frm),'to':hex(to),'kind':x['type'],'originalEncoding':mode})
    evidence={'schema':1,'date':'2026-10-08','originalSha256':SHA,'imageBase':hex(pe.base),'sourceSha256':sources,'functions':functions,'descriptors':descriptors,'spans':spans,'imports':referenced,'verifiedXrefs':verified_xrefs,'xrefCapture':capture['xrefQueries'],'limits':'Selected original-file functions and their explicit chunks only. Direct xrefs are supporting context, not exhaustive alias provenance. Unknown transitive callees remain open.'}
    external_chunks={c['addr'] for f in functions for c in f['instructionChunks'] if c['idaProof']=='additional IDA chunk'}
    verification={'success':True,'originalSha256':SHA,'freshFunctions':fresh,'reusedFunctions':len(functions)-fresh,'functions':len(functions),'instructions':count,'primaryByteSpanTotal':primary_bytes,'listedInstructionByteTotal':chunk_bytes,'externalInstructionChunks':len(external_chunks),'additionalCapturedSpans':len(extra),'descriptors':len(descriptors),'semanticAnchors':len(anchors),'annotations':len(annotations['annotations']),'verifiedXrefs':len(verified_xrefs),'referencedImportSites':len(referenced),'originalImportIdentities':len(imports),'gameExecuted':False}
    return {'evidence.json':encoded(evidence),'listings.txt':''.join(listing).encode(),'verification.json':encoded(verification)},verification

def main():
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,default=DEFAULT);p.add_argument('--capture-requests',action='store_true');p.add_argument('--check',action='store_true');args=p.parse_args();pe=PE(args.original)
    if args.capture_requests:print(json.dumps(derive(pe,True)));return
    files,result=derive(pe)
    if args.check:
        for name,data in files.items():need((HERE/name).read_bytes()==data,'stale derived '+name)
        manifest=load(HERE/'manifest.json')['files']
        need(set(manifest)=={f.name for f in HERE.iterdir() if f.is_file() and f.name!='manifest.json'},'manifest coverage')
        for name,info in manifest.items():need((HERE/name).stat().st_size==info['bytes'] and digest((HERE/name).read_bytes())==info['sha256'],'manifest '+name)
    else:
        for name,data in files.items():(HERE/name).write_bytes(data)
    print(json.dumps(result))
if __name__=='__main__':main()
