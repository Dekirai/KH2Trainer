"""Check IDA bodies/chunks and reviewed native anchors against the original PE.
--check is read-only. This does not run game code or establish runtime validity.
"""
import argparse, hashlib, importlib.util, json, math, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=0x140000000
FILES=['evidence.json','extended-evidence.json','support-evidence.json','effect-update-evidence.json','vector-scale-evidence.json','imported-evidence.json','effect-angle-evidence.json']
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def blob(x):return bytes(int(v,16) for v in x.split())
def check(x,why):
 if not x:raise AssertionError(why)
def derive():
 spec=importlib.util.spec_from_file_location('object_pe',HERE.parent/'bdx-trap-registry-20261008/verify.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);pe=mod.PE(mod.TARGET)
 def read(a,n):
  b,z=pe.read(a,n);check(not z,'expected stored PE data '+hex(a));return b
 cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
 extras=load(HERE/'additional-bytes.json');spans={}
 for s in extras['regions']+extras['constants']+load(HERE/'layout-rtti.json')['regions']+load(HERE/'effect-angle-evidence.json')['importThunks']:
  a=int(s['addr'],16);b=blob(s['data']);check(read(a,len(b))==b,'additional bytes '+hex(a));spans[a]=b
 imported=load(HERE/'imported-evidence.json')
 for p in imported['sourceFiles']:check(sha((ROOT/p['path']).read_bytes())==p['sha256'],'frozen source '+p['path'])
 functions=[];by_fn={};all_ins={};primary_bytes=0;instructions=0
 for origin in FILES:
  document=load(HERE/origin);check(document['originalSha256']==mod.SHA,'original identity')
  for f in document['functions']:
   start=int(f['addr'],16);raw=blob(f['originalBytes']);size=f['size'];d=f['disassembly'];dc=f.get('decompile');lines=d['asm']['lines']
   check(len(raw)==size and read(start,size)==raw,'primary bytes '+f['addr'])
   check(d['cursor'].get('done') and d['instruction_count']==d['total_instructions']==len(lines),'complete ASM '+f['addr'])
   check(sum(p['instruction_count'] for p in f.get('pages',[d]))==len(lines),'ASM page sum '+f['addr'])
   if dc:check(dc['cursor'].get('done') and not dc.get('truncated'),'complete decompilation '+f['addr'])
   else:check(origin=='effect-angle-evidence.json','only explicitly ASM-only support bodies may omit pseudocode')
   chunks=[];ins=[]
   for l in lines:
    a=int(l['addr'],16);i=next(cs.disasm(read(a,15),a,count=1),None);check(i is not None,'instruction '+hex(a));ins.append(i);all_ins[a]=i
    if chunks and chunks[-1][1]==a:chunks[-1][1]=a+i.size
    else:chunks.append([a,a+i.size])
   check(chunks[0]==[start,start+size],'primary body extent '+f['addr'])
   for a,z in chunks[1:]:check(spans.get(a)==read(a,z-a),'external chunk '+hex(a))
   by_fn[start]=ins;primary_bytes+=size;instructions+=len(ins)
   functions.append({'addr':f['addr'],'source':origin,'bytes':size,'instructions':len(ins),'pseudocodeCaptured':dc is not None,'chunks':[{'addr':hex(a),'size':z-a,'sha256':sha(read(a,z-a))} for a,z in chunks]})
 # Validate the original RTTI chain that names the enclosing object.
 vt=BASE+0x5B87A8;col=struct.unpack('<Q',read(vt-8,8))[0];cv=struct.unpack('<6I',read(col,24));td=BASE+cv[3]
 check(cv[0]==1 and cv[5]==col-BASE,'relative RTTI locator');name=pe.cstr(td-BASE+16)
 check(name=='.?AVEFFECT@ryj@@','original effect class name')
 check(vt-8 in spans and col in spans and td in spans,'RTTI independently captured by IDA')
 destructor=by_fn[BASE+0x2BCF90]
 check(any(i.mnemonic=='lea' and any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==vt for o in i.operands) for i in destructor),'destructor uses this vtable')
 lvt=BASE+0x5B1E20;lcol=struct.unpack('<Q',read(lvt-8,8))[0];lcv=struct.unpack('<6I',read(lcol,24));ltd=BASE+lcv[3]
 check(lcv[0]==1 and lcv[5]==lcol-BASE and pe.cstr(ltd-BASE+16)=='.?AVCacheBuffLayout@dk@@','original cached-layout RTTI')
 check(lvt-8 in spans and lcol in spans and ltd in spans,'layout RTTI captured by IDA')
 check(any(i.mnemonic=='lea' and any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==lvt for o in i.operands) for i in by_fn[BASE+0x167720]),'layout constructor uses original RTTI vtable')
 # Exact selected ABI, store, branch and shared-tail instructions, not names from pseudocode.
 anchors={
  0x41D44E:('movss','xmm3, dword ptr [r14 + 0x10]'),0x41D672:('movss','xmm6, dword ptr [rcx + 0x10]'),
  0x41D050:('movaps','xmm2, xmm6'),0x41D14E:('movaps','xmm2, xmm6'),
  0x3B7308:('comiss','xmm7, xmm6'),0x3B730B:('ja','0x1403b7318'),0x3B7314:('maxss','xmm6, xmm7'),
  0x2BE642:('jbe','0x1402be667'),0x2BE6B2:('jbe','0x1402be6d8'),
  0x2C2830:('mov','byte ptr [rcx + 0x91], 1'),0x2C2FC0:('lea','rax, [rcx + 0x10]'),0x2C2FF0:('lea','rax, [rcx + 0x20]'),
  0x41D891:('lea','rcx, [rsp + 0x60]'),0x3A16B2:('mov','word ptr [rcx + rax*2 + 8], dx'),
  0x3A1379:('mov','word ptr [r11 + rax*2 + 0x54], cx'),0x3A1758:('mov','byte ptr [rsi + 0x12], r14b'),
  0x3A17CF:('mov','word ptr [rax + 2], bx'),0x3A17D8:('mov','word ptr [rax], di'),0x41DF2B:('mov','word ptr [rax], cx'),
  0x4B12C4:('movss','xmm2, dword ptr [rbx + 0x10]'),0x4B12F4:('movss','xmm2, dword ptr [rbx + 0x20]'),
  0x4B1384:('movss','xmm0, dword ptr [rbx]'),0x4B0251:('call','rax')}
 checked=[]
 for rva,want in anchors.items():
  i=all_ins.get(BASE+rva);check(i is not None,'anchor must be at captured instruction start '+hex(rva));check((i.mnemonic,i.op_str)==want,'semantic anchor '+hex(rva));checked.append({'rva':hex(rva),'instruction':i.mnemonic+' '+i.op_str,'bytes':bytes(i.bytes).hex()})
 def calls(rva):return {o.imm-BASE for i in by_fn[BASE+rva] if i.mnemonic in ('call','jmp') for o in i.operands if o.type==X86_OP_IMM}
 edges={0x41CFE0:{0x3B7680},0x41D100:{0x3B75F0},0x41D3D0:{0x3B7200,0x1A8E60},0x41D650:{0x3B7560},0x41E380:{0x1AAE60,0x13F900},0x3B7680:{0x1AAD20},0x3B75F0:{0x1AAC80},0x1AAD20:{0x141270},0x1AAC80:{0x1411B0},0x1AAE60:{0x1411B0,0x141270,0x141320},0x41E270:{0x2BE630,0x2BE6A0},0x2BE8A0:{0x2C1FB0,0x2C1F50},0x2C1FB0:{0x4B01C0},0x2C1F50:{0x4AF410},0x41DF10:{0x3A1410},0x41DF40:{0x3A1410,0x3A1680},0x41DEF0:{0x3A1780},0x3E0CC0:{0x3A1410,0x3A14E0},0x41E7E0:{0x3A1330},0x41E720:{0x3A16C0},0x41DDF0:{0x167720},0x167720:{0x39CC40,0x1677D0}}
 for rva,targets in edges.items():check(targets<=calls(rva),'reviewed call edge '+hex(rva))
 angle_edges={0x4B1280:{0x478DE0,0x478DF0,0x478E00},0x478DE0:{0x1408F0},0x478DF0:{0x140AB0},0x478E00:{0x140C60}}
 for rva,targets in angle_edges.items():check(targets<=calls(rva),'effect rotation edge '+hex(rva))
 imports=pe.imports();trig=[]
 for off in [0,6]:
  a=BASE+0x471B98+off;i=next(cs.disasm(read(a,6),a,count=1));op=i.operands[0]
  check(i.mnemonic=='jmp' and op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP,'trigonometric import thunk')
  identity=imports[i.address+i.size+op.mem.disp];trig.append({'addr':hex(a),'dll':identity[0],'symbol':identity[1]})
 check({x['symbol'] for x in trig}=={'cosf','sinf'},'original trigonometric imports')
 # The translation write destination is in the adapter's local stack frame.
 local=calls(0x41D800);check(local=={0x142280,0x1AA7D0,0x4AD270,0x1A8E60},'local-transform direct call closure')
 check(struct.unpack('<4f',read(BASE+0x623CE0,16))==(0,0,1,0),'forward vector')
 check(struct.unpack('<4f',read(BASE+0x623CB0,16))==(1,0,0,0),'X basis')
 check(struct.unpack('<4f',read(BASE+0x623CC0,16))==(0,1,0,0),'Y basis')
 check(struct.unpack('<4f',read(BASE+0x623DF0,16))==(0,0,0,1),'identity translation')
 check(struct.unpack('<f',read(BASE+0x623B90,4))[0]==4.0,'ring fade duration')
 ann=load(HERE/'annotations.json');descriptor_checks=[]
 for r in imported['descriptors']:
  raw=read(BASE+r['descriptorRva'],16);fn,flags,_=struct.unpack('<QII',raw);e=ann[f"0:{r['index']}"]
  check(fn==BASE+r['handlerRva'] and flags==r['flags'],'original descriptor')
  check(e['handlerRva']==r['handlerRva'] and e['declaredOperandCount']==flags&65535 and e['hasReturnSlot']==bool(flags&0x40000000),'annotation identity')
  descriptor_checks.append({'index':r['index'],'handlerRva':hex(r['handlerRva']),'flags':hex(flags),'originalBytes':raw.hex()})
 check(len(ann)==len(descriptor_checks)==27,'annotation extent')
 # Independent boundary calculations illustrate the specified raw float path.
 def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
 tau=struct.unpack('<f',read(BASE+0x623BA4,4))[0]
 stalled=[x for x in [math.inf,-math.inf,float(2**28),float(-(2**28))] if f32(x+(-tau if x>0 else tau))==x]
 check(len(stalled)==4,'repeated float wrap can stall')
 # For an antiparallel pair, zero cross axis makes Rodrigues = cos(theta)*I.
 antiparallel=[{'radians':t,'resultLength':abs(math.cos(t))} for t in [0,math.pi/4,math.pi/2,math.pi]]
 check(antiparallel[1]['resultLength']<1 and antiparallel[2]['resultLength']<1e-10,'zero-axis degeneracy')
 return {'success':True,'scope':'Original PE and captured instruction boundaries; selected semantic anchors and illustrative arithmetic. No target instruction execution, runtime pointer validation or complete transitive closure claim.','originalSha256':mod.SHA,'functions':functions,'functionCount':len(functions),'uniqueFunctionCount':len(by_fn),'instructions':instructions,'primaryBytes':primary_bytes,'additionalSpans':len(spans),'rtti':{'vtable':hex(vt),'locator':hex(col),'typeDescriptor':hex(td),'name':name},'layoutRtti':{'vtable':hex(lvt),'locator':hex(lcol),'typeDescriptor':hex(ltd),'name':'.?AVCacheBuffLayout@dk@@'},'trigImports':trig,'semanticAnchors':checked,'callEdgeGroups':len(edges)+len(angle_edges),'descriptors':descriptor_checks,'illustrativeArithmetic':{'floatWrapStalls':['+infinity','-infinity','+2^28','-2^28'],'antiparallel':antiparallel}}
def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();result=derive();data=encoded(result)
 if a.check:
  check((HERE/'verification.json').read_bytes()==data,'verification differs')
  m=load(HERE/'manifest.json')
  for name,row in m['files'].items():
   b=(HERE/name).read_bytes();check(len(b)==row['bytes'] and sha(b)==row['sha256'],'manifest '+name)
 else:(HERE/'verification.json').write_bytes(data)
 print(json.dumps({k:result[k] for k in ['success','functionCount','uniqueFunctionCount','instructions','primaryBytes','additionalSpans','callEdgeGroups']}))
if __name__=='__main__':main()
