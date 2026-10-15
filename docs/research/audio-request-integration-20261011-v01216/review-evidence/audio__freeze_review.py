from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source_names=['src/KH2Trainer.Bridge/AudioRequestFeatures.inl','src/KH2Trainer.Bridge/AudioRequestSignatures.h','src/KH2Trainer.Bridge/TrainerBridge.cpp','src/KH2Trainer.Bridge/DevToolsProtocol.h','src/KH2Trainer/Data/features.json','src/KH2Trainer/ViewModels/FeatureViewModel.cs','src/KH2Trainer/ViewModels/Navigation.cs','src/KH2Trainer/Infrastructure/Observable.cs','src/KH2Trainer.Core/Models.cs','src/KH2Trainer.Core/ProfileStore.cs','src/KH2Trainer.Core/BridgeProtocol.cs','tests/KH2Trainer.Bridge.Tests/AudioRequestGuardTests.cpp','tests/KH2Trainer.Bridge.Tests/PlayerBridgeTests.cpp','tests/KH2Trainer.Bridge.Tests/run-tests.ps1','tests/KH2Trainer.Core.Tests/AudioMotionCatalogTests.cs','tests/KH2Trainer.UiTests/AudioRequestUiChecks.cs','tests/KH2Trainer.UiTests/Program.cs','src/KH2Trainer/Themes/FeatureTemplates.xaml','src/KH2Trainer/KH2Trainer.csproj']
review_names=['review_design.py','design-review.json','production_route_review.cpp','run_production_review.ps1','production-route.log','production_route_review.exe','ManagedReview.csproj','ManagedReview.cs','managed-build.log','managed-review.json','author-tests/native-AudioRequestGuardTests.txt','report.txt','freeze_review.py']
design=json.loads((H/'design-review.json').read_text())
managed=json.loads((H/'managed-review.json').read_text())
assert design['checks']>=13153 and managed['checks']==89
assert '22380 checks, 0 failures, 15 actual TrainerFrame calls; zero test defines.' in (H/'production-route.log').read_text(encoding='utf-8-sig')
assert '21097 checks, 0 failures' in (H/'author-tests/native-AudioRequestGuardTests.txt').read_text(encoding='utf-8-sig')
impl=R/'artifacts/audio-request-implementation-20261011/manifest.json'
assert impl.exists(),'implementation manifest not frozen yet'
for name,pin in json.loads(impl.read_text(encoding='utf-8-sig'))['files'].items():
 p=impl.parent/name
 assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],name
for name,pin in json.loads((impl.parent/'implementation.json').read_text(encoding='utf-8-sig'))['sourcePins'].items():
 assert sha(R/name)==pin['sha256'],name
assert sha(impl)=='bb7d29b1d871755196f6adcee558f63117db8e3f2b3bf0a13ba51261fe636045'
ui=R/'artifacts/audio-request-ui-20261011-final'
ui_report=json.loads((ui/'report.json').read_text(encoding='utf-8-sig'))
assert ui_report['audioRequests']['success'] and ui_report['audioRequests']['checks']==49 and ui_report['windowCount']==0
ui_pins={'report.json':sha(ui/'report.json')}
for name in ui_report['audioRequests']['renders']:
 ui_pins['AudioRequests/'+name]=sha(ui/'AudioRequests'/name)
report={'status':'ACCEPTED_BOUNDED_AUDIO_SCALAR_IMPLEMENTATION','openBlockers':[],
 'designManifestSha256':design['designManifestSha256'],'implementationManifestSha256':sha(impl),
 'originalSha256':design['originalSha256'],'checks':{'independentPEAndBranchChecks':design['checks'],'nativeBranchModelCases':4212,'independentProductionFixture':22380,'actualTrainerFrameCalls':15,'independentManagedFixture':89,'authorTargetedSuiteRerun':21097,'rootUiChecksReviewed':49},
 'rootUiArtifactPins':ui_pins,'visuallyInspectedRootRenders':['AudioRequests/audio-requests-0.png','AudioRequests/audio-requests-7.png'],
 'sourcePins':{n:sha(R/n) for n in source_names},'reviewPins':{n:sha(H/n) for n in review_names},
 'limitations':['No atomic snapshot, complete writer census, pool consistency or playback guarantee.','Synthetic only; no game/GUI/attach/injection/save/original writes.','Actual native TrainerFrame compiled and executed without test defines; original Update and successful OnFrame UI path not executed.','Actual managed source logic checked; final package and live behavior outside scope.']}
(H/'review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'reviewSha256':sha(H/'review.json'),'implementationManifestSha256':sha(impl),'status':report['status']}))
