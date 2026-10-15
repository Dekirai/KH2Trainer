"""Verify the narrow upper-study transport amendment with original parser helpers."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
from collections import Counter
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
PARSER=ROOT/'scripts/update-analysis-coverage.py'
def load(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(j):return sha(json.dumps(j,sort_keys=True,separators=(',',':')).encode())
def dump(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def need(ok,s):
 if not ok:raise AssertionError(s)
spec=importlib.util.spec_from_file_location('coverage_original',PARSER);parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
def inspect(report,evidence,deps):
 refs=[r for c in report['claims'] for r in c['evidence']]
 status=Counter(parser.resolve_reference(HERE/'report.json',r)['status'] for r in refs)
 compare=parser.pe_comparer(parser.DEFAULT_BINARY);rows=[]
 for label,fs in [('fresh',evidence['functions']),('reused',deps['functions'])]:
  for f in fs:
   ok,addrs,reason=parser.body_assembly(f);spans=parser.original_spans(f)
   rows.append(dict(addr=f['addr'],kind=label,completeASM=ok,reason=reason,originalByteCount=sum(len(b) for a,b in spans),allOriginalBytesMatch=bool(spans) and all(compare(a,b) for a,b in spans)))
 return dict(referenceCount=len(refs),referenceStatuses=dict(status),bodies=rows)
def run():
 before=load(HERE/'integration-before.json');report=load(HERE/'report.json');e=load(HERE/'evidence.json');d=load(HERE/'dependencies.json')
 need(sha(PARSER.read_bytes())==before['parserSha256'],'parser unmodified')
 old=json.loads(before['reportJson']);changes=[]
 for c in old['claims']:
  for k,r in enumerate(c['evidence']):
   if r.startswith('evidence.json#dependencies['):
    new=r.replace('evidence.json#dependencies[','dependencies.json#functions[',1);c['evidence'][k]=new;changes.append(dict(before=r,after=new,address=c['address']))
 need(old==report,'only dependency reference selectors changed')
 need(digest({k:v for k,v in e.items() if k not in ['functions','dependencies']})==before['evidenceMetadataDigest'],'evidence metadata unchanged')
 for bucket in ['functions','dependencies']:
  for f in e[bucket]:
   core={k:v for k,v in f.items() if k not in ['disassembly','pages','pseudocode','sourceMetadata']};core['originalBytes']=bytes.fromhex(core['originalBytes']).hex()
   need(digest(core)==before['evidenceDigests'][bucket][f['addr']],'old evidence core unchanged')
 for f in d['functions']:
  core={k:v for k,v in f.items() if k not in ['disassembly','pages','pseudocode','sourceMetadata']};core['originalBytes']=bytes.fromhex(core['originalBytes']).hex()
  need(digest(core)==before['dependencyDigests'][f['addr']],'old dependency body unchanged')
 for n in ['capture.json','capture-2.json','model.py','model-results.json','anchors.json','report.txt']:
  need(sha((HERE/n).read_bytes())==before['manifest']['files'][n]['sha256'],'unchanged semantics/capture '+n)
 after=inspect(report,e,d);need(after['referenceStatuses']=={'exists':after['referenceCount']},'all references resolve')
 need(all(x['completeASM'] and x['allOriginalBytesMatch'] for x in after['bodies']),'all parser bodies ASM+PE')
 need(len(after['bodies'])==35,'19 fresh+16 reused bodies')
 ns={'__file__':str(ROOT/'docs/research/voice-resource-teardown-20261011/verify.py'),'__name__':'portable_root_probe'}
 exec(compile((HERE/'verify.py').read_text(encoding='utf-8'),'portable-root-probe','exec'),ns);need(ns['ROOT']==ROOT,'root from docs depth')
 return dict(status='PASS',parserSha256=before['parserSha256'],before=before['parserResult'],after=after,changedReferences=changes,semanticClaimsUnchanged=True,evidenceCorePreserved=True,capturesModelsAnchorsReportTextUnchanged=True,portableDocsRootProbe=True,limits='Only original parser helpers; no parser/coverage/product/docs changes or native execution. Reference and transport validation adds no lifetime guarantee.')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--snapshot',action='store_true');ap.add_argument('--write',action='store_true');a=ap.parse_args()
 if a.snapshot:
  need(not (HERE/'integration-before.json').exists(),'snapshot already exists')
  r=load(HERE/'report.json');e=load(HERE/'evidence.json');d=load(HERE/'dependencies.json')
  j=dict(parserSha256=sha(PARSER.read_bytes()),manifest=load(HERE/'manifest.json'),manifestSha256=sha((HERE/'manifest.json').read_bytes()),reportJson=json.dumps(r),provenance=load(HERE/'provenance.json'),evidenceSha256=sha((HERE/'evidence.json').read_bytes()),evidenceMetadataDigest=digest({k:v for k,v in e.items() if k not in ['functions','dependencies']}),evidenceDigests={k:{f['addr']:digest(f) for f in e[k]} for k in ['functions','dependencies']},dependencyDigests={f['addr']:digest(f) for f in d['functions']},parserResult=inspect(r,e,d))
  dump(HERE/'integration-before.json',j);print('saved original state');return
 j=run()
 if a.write:dump(HERE/'integration-check.json',j)
 else:need(load(HERE/'integration-check.json')==j,'reproducible integration check')
 print('PASS',j['before']['referenceStatuses'],'->',j['after']['referenceStatuses'],'35 bodies')
if __name__=='__main__':main()
