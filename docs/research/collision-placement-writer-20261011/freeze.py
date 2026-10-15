"""Freeze only this study folder after successful reproduction."""
import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
sha=lambda b:hashlib.sha256(b).hexdigest()
provenance=dict(originalExeSha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed',
 captureOperator='/root',captureSource='Existing root IDA session28e14b48; supplied immutable tool-response JSON files',
 localAuthority='Local idb_list did not expose the root handle. No local session was adopted/opened, and no worker was started or restarted.',
 autoAnalysis='No autoanalysis requested or IDB mutation performed; these captures do not prove global analysis completion.',
 interpreterBase=dict(path='docs/research/collision-query-geometry-20261011/machine.py',sha256=sha((R/'docs/research/collision-query-geometry-20261011/machine.py').read_bytes()),
 changes=['MOVABS/DEC/MAXSS','UCOMISS and unordered parity branches','Declared tailcall-stub return handling'],
 limitation='Parity is tracked for floating comparisons; selected JP uses follow UCOMISS. No general integer-parity interpreter claim.'),
 coverageParserSha256=sha((R/'scripts/update-analysis-coverage.py').read_bytes()))
(H/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
files=[]
for p in sorted(H.rglob('*')):
 if p.is_file() and p!=H/'manifest.json':
  b=p.read_bytes();files.append(dict(path=p.relative_to(H).as_posix(),length=len(b),sha256=sha(b)))
m=dict(schema=1,status='frozen-for-independent-review',scope='Bounded local native state/result evidence, no placement approval',files=files)
(H/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
print(len(files),'members',sha((H/'manifest.json').read_bytes()))
