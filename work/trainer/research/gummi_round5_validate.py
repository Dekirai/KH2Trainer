"""Offline integrity checks for round5 static evidence; no game/API execution."""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / 'work/trainer/research'
report_path = RESEARCH / 'gummi_round5_deep.json'
report = json.loads(report_path.read_text(encoding='utf-8-sig'))
inv = json.loads((ROOT / 'work/pe/inventory.json').read_text(encoding='utf-8-sig'))
original = Path(report['original_path']).read_bytes()
actual_hash = hashlib.sha256(original).hexdigest().upper()
assert actual_hash == report['original_sha256']
base = int(inv['imagebase'], 16)

def original_bytes(address, size):
    rva = address - base
    for section in inv['sections']:
        start = int(section['rva'], 16)
        if start <= rva and rva + size <= start + section['size']:
            raw = int(section['raw'], 16) + rva - start
            return original[raw:raw + size]
    raise AssertionError(('unmapped file span', hex(address), size))

def decode(data):
    return bytes(int(x, 16) for x in data.split())

code = json.loads((RESEARCH / 'gummi_round5_original_bytes.json').read_text())
sizes = {int(x['Address'], 16): x['size'] for x in code['functions']}
spans = []
for function in code['functions']:
    start = int(function['Address'], 16)
    offset = 0
    for chunk in function['chunks']:
        assert int(chunk['addr'], 16) == start + offset
        offset += len(decode(chunk['data']))
    assert offset == function['size']
for item in [c for f in code['functions'] for c in f['chunks']] + code['shared_tail']['result']:
    address = int(item['addr'], 16)
    data = decode(item['data'])
    assert data == original_bytes(address, len(data)), hex(address)
    spans.append((address, address + len(data)))

audit_path = ROOT / 'work/trainer/audit/function_status.jsonl'
audit = {int(x['address'], 16): x for x in
         (json.loads(line) for line in audit_path.read_text(encoding='utf-8-sig').splitlines())
         if x['domain'] == 'native'}
functions = {}
bundle = {'session': '5b5ee46c', 'source_idb': report['private_idb'], 'functions': {}}
for path in sorted((RESEARCH / 'gummi_round5_evidence').glob('*.json')):
    obj = json.loads(path.read_text())
    address = int(obj['Address'], 16)
    asm = obj['disassembly']
    pages = asm['pages']
    total = pages[0]['total_instructions']
    offset = 0
    all_lines = []
    for i, page in enumerate(pages):
        assert int(page['asm']['start_ea'], 16) == address
        assert page['total_instructions'] == total
        assert not page['cursor'].get('cancelled', False)
        lines = page['asm']['lines']
        assert len(lines) == page['instruction_count']
        offset += len(lines)
        all_lines += lines
        if i + 1 < len(pages):
            assert page['cursor']['next'] == offset
            assert not page['cursor'].get('done', False)
        else:
            assert page['cursor'].get('done') is True
            assert page['cursor'].get('next') is None
    assert offset == total == asm['joined_line_count'] == asm['total_instructions']
    assert len({int(x['addr'], 16) for x in all_lines}) == offset
    for line in all_lines:
        instruction_address = int(line['addr'], 16)
        assert any(lo <= instruction_address < hi for lo, hi in spans), line
    pc = obj['pseudocode']
    assert not pc.get('error') and not pc.get('truncated')
    assert not pc.get('cursor', {}).get('cancelled')
    assert pc.get('cursor', {}).get('next') is None
    assert pc['line_count'] == pc['total_lines'] == len(pc['code'].splitlines())
    functions[address] = {'Address': hex(address), 'instructions': total,
                          'pseudocode_lines': pc['line_count']}
    bundle['functions'][hex(address)] = {
        'addr': hex(address), 'pages': pages, 'instruction_count': total,
        'total_instructions': total, 'complete': True,
        'cursor': {'done': True, 'next': None, 'cancelled': False},
        'decompile': pc,
        'raw_capture_path': str(path.relative_to(ROOT)).replace('\\', '/'),
        'original_bytes': 'work/trainer/research/gummi_round5_original_bytes.json'}

(RESEARCH / 'gummi_round5_evidence.json').write_text(
    json.dumps(bundle, indent=2) + '\n', encoding='utf-8')

for claim in report['claims']:
    address = int(claim['Address'], 16)
    assert address in functions
    claim['Evidence'] = list(dict.fromkeys(
        p.replace('gummi_round5_code_bytes_all.json', 'gummi_round5_original_bytes.json')
         .replace('gummi_round5_shared_tail_bytes.json', 'gummi_round5_original_bytes.json')
        for p in claim['Evidence']))
    top = 'work/trainer/research/gummi_round5_evidence.json#/functions/' + hex(address)
    if top not in claim['Evidence']:
        claim['Evidence'].insert(0, top)
    for evidence in claim['Evidence']:
        assert (ROOT / evidence.split('#', 1)[0]).is_file(), evidence
    previous = audit.get(address, {})
    claim['PriorAuditTier'] = previous.get('evidence_tier')
    claim['PriorAuditClaims'] = previous.get('claims', [])
assert len(functions) == len(report['claims'])
summary = {
    'function_count': len(functions),
    'dedicated_asm_instruction_count': sum(x['instructions'] for x in functions.values()),
    'pseudocode_line_count': sum(x['pseudocode_lines'] for x in functions.values()),
    'original_code_spans': len(spans),
    'original_code_bytes': sum(hi-lo for lo, hi in spans),
    'all_page_and_joined_counts_match': True,
    'all_instruction_addresses_have_original_bytes': True,
    'all_code_bytes_match_original_exe': True,
    'current_original_sha256': actual_hash,
    'audit_path': str(audit_path.relative_to(ROOT)),
    'audit_sha256_at_comparison': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
    'prior_tier_counts': {str(t): sum(c['PriorAuditTier'] == t for c in report['claims'])
                          for t in sorted(set(c['PriorAuditTier'] for c in report['claims']))},
    'scope': 'Counts concern complete captured bodies and the stated claims, not full semantic coverage of every branch.'
}
report['evidence_summary'] = summary
report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
(RESEARCH / 'gummi_round5_validation.json').write_text(
    json.dumps({'summary': summary, 'functions': list(functions.values())}, indent=2) + '\n',
    encoding='utf-8')
print(json.dumps(summary, indent=2))
