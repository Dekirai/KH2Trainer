"""Read-only frozen-archive and normalized original-PE evidence verification."""
import argparse,hashlib,importlib.util,json,struct,zipfile
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
H=Path(__file__).resolve().parent;ROOT=next(p for p in H.parents if (p/'src/KH2Trainer').is_dir());B=0x140000000
sha=lambda b:hashlib.sha256(b).hexdigest();load=lambda p:json.loads(p.read_bytes());num=lambda n:int(n,16) if isinstance(n,str) else n
def rawrows(f):
    if 'instructions' in f:return [{'addr':r['addr'],'instruction':r.get('ida',r['instruction'])} for r in f['instructions']]
    return (f.get('asm') or f.get('disassembly',{}).get('asm'))['lines']
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    manifest=load(H/'manifest.json')
    assert {p.name for p in H.iterdir() if p.is_file()}=={r['path'] for r in manifest['files']}|{'manifest.json'}
    for r in manifest['files']:
        b=(H/r['path']).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256'],r['path']
    provenance=load(H/'provenance.json');a=provenance['archive'];assert sha((H/a['path']).read_bytes())==a['sha256']
    with zipfile.ZipFile(H/a['path']) as z:
        assert len(z.namelist())==len(set(z.namelist()))==len(a['members'])
        assert set(z.namelist())=={r['path'] for r in a['members']}
        members={n:z.read(n) for n in z.namelist()}
    for r in a['members']:
        b=members[r['path']];assert len(b)==r['bytes'] and sha(b)==r['sha256']
    for prefix,key in [('study','studyManifest'),('review','reviewManifest')]:
        b=members[prefix+'/manifest.json'];assert sha(b)==provenance['manifestPins'][key]
        source=json.loads(b);source_rows=source['files'] if isinstance(source,dict) else source
        path_prefix='artifacts/'+('review-' if prefix=='review' else '')+provenance['study']+'/'
        source_rows=[dict(r,path=r['path'].removeprefix(path_prefix)) for r in source_rows]
        assert {n for n in members if n.startswith(prefix+'/')}=={prefix+'/'+r['path'] for r in source_rows}|{prefix+'/manifest.json'}
        for r in source_rows:
            b=members[prefix+'/'+r['path']];assert len(b)==r.get('size',r.get('bytes')) and sha(b)==r['sha256']
    reviewed=json.loads(members['review/review.json'])
    assert reviewed['status'] in ('PASS','ACCEPTED'),reviewed['status']
    data=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
    assert sha(data)=='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
    nt=struct.unpack_from('<I',data,0x3c)[0];opt=nt+24;assert struct.unpack_from('<Q',data,opt+24)[0]==B
    sections=[struct.unpack_from('<IIII',data,opt+struct.unpack_from('<H',data,nt+20)[0]+40*i+8) for i in range(struct.unpack_from('<H',data,nt+6)[0])]
    def pe(at,size):
        for vs,start,rs,offset in sections:
            if start<=at-B and at-B+size<=start+rs:return data[offset+at-B-start:offset+at-B-start+size]
        raise AssertionError(hex(at))
    spec=importlib.util.spec_from_file_location('coverage_rules',ROOT/'scripts/update-analysis-coverage.py');rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
    inventory={num(f['address']):f['size'] for line in (ROOT/'docs/research/coverage/function_status.jsonl').read_text('utf8').splitlines() if (f:=json.loads(line))['domain']=='native'}
    evidence=load(H/'evidence.json');source_map={m['addr']:m for m in provenance['normalizedSources']};cs=Cs(CS_ARCH_X86,CS_MODE_64)
    aliases={'retn':'ret','jz':'je','jnz':'jne','jnb':'jae','jna':'jbe','jnl':'jge','jng':'jle','cmovz':'cmove','cmovnz':'cmovne','setz':'sete','setnz':'setne','setnb':'setae','sal':'shl'}
    totals={'functions':len(evidence['functions']),'instructions':0,'bodyBytes':0,'dataBytes':0,'ranges':len(evidence.get('code_ranges',[])),'rangeBytes':0,'rangeInstructions':0}
    for key in ['functions','code_ranges']:
        for f in evidence.get(key,[]):
            at=num(f['addr']);b=bytes.fromhex(f['originalBytes']);assert b==pe(at,f['size']) and len(b)==f['size'] and sha(b)==f['sha256']
            assert rules.original_spans(f)==[(at,b)]
            m=source_map[f['addr']];rawdoc=json.loads(members[m['archiveMember']]);raw=next(x for x in rawdoc[m['collection']] if num(x['addr'])==at)
            assert bytes.fromhex(raw['originalBytes'])==b and raw['size']==f['size']
            rows=rawrows(raw)
            if key=='functions':
                assert f['complete'] and inventory[at]==f['size']
                assert f['pages']==[f['disassembly']] and f['disassembly']['asm']['lines']==rows
                complete,heads,reason=rules.body_assembly(f);assert complete,reason
                assert heads==[num(r['addr']) for r in rows]
                totals['bodyBytes']+=len(b)
            else:
                assert not f['complete'] and at not in inventory and num(f['end_exclusive'])==at+f['size']
                assert f['asm']['lines']==rows and f['observed_line_count']==len(rows)
                totals['rangeBytes']+=len(b)
            count=0
            for n,r in enumerate(rows):
                pos=num(r['addr']);end=num(rows[n+1]['addr']) if n+1<len(rows) else at+len(b);text=r['instruction'];mn=text.split()[0]
                assert at<=pos<end<=at+len(b)
                if mn in ('align','db','dw','dd','dq'):continue
                i=next(cs.disasm(b[pos-at:end-at],pos,count=1));assert i.size<=end-pos
                actual={'movabs':'mov'}.get(i.mnemonic.split()[0],i.mnemonic.split()[0])
                assert aliases.get(mn,mn)==actual or (text=='xchg ax, ax' and actual=='nop'),(hex(pos),text,i.mnemonic)
                count+=1
            totals['instructions' if key=='functions' else 'rangeInstructions']+=count
    for f in evidence.get('data',[]):
        b=bytes.fromhex(f['originalBytes']);assert len(b)==f['size'] and b==pe(num(f['addr']),len(b)) and sha(b)==f['sha256'];totals['dataBytes']+=len(b)
    report=load(H/'report.json');claims=report['claims'];ranges=report.get('findings',[]);refs=0
    if 'study/report.json' in members:
        old=json.loads(members['study/report.json']);before=old['claims']+old.get('rangeFindings',[])
        assert len(before)==len(claims)+len(ranges)
        for c,o in zip(claims+ranges,before):assert all(c[k]==o[k] for k in ['addr','Finding','Limitations'])
    else:
        assert provenance['study']=='motion-production-gap-20261013' and len(claims)==6 and not ranges
        scheduler=json.loads(members['study/scheduler-order.json']);assert totals['functions']==scheduler['functionCount']==6 and totals['instructions']==scheduler['instructionCount']==432 and totals['bodyBytes']==scheduler['extentBytes']==1623
    for c in claims+ranges:
        assert c['Finding'] and c['Limitations'] and c['addr'] in source_map
        for ref in c['Evidence']:
            assert rules.resolve_reference(H/'report.json',ref).get('status')=='exists',ref;refs+=1
    assert len(claims)==len({c['addr'] for c in claims})
    assert all(c['addr'] in {f['addr'] for f in evidence['functions']} for c in claims)
    assert all(c['addr'] in {f['addr'] for f in evidence.get('code_ranges',[])} for c in ranges)
    print(json.dumps({'status':'PASS','study':provenance['study'],'counts':totals,'claims':len(claims),'rangeFindings':len(ranges),'references':refs,'archiveMembers':len(members),'byteFailures':0,'semanticEmulator':False}))
if __name__=='__main__':main()
