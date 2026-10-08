"""Small fail-closed regression checks for the recorded ASM pagination validator."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('scale_evidence_verifier', here/'verify.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
evidence = json.loads((here/'evidence.json').read_text(encoding='utf-8'))
checks = 0
for function in evidence['functions']:
    module.validate_body(function)
    checks += 1
baseline = next(f for f in evidence['functions'] if len(f['pages']) > 1)
def rejected(name, change):
    global checks
    value = copy.deepcopy(baseline)
    change(value)
    try:
        module.validate_body(value)
    except (ValueError, KeyError, TypeError):
        checks += 1
        return
    raise AssertionError('Accepted invalid fixture: ' + name)
rejected('missing final cursor', lambda f: f.pop('cursor'))
rejected('cancelled aggregate', lambda f: f['cursor'].update(cancelled=True))
rejected('not done', lambda f: f['cursor'].update(done=False))
rejected('residual next', lambda f: f['cursor'].update(next=1))
rejected('bool count', lambda f: f.update(instruction_count=True))
rejected('negative total', lambda f: f.update(total_instructions=-1))
rejected('null lines', lambda f: f['pages'][0]['asm'].update(lines=None))
rejected('truncated array', lambda f: f['pages'][0]['asm']['lines'].pop())
rejected('missing next', lambda f: f['pages'][0]['cursor'].pop('next'))
rejected('wrong next', lambda f: f['pages'][0]['cursor'].update(next=1))
rejected('cancelled page', lambda f: f['pages'][0]['cursor'].update(cancelled=True))
rejected('wrong page total', lambda f: f['pages'][0].update(total_instructions=1))
rejected('wrong offset', lambda f: f['pages'][0].update(offset=9))
rejected('wrong start', lambda f: f['pages'][0]['asm'].update(start_ea='0x1'))
rejected('empty instruction', lambda f: f['pages'][0]['asm']['lines'][0].update(instruction=''))
rejected('bad bytes', lambda f: f.update(originalBytes='0x90'))
rejected('duplicate function row', lambda f: f['pages'][0]['asm']['lines'][1].update(addr=f['pages'][0]['asm']['lines'][0]['addr']))
report = dict(success=True, checks=checks, failures=0,
              scope='Saved evidence validator only; no game or product execution.')
(here/'verifier-tests.json').write_text(json.dumps(report, indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
