"""Normalize six captured bodies without changing recorded ASM metadata or code."""
import argparse, hashlib, json, runpy
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'src/KH2Trainer.Core').is_dir())
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
capture_name = 'docs/research/audio-observation-design-20261011/capture.json'
capture = ROOT / capture_name
if not capture.is_file():
    capture = ROOT / 'artifacts/audio-observation-design-20261011/capture.json'
assert sha(capture) == 'ae5c844019706c50736445126a93f3368c75ce4e3612026846b8286d01925455'
c = load(capture)
coverage = ROOT / 'scripts/update-analysis-coverage.py'
parser = runpy.run_path(str(coverage))  # Imports helpers; never calls main/run.
compare = parser['pe_comparer'](parser['DEFAULT_BINARY'])
assert compare is not None
captured = {int(x['addr'], 0): bytes(int(t, 16) for t in x['data'].split()) for x in c['bytes']['result']}
decoder = Cs(CS_ARCH_X86, CS_MODE_64)
rows = []
instructions = 0
for f in c['disassembly']:
    address = int(f['addr'], 0)
    blob = captured[address]
    assert len(blob) == f['size'] and compare(address, blob)
    row = dict(addr=hex(address), size=f['size'], disassembly=f['asm'],
               originalBytes=blob.hex(' '), sha256=hashlib.sha256(blob).hexdigest(),
               sourceCapture=capture_name)
    # Keep the entire original cursor/count/address object. No completion
    # flags or missing pagination metadata are synthesized by normalization.
    complete, addresses, reason = parser['body_assembly'](row)
    assert complete, (row['addr'], reason)
    decoded = list(decoder.disasm(blob, address))
    assert sum(i.size for i in decoded) == f['size']
    assert [i.address for i in decoded] == addresses
    spans = parser['original_spans'](row)
    assert spans == [(address, blob)] and all(compare(a, b) for a, b in spans)
    instructions += len(decoded)
    rows.append(row)
assert len(rows) == 6 and instructions == 165 and sum(r['size'] for r in rows) == 849
report = load(HERE / 'report.json')
assert {x['addr'] for x in report['claims']} == {x['addr'] for x in rows}
for claim in report['claims']:
    assert claim['Evidence'][0] == f"evidence.json#functions[addr={claim['addr']}]"
    assert next(r for r in rows if r['addr'] == claim['addr'])['sha256'] == claim['originalBodySha256']
evidence = dict(schema=1, Domain='native', originalSha256=parser['TARGET_SHA'], imageBase=hex(parser['BASE']),
                sourceCapture=capture_name, sourceCaptureSha256=sha(capture), functions=rows,
                normalization='Original disassembly aggregate objects and byte spans retained; no metadata inferred.')
blob = (json.dumps(evidence, indent=2) + '\n').encode()
receipt = dict(success=True, functions=6, instructions=165, originalBodyBytes=849,
               unchangedOriginalCaptureSha256=sha(capture), evidenceSha256=hashlib.sha256(blob).hexdigest(),
               coverageParser='scripts/update-analysis-coverage.py', coverageParserSha256=sha(coverage),
               checks=['Each original byte span equals the identified retail PE.',
                       'Existing body_assembly accepts all six original completion metadata objects.',
                       'Existing original_spans parses the exact original bytes for all six functions.',
                       'Independent full Capstone decode matches every original instruction address.',
                       'Every report claim addresses the matching normalized function and original body hash.'])
args = argparse.ArgumentParser()
args.add_argument('--check', action='store_true')
checking = args.parse_args().check
for path, content in [(HERE / 'evidence.json', blob),
                      (HERE / 'evidence-verification.json', (json.dumps(receipt, indent=2) + '\n').encode())]:
    if checking:
        assert path.read_bytes() == content, path
    else:
        path.write_bytes(content)
print(json.dumps(dict(success=True, functions=6, instructions=165, originalBodyBytes=849,
                     evidenceSha256=receipt['evidenceSha256'])))
