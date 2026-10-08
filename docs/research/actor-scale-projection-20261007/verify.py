"""Original-byte audit and counterexamples to finite-input-only projection checks."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
source = HERE.parent / 'actor-scale-contract-20261007/verify.py'
spec = importlib.util.spec_from_file_location('scale_evidence_validator', source)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

def f32(value):
    try:
        return struct.unpack('<f', struct.pack('<f', value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)

def main():
    evidence_bytes = (HERE / 'evidence.json').read_bytes()
    evidence = json.loads(evidence_bytes)
    original = validator.DEFAULT_EXE.read_bytes()
    report = validator.validate(evidence, original)
    checks = 0
    def check(ok, message):
        nonlocal checks
        checks += 1
        if not ok:
            raise ValueError(message)
    bodies = {int(f['addr'], 16): f for f in evidence['functions']}
    tables = {int(d['addr'],16): validator.octets(d['originalBytes']) for d in evidence['data']}
    check(struct.unpack_from('<Q', tables[0x1405B4958], 40)[0] == 0x1401DA6A0, 'Prototype vcall slot')
    check(struct.unpack_from('<Q', tables[0x1405B4A38], 40)[0] == 0x1401DB470, 'RAW vcall slot')
    check(struct.unpack('<f', tables[0x140623C48])[0] == -1, 'current-frame sentinel')
    check(struct.unpack('<f', tables[0x140623BD4])[0] == 60, 'native RAW frame divisor')
    instructions = lambda addr: [x['instruction'] for x in bodies[addr]['asm']['lines']]
    extract = instructions(0x1403C7B20)
    check('movaps xmm7, xmm2' in extract and 'movaps xmm2, xmm7' in extract and
          'call qword ptr [rax+28h]' in extract, 'extractor third float register retained')
    raw = instructions(0x1401DB470)
    check('subss xmm2, xmm1' in raw and 'movaps xmm3, xmm2' in raw and
          'call sub_1401DB700' in raw, 'RAW fractional fourth argument retained')
    # Scalar2 is inside the proposed policy. Both current and input translation
    # can be finite while a single candidate basis/translation product overflows.
    native_translation = f32(2e38)
    current = f32(1 * native_translation)
    candidate = f32(2 * native_translation)
    check(math.isfinite(native_translation) and math.isfinite(current) and not math.isfinite(candidate),
          'finite current projection does not imply finite scaled projection')
    # Native loop steps use Float32. Finite endpoints alone do not establish
    # positive span, or that repeatedly adding a span changes the current value.
    zero_span = f32(f32(8) - f32(8))
    check(f32(f32(1) + zero_span) == f32(1), 'equal endpoints cannot advance a wrap loop')
    check(f32(f32(2**30) + f32(1)) == f32(2**30), 'Float32 addition may not advance at large magnitude')
    report.update(evidenceSha256=hashlib.sha256(evidence_bytes).hexdigest(), checks=checks,
                  failures=0, liveGame=False, productScaleWrites=False,
                  syntheticScope='Arithmetic counterexamples and evidence-integrity assertions; no gameplay simulation.')
    (HERE / 'verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('bodies','data')}))

if __name__ == '__main__':
    main()
