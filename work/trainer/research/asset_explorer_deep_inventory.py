import collections,hashlib,json,os,pathlib,struct
ROOT=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\Modding\openkh\data\kh2')
OUT=pathlib.Path('work/trainer/research/asset_explorer_deep_corpus.json')
counts=collections.Counter(); types=collections.Counter(); headers=collections.Counter(); flags=collections.Counter(); examples={}; invalid=[]; special=[]; exts=collections.Counter()
def scan(f,start,length,path,depth,ancestors):
    f.seek(start);h=f.read(16)
    if len(h)<16 or h[:3]!=b'BAR':return False
    counts['bar_candidates']+=1
    magic,n,base,tail=struct.unpack('<4sIII',h)
    if n>65536 or 16+16*n>length:
        invalid.append(dict(path=path,length=length,header=h.hex(),reason='table exceeds bounded container or count cap')); return False
    headers[(magic.hex(),base,tail)]+=1
    f.seek(start+16);table=f.read(16*n)
    entries=[struct.unpack_from('<HH4sII',table,16*i) for i in range(n)]
    bad=[i for i,(t,fl,tag,off,size) in enumerate(entries) if size and (off<16+16*n or off>length or size>length-off)]
    if bad:
        invalid.append(dict(path=path,length=length,header=h.hex(),reason='nonempty span outside payload region',entries=bad[:10]));return False
    counts['valid_bars']+=1;counts['entries']+=n
    if depth:counts['nested_bars']+=1
    seen=set()
    for i,(t,fl,tag,off,size) in enumerate(entries):
        types[t]+=1;flags[fl]+=1
        row=dict(path=path,index=i,type=t,flags=fl,tagHex=tag.hex(),tag=tag.decode('ascii','backslashreplace'),offset=off,size=size)
        if t not in examples:examples[t]=row
        if not size:
            counts['empty_entries']+=1
            if off==0xffffffff:counts['empty_sentinel_minus1']+=1
            continue
        key=(start+off,size)
        if key in seen:counts['alias_spans']+=1;continue
        seen.add(key)
        if fl and len(special)<15:special.append(row)
        if depth<12 and key not in ancestors:
            scan(f,start+off,size,path+'!'+str(i)+':'+tag.hex(),depth+1,ancestors|{key})
        elif depth>=12:counts['depth_cap']+=1
    return True
for folder,dirs,files in os.walk(ROOT,followlinks=False):
    dirs[:]=[d for d in dirs if not pathlib.Path(folder,d).is_symlink()]
    for name in files:
        p=pathlib.Path(folder,name)
        if p.is_symlink():continue
        counts['files']+=1;exts[p.suffix.lower()]+=1
        try:
            with p.open('rb') as f:scan(f,0,p.stat().st_size,str(p.relative_to(ROOT)).replace('\\','/'),0,set())
        except (OSError,ValueError) as e:invalid.append(dict(path=str(p),reason=str(e)))
result=dict(root=str(ROOT),counts=dict(counts),extensions=dict(exts.most_common()),types=dict(sorted(types.items())),headers=[dict(magic=k[0],base=k[1],tail=k[2],count=v) for k,v in headers.most_common()],entryFlags=dict(flags.most_common()),typeExamples=list(examples.values()),specialExamples=special,invalid=invalid)
OUT.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:result[k] for k in ('counts','headers','entryFlags')},indent=2));print('invalid',len(invalid))

