"""Reproduce the next bounded BDX metadata update; verify original descriptor bytes."""
import argparse, hashlib, importlib.util, json, struct
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def manifest(path):
    rows=load(path)['files']
    entries=rows.items() if isinstance(rows,dict) else ((r.get('file',r.get('path')),r) for r in rows)
    count=0
    for name,row in entries:
        p=path.parent/name
        assert sha(p)==(row if isinstance(row,str) else row['sha256']),(path,name)
        if isinstance(row,dict) and 'bytes' in row:assert p.stat().st_size==row['bytes']
        count+=1
    return dict(sha256=sha(path),files=count)

def derive():
    baseline=HERE.parent/'bdx-mission-gummi-implementation-20261008/catalog-data.json'
    data=load(baseline)
    rows={(r['bank'],r['index']):dict(r) for r in data['descriptors']}
    original={key:dict(row) for key,row in rows.items()}
    assert sum(bool(r['name']) for r in rows.values())==239
    sources=[baseline]
    studies=['bdx-bank3-extended-20261008','voice-request-lifecycle-20261008']
    pins={name:manifest(HERE.parent/name/'manifest.json') for name in studies}
    source=HERE.parent/studies[0]/'annotations.json';sources.append(source)
    changes=[]
    for key,a in load(source)['annotations'].items():
        bank,index=map(int,key.split(':'));row=rows[bank,index]
        assert not row['name'],('unexpected replacement',key)
        handler=int(a['handlerRva'],0) if isinstance(a['handlerRva'],str) else a['handlerRva']
        assert handler==row['handlerRva'],key
        assert a['declaredOperandCount']==(row['flags']&65535) and a['hasReturnSlot']==bool(row['flags']&0x40000000),key
        for field in ['name','summary','notes','evidence']:row[field]=a[field]
        changes.append(dict(bank=bank,index=index,kind='new',source=source.relative_to(ROOT).as_posix()))
    voice=rows[1,262]
    voice['notes']+=' The selected Voice update consumes its pending ID before request admission. A rejected admission therefore does not retain it for an automatic retry. A nonzero handle can still identify a queued request; it does not prove playback. The captured EE consumer advances the request after a backend call even on the missing-ORIGIN-bank return path. EE playback control uses the resource-derived key, Voice ID and group 2; a separate pool handle does not establish exclusive backend ownership. These are conditional paths, not a live audio observation or a complete backend/lifetime contract.'
    voice['evidence']+='; voice-request-lifecycle-20261008/capture.json; voice-request-lifecycle-20261008/additional-capture.json; voice-request-lifecycle-20261008/report.txt'
    changes.append(dict(bank=1,index=262,kind='expanded',source='docs/research/voice-request-lifecycle-20261008/report.txt'))
    data['descriptors']=[rows[k] for k in sorted(rows)]
    verifier=HERE.parent/'bdx-trap-registry-20261008/verify.py';sources.append(verifier)
    spec=importlib.util.spec_from_file_location('v01215_original_pe',verifier)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);pe=module.PE(module.TARGET)
    banks={b['bank']:b for b in data['banks']}
    for key,row in rows.items():
        assert all(row[f]==original[key][f] for f in ['bank','index','descriptorRva','handlerRva','flags']),key
        assert row['descriptorRva']==banks[key[0]]['tableRva']+16*key[1]
        raw,zero=pe.read(pe.base+row['descriptorRva'],16);assert not zero
        assert struct.unpack('<QII',raw)==(pe.base+row['handlerRva'] if row['handlerRva'] else 0,row['flags'],0),key
    changed={(c['bank'],c['index']) for c in changes}
    assert len(changed)==len(changes)==18 and sum(c['kind']=='new' for c in changes)==17
    assert len(rows)==1063 and sum(bool(r['name']) for r in rows.values())==256
    assert sum(r['handlerRva']==0 for r in rows.values())==15
    assert all(row==original[key] for key,row in rows.items() if key not in changed)
    receipt=dict(success=True,descriptors=1063,annotations=256,newAnnotations=17,expandedAnnotations=1,nullHoles=15,unchangedRows=len(rows)-len(changes),unchangedNumericRows=len(rows),changes=changes,upstreamManifests=pins,sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],scope='Offline descriptive metadata. Original numeric records, bytecode and native entrypoints unchanged.')
    return data,receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    data,receipt=derive()
    for p,x in [(HERE/'catalog-data.json',data),(HERE/'metadata-checks.json',receipt),(ROOT/'src/KH2Trainer.Core/Data/BdxNativeCalls.json',data)]:
        if args.check:assert p.read_bytes()==enc(x),p
        else:p.write_bytes(enc(x))
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['changes','sources','upstreamManifests']}))
