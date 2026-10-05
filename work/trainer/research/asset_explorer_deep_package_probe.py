import collections,hashlib,json,pathlib,re,struct,zlib
ROOT=pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-')
OUT=pathlib.Path('work/trainer/research')
src=(OUT/'asset_explorer_deep_sources/OpenKh.Egs_EgsEncryption.cs').read_text()
sbox=bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})',src.split('MasterKey =')[1].split('};')[0]))
rcon=[1,2,4,8,16,32,64,128,27,54]
def transform(data,seed):
    key=bytearray(176);key[:16]=bytes(v or i for i,v in enumerate(seed))
    for i in range(40):
        frame=key[12+i*4:16+i*4]
        if i%4==0:frame=bytes([sbox[frame[1]]^rcon[i//4],sbox[frame[2]],sbox[frame[3]],sbox[frame[0]]])
        key[16+i*4:20+i*4]=bytes(a^b for a,b in zip(key[i*4:i*4+4],frame))
    mask=bytes(__import__('functools').reduce(lambda a,b:a^b,(key[16*r+j] for r in range(11))) for j in range(16))
    data=bytearray(data)
    for i in range(min(len(data)//16*16,256)):data[i]^=mask[i%16]
    return bytes(data)
names=(ROOT/'Modding/openkh/resources/kh2idx.txt').read_text().splitlines()
# Exact path dictionary only; no hash-based name invention.
named={hashlib.md5(n.encode()).digest():n for n in names}
wanted={'00battle.bin','03system.bin','00common.bdx','00effect.bar','obj/P_EX100.mdlx','obj/P_EX100.mset','msg/us/sys.bar','ard/us/tt00.ard'}
result=[]
for hed in sorted((ROOT/'Image/dt').glob('kh2_*.hed')):
    data=hed.read_bytes();pkg=hed.with_suffix('.pkg');plen=pkg.stat().st_size
    rows=[]; stats=collections.Counter();sample=[]
    assert len(data)%32==0
    with pkg.open('rb') as f:
        for idx in range(len(data)//32):
            digest,off,stored,actual=struct.unpack_from('<16sQii',data,idx*32)
            name=named.get(digest)
            stats['entries']+=1;stats['named']+=name is not None
            if stored==0:stats['zeroStored']+=1
            if off>plen or stored<0 or stored>plen-off:
                stats['badHedBounds']+=1;continue
            if stored==0:continue
            f.seek(off);seed=f.read(16)
            if len(seed)!=16:stats['shortHeader']+=1;continue
            raw,n,mode,date=struct.unpack('<iiii',seed)
            stats['mode:'+str(mode if mode<1 else 'compressed')]+=1
            if n<0 or n>65536 or raw<0 or 16+48*n>stored:
                stats['invalidHeader']+=1;continue
            if name not in wanted and len(sample)>=3:continue
            if raw>16*1024*1024:continue
            f.seek(off+16);metadata=f.read(n*48)
            packedSize=mode if mode>0 and raw>16 else raw
            if packedSize<0 or 16+48*n+packedSize>stored:stats['invalidPayload']+=1;continue
            packed=f.read(packedSize)
            decoded=transform(packed,seed) if raw>16 and mode>=-1 else packed
            if raw>16 and mode>0:
                try: decoded=zlib.decompress(decoded)
                except zlib.error as e:sample.append(dict(index=idx,name=name,error=str(e)));continue
            loose=ROOT/'Modding/openkh/data/kh2'/name if name else None
            comparison=(hashlib.sha256(loose.read_bytes()).hexdigest()==hashlib.sha256(decoded).hexdigest()) if loose and loose.exists() else None
            remnants=[];pos=16+48*n+(mode if mode>=0 else ((raw+15)&~15))
            for j in range(n):
                tag,logical,original,rraw,rmode=struct.unpack_from('<32siiii',metadata,48*j)
                rpacked=rmode if rmode>=0 else ((rraw+15)&~15)
                remnants.append(dict(index=j,nameBytes=tag.hex(),name=tag.split(b'\0')[0].decode('ascii','backslashreplace'),diskLogicalOffset=logical,computedStoredOffset=pos,originalAssetOffset=original,rawLength=rraw,mode=rmode,storedSpan=rpacked,bounded=pos>=0 and rpacked>=0 and pos<=stored and rpacked<=stored-pos))
                pos+=rpacked
            sample.append(dict(index=idx,name=name,md5=digest.hex(),offset=off,hedStored=stored,hedActual=actual,header=seed.hex(),rawLength=raw,remastered=n,mode=mode,decodedLength=len(decoded),decodedSha256=hashlib.sha256(decoded).hexdigest(),prefix=decoded[:32].hex(),looseExactMatch=comparison,remasterEntries=remnants))
    result.append(dict(hed=str(hed),hedSha256=hashlib.sha256(data).hexdigest(),pkg=str(pkg),pkgLength=plen,stats=dict(stats),samples=sample))
    print(hed.name,dict(stats),[(x.get('name'),x.get('looseExactMatch')) for x in sample],flush=True)
(OUT/'asset_explorer_deep_packages.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

