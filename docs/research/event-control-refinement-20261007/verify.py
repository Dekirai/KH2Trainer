"""Read-only reuse of the bounded original-byte/complete-ASM verifier."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('shared_verifier', HERE.parent/'actor-scale-writers-20261007'/'verify.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
source = (HERE/'evidence.json').read_bytes()
report = verifier.validate(json.loads(source), verifier.DEFAULT_EXE.read_bytes())
report['evidenceSha256'] = hashlib.sha256(source).hexdigest()
(HERE/'verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, indent=2))
