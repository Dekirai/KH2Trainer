"""Read-only verification of the saved IDA bodies and retail object-role data.

No game process access. Run from any directory using Python 3.13.
The archived reference transform is needed only to decode the retail package;
its exact source digest is recorded. Object bytes themselves are not exported.
"""
import argparse, hashlib, json, pathlib, re, struct, zlib

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('--game-root', type=pathlib.Path, default=pathlib.Path(
    r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-'))
args = ap.parse_args()
exe = args.game_root / 'KINGDOM HEARTS II FINAL MIX.exe'
evidence = json.loads((HERE / 'evidence.json').read_text(encoding='utf-8'))

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

assert digest(exe) == evidence['inputSha256']
with exe.open('rb') as stream:
    header = stream.read(4096)
    pe = struct.unpack_from('<I', header, 60)[0]
    section_count = struct.unpack_from('<H', header, pe+6)[0]
    optional_size = struct.unpack_from('<H', header, pe+20)[0]
    image_base = struct.unpack_from('<Q', header, pe+24+24)[0]
    sections = []
    for i in range(section_count):
        off = pe+24+optional_size+40*i
        size, rva, raw_size, raw = struct.unpack_from('<IIII', header, off+8)
        sections.append((rva, raw_size, raw))
    validated = []
    for function in evidence['functions']:
        address = int(function['addr'], 16)
        body = bytes(int(x,16) for x in function['originalBytes'].split())
        rva = address-image_base
        section = next(s for s in sections if s[0] <= rva and rva+len(body) <= s[0]+s[1])
        stream.seek(section[2]+rva-section[0])
        assert stream.read(len(body)) == body, function['addr']
        asm = function['disassembly']
        lines = asm['asm']['lines']
        assert asm['instruction_count'] == asm['total_instructions'] == len(lines)
        assert asm['cursor'].get('done') is True and asm['cursor'].get('next') is None
        addresses = [int(line['addr'],16) for line in lines]
        assert addresses[0] == address and addresses == sorted(set(addresses))
        assert all(address <= x < address+len(body) for x in addresses)
        validated.append(dict(addr=function['addr'], bytes=len(body), instructions=len(lines), sha256=hashlib.sha256(body).hexdigest()))

reference = HERE / 'reference/OpenKh.Egs_EgsEncryption.cs'
assert digest(reference) == '62609383cff28cd07733b03cd40b5d5bc48c2a901ef67e2fd08a53ae9edd5e1f'
# Parse one known constant table as data; never execute or import this source.
source = reference.read_text(encoding='utf-8')
sbox = bytes(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{2})', source.split('MasterKey =')[1].split('};')[0]))
assert len(sbox) == 256
rcon = [1,2,4,8,16,32,64,128,27,54]
def transform(data,seed):
    key=bytearray(176); key[:16]=bytes(v or i for i,v in enumerate(seed))
    for i in range(40):
        frame=key[12+i*4:16+i*4]
        if i%4==0:
            frame=bytes([sbox[frame[1]]^rcon[i//4],sbox[frame[2]],sbox[frame[3]],sbox[frame[0]]])
        key[16+i*4:20+i*4]=bytes(a^b for a,b in zip(key[i*4:i*4+4],frame))
    mask=bytes(__import__('functools').reduce(lambda a,b:a^b,(key[16*r+j] for r in range(11))) for j in range(16))
    data=bytearray(data)
    for i in range(min(len(data)//16*16,256)): data[i]^=mask[i%16]
    return bytes(data)

target = hashlib.md5(b'00objentry.bin').digest()
assets = []
for hed in sorted((args.game_root/'Image/dt').glob('kh2_*.hed')):
    index = hed.read_bytes()
    assert len(index)%32 == 0
    for ordinal in range(len(index)//32):
        name, offset, stored, actual = struct.unpack_from('<16sQii',index,ordinal*32)
        if name != target: continue
        pkg = hed.with_suffix('.pkg')
        assert 0 <= offset <= pkg.stat().st_size and 16 <= stored <= pkg.stat().st_size-offset
        with pkg.open('rb') as stream:
            stream.seek(offset); seed=stream.read(16)
            raw, remasters, mode, date=struct.unpack('<iiii',seed)
            assert 0 < raw < 16*1024*1024 and 0 <= remasters <= 65536
            size=mode if mode>0 and raw>16 else raw
            assert 16+48*remasters+size <= stored
            stream.seek(offset+16+48*remasters); packed=stream.read(size)
        decoded=transform(packed,seed) if raw>16 and mode>=-1 else packed
        if raw>16 and mode>0: decoded=zlib.decompress(decoded)
        assert len(decoded)==raw
        count=struct.unpack_from('<I',decoded,4)[0]
        assert 8+96*count <= len(decoded)
        rows=[]
        for i in range(count):
            row=decoded[8+96*i:8+96*(i+1)]
            character=struct.unpack_from('<H',row,76)[0]
            if character in (1,4,14):
                rows.append(dict(ordinal=i, objectId=struct.unpack_from('<I',row)[0],
                    model=row[8:40].split(b'\0')[0].decode('ascii'), characterId=character,
                    form=struct.unpack_from('<b',row,87)[0], weaponGroup=struct.unpack_from('<H',row,78)[0]))
        loose=args.game_root/'Modding/openkh/data/kh2/00objentry.bin'
        assets.append(dict(hed=str(hed), hedSha256=digest(hed), ordinal=ordinal, pkg=str(pkg), offset=offset,
            decodedSha256=hashlib.sha256(decoded).hexdigest(), rows=rows,
            looseExactMatch=(decoded==loose.read_bytes()) if loose.exists() else None))
assert assets
report=dict(binary=str(exe), binarySha256=evidence['inputSha256'],
    allOriginalBytesMatch=True, functionCount=len(validated), instructionCount=sum(x['instructions'] for x in validated),
    byteCount=sum(x['bytes'] for x in validated), functions=validated,
    assetTransformReference='reference/OpenKh.Egs_EgsEncryption.cs', assetTransformReferenceSha256=digest(reference), assets=assets)
(HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(f"Verified {len(validated)} complete bodies, {report['instructionCount']} instructions, {report['byteCount']} original PE bytes; {len(assets)} retail object table(s).")
