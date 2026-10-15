"""One selected retail-equal stored BDX; syntactic CFG, never execution."""
from pathlib import Path
import hashlib, importlib.util, json, struct
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'Directory.Build.props').exists())
D=R/'docs/research/bdx-inspection-20261008/bdx_inspect.py'
sp=importlib.util.spec_from_file_location('selected_bdx',D); dec=importlib.util.module_from_spec(sp);sp.loader.exec_module(dec)
P=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\Modding\openkh\data\kh2\obj\N_HB040_BTL.mdlx')
def sha(b):return hashlib.sha256(b).hexdigest()
def build():
 b=P.read_bytes(); retail=json.loads((H/'retail.json').read_text());assert sha(b)==retail['hits'][0]['sha256']
 assert b[:4]==b'BAR\x01'
 typ,link,name,off,length=struct.unpack_from('<HH4sII',b,48)
 assert typ==3 and name==b'n_hb' and off+length<=len(b)
 data=b[off:off+length];doc=dec.inspect(data)
 sites=[x for x in doc['instructions']if x['group']==10 and (x['sub'],x['operands'][0])in ((10,3),(10,4),(7,26))]
 nodes={x['pc']:x for x in doc['instructions']}
 for x in sites:
  pc=x['pc']; x['precedingBlock']=[nodes[k]for k in sorted(nodes)if pc-5<=k<pc]
  x['eventPaths']=[{'event':e['id'],'path':p}for e in doc['header']['events']if (p:=dec.path_to(doc,e['pc'],pc))is not None]
 result=dict(scope='One selected retail-equal BAR script. Complete event-rooted syntactic decode and five selected callsites; CFG paths include unknown native continuations and are not runtime traces or proof of feasible call/return matching.',asset='obj/N_HB040_BTL.mdlx',assetSha256=sha(b),assetLength=len(b),barEntry=dict(ordinal=2,type=typ,name=name.decode(),offset=off,length=length),decoder=dict(path=D.relative_to(R).as_posix(),sha256=sha(D.read_bytes())),document=doc,selectedSites=sites)
 return result
if __name__=='__main__':
 r=build();(H/'script-evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(scriptBytes=r['barEntry']['length'],instructions=len(r['document']['instructions']),callsites=[dict(pc=x['pc'],bank=x['sub'],index=x['operands'][0],events=[e['event']for e in x['eventPaths']])for x in r['selectedSites']]),indent=2))
