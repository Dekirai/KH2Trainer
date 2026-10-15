"""Verify captured native adapter bodies; no native code is executed."""
from pathlib import Path
import argparse, hashlib, json, struct, zipfile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer').is_dir())
parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
def load(name):
    if (HERE / name).is_file(): return json.loads((HERE / name).read_bytes())
    with zipfile.ZipFile(HERE/'raw.zip') as archive: return json.loads(archive.read(name))
sha = lambda data: hashlib.sha256(data).hexdigest()
raw = Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe').read_bytes()
assert sha(raw) == '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
pe = struct.unpack_from('<I', raw, 0x3c)[0]
base = struct.unpack_from('<Q', raw, pe + 24 + 24)[0]
assert base == 0x140000000
table = pe + 24 + struct.unpack_from('<H', raw, pe + 20)[0]
sections = [(raw[table+i*40:table+i*40+8].rstrip(b'\0').decode(), *struct.unpack_from('<IIII', raw, table+i*40+8))
            for i in range(struct.unpack_from('<H', raw, pe+6)[0])]
def original(addr, size):
    for name, virtualsize, va, count, offset in sections:
        if va <= addr-base and addr-base+size <= va+count:
            return raw[offset+addr-base-va:offset+addr-base-va+size]
    raise ValueError(hex(addr))
def section(addr):
    return next(name for name, virtualsize, va, count, offset in sections if va <= addr-base < va+max(virtualsize,count))
xrefs = load('xrefs.json')
assert not xrefs['more'] and xrefs['xref_count'] == len(xrefs['xrefs']) == 43
code = [row for row in xrefs['xrefs'] if row['type'] == 'code']
expected = {int(row['fn']['addr'],16):row for row in code}
assert len(expected) == len(code) == 42
captured = {int(row['addr'],16):bytes(int(b,16) for b in row['data'].split()) for row in load('bytes.json')['result']}
assert set(captured) == set(expected)
inventory = {int(row['address'],16):row for line in (ROOT/'docs/research/coverage/function_status.jsonl').read_text().splitlines()
             if (row:=json.loads(line))['domain']=='native'}
# Canonical encoding after zeroing the CALL rel32 displacement. This represents
# all instructions, including the stack accesses and the incoming RCX overwrite.
canonical = bytes.fromhex('48 83 ec 38 8b 44 24 68 48 8d 8a 10 0c 00 00 45 8b d1 89 44 24 20 4c 8b 4c 24 60 45 8b d8 45 8b c2 41 8b d3 e8 00 00 00 00 48 83 c4 38 c3')
decoder = Cs(CS_ARCH_X86, CS_MODE_64)
records = []
query_names = sorted(path.name for path in HERE.glob('insns-*.json'))
if not query_names:
    with zipfile.ZipFile(HERE/'raw.zip') as archive:
        query_names = sorted(name for name in archive.namelist() if name.startswith('insns-') and name.endswith('.json'))
for query_name in query_names:
    for query in load(query_name)['result']:
        assert query['cursor'] == {'done':True} and not query.get('truncated') and not query.get('error')
        addr = int(query['query']['func'],16)
        assert query['ranges'] == [{'start':hex(addr),'end':hex(addr+46)}]
        data = captured[addr]
        assert len(data) == inventory[addr]['size'] == int(expected[addr]['fn']['size'],16) == 46
        assert data == original(addr,46)
        decoded = list(decoder.disasm(data,addr))
        assert sum(i.size for i in decoded) == 46
        assert query['count'] == query['scanned'] == len(decoded) == len(query['matches']) == 12
        assert [int(row['addr'],16) for row in query['matches']] == [i.address for i in decoded]
        assert [row['disasm'].split()[0].replace('retn','ret') for row in query['matches']] == [i.mnemonic for i in decoded]
        assert data[:37]+b'\0'*4+data[41:] == canonical
        target = addr+41+struct.unpack_from('<i',data,37)[0]
        assert target == base+0x3D25D0 and int(expected[addr]['addr'],16) == addr+36
        records.append({'addr':hex(addr),'size':46,'name':expected[addr]['fn']['name'],
            'sha256':sha(data),'originalBytes':data.hex(),'rawQuery':query_name,
            'callAddress':hex(addr+36),'target':hex(target),
            'instructions':[{'addr':hex(i.address),'bytes':i.bytes.hex(),'instruction':i.mnemonic+' '+i.op_str} for i in decoded],
            'idaInstructions':query['matches']})
assert len(records) == len({r['addr'] for r in records}) == 42
records.sort(key=lambda row:int(row['addr'],16))
noncode = [{'addr':row['addr'],'type':row['type'],'section':section(int(row['addr'],16))}
           for row in xrefs['xrefs'] if row['type'] != 'code']
assert noncode == [{'addr':'0x142bb8b50','type':'data','section':'.pdata'}]
report = {'status':'PASS','originalSha256':sha(raw),'scope':'Complete selected original-PE body, IDA-head and Capstone comparison. Exact relative-call normalization; no native execution or runtime type/lifetime proof.',
    'functions':records,'functionCount':42,'instructions':504,'bodyBytes':1932,
    'normalizedEncoding':canonical.hex(),'normalizedSha256':sha(canonical),
    'noncodeXrefs':noncode,'idaSession':'9d62332c','autoAnalysisCompleteEstablished':False}
data = (json.dumps(report,indent=2)+'\n').encode()
if args.check: assert (HERE/'verification.json').read_bytes() == data
else: (HERE/'verification.json').write_bytes(data)
print(json.dumps({key:report[key] for key in ['status','functionCount','instructions','bodyBytes','normalizedSha256','noncodeXrefs']}))
