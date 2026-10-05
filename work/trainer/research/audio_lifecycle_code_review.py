"""Record the independent read-only AudioFeatures review and signature check."""
import pathlib,json,hashlib,re
root=pathlib.Path(__file__).resolve().parents[3]
native=root/'trainer/Native/AudioFeatures.inl'
source=native.read_text(encoding='utf-8')
inv=json.loads((root/'work/pe/inventory.json').read_text(encoding='utf-8'))
image=pathlib.Path(inv['path']).read_bytes()
checks=[]
for name,rva in {'ConstructCode':0x79c90,'SetCode':0x7fad0,'DestroyCode':0x7f7e0,'FactoryCode':0x936a0,'BusSetCode':0xa54d0,'XaSetCode':0xa8830,'GenericSetCode':0xc4b80}.items():
    match=re.search(r'constexpr BYTE '+name+r'\[\]=\{([^}]+)\}',source)
    expected=bytes(int(x,16) for x in match[1].split(','))
    sec=next(s for s in inv['sections'] if int(s['rva'],0)<=rva<int(s['rva'],0)+s['size'])
    off=int(sec['raw'],0)+rva-int(sec['rva'],0)
    checks.append({'name':name,'rva':hex(rva),'bytes':len(expected),'matchesOriginalImage':expected==image[off:off+len(expected)]})
assert all(c['matchesOriginalImage'] for c in checks)
def line(text):
    return next(i for i,s in enumerate(source.splitlines(),1) if text in s)
review=[
('ThreadReady','ThreadReady enforces the recorded engine thread, fresh host heartbeat, supported image base and enabled bridge. Existing OnFrame rejects original Update returns other than0 before TrainerFrame. This is the lifetime condition proved by121D90.'),
('bool GraphReady','Driver readiness uses BYTE+52, matching091250. Master child pointer+336 and DWORD count+344 match08D720. Exact native driver/factory and supported master identities are checked.'),
('bool BusReady','ID0 selects master; IDs1..count select list[id-1], matching07FAD0. Bus identity, ID, first DynamicValue stage and setter identity are checked before use. Finite/range checks are conservative, not assumptions that all audible gain is0..1.'),
('bool MakePlan','Slots144/145 target IDs0/1. Effects targets the selected bus2/3 plus4..8; voice targets the complementary bus and applies0.9 only for unswapped softened routing. Saved settings reset reads all four ushort levels at offsets20/22/24/26, including the actual master setting.'),
('bool ApplyPlan','All target buses are preflighted before any gain setter; all temporary controllers are constructed and checked before the first setter. SameGraph rejects root changes. Set uses RCX controller, XMM1 float gain and R8D duration1. Temporary destruction is in finally. A later setter failure is correctly reported as possibly partially applied rather than falsely rolled back.'),
('bool AudioHandle','Action input must be finite0..100. TryEnterCriticalSection returns a retry message if busy; LeaveCriticalSection is guaranteed in finally. No direct config, pause or gain-field writes are made by this module.'),
('void AudioSnapshot','All bus stage reads and snapshot copies occur under the same global Sound CS used by identified native interpolation paths. Individual invalid buses remain unpublished. Group target readout is published only when the selected Effects buses agree.'),
]
result={
 'date':'2026-10-04',
 'scope':'Independent source/ABI/lifetime review of the root draft; no native build, synthetic harness run, product modification or live game operation performed by this reviewer.',
 'source':'trainer/Native/AudioFeatures.inl',
 'sourceSha256':hashlib.sha256(native.read_bytes()).hexdigest(),
 'bridgeSha256':hashlib.sha256((root/'trainer/Native/TrainerBridge.cpp').read_bytes()).hexdigest(),
 'targetSha256':hashlib.sha256(image).hexdigest(),
 'conclusion':'No substantial source defect found in the reviewed version under the documented native post-update lifetime contract.',
 'findings':[],
 'reviewedAreas':[{'line':line(anchor),'assessment':assessment} for anchor,assessment in review],
 'signatureChecks':checks,
 'evidence':['work/trainer/research/audio_lifecycle.json','work/trainer/research/audio_lifecycle_evidence.json','work/trainer/research/audio_lifecycle_settings_evidence.json','work/trainer/research/audio_bus_setter_asm.json'],
 'testRecommendations':[
  'Busy CS and wrong thread/stale heartbeat must yield zero native setter calls.',
  'Invalid final target bus must reject a multi-bus operation before any setter.',
  'Invalid final constructed controller or changed graph must yield zero setters while destroying all constructed controllers.',
  'Exercise all swapped/softened combinations and all four loaded settings, with master different from100 percent.',
  'Gain0 still calls the duration1 setter; never pause/stop or duration0.',
  'Verify ID0 master plus IDs1..8 and exact once-per-target calls for all plans.',
  'Failure after a successful earlier setter must report possible partial application and always release global CS.',
  'Snapshot must not publish an invalid bus or an Effects target when group targets differ.'
 ],
 'limits':[
  'No live listening/game verification and no independent audio harness run were performed here; root owns build/test integration.',
  'Music/Effects/Voice labels describe the analyzed routing groups. Direct English localization labels for those settings fields were not recovered.',
  'An unsupported external mod invoking private audio reset/teardown from another thread is outside the proven call-site contract.',
  'Source hash binds this review; later edits require a delta check.'
 ]
}
dest=root/'work/trainer/research'
(dest/'audio_lifecycle_code_review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
lines=['Independent AudioFeatures review',result['conclusion'],'Source SHA256: '+result['sourceSha256'],'Bridge SHA256: '+result['bridgeSha256'],result['scope'],'']
for x in result['reviewedAreas']: lines.append('Line '+str(x['line'])+': '+x['assessment'])
lines+=['','All seven embedded signatures match the original SHA-bound executable.','','Recommended isolated checks:']+['- '+x for x in result['testRecommendations']]+['','Limits:']+['- '+x for x in result['limits']]
(dest/'audio_lifecycle_code_review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'sourceSha256':result['sourceSha256'],'signatureChecks':len(checks),'findings':0},indent=2))
