import json,struct,pathlib,hashlib
root=pathlib.Path(__file__).resolve().parents[3]
inv=json.loads((root/'work/pe/inventory.json').read_text(encoding='utf-8'))
methods=json.loads((root/'work/pe/methods_compact.json').read_text(encoding='utf-8'))
data=pathlib.Path(inv['path']).read_bytes()
sections=inv['sections']
def locate(off):
    for s in sections:
        raw=int(s['raw'],0)
        if raw<=off<raw+s['size']:
            return {'fileOffset':hex(off),'section':s['name'],'rva':hex(int(s['rva'],0)+off-raw)}
    return {'fileOffset':hex(off),'section':None,'rva':None}
def hits(pattern):
    out=[]; start=0
    while (i:=data.find(pattern,start))>=0:
        out.append(locate(i)); start=i+1
    return out
out={'sha256':hashlib.sha256(data).hexdigest(),'methodsChecked':len(methods),'exportsChecked':len(inv['exports']),'method':'Read-only raw PE pointer/RVA scan, CLR MethodDef and export cross-check; data references alone do not establish execution reachability.','targets':[]}
for rva in [0x08DB30,0x077A30,0x137BB0,0x136640,0x077480,0x077500,0x091670]:
    rh=hits(struct.pack('<I',rva))
    for h in rh:
        if h['section']=='.pdata':
            begin,end,unwind=struct.unpack_from('<III',data,int(h['fileOffset'],0))
            h['runtimeFunction']={'beginRva':hex(begin),'endRva':hex(end),'unwindRva':hex(unwind)}
    out['targets'].append({'rva':hex(rva),'fullVaPointerOccurrences':hits(struct.pack('<Q',0x140000000+rva)),'rvaValueOccurrences':rh,'clrMethods':[m for m in methods if m['rva']==rva],'exports':[x for x in inv['exports'] if int(x['rva'],0)==rva]})
(root/'work/trainer/research/audio_lifecycle_indirect_audit.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({'sha256':out['sha256'],'targets':out['targets']},indent=2))
