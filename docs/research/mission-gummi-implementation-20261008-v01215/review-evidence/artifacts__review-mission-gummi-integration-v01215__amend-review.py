"""Bounded post-review verifier amendment; no compiled probe reruns."""
import ast,copy,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=ROOT/'artifacts/review-mission-gummi-integration-v01215.json'
initial=HERE/'review-initial.json'
if not initial.exists():initial.write_bytes(receipt.read_bytes())
prior=load(initial);out=load(receipt)
verify=ROOT/'docs/research/mission-gummi-implementation-20261008-v01215/verify.py'
freeze=ROOT/'artifacts/freeze-v01215-integration.py'
tree=ast.parse(verify.read_text());freezeTree=ast.parse(freeze.read_text())
checks=0
def check(ok,label):
 global checks
 checks+=1
 if not ok:raise AssertionError(label)
def assign(tree,name):
 return next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
def expression(node,namespace):return eval(compile(ast.Expression(node),'<actual verifier AST>','eval'),namespace)
expected=ast.literal_eval(assign(tree,'expected_statuses').value)
check(expected=={'review-voice.json':'ACCEPTED_BOUNDED_STATIC_RESEARCH','review-mission.json':'ACCEPTED_BOUNDED_NATIVE_IMPLEMENTATION','review-bank3.json':'ACCEPTED_BOUNDED_STATIC_RESEARCH','review-integration.json':'ACCEPTED_OFFLINE_PRODUCT_INTEGRATION'},'four exact status values')
loop=next(n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [x.id for x in n.target.elts]==['name','review'])
code=compile(ast.Module(body=[loop],type_ignores=[]),'<actual review-loop AST>','exec')
fixture=HERE/'amendment-fixture';study=fixture/'study';study.mkdir(parents=True,exist_ok=True)
specs={
 'review-voice.json':('pins','artifacts/sample-review.py',study/'review-evidence/artifacts__sample-review.py'),
 'review-mission.json':('sourcePins','src/native.cpp',fixture/'src/native.cpp'),
 'review-bank3.json':('sourceHashes','sample.json',fixture/'docs/research/bdx-bank3-extended-20261008/sample.json'),
 'review-integration.json':('sourcePins','src/managed.cs',fixture/'src/managed.cs')}
reviews={}
for name,(field,key,path) in specs.items():
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
 reviews[name]=dict(status=expected[name],blockers=[],success=True)
 reviews[name][field]={key:{'sha256':sha(path)} if name=='review-mission.json' else sha(path)}
def run(candidate):exec(code,dict(reviews=candidate,expected_statuses=expected,ROOT=fixture,HERE=study,sha=sha))
run(reviews);check(True,'all four valid review shapes accepted')
for name,(field,key,path) in specs.items():
 for member,value in [('status','UNKNOWN'),('blockers',['blocking finding']),('success',False)]:
  altered=copy.deepcopy(reviews);altered[name][member]=value
  try:run(altered);rejected=False
  except AssertionError:rejected=True
  check(rejected,('mutated review status rejected',name,member))
 altered=copy.deepcopy(reviews);altered[name][field][key]={'sha256':'0'*64} if name=='review-mission.json' else '0'*64
 try:run(altered);rejected=False
 except AssertionError:rejected=True
 check(rejected,('stale source pin rejected',name))
 original=path.read_bytes();path.write_bytes(original+b'mutated')
 try:run(reviews);rejected=False
 except AssertionError:rejected=True
 finally:path.write_bytes(original)
 check(rejected,('mutated pinned bytes rejected',name))

ownAssertion=next(n for n in tree.body if isinstance(n,ast.Assert) and 'set(own_files)' in ast.unparse(n))
(study/'manifest.json').write_text('{}');(study/'nested').mkdir(exist_ok=True);(study/'nested/manifest.json').write_text('{}')
expectedFiles=expression(ownAssertion.test.comparators[0],dict(HERE=study))
check('nested/manifest.json' in expectedFiles and 'manifest.json' not in expectedFiles,'only exact top-level manifest excluded')
ns=dict(HERE=study,own_files={k:{} for k in expectedFiles})
check(expression(ownAssertion.test,ns),'exact file set accepted')
ns['own_files'].pop('nested/manifest.json');check(not expression(ownAssertion.test,ns),'unlisted nested manifest rejected')

names=assign(freezeTree,'current_names').value
extensions=ast.literal_eval(assign(freezeTree,'extensions').value);excluded=ast.literal_eval(assign(freezeTree,'excluded').value)
current=expression(names,dict(ROOT=ROOT,extensions=extensions,excluded=excluded))
with zipfile.ZipFile(ROOT/'artifacts/packages/KH2_Trainer_v0.12.14/Source.zip') as z:baseline={n for n in z.namelist() if n.startswith(('src/','tests/'))}
new=ast.literal_eval(assign(freezeTree,'new').value)
check(current==baseline|new,'actual freeze source-set expression exactly matches release14 plus two new files')
check("p != OUT / 'manifest.json'" in ast.unparse(freezeTree),'freeze excludes only own root manifest')
for text in ["ui['windowCount'] == 0","ui['bindingErrors'] == 0","ui['missionCounters']['checks'] == 31","ui['featurePages']['features'] == 358","int(core[1]) == 3294","int(core[2]) == 0","arithmetic['failures'] == 0","arithmetic['cases'] == 457368","arithmetic['liveGame'] is False"]:
 check(text in ast.unparse(tree),('explicit evidence bound',text))
for relative in ['artifacts/review-mission-gummi-integration-v01215/probe-result.json','artifacts/review-mission-gummi-integration-v01215/bdx-probe/result.json']:
 check(sha(ROOT/relative)==prior['sourcePins'][relative],('compiled probe receipt unchanged',relative))
changedPins=[]
for name,digest in prior['sourcePins'].items():
 actual=sha(ROOT/name)
 if actual!=digest:changedPins.append(name)
check(changedPins==['docs/research/mission-gummi-implementation-20261008-v01215/verify.py'],('only verifier changed among original pins',changedPins))
amendment=dict(status='ACCEPTED_POST_REVIEW_VERIFICATION_AMENDMENT',checks=checks,initialReviewSha256=sha(initial),changedPriorPins=changedPins,
 reviewedPins={verify.relative_to(ROOT).as_posix():sha(verify),freeze.relative_to(ROOT).as_posix():sha(freeze)},
 retainedCompiledChecks=dict(managed=3840,bdx=13884,rerun=False),
 findings=['Verifier explicitly checks each accepted status and all available source/manifest pins. Copied artifact evidence is resolved within the study package.',
 'Actual extracted review-loop AST rejected unsupported statuses, blockers, false success, stale hashes and mutated file bytes for all four receipt forms.',
 'Actual manifest-set AST rejects an unlisted nested manifest.json. Exact top-level exclusion was requested and corrected in verifier and freeze.',
 'Freeze source-set expression matches filtered current src/tests files to the previous archive plus exactly two new files. Copied review artifact pins remain checked before copying.',
 'Core/UI/arithmetic report constraints are explicit. Completed frozen output and final package execution remain parent work.'],
 scope='Limited static and isolated verifier-AST regression review; no full freeze execution, production changes or compiled-test reruns.')
amend=HERE/'post-review-amendment.json';amend.write_text(json.dumps(amendment,indent=2)+'\n',encoding='utf-8')
out['sourcePins'][verify.relative_to(ROOT).as_posix()]=sha(verify)
for p in [freeze,amend,Path(__file__)]:out['sourcePins'][p.relative_to(ROOT).as_posix()]=sha(p)
out['verificationAmendment']=amendment
receipt.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(success=True,amendmentChecks=checks,receiptSha256=sha(receipt),verifySha256=sha(verify),freezeSha256=sha(freeze))))
