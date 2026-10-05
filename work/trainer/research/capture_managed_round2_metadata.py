import hashlib
import json
import pathlib
import re
import struct
import sys

root = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / 'work/pe/deps'))
import dnfile

source = pathlib.Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
data = source.read_bytes()
pe = dnfile.dnPE(data=data)
research = root / 'work/trainer/research'
evidence = []
for name in ('managed_tools_round2_evidence.json', 'managed_tools_round2_codec_evidence.json'):
    evidence.extend(json.loads((research / name).read_text(encoding='utf-8-sig')))
methods = []
fields = []
all_methods = []
for typedef in pe.net.mdtables.TypeDef.rows:
    owner = str(typedef.TypeNamespace) + '.' + str(typedef.TypeName)
    for item in typedef.MethodList:
        method = item.row
        name = str(method.Name)
        row = {'token': hex(0x06000000 + item.row_index), 'owner': owner, 'name': name,
               'rva': method.Rva, 'native': method.ImplFlags.miNative, 'cil': method.ImplFlags.miIL,
               'signatureHex': method.Signature.value.hex()}
        all_methods.append(row)
        for body in evidence:
            display = body['asm']['name']
            expected = '::' + name if owner == '.<Module>' else owner + '::' + name
            if display != expected:
                continue
            assert row['cil'] and row['rva']
            header = pe.get_data(row['rva'], 12)
            if header[0] & 3 == 2:
                header_size, code_size, local_sig, init_locals = 1, header[0] >> 2, 0, False
            else:
                flags, max_stack, code_size, local_sig = struct.unpack('<HHII', header)
                header_size = ((flags >> 12) & 15) * 4
                init_locals = bool(flags & 16)
            code = pe.get_data(row['rva'] + header_size, code_size)
            assert len(code) == code_size
            methods.append({**row, 'idaSyntheticAddress': body['addr'], 'headerBytes': pe.get_data(row['rva'], header_size).hex(),
                            'codeSize': code_size, 'codeSha256': hashlib.sha256(code).hexdigest(),
                            'localSignatureToken': hex(local_sig), 'initLocals': init_locals,
                            'note': 'RVA locates the on-disk CLR method header, not a native callable entrypoint.'})

field_names = set()
for body in evidence:
    for line in body['asm']['lines']:
        if line['instruction'].startswith(('ldsflda ', 'ldsfld ', 'stsfld ')):
            field_names.add(line['instruction'].rsplit(' ', 1)[-1])
for row in pe.net.mdtables.FieldRva.rows:
    name = str(row.Field.row.Name)
    if name not in field_names:
        continue
    raw = pe.get_data(row.Rva, 512)
    value = raw.split(b'\0')[0]
    fields.append({'name': name, 'token': hex(0x04000000 + row.Field.row_index),
                   'rva': hex(row.Rva), 'va': hex(pe.OPTIONAL_HEADER.ImageBase + row.Rva),
                   'asciiBeforeFirstNul': value.decode('ascii', errors='backslashreplace'),
                   'first32BytesHex': raw[:32].hex()})
interesting = [m for m in all_methods if m['native'] and re.search(
    r'TinyTexEntry.encodeImage|TexCommon.EncodePNG|TexCommon.EncodeTGA|ModelScarcher|MotionScarcher|SoundSearcher', m['name'])]
result = {'source': str(source), 'sourceSha256': hashlib.sha256(data).hexdigest(),
          'methodBodies': methods, 'fieldRvas': fields, 'nativeBoundaries': interesting}
assert len(methods) == len(evidence), (len(methods), len(evidence))
(research / 'managed_tools_round2_metadata.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'methodBodies': len(methods), 'fieldRvas': len(fields), 'nativeBoundaries': interesting}, indent=2))
