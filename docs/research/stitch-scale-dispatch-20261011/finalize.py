"""Author-only packaging within this study directory; not a verifier."""
from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent
R=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
p=H/'report.json'
s=p.read_text(encoding='utf-8').replace('sets bit2 in Actor+3608 and Actor+3344','sets mask0x2 in Actor+3608 and Actor+3344').replace('remaining16 key bytes','remaining12 key bytes').replace('complete1CC760 RET0 body','complete1CC760 RET 0 body (no return-value assignment)')
p.write_text(s,encoding='utf-8')
p=H/'parser-check.py'
s=(R/'artifacts/actor-scale-ownership-20261011/parser-check.py').read_text().replace("e['functions']+e['dependencies']","e['functions']+json.loads((H/'dependencies.json').read_bytes())['functions']")
p.write_text(s,encoding='utf-8')
