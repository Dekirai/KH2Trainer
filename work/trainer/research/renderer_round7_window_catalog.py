"""Reproduce the scoped window-control catalog. This does not alter the merged catalog."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
level='Full native ASM, exact original PE bytes and isolated original-body/lifecycle tests. Live graphics validation is pending.'
def entry(slot,id,name,description,kind,lo,hi,unit,finding):
    return dict(Id='window.'+id,Category='Window and Resolution',Name=name,Description=description,Kind=kind,
        CommandId=1000+slot if kind=='Action' else 0,ValueSlot=-1 if kind=='Action' else slot,CapabilitySlot=slot,
        Minimum=lo,Maximum=hi,DefaultValue=0,Step=1,Unit=unit,RequiresScene=False,ChangesProgression=False,CanSaveInProfile=False,
        RestoreBehavior=('Completed requests remain applied after disconnect. Later game settings or window changes can replace them.' if kind=='Action' else
                         'Read-only snapshot. No effect is applied or restored. All six fields are omitted if the renderer/window lease, synchronization or native state is invalid.'),
        Evidence=[dict(Address='0x140124FE0 / 0x140119E90 / 0x140123020 / 0x140117FD0',Finding=finding,Level=level)])
items=[]
x=entry(431,'resolution','Set windowed resolution','Queue a normal window with whole-pixel dimensions. The native setter fits the rectangle to 16:9; desktop and renderer heap limits can reduce the actual size. Wait for an existing resize before issuing another request.','Action',0,1,'',
        'Mode 0 copies two float32 dimensions under GX+31432 with native float32 fit and integer truncation. The normal render frame later performs fence/rebuild/window work.')
x['Arguments']=[dict(Name='Width (whole pixels)',Minimum=640,Maximum=7680,DefaultValue=1920),dict(Name='Height (whole pixels)',Minimum=360,Maximum=4320,DefaultValue=1080)]
items.append(x)
items.append(entry(432,'maximize','Maximize game window','Queue native maximized window mode. This exits exclusive fullscreen through the normal game resize path; it does not select or enumerate a new fullscreen mode.','Action',0,1,'',
    'Mode 2 of 124FE0 leaves the request dimensions unchanged, sets native mode 2/fullscreen false, and marks a change by comparison.123020 later uses ShowWindow(3).'))
for slot,id,name,description in [(433,'actual_width','Actual render width','Current native render width after any completed resource resize; the command acknowledgement alone does not establish this result.'),
    (434,'actual_height','Actual render height','Current native render height after any completed resource resize; desktop/heap limits can make it smaller than the requested rectangle.')]:
    items.append(entry(slot,id,name,description,'ReadOnly',1,16384,'px','GX+8/+12 are copied under the presentation mutex. Bounds 1..16384 are an explicit diagnostic policy.'))
x=entry(435,'native_mode','Native active window mode','Mode 0 windowed, 1 exclusive fullscreen, 2 maximized. This is the consumed native mode field, not a separate OS-window or successful fullscreen-transition probe.','ReadOnly',0,2,'',
    '119E90 copies request mode +1028 to active1048; later native window/resource work may still fail or be superseded. Only integer 0..2 is published.')
x['Choices']=[dict(Label='Windowed',Value=0),dict(Label='Exclusive fullscreen',Value=1),dict(Label='Maximized',Value=2)]
items.append(x)
x=entry(436,'pending','Window change pending or blocked','1 means a pending/active dirty request, positive native retry, resource transition, or native size-handler suppression.0 means these fields are idle; it does not prove that a particular prior request completed successfully.','ReadOnly',0,1,'',
    'Under resize CS reads +1024,1044,1040,1072 and1064. Invalid flags/countdown/modes/dimensions suppress the full six-value snapshot. A busy CS is unavailable, not idle.')
x['Choices']=[dict(Label='Idle',Value=0),dict(Label='Pending or blocked',Value=1)]
items.append(x)
for slot,id,name,description in [(437,'requested_width','Stored request width','Last stored native request width after 16:9 fitting. Maximization preserves this field, so it is not the maximized client width.'),
    (438,'requested_height','Stored request height','Last stored native request height after 16:9 fitting. A later native request can replace it; no trainer ownership token exists.')]:
    items.append(entry(slot,id,name,description,'ReadOnly',1,16384,'px','GX+1032/+1036 are read under resize CS. Native mode 0 writes the fitted integer pair; mode 2 preserves it.'))
(HERE/'window_display_features.json').write_text(json.dumps(items,indent=2)+'\n',encoding='utf-8')
print('Wrote eight window features, slots431..438; actions431/432; profiles disabled.')
