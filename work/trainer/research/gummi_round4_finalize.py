import json, hashlib
from pathlib import Path

R=Path('work/trainer/research')
evidence=json.loads((R/'gummi_round4_evidence.json').read_text('utf-8'))
audit={r['address'].lower():r for r in map(json.loads,Path('work/trainer/audit/function_status.jsonl').read_text('utf-8').splitlines())}
defs=json.loads((R/'gummi_round4_claims_draft.json').read_text('utf-8'))
claims=[]
for short,finding,limitations in defs:
    addr='0x140'+short
    assert addr in evidence['functions'],addr
    old=audit.get(addr.lower(),{})
    claims.append({'Address':addr,'Finding':finding,'Evidence':['work/trainer/research/gummi_round4_evidence.json#/functions/'+addr], 'Limitations':limitations+' Static analysis; no live execution in this round.', 'PriorAuditTier':old.get('evidence_tier'), 'PriorAuditClaims':old.get('claims',[])})
owner=json.loads((R/'gummi_round4_owner_evidence.json').read_text('utf-8'))
extra=[
('14F770','Allocates a152-byte task, stores callback+0, manager+88, group+96, priority+100, cleanup+104 and fiber+112, then inserts it in the manager head16/tail24 doubly linked list using next120/previous128 in ascending priority order.','Allocation and list insertion are engine operations; trainer code only validates the current list.'),
('14F680','Unlinks a task and zeroes its next/previous links before invoking cleanup+104, then frees the task and optional fiber through its owning manager.','This ordering makes the current linked task a useful ENEMY_SHOT lifetime witness; a cached task address is insufficient.'),
('14FA60','Manager destruction traverses linked tasks, unlinks each before cleanup, destroys optional fibers, frees tasks and finally frees the manager.','The Gummi module scheduler and heap identity still must be validated before reading the list.'),
('14FD60','Scheduler dispatch sets manager+32 to the current task, invokes direct callbacks or fibers, then clears+32 and retires callbacks that became null.','The proposed trainer clear requires manager+32==0 and executes after the native outer update on the game thread.'),
('1E1FA0','Gummi allocation delegates to virtual slot+8 on heap globalAE94F0, matching the allocation path used by the ENEMY_SHOT pool initializer.','A raw readable pointer alone is not a proof of a live allocation.'),
('1E2030','Gummi free delegates to virtual slot+16 on the same heap globalAE94F0.','Pool pointers must not be reused across heap or module replacement.'),
('1FA7E0','Main-ship collision refreshes native geometry and tests its two indexed geometry arrays against an incoming shape, returning after the first collision.','This read/update path assumes valid native geometry counts and arrays; it is not a proposed trainer call.'),
('1FA8D0','Special ship-part collision selects only part IDs599/600, supplies radii20/30 in XMM2 to the shape builder and tests them against the incoming shape.','Other part IDs contribute no positive radius in this path. No claim of general shield invulnerability is made.')]
owner_count=0
for short,finding,limitations in extra:
    addr='0x140'+short
    idx=next(i for i,f in enumerate(owner['functions']) if f['addr'].lower()==addr.lower())
    f=owner['functions'][idx]
    lines=[line for page in f['pages'] for line in page['asm']['lines']]
    assert len(lines)==f['pages'][0]['total_instructions']
    assert all(page['asm']['start_ea'].lower()==addr.lower() for page in f['pages'])
    assert sum(p['line_count'] for p in f['pseudocode'])==f['pseudocode'][0]['total_lines']
    assert not any(p.get('truncated',False) for p in f['pseudocode'])
    owner_count+=len(lines)
    old=audit.get(addr.lower(),{})
    claims.append({'Address':addr,'Finding':finding,'Evidence':[f'work/trainer/research/gummi_round4_owner_evidence.json#/functions/{idx}'], 'Limitations':limitations+' Static analysis; no live execution in this round.', 'PriorAuditTier':old.get('evidence_tier'), 'PriorAuditClaims':old.get('claims',[])})
summary=dict(evidence['validation'])
summary.update({'supplement_functions':len(extra),'supplement_asm_instructions':owner_count,'combined_functions':len(evidence['functions'])+len(extra),'combined_asm_instructions':evidence['validation']['asm_instruction_count']+owner_count,'note':'Initial75 complete bodies were captured before a local health-readiness mismatch. Root then reopened the same annotated IDB with real auto_wait and captured8 supplemental owner/collision functions. All actual line counts and start addresses were checked independently. No new worker was started by this subagent.'})
report={'title':'Gummi round4: enemy shots, collision and Drain ownership', 'status':'Source/tests/catalog/research frozen; slots360/361 implemented;208 own synthetic checks pass. Root independently reviewed source and found no blocker. Common integration remains root-owned; no live tests.', 'original_path':evidence['original_path'], 'original_sha256':evidence['original_sha256'], 'image_base':evidence['imagebase'], 'evidence_summary':summary, 'claims':claims}
(R/'gummi_round4_deep.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n','utf-8')

# Original-file bytes, not a process read or IDB mutation. Lengths are the
# previously exported IDA function boundaries and are recorded explicitly.
inventory=json.loads(Path('work/pe/inventory.json').read_text('utf-8'))
exe=Path(inventory['path']).read_bytes()
assert hashlib.sha256(exe).hexdigest().lower()==evidence['original_sha256'].lower()
pins=[]
for short in ['21E830','23E020','23DAC0','21F1F0']:
    rva=int(short,16); row=audit['0x140'+short.lower()]; size=row['size']
    for sec in inventory['sections']:
        start=int(sec['rva'],16); raw=int(sec['raw'],16)
        if start<=rva and rva+size<=start+sec['size']:
            data=exe[raw+rva-start:raw+rva-start+size]
            assert len(data)==size
            pins.append({'Address':'0x140'+short, 'RVA':hex(rva), 'length':size, 'source':'Original PE; boundary from work/trainer/audit/function_status.jsonl', 'hex':data.hex(' '), 'sha256':hashlib.sha256(data).hexdigest()})
            break
    else: raise RuntimeError(short)
(R/'gummi_round4_code_bytes.json').write_text(json.dumps({'original_path':inventory['path'],'original_sha256':hashlib.sha256(exe).hexdigest(), 'functions':pins},indent=2)+'\n','utf-8')
print(json.dumps({'claims':len(claims),'functions':len(evidence['functions']),'asm':sum(len(v['asm']['lines']) for v in evidence['functions'].values()),'pins':[(p['RVA'],p['length']) for p in pins]}))
