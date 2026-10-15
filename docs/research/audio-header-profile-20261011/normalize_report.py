"""Author-only canonical claim field names for the existing coverage parser."""
from pathlib import Path
import json
p=Path(__file__).resolve().parent/'report.json';j=json.loads(p.read_bytes())
mapping={'address':'addr','finding':'Finding','limitations':'Limitations','evidence':'Evidence'}
j['claims']=[{mapping.get(k,k):v for k,v in c.items()} for c in j['claims']]
p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
