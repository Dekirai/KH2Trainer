"""Build/check this bounded static evidence package. Never runs IDA or the game."""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, struct
import capstone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 0x140000000
TARGET = '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
EXE = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')

def require(value, reason):
    if not value: raise ValueError(reason)
def sha(b): return hashlib.sha256(b).hexdigest()
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def encode(d): return (json.dumps(d, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
def blob(s): return bytes(int(x,16) for x in s.split())
def hx(n): return hex(n)
def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def assemble(raw, source):
    a=raw['addr']
    if 'pages' in raw:
        pages=copy.deepcopy(raw['pages'])
        first=copy.deepcopy(pages[0]);first['asm']['lines']=[x for p in pages for x in p['asm']['lines']]
        first['instruction_count']=len(first['asm']['lines']);first['cursor']=copy.deepcopy(pages[-1]['cursor'])
        out={'addr':a,'disassembly':first,'pages':pages}
    elif 'disasm' in raw:
        out={'addr':a,'disassembly':copy.deepcopy(raw['disasm'])}
    elif 'disassembly' in raw:
        out={'addr':a,'disassembly':copy.deepcopy(raw['disassembly'])}
    else:
        raise ValueError('Missing captured ASM '+a)
    out['size']=raw.get('size',int(raw['lookup']['result'][0]['fn']['size'],16) if 'lookup' in raw else None)
    out['originalBytes']=raw.get('originalBytes')
    out['provenance']=source
    if 'pseudocodePages' in raw:
        pages=raw['pseudocodePages'];lines=0
        for i,p in enumerate(pages):
            require(p.get('error') is None and not p['cursor'].get('cancelled'), 'Incomplete pseudocode')
            require(len(p['code'].splitlines())==p['line_count'],'Pseudocode count')
            lines+=p['line_count']
            require(p['total_lines']==pages[0]['total_lines'],'Pseudocode totals')
            if i+1<len(pages): require(p['cursor'].get('next')==lines,'Pseudocode pagination')
            # This tool sets truncated=true on every page of a paginated
            # function, including its final page. Exact counts and cursors,
            # never that preview flag alone, establish the joined coverage.
            else: require(p['cursor'].get('done') is True and p['cursor'].get('next') is None,'Pseudocode final cursor')
        require(lines==pages[0]['total_lines'],'Pseudocode aggregate')
        out['pseudocode']={'code':'\n'.join(p['code'] for p in pages),'total_lines':lines,'cursor':{'done':True}}
        out['pseudocodePages']=copy.deepcopy(pages)
    return out

def derive():
    imports=load(HERE/'imports.json'); sources={}
    for entry in imports['sources']:
        b=(ROOT/entry['path']).read_bytes()
        require(sha(b)==entry['sha256'] and len(b)==entry['bytes'],'Reused source changed: '+entry['path'])
        if entry['path'].endswith('.json'):sources[entry['path']]=json.loads(b)
    pe=module(ROOT/'docs/research/actor-scale-contract-20261007/verify.py','pe_reader')
    cv=module(ROOT/'scripts/update-analysis-coverage.py','coverage_helpers')
    original=EXE.read_bytes();require(sha(original)==TARGET,'Original PE SHA')
    read=pe.original_reader(original,BASE)
    nt=struct.unpack_from('<I',original,0x3c)[0];optional=nt+24
    section_table=optional+struct.unpack_from('<H',original,nt+20)[0]
    section_count=struct.unpack_from('<H',original,nt+6)[0]
    sections=[struct.unpack_from('<4I',original,section_table+40*i+8) for i in range(section_count)]
    discovery=load(HERE/'discovery.json');q=discovery['queries']
    require(q['server_health']['auto_analysis_ready'] and q['survey_binary']['metadata']['sha256']==TARGET,'IDA identity/readiness')
    require(q['imports']['next_offset'] is None,'Imports pagination')
    # Check the recorded import inventory against the PE's original INT/IAT.
    def cstr(rva):
        chars=[]
        for j in range(4096):
            c=read(BASE+rva+j,1)[0]
            if c==0:return bytes(chars).decode('ascii')
            chars.append(c)
        raise ValueError('Unterminated PE import name')
    import_rva,import_size=struct.unpack_from('<II',original,optional+112+8)
    original_imports={}
    for off in range(0,import_size,20):
        oft,stamp,chain,name,iat_rva=struct.unpack('<5I',read(BASE+import_rva+off,20))
        if not any((oft,stamp,chain,name,iat_rva)):break
        dll=cstr(name).lower().removesuffix('.dll')
        for j in range(65536):
            value=struct.unpack('<Q',read(BASE+(oft or iat_rva)+8*j,8))[0]
            if not value:break
            original_imports[BASE+iat_rva+8*j]=(dll,value&0xffff if value>>63 else cstr(value+2))
    recorded_imports={int(x['addr'],16):(x['module'].lower(),x['imported_name'].removeprefix('__imp_')) for x in q['imports']['data']}
    require(set(recorded_imports)==set(original_imports),'Import address inventory differs from PE')
    ordinal_imports=[]
    for address,(dll,name) in original_imports.items():
        require(recorded_imports[address][0]==dll,'Import DLL differs from PE')
        if isinstance(name,int):
            ordinal_imports.append({'addr':hx(address),'module':dll,'ordinal':name,'idaLabel':recorded_imports[address][1],'labelVerifiedByPE':False})
        else:require(recorded_imports[address][1]==name,'Import name differs from PE')
    for name in ('xrefs_to','xrefs_tables','xrefs_tablebase'):
        for x in q[name]['result']: require(x.get('more') is False and x['xref_count']==len(x['xrefs']),'Xrefs incomplete')
    for p in q['pointer_search']['result']:
        require(p['cursor'].get('done') is True and p['cursor'].get('next') is None and not p['cursor'].get('cancelled'),'Pointer scan pagination')
        require(p['n']==len(p['matches']),'Pointer count')
        for a in p['matches']:require(read(int(a,16),8)==blob(p['pattern']),'Pointer match PE bytes')
        pattern=blob(p['pattern']);found=[]
        for _,rva,length,filepos in sections:
            section=original[filepos:filepos+length];offset=0
            while (offset:=section.find(pattern,offset))>=0:
                found.append(BASE+rva+offset);offset+=1
        require(sorted(found)==sorted(int(x,16) for x in p['matches']), 'Exact qword search differs from original PE sections')
    data=q['table_bytes']['result']+q['rootbytes']['result']+load(HERE/'final-data.json')['result']
    for d in data:require(read(int(d['addr'],16),len(blob(d['data'])))==blob(d['data']),'Captured data bytes')
    fresh=load(HERE/'fresh-body-pages.json')['functions']
    extra=load(HERE/'extra-body-pages.json')
    for x in extra['xrefs']['result']:require(x.get('more') is False and x['xref_count']==len(x['xrefs']),'Extra xrefs incomplete')
    rawbytes={b['addr']:b['data'] for result in extra['additionalBytes'] for b in result['result']}
    rawbytes.update({b['addr']:b['data'] for b in q['rootbytes']['result']})
    pool={}
    for source,doc in sources.items():
        for f in doc.get('functions',[]):
            # Prior evidence uses aggregate ASM plus finished pages.
            g=copy.deepcopy(f)
            if 'asm' in g and 'pages' not in g:
                g['disassembly']={k:g[k] for k in ('addr','asm','instruction_count','total_instructions','cursor')}
            if 'asm' in g or 'disasm' in g:pool[f['addr']]=assemble(g,source)
    for f in fresh+extra['functions']:
        g=copy.deepcopy(f)
        if 'originalBytes' not in g:g['originalBytes']=rawbytes[g['addr']]
        if 'size' not in g and 'lookup' not in g:g['size']=pool[g['addr']]['size']
        pool[g['addr']]=assemble(g,'fresh-body-pages.json' if f in fresh else 'extra-body-pages.json')
    scope={hex(BASE+int(x,16)) for x in (
        '3c0010 3c0280 3c06b0 3c07e0 3c2120 3c2240 3ebf30 3ee8a0 3ee8c0 '
        '4016b0 4112b0 411350 439ef0 439f50 439fc8 43a028 4ad240 4ad270 4ad2c0 '
        '4ad390 4ad3f0 431aa0 431a70 3ebf20 26acc0 26ace0 3e1720 3e1410 41b400 '
        '439b8c 439d5c 3b5e80 3e1840 3e1c80 41b320 41c690 3c6aa0 3bfab0 3bf4e0 '
        '3beec0 12fdb0 130030 130130').split()}
    require(scope<=set(pool),'Missing scoped body')
    pool={a:pool[a] for a in scope}
    cs=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);cs.detail=True
    decoded={};receipts=[];padding=[]
    for a,f in pool.items():
        ok,addresses,reason=cv.body_assembly(f);require(ok,a+': '+reason)
        b=blob(f['originalBytes']);start=int(a,16)
        require(len(b)==f['size'] and read(start,len(b))==b,'Body PE mismatch '+a)
        ins=[];last=start
        for x in addresses:
            if x!=last:
                gap=b[last-start:x-start];pad=list(cs.disasm(gap,last))
                require(x>last and sum(i.size for i in pad)==len(gap) and
                        all(i.mnemonic in ('nop','int3') for i in pad),'Unexplained instruction gap '+a)
                padding.append({'function':a,'start':hx(last),'endExclusive':hx(x),'originalBytes':gap.hex(' ')})
            i=next(cs.disasm(b[x-start:],x,count=1),None);require(i is not None,'Undecodable instruction')
            ins.append(i);last=x+i.size
        tail=start+len(b)-last
        require(tail==0 or a=='0x14041b400' and tail==231,'Unexpected non-instruction tail '+a)
        decoded[a]=ins
    # Exact ordinary direct-call/tail graph for the two roots and adapters.
    roots=['0x1404112b0','0x140411350','0x140431aa0','0x140431a70']
    todo=roots+['0x1403ebf20'];closure=set();edges=[]
    iat={int(i['addr'],16):i for i in q['imports']['data']}
    while todo:
        a=todo.pop()
        if a in closure:continue
        require(a in decoded,'Uncaptured direct descendant '+a);closure.add(a)
        start=int(a,16);end=start+pool[a]['size']
        for i in decoded[a]:
            if not (i.group(capstone.CS_GRP_CALL) or i.group(capstone.CS_GRP_JUMP)):continue
            op=i.operands[0]
            if op.type==capstone.x86.X86_OP_IMM:
                if start<=op.imm<end:continue
                target=hx(op.imm);todo.append(target)
                edges.append({'function':a,'site':hx(i.address),'kind':i.mnemonic,'target':target})
            elif op.type==capstone.x86.X86_OP_MEM and op.mem.base==capstone.x86.X86_REG_RIP:
                ptr=i.address+i.size+op.mem.disp
                require(ptr in iat or ptr==0x14057bca0,'Unresolved native indirect boundary')
                target=iat[ptr]['imported_name'] if ptr in iat else 'guard dispatch: decoded condition-variable API; external contract'
                edges.append({'function':a,'site':hx(i.address),'kind':i.mnemonic,'pointer':hx(ptr),'external':target})
            else:raise ValueError('Unresolved register transfer '+hx(i.address))
    selected=set(closure)|{'0x14026acc0','0x14026ace0','0x1403e1720','0x1403e1410','0x14041b400','0x140439b8c','0x140439d5c'}
    selected|={'0x1403b5e80','0x1403e1840','0x1403e1c80','0x14041b320','0x14041c690','0x1403c6aa0','0x1403bfab0','0x1403bf4e0','0x1403beec0','0x14012fdb0','0x140130030','0x140130130'}
    functions=[pool[a] for a in sorted(selected)]
    _,baseline,_=cv.load_baseline();native={int(f['address'],16):f for f in baseline['functions'] if f['domain']=='native'}
    for f in functions:require(native[int(f['addr'],16)]['size']==f['size'],'Inventory extent')
    # Native exception directory records, retained with their exact bytes.
    exc_rva,exc_size=struct.unpack_from('<II',original,optional+112+3*8)
    pdata=read(BASE+exc_rva,exc_size);unwind=[]
    for a in roots+['0x1404ad2c0','0x14041b400']:
        fstart=int(a,16)-BASE;fend=fstart+pool[a]['size'];matches=[]
        for j in range(0,len(pdata),12):
            s,e,u=struct.unpack_from('<III',pdata,j)
            if s<fend and e>fstart:matches.append((j,(s,e,u)))
        require(matches and matches[0][1][0]==fstart,'Runtime function identity '+a)
        for j,(start,end,uw) in matches:
            h=read(BASE+uw,4);flags=h[0]>>3;n=4+((h[2]+1)&~1)*2+(12 if flags&4 else 4 if flags&3 else 0)
            unwind.append({'function':a,'recordStart':hx(BASE+start),'pdataAddress':hx(BASE+exc_rva+j),'pdataBytes':pdata[j:j+12].hex(' '),'endExclusive':hx(BASE+end),'unwindAddress':hx(BASE+uw),'unwindBytes':read(BASE+uw,n).hex(' '),'version':h[0]&7,'flags':flags,'prologSize':h[1]})
        if a in roots:require(len(matches)==1 and matches[0][1][1]==fend and unwind[-1]['flags']==0,'Root exception extent/flags changed')
    bank=struct.unpack('<Q',read(0x1407534a0,8))[0];require(bank==0x140756b60,'Bank2 root')
    traps=[]
    for index,thunk,argc,root in [(9,0x140431a70,3,0x140411350),(95,0x140431aa0,2,0x1404112b0)]:
        addr=bank+index*16;b=read(addr,16);ptr,flags=struct.unpack_from('<QI',b)
        require(ptr==thunk and flags==argc,'Trap descriptor')
        last=decoded[hx(thunk)][-1];require(last.mnemonic=='jmp' and last.operands[0].imm==root,'Adapter tail target')
        rootins=decoded[hx(root)];require(rootins[-1].mnemonic=='ret','Rebind normal return')
        traps.append({'bank':2,'index':index,'descriptor':hx(addr),'originalBytes':b.hex(' '),'thunk':hx(thunk),'root':hx(root),'argumentCount':argc,'pushesReturnSlot':bool(flags&0x40000000),'canonicalOpcodeWords':[0x8a,index]})
    # Operand-copy model is a reading aid, not interpreter execution.
    for count in (2,3):
        stack=list(range(count));result=[None]*count
        for j in reversed(range(count)):result[j]=stack.pop()
        require(result==list(range(count)) and not stack,'Dispatch operand order')
    semantic_sites={
        0x1403ebf44:('movsxd','rcx, ecx'),
        0x1404112d7:('mov','qword ptr [rdi + 0x5c0], rax'),
        0x1404112e1:('test','rax, rax'),
        0x1404112e4:('je','0x1404112f4'),
        0x1404112ee:('mov','dword ptr [rbx + 0x268], eax'),
        0x140411377:('mov','qword ptr [rdi + 0x5c0], rax'),
        0x140411381:('test','rax, rax'),
        0x140411384:('je','0x140411394'),
        0x14041138e:('mov','dword ptr [rbx + 0x268], eax'),
        0x14041c4aa:('mov','rcx, qword ptr [rsp + 0x68]'),
        0x14041c4b6:('mov','rdi, qword ptr [rcx + rax*8]'),
        0x14041c4cf:('movzx','edx, word ptr [rdi + 8]'),
        0x14041c4fa:('call','qword ptr [rdi]'),
        0x14041c4fc:('test','dword ptr [rdi + 8], 0x40000000'),
        0x140431aa6:('mov','ebx, dword ptr [rcx + 8]'),
        0x140431aa9:('mov','ecx, dword ptr [rcx]'),
        0x140431ab0:('mov','ecx, dword ptr [rax + 4]'),
        0x140431a76:('mov','ebx, dword ptr [rcx + 8]'),
        0x140431a79:('mov','ecx, dword ptr [rcx]'),
        0x140431a80:('mov','ecx, dword ptr [rax + 4]'),
    }
    by_site={i.address:i for a in selected for i in decoded[a]}
    for site,expected in semantic_sites.items():
        i=by_site[site];require((i.mnemonic,i.op_str)==expected,'Critical ABI instruction differs '+hx(site))
    # The interpreter's rdata xref is a chained RUNTIME_FUNCTION record,
    # not an independently registered native callback.
    require(struct.unpack('<III',read(0x1406ef8b0,12))==(0x41b400,0x41b502,0x6ef870),'Interpreter chained unwind record')
    for a in selected:
        f=pool[a];receipts.append({'addr':a,'instructions':len(decoded[a]),'bodyBytes':f['size'],'bodySha256':sha(blob(f['originalBytes']))})
    bodydoc={'schema':1,'domain':'native','originalSha256':TARGET,'imageBase':hx(BASE),'functions':functions,'data':data,'scope':'Full captured/reused bodies; selected observations only. Interpreter final 231 bytes are padding/switch data.'}
    detail={'schema':1,'traps':traps,'normalRebindClosure':sorted(closure),'transferEdges':edges,'exceptionMetadata':unwind,'paddingGaps':sorted(padding,key=lambda x:x['start']),'imports':q['imports'],'ordinalImports':ordinal_imports,
            'bindingStoreCondition':'After acquisition returns, Actor+0x5c0 is always assigned its result; STATUS+0x268 is assigned only when that result is nonnull.',
            'bsearchContract':{'keyConstruction':'3EBF44 sign-extends ECX into RCX; parameter ID0 is a null key at3EBF5A.',
                               'normalClosurePrecondition':'Nonzero key and all other bsearch parameter preconditions satisfied, with valid table/count/comparator and resources.',
                               'invalidParameterBoundary':'The documented CRT invalid-parameter handler may run for null key. Its behavior is outside this closure; reaching the ID0x45 retry requires the first call to return null.'},
            'limits':['Normal retail direct/tail closure plus fixed bsearch comparator, with valid nonzero bsearch key and other external CRT/Win32 contracts.','Invalid bsearch parameters can invoke an unclosed external invalid-parameter handler; no no-yield or normal-return claim covers that path.','No shipped Event27 bytecode path, complete mutable-table/alias closure, or live thread exclusion established.','VM dispatch table includes mutable banks; the two recorded setter callers change bank9, not bank2.','PE independently confirms import addresses/modules/named symbols and ordinal numbers; names resolved by IDA for ordinal imports remain labels.']}
    receipt={'status':'PASS','functions':len(functions),'instructions':sum(len(decoded[a]) for a in selected),'originalBodyBytes':sum(pool[a]['size'] for a in selected),'normalClosureFunctions':len(closure),'bodyReceipts':sorted(receipts,key=lambda x:x['addr']),'checks':['pinned imported sources','original PE SHA and every body/data/pointer byte','ASM and pseudocode pagination','contiguous instruction boundaries with explicit interpreter tail data','central coverage metadata and frozen extent match','direct/tail closure including fixed bsearch comparator','trap descriptors and adapter tails','original exception directory/unwind bytes','operand order reading model'],'scope':'Static verification only; no game, native hook or interpreter execution.'}
    return {'evidence.json':encode(bodydoc),'dispatch-contract.json':encode(detail),'verification.json':encode(receipt)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    products=derive()
    for name,b in products.items():
        if args.check:require((HERE/name).read_bytes()==b,'Derived mismatch '+name)
        else:(HERE/name).write_bytes(b)
    if args.check and (HERE/'manifest.json').exists():
        for n,r in load(HERE/'manifest.json')['files'].items():require(sha((HERE/n).read_bytes())==r['sha256'],'Manifest mismatch '+n)
    r=json.loads(products['verification.json']);print('PASS:',{k:r[k] for k in ('functions','instructions','originalBodyBytes','normalClosureFunctions')})
    if (HERE/'report.json').exists():
        cv=module(ROOT/'scripts/update-analysis-coverage.py','coverage_claim_helpers')
        ev=json.loads(products['evidence.json']);owners={f['addr'] for f in ev['functions']}
        for c in load(HERE/'report.json')['claims']:
            require(c['addr'] in owners and c['Finding'] and c['Limitations'],'Invalid bounded claim')
            for ref in c['Evidence']:require(cv.resolve_reference(HERE/'report.json',ref)['status']=='exists','Unresolved claim evidence')

if __name__=='__main__':main()
