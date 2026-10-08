"""Independent original-PE, complete-chunk and bounded catalog-semantics checks.
No target instruction, game script, process or UI is executed. --check is read-only.
"""
import argparse, hashlib, importlib.util, json, math, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
BASE=0x140000000
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def blob(s):return bytes(int(x,16) for x in s.split())
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def check(v,message):
    if not v:raise AssertionError(message)
def module(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def derive():
    pe_module=module(ROOT/'docs/research/bdx-trap-registry-20261008/verify.py','catalog_original_pe')
    pe=pe_module.PE(ORIGINAL)
    def read(a,n):
        b,zero=pe.read(a,n);check(zero==0,'expected stored original bytes '+hex(a));return b
    e=load(HERE/'evidence.json');h=load(HERE/'helpers.json');catalog=load(HERE/'catalog-data.json')
    capture=load(HERE/'chunk-bytes.json')['additionalIdaCapture']
    check(capture['health']['status']=='ok' and capture['health']['auto_analysis_ready'],'IDA capture health')
    extra={int(s['addr'],16):blob(s['data']) for s in capture['regions']+capture['constants']}
    for a,b in extra.items():check(read(a,len(b))==b,'additional IDA vs original '+hex(a))
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    all_ins={};by_function={};function_checks=[];instruction_count=0;primary_bytes=0
    for origin,document in [('evidence.json',e),('helpers.json',h)]:
        for f in document['functions']:
            start=int(f['addr'],16);raw=blob(f['originalBytes']);size=f['size']
            check(len(raw)==size and read(start,size)==raw,'primary bytes '+f['addr'])
            d=f['disassembly'];lines=d['asm']['lines'];pages=f.get('pages',[d])
            check(d['cursor'].get('done') and len(lines)==d['instruction_count']==d['total_instructions'],'ASM completeness '+f['addr'])
            check(sum(p['instruction_count'] for p in pages)==len(lines) and pages[-1]['cursor'].get('done'),'ASM pagination '+f['addr'])
            dc=f['decompile'];check(dc['cursor'].get('done') and not dc.get('truncated'),'decompile pagination '+f['addr'])
            ins=[];regions=[]
            for line in lines:
                a=int(line['addr'],16);i=next(cs.disasm(read(a,15),a,count=1),None);check(i is not None,'decode '+hex(a))
                ins.append(i);all_ins[a]=i
                if regions and regions[-1][1]==a:regions[-1][1]=a+i.size
                else:regions.append([a,a+i.size])
            check(regions[0]==[start,start+size],'primary extent '+f['addr'])
            chunks=[]
            for a,z in regions:
                b=read(a,z-a)
                if a==start:check(b==raw,'primary chunk identity');proof=origin+'#'+f['addr']+'.originalBytes'
                else:check(extra.get(a)==b,'uncaptured external chunk '+hex(a));proof='additionalIdaCapture.regions#'+hex(a)
                chunks.append(dict(addr=hex(a),size=z-a,originalBytes=b.hex(' '),idaProof=proof))
            function_checks.append(dict(addr=f['addr'],source=origin,primarySize=size,instructions=len(ins),chunks=chunks))
            by_function[start]=ins;instruction_count+=len(ins);primary_bytes+=size
    # This jump is an external tail target, not a chunk in IDA's adapter listing.
    tail=extra[BASE+0x1545b0];tail_ins=list(cs.disasm(tail,BASE+0x1545b0))
    check(sum(i.size for i in tail_ins)==len(tail),'complete timing tail')
    all_ins.update({i.address:i for i in tail_ins})
    spans=[]
    for s in h['spans']:
        a=int(s['addr'],16);b=blob(s['data']);check(read(a,len(b))==b,'helper span '+hex(a))
        spans.append(dict(addr=hex(a),size=len(b),originalBytes=b.hex(' ')))
    for s in capture['constants']:
        a=int(s['addr'],16);b=blob(s['data']);spans.append(dict(addr=hex(a),size=len(b),originalBytes=b.hex(' ')))
    expected_constants={0x5b4d30:'0000802f',0x623a80:'0000803f',0x623b78:'db0f4940',0x623ba4:'db0fc940',0x623c48:'000080bf'}
    for rva,b in expected_constants.items():check(read(BASE+rva,4).hex()==b,'numeric constant '+hex(rva))
    for s in e['bank0']['result']:
        a=int(s['addr'],16);b=blob(s['data']);check(read(a,len(b))==b,'bank0 table capture')
    descriptor_checks=[]
    for r in catalog['descriptors']:
        a=BASE+r['descriptorRva'];b=read(a,16);fn,flags,_=struct.unpack('<QII',b)
        check(fn==(BASE+r['handlerRva'] if r['handlerRva'] else 0) and flags==r['flags'],'descriptor '+str((r['bank'],r['index'])))
        descriptor_checks.append(dict(bank=r['bank'],index=r['index'],addr=hex(a),originalBytes=b.hex(' ')))
    check(len(descriptor_checks)==150,'bounded catalog row count')
    rows={(r['bank'],r['index']):r for r in catalog['descriptors']}
    check({i for (b,i),r in rows.items() if b==0 and r['handlerRva']==0}=={10,33,34,71,72},'bank0 holes')
    check(len(e['functions'])==100 and len(h['functions'])==17,'capture body counts')
    check({BASE+r['handlerRva'] for (b,i),r in rows.items() if b==0 and r['handlerRva']}=={int(f['addr'],16) for f in e['functions']},'all bank0 descriptor bodies')
    registry_path=ROOT/'docs/research/bdx-trap-registry-20261008/registry-snapshot.json'
    registry=load(registry_path)
    for b in catalog['banks']:
        r=next(r for r in registry['entries'] if r['bank']==b['bank'])
        actual=struct.unpack('<Q',read(int(r['slot'],16),8))[0]
        check(actual==(int(r['originalTable'],16) if r['originalTable'] else 0),'original bank pointer')
        check(b['state']==(1 if actual else 2) and b['tableRva']==int(r['originalTable'] or r['installedVariant'],16)-BASE,'catalog bank state')
    # Exact assertions, selected independently from original-byte disassembly.
    expected={
      0x41dbfa:('movabs','rdx, 0x100000000'),0x41dc04:('mov','r8d, dword ptr [rcx]'),
      0x41dc10:('lea','eax, [r8 - 1]'),0x41dc14:('add','rax, rdx'),0x41dc20:('div','r8'),0x41dc2b:('div','r8'),
      0x41dc53:('mov','edx, eax'),0x41dc55:('cvtsi2ss','xmm0, rdx'),0x41dc62:('mulss','xmm0, dword ptr [rcx]'),
      0x41dc93:('movss','xmm2, dword ptr [rcx + 8]'),0x41dc98:('subss','xmm2, dword ptr [rcx]'),
      0x41dc9c:('mov','edx, eax'),0x41dc9e:('cvtsi2ss','xmm0, rdx'),0x41dcab:('mulss','xmm2, xmm0'),0x41dcaf:('addss','xmm2, dword ptr [rcx]'),
      0x41ca72:('cdq',''),0x41ca73:('xor','eax, edx'),0x41ca75:('sub','eax, edx'),
      0x41cfbf:('movss','dword ptr [rbx + 0xc], xmm0'),0x41cfc9:('movss','dword ptr [rdi], xmm0'),
      0x1420d2:('ucomiss','xmm2, xmm1'),0x1420d5:('jp','0x1401420d9'),0x1420d7:('je','0x140142104'),
      0x1420e1:('divss','xmm0, xmm2'),0x1420f2:('movaps','xmm0, xmm2'),
      0x1420f5:('movss','dword ptr [rbx], xmm6'),0x1420f9:('movss','dword ptr [rbx + 4], xmm7'),0x1420fe:('movss','dword ptr [rbx + 8], xmm8'),
      0x41d1d4:('movss','xmm1, dword ptr [rax + 8]'),0x41d1d9:('movss','xmm0, dword ptr [rax]'),
      0x41d1e2:('movss','xmm1, dword ptr [rbx + 8]'),0x41d1ea:('movss','xmm0, dword ptr [rbx]'),0x41d1f3:('subss','xmm6, xmm0'),
      0x13fcc9:('shufps','xmm2, xmm2, 0'),0x13fccd:('mulps','xmm2, xmm0'),0x13fcd0:('movups','xmmword ptr [rcx], xmm2'),
      0x41d4b2:('movss','xmm6, dword ptr [rcx + 0x10]'),0x41d4b7:('mov','ecx, dword ptr [rcx + 8]'),
      0x41d51e:('movaps','xmm3, xmm6'),0x41d528:('mov','r8, rdi'),0x41d52b:('mov','rdx, rsi'),
      0x140255:('subss','xmm4, xmm6'),0x14025d:('mulss','xmm0, xmm6'),0x14026c:('mulss','xmm7, xmm4'),0x1402e7:('movups','xmmword ptr [rcx], xmm7'),
      0x142137:('mov','dword ptr [rcx + 0xc], 0'),0x41d5ee:('mov','r8, rsi'),0x41d5f6:('mov','rdx, rdi'),
      0x3b7523:('jb','0x1403b752d'),0x3b7535:('comiss','xmm0, xmm1'),0x3b7538:('jb','0x1403b7547'),0x3b7547:('movaps','xmm0, xmm1'),
      0x3b7762:('mov','dword ptr [rsp + 0x24], esi'),0x3b776b:('movss','xmm2, dword ptr [rbx + 4]'),
      0x3b779c:('mov','dword ptr [rdi + 8], esi'),0x3b77a9:('mov','dword ptr [rdi + 0xc], 0x3f800000'),
      0x41e5d0:('mov','dword ptr [rax + 8], ebx'),0x41e754:('add','byte ptr [rax + 9], cl'),
      0x41e774:('add','byte ptr [rax + 0xa], cl'),0x41e794:('add','byte ptr [rax + 0xb], cl'),
      0x41e7b0:('mov','byte ptr [rax + 0xe], bl'),0x41e7d4:('add','byte ptr [rax + 8], cl'),
      0x433a04:('shr','rax, 5'),0x433a0f:('and','edx, 0x1f'),0x433a15:('bt','eax, edx'),
      0x433a29:('shr','rax, 5'),0x433a2d:('and','ecx, 0x1f'),0x433a3d:('and','dword ptr [rdx], eax'),
      0x433a49:('shr','rax, 5'),0x433a4d:('and','ecx, 0x1f'),0x433a5b:('or','dword ptr [rdx], eax')}
    semantic=[]
    for rva,wanted in expected.items():
        i=all_ins[BASE+rva];check((i.mnemonic,i.op_str)==wanted,'anchor '+hex(rva)+' actual '+i.mnemonic+' '+i.op_str)
        semantic.append(dict(addr=hex(i.address),mnemonic=i.mnemonic,operands=i.op_str,originalBytes=bytes(i.bytes).hex(' ')))
    call_edges={0x41cfba:0x142080,0x41d1fa:0x3b6f20,0x41d35b:0x142080,0x41d37d:0x13fcc0,
                0x41d392:0x13fcc0,0x41d3a7:0x13fce0,0x41d52e:0x140230,0x41d5f9:0x142120,
                0x41d7c4:0x3b7510,0x41d9d6:0x3b7710,0x3b7758:0x1a8e60,0x3b7766:0x140f50,
                0x41dd04:0x1545b0}
    for a,t in call_edges.items():
        i=all_ins[BASE+a];check(i.mnemonic in ('call','jmp') and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==BASE+t,'call anchor '+hex(a))
    for index in (0,1,2,8,24,25,26,60):
        ins=by_function[BASE+rows[0,index]['handlerRva']];check(len(ins)==1 and ins[0].mnemonic=='ret','no-op '+str(index))
    # Original import identities for direct calls and local jmp-to-IAT thunks.
    imports=pe.imports();import_calls=[]
    for i in all_ins.values():
        if i.mnemonic not in ('call','jmp') or len(i.operands)!=1:continue
        op=i.operands[0];thunk=None;target=None
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:target=i.address+i.size+op.mem.disp
        elif op.type==X86_OP_IMM:
            t=op.imm
            try:q=next(cs.disasm(read(t,6),t,count=1),None)
            except AssertionError:continue
            if q and q.mnemonic=='jmp' and q.operands[0].type==X86_OP_MEM and q.operands[0].mem.base==X86_REG_RIP:
                target=q.address+q.size+q.operands[0].mem.disp;thunk=dict(addr=hex(t),originalBytes=bytes(q.bytes).hex(' '))
        if target in imports:
            dll,symbol=imports[target];import_calls.append(dict(site=hex(i.address),iat=hex(target),dll=dll,symbol=symbol,thunk=thunk))
    check(any(x['site']=='0x14041d1dd' and x['symbol']=='atan2f' for x in import_calls),'atan2f identity')
    check(any(x['site']=='0x1403b754e' and x['symbol']=='acosf' for x in import_calls),'acosf identity')
    # Arithmetic examples are Python models of reviewed instructions, not machine-code tests.
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    factor=struct.unpack('<f',read(BASE+0x5b4d30,4))[0];check(factor==2**-32,'float random scale')
    check(f32(f32(0xffffffff)*factor)==1.0,'rounded upper RNG endpoint')
    check(((0x80000000^0xffffffff)-0xffffffff)&0xffffffff==0x80000000,'INT_MIN abs wrapping')
    for n in [1,2,3,17,0x7fffffff,0x80000000,0xffffffff]:
        denominator=((1<<32)+n-1)//n
        check(denominator==math.ceil((1<<32)/n),'integer RNG denominator')
        check(0xffffffff//denominator<n,'integer RNG bounded result')
    # x86 unordered COMISS sets CF=1: both JB branches take the acos path.
    angle_paths=[]
    for dot in [-2.,-1.,0.,1.,2.,float('nan')]:
        unordered=math.isnan(dot)
        result='zero' if not(unordered or dot<1) else ('acosf' if unordered or -1<dot else 'pi')
        angle_paths.append(dict(input='NaN' if unordered else dot,result=result))
    check(angle_paths[-1]['result']=='acosf','unordered angle path')
    check('reaches acosf' in rows[0,84]['notes'] and 'also selects pi' not in rows[0,84]['notes'],'corrected catalog NaN claim')
    claims=load(HERE/'claims.json')['claims']
    annotated=[r for r in catalog['descriptors'] if r['name']]
    check(len(claims)==len(annotated)==44,'addressed annotation claim count')
    for r in annotated:
        prefix=f"Native descriptor {r['bank']}:{r['index']} ({r['name']}): "
        matches=[c for c in claims if c['Finding'].startswith(prefix)]
        check(len(matches)==1 and matches[0]['addr']==hex(BASE+r['handlerRva']),'addressed catalog claim')
        check(matches[0]['Finding']==prefix+r['summary'] and r['notes'] in matches[0]['Limitations'],'claim text matches reviewed metadata')
    embedded=ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
    check(load(embedded)==catalog,'embedded product data matches reviewed catalog')
    sources=['evidence.json','helpers.json','catalog-data.json','build_catalog.py','claims.json']
    source_hashes=[dict(path=n,sha256=sha((HERE/n).read_bytes())) for n in sources]
    source_hashes+= [dict(path=str(p.relative_to(ROOT)),sha256=sha(p.read_bytes())) for p in [registry_path,ROOT/'docs/research/bdx-trap-registry-20261008/verify.py',embedded]]
    chunks=dict(additionalIdaCapture=capture,functions=function_checks,
                separateTail=dict(sourceAdapter='0x14041dd00',addr='0x1401545b0',size=len(tail),originalBytes=tail.hex(' '),instructions=[dict(addr=hex(i.address),instruction=i.mnemonic+' '+i.op_str) for i in tail_ins]),dataSpans=spans)
    verification=dict(success=True,failures=0,sourceHashes=source_hashes,originalSha256=sha(pe.raw),
        adapterFunctions=100,helperFunctions=17,listedInstructions=instruction_count,primaryBodyBytes=primary_bytes,
        asmChunks=sum(len(f['chunks']) for f in function_checks),separateTailBytes=len(tail),descriptorChecks=len(descriptor_checks),
        descriptors=descriptor_checks,semanticAnchors=semantic,callAnchors=[dict(site=hex(BASE+a),target=hex(BASE+t)) for a,t in call_edges.items()],
        importCalls=sorted(import_calls,key=lambda x:x['site']),angleBranchExamples=angle_paths,
        review=dict(status='PASS after correction',correctedFinding='0:84 unordered/NaN follows both JB branches to acosf, rather than selecting pi; unmasked FP exceptions can terminate earlier.',
          reviewedCatalogAnnotations=sum(bool(r['name']) for r in catalog['descriptors']),
          focus=['0:7 helper returns original length in XMM0; adapter stores it to w and VM slot; helper normalizes xyz only.',
            '0:21 operand1 angle minus operand0 angle; no vector NaN-sanitization loop in adapter.',
            '0:45 copied w survives xyz normalization and participates in both four-component scales and final addition.',
            '0:78 adapter reverses native helper argument order; helper multiplies RDX by t and R8 by1-t, matching a*(1-t)+b*t.',
            '0:82 operand order and cross-product w=0;0:102 horizontal length uses copied y=0, pitch atan2(-y,horizontal), yaw atan2(x,z), z=0,w=1.',
            '0:16 unsigned division and zero-divisor fault path;0:17/18 EDX write zero-extends before signed64 conversion; original constant is2^-32.',
            '0:22 INT_MIN wraps;0:23 double conversion/sign mask is not a raw float-bit abs.',
            'Vector sanitization modifies caller input memory; shared result slots are not stable owned copies.'],
          limits=['Byte/listing completeness is not transitive semantic closure of all100 adapters.','Only44 catalog annotations are reviewed; blank entries remain unannotated.','External CRT, static-local initialization, FP exception controls, pointer validity, concurrency and live effects remain outside this static review.','Known normal-path side effects are documented; no safe-to-execute or pure-call promise.','No target code was executed.']))
    return chunks,verification

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    chunks,verification=derive()
    for name,obj in [('chunk-bytes.json',chunks),('verification.json',verification)]:
        b=encoded(obj)
        if args.check:check((HERE/name).read_bytes()==b,'derived file mismatch '+name)
        else:(HERE/name).write_bytes(b)
    print(json.dumps({k:verification[k] for k in ['success','failures','adapterFunctions','helperFunctions','listedInstructions','primaryBodyBytes','asmChunks','descriptorChecks']}))
if __name__=='__main__':main()
