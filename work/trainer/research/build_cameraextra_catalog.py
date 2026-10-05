from pathlib import Path
import json
root=Path(__file__).resolve().parents[3]
specs=[
 (240,'camera.roll','Camera roll','Number',-180,180,0,1,'degrees','Set the additional native roll angle of the held free camera. Enable free camera first. The setting ends when camera ownership or the scene changes.','0x14019D3D0 / 0x14019CBA0 / 0x1401AADC0','Camera+120 is an additional roll angle in radians, applied to the view after eye/target/up.'),
 (241,'camera.owner','Camera owner','ReadOnly',-2147483648,2147483647,0,1,'','Native camera owner: 0 normal follow, 1 scripted camera, 2 observed minigame control. Other values are not classified.','0x14019CE70 / 0x14019DDA0','Camera owner is int32 at RVA AC1528, separate from the bank and controller mode.'),
 (242,'camera.controller_mode','Follow controller mode','ReadOnly',0,10,0,1,'','Native field camera branch. Mode 0 is normal follow; other branches may belong to aiming, tracking or scripted actions.','0x140166100','The field controller dispatches its int32 mode at RVA 718CA8.'),
 (243,'camera.recenter','Recenter behind player','Action',0,1,0,1,'','Queue the native recenter behind the followed player and restore its preset follow distance. Requires the normal camera, a living current player and no menu, event or transition.','0x140430B60 / 0x140165A40 / 0x140165110','Request byte+65 is set immediately before the next normal follow task and consumed during that update.'),
 (244,'camera.snap','Snap camera interpolation','Action',0,1,0,1,'','Queue one native camera snap to its current desired pose. Requires normal follow and free camera disabled. This does not change the player or camera owner.','0x140430B40 / 0x140165BC0 / 0x140166100','Request byte+64 is consumed by the ordinary field camera update before smoothing.'),
 (245,'camera.pending','Pending camera action','ReadOnly',0,2,0,1,'','0 none, 1 recenter queued, 2 camera snap queued. Requests expire after 1.5 seconds or when player, scene, ownership or connection changes.','0x140164860 / 0x140164CB0','The trainer queues a request for the existing group 1, priority 26000 camera task; it does not run an extra camera update.'),
 (246,'camera.follows_player','Camera follows current player','ReadOnly',0,1,0,1,'','Whether the native field controller currently holds the freshly validated player pointer.','0x140164C60 / 0x140164CF0','The borrowed followed-actor pointer is at RVA 718CB0 and is cleared by player teardown.'),
 (247,'camera.follow_distance','Native follow distance','ReadOnly',0,1000000,0,1,'units','Read the native follow distance parameter. Collision and interpolation can make the rendered eye-to-target distance different.','0x1401654D0 / 0x140164520','Controller+88 is the native distance input, bounded by controller+212/+216 in the zoom input path.'),
 (248,'camera.focus_distance','Eye to target distance','ReadOnly',0.01,1000000,0.01,0.1,'units','Read the geometric distance from the rendered camera eye to its target point. This is not an optical depth of field setting.','0x14019D340 / 0x14019CBA0','Camera+72/+88 hold eye and target vectors used to build the view.')
]
rows=[]
for slot,id,name,kind,lo,hi,default,step,unit,description,address,finding in specs:
    rows.append(dict(Id=id,Category='Camera',Name=name,Description=description,Kind=kind,
       CommandId=1000+slot if kind!='ReadOnly' else 0,ValueSlot=slot if kind!='Action' else -1,
       CapabilitySlot=slot,Minimum=lo,Maximum=hi,DefaultValue=default,Step=step,Unit=unit,
       RequiresScene=kind!='ReadOnly',ChangesProgression=False,CanSaveInProfile=False,
       RestoreBehavior=('Held roll is released with free camera. Native follow resumes its own pose; no camera bank is restored.' if slot==240 else
         'Pending request is canceled on timeout, disconnect or camera/player/scene ownership loss. Executed native recenter/snap is a one-time action.' if kind=='Action' else
         'Read only. Availability follows the current camera and field scene.'),
       Evidence=[dict(Address=address,Finding=finding,Level='Complete native IDA assembly and static control-flow review; synthetic guard tests passed. Live camera validation is pending.')]))
path=root/'work/trainer/research/cameraextra_features.json'
path.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(str(path))
