"""One-time proposal-context capture. Does not overwrite an existing context snapshot."""
import hashlib,json,pathlib,zipfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'src/KH2Trainer.Core').is_dir())
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,obj):
    p=HERE/name
    assert not p.exists(), 'Context already captured: '+name
    p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
paths=['src/KH2Trainer.Bridge/GummiFeatures.inl','src/KH2Trainer.Bridge/GummiExtraFeatures.inl','src/KH2Trainer.Bridge/TrainerBridge.cpp','src/KH2Trainer.Core/BridgeProtocol.cs','src/KH2Trainer/Data/features.json']
zpath=HERE/'context-source.zip';assert not zpath.exists()
with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name in paths:
        zi=zipfile.ZipInfo(name,date_time=(2026,10,11,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;z.writestr(zi,(ROOT/name).read_bytes())
features=json.loads((ROOT/paths[-1]).read_text(encoding='utf-8-sig'))
assert len(features)==361 and max(x['CapabilitySlot'] for x in features)==484
assert not any(x.get('CapabilitySlot')==485 or x.get('ValueSlot')==485 or x.get('CommandId')==1485 for x in features)
save('context.json',{'scope':'Historical v0.12.17 product snapshot for proposal only; no later current-source equality implied','sourceArchive':'context-source.zip','sourceArchiveSha256':sha(zpath.read_bytes()),'files':[{'path':p,'sha256':sha((ROOT/p).read_bytes())} for p in paths],'featureCount':361,'maximumCapability':484,'proposedCapability':485,'proposedCommand':1485,'slotUnusedAtCapture':True,'protocolValues':512})
archive=ROOT/'docs/legacy/KH2_Trainer_v0.11_Source.zip'
expected='35e3cb99435e447af21c321799ad8d50145372827410d9f11bd5eb21289c2d5d';assert sha(archive.read_bytes())==expected
members=['gummi_controls_contract.txt','gummi_controls_deep_evidence.json','gummi_controls_weapon_evidence.json','gummi_controls_code_bytes.json','gummi_extra_independent_review.txt']
with zipfile.ZipFile(archive) as z:
    deps=[{'member':'work/trainer/research/'+n,'sha256':sha(z.read('work/trainer/research/'+n))} for n in members]
save('dependencies.json',{'scope':'Historical unchanged evidence for Gummi ownership/charge/initialization. Not newly executed tests and not new function claims. Fresh bodies and bytes are captured separately in this study.','archive':'docs/legacy/KH2_Trainer_v0.11_Source.zip','sha256':expected,'members':deps})
