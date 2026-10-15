"""Read-only compatibility check against the unmodified coverage parser.

--snapshot was used once before the bounded transport-format amendment.
"""
import argparse,copy,hashlib,importlib.util,json,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
PARSER=ROOT/'scripts/update-analysis-coverage.py'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
def digest(j):return sha(json.dumps(j,sort_keys=True,separators=(',',':')).encode())
def dump(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def need(x,s):
 if not x:raise AssertionError(s)
spec=importlib.util.spec_from_file_location('unchanged_coverage_parser',PARSER);parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
def refs(report):return [r for c in report['claims'] for r in c['evidence']]
def inspect(report,evidence):
 statuses=Counter(parser.resolve_reference(HERE/'report.json',r)['status'] for r in refs(report))
 rows=[];compare=parser.pe_comparer(parser.DEFAULT_BINARY)
 for f in evidence['functions']:
  ok,addrs,reason=parser.body_assembly(f);spans=parser.original_spans(f)
  rows.append(dict(addr=f['addr'],completeASM=ok,reason=reason,originalByteCount=sum(len(b) for a,b in spans),allOriginalBytesMatch=bool(spans) and all(compare(a,b) for a,b in spans)))
 return dict(referenceStatuses=dict(statuses),referenceCount=len(refs(report)),functions=rows)
def run():
 before=load(HERE/'integration-before.json');report=load(HERE/'report.json');evidence=load(HERE/'evidence.json')
 need(sha(PARSER.read_bytes())==before['parserSha256'],'parser unchanged')
 old=json.loads(before['reportJson']);changed=[]
 for c in old['claims']:
  for k,r in enumerate(c['evidence']):
   if r=='evidence.json#anchors' or r.startswith('model-results.json#'):
    c['evidence'][k]=r.partition('#')[0];changed.append(dict(address=c['address'],before=r,after=c['evidence'][k]))
 need(old==report and len(changed)==34,'only34 unsupported reference fragments changed')
 need(load(HERE/'provenance.json')['capturePins']==before['provenance']['capturePins'],'original capture pins unchanged')
 top={k:v for k,v in evidence.items() if k!='functions'};need(digest(top)==before['evidenceWithoutFunctionsDigest'],'nonfunction evidence unchanged')
 for f in evidence['functions']:
  core={k:v for k,v in f.items() if k not in ['disassembly','pages','pseudocode','sourceMetadata']};core['originalBytes']=bytes.fromhex(core['originalBytes']).hex()
  need(digest(core)==before['functionDigests'][f['addr']],'original evidence fields preserved '+f['addr'])
 after=inspect(report,evidence);need(after['referenceStatuses']=={'exists':after['referenceCount']},'all report references resolve')
 need(all(x['completeASM'] and x['allOriginalBytesMatch'] for x in after['functions']),'full parser ASM+PE')
 need(sum(x['originalByteCount'] for x in after['functions'])==13520,'all captured bytes retained')
 # Execute only module definitions with the planned docs location; build/main
 # are not called and no files are created in docs.
 import model
 ns={'__file__':str(ROOT/'docs/research/audio-bank-retirement-20261011/verify.py'),'__name__':'portable_root_probe'}
 exec(compile((HERE/'verify.py').read_text(encoding='utf-8'),'portable-root-probe','exec'),ns)
 need(ns['ROOT']==ROOT,'repository root found from docs depth')
 return dict(status='PASS',parserSha256=before['parserSha256'],before=before['parserResult'],after=after,changedReferences=changed,semanticClaimFieldsUnchanged=True,oldEvidenceCoreFieldsPreserved=True,portableDocsRootProbe=True,originalCapturePinsUnchanged=True,limits='Calls only existing parser helpers; no coverage regeneration, parser mutation, native execution, product or docs writes.')
def main():
 p=argparse.ArgumentParser();p.add_argument('--snapshot',action='store_true');p.add_argument('--write',action='store_true');a=p.parse_args()
 if a.snapshot:
  need(not (HERE/'integration-before.json').exists(),'snapshot exists')
  report=load(HERE/'report.json');e=load(HERE/'evidence.json')
  dump(HERE/'integration-before.json',dict(parserSha256=sha(PARSER.read_bytes()),manifest=load(HERE/'manifest.json'),manifestSha256=sha((HERE/'manifest.json').read_bytes()),reportJson=json.dumps(report),provenance=load(HERE/'provenance.json'),evidenceSha256=sha((HERE/'evidence.json').read_bytes()),evidenceWithoutFunctionsDigest=digest({k:v for k,v in e.items() if k!='functions'}),functionDigests={f['addr']:digest(f) for f in e['functions']},parserResult=inspect(report,e)))
  print('saved original integration state');return
 j=run()
 if a.write:dump(HERE/'integration-check.json',j)
 else:need(load(HERE/'integration-check.json')==j,'reproducible integration check')
 print(json.dumps({k:v for k,v in j.items() if k not in ['before','after','changedReferences']}));print('references',j['before']['referenceStatuses'],'->',j['after']['referenceStatuses'])
if __name__=='__main__':main()
