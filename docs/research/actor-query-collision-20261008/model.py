"""Small decision models for the captured collision helpers; no native execution."""
import math, struct

def category_accept(attribute, category, mask=15, value=4, inverse=1,
                    special_enabled=False, special_state=False):
    equal = attribute & mask == value
    if (not equal if inverse == 1 else equal) is False:
        return False
    if special_enabled and special_state and attribute & 15 == 5:
        return True
    masks = {0: 0x10, 1: 0x20, 2: 0x40, 3: 0x80010,
             4: 0x80, 5: 0x100, 6: 0x10}
    return category not in masks or bool(attribute & masks[category])

def signed_child(word):
    return None if word == 65535 else struct.unpack('<h', struct.pack('<H', word))[0]

def ray_scalar_gates(denominator, t):
    # COMISS followed by JAE for the denominator, then JA for each endpoint.
    # Unordered sets ZF/PF/CF: JAE and JA are both false.
    if not math.isnan(denominator) and denominator >= 0:
        return False
    if not math.isnan(t) and (t > 1 or 0 > t):
        return False
    return True

def ordered_overlap(a, b):
    return all(a[k+3] >= b[k] and a[k] <= b[k+3] for k in range(3))

def choose_hit(squared_distances):
    best, selected = struct.unpack('<f', struct.pack('<f', 1e14))[0], None
    for i, distance in enumerate(squared_distances):
        if best > distance:
            best, selected = distance, i
    return selected

def run():
    results = []
    def check(name, actual, expected):
        assert actual == expected, (name, actual, expected)
        results.append(dict(name=name, actual=actual, expected=expected))
    for cat, required in [(0,16),(1,32),(2,64),(3,16),(3,0x80000),(4,128),(5,256),(6,16)]:
        check(f'category {cat} accepts mask {required}', category_accept(required,cat), True)
        check(f'category {cat} rejects zero for mask {required}', category_accept(0,cat), False)
    for cat in [7,15,16,-1]:
        check(f'category {cat} takes default acceptance after attribute filter', category_accept(0,cat), True)
    check('low attribute 4 remains excluded', category_accept(0x14,0), False)
    check('equal filter mode accepts value', category_accept(0x14,0,inverse=0), True)
    check('mode byte 2 uses equality too', category_accept(0x14,0,inverse=2), True)
    check('special low-5 acceptance', category_accept(5,0,special_enabled=True,special_state=True), True)
    check('special requires both flags', category_accept(5,0,special_enabled=True), False)
    check('query clears special enabled flag', category_accept(5,0,special_state=True), False)
    # Caller supplies WORD count zero and 1024 WORD storage. The function caps
    # writes, but this does not bound traversal of cyclic or malformed node data.
    writes = list(range(min(1400,1023)))
    check('candidate write capacity', len(writes), 1023)
    check('last candidate write index', writes[-1], 1022)
    for raw, expected in [(0,0),(32767,32767),(32768,-32768),(65534,-2),(65535,None)]:
        check(f'child WORD {raw}', signed_child(raw), expected)
    for denom,t,expected,label in [(-1,0,True,'start'),(-1,1,True,'end'),
          (-1,-0.1,False,'before'),(-1,1.1,False,'after'),(0,0.5,False,'parallel'),
          (1,0.5,False,'back-facing'),(float('nan'),float('nan'),True,'unordered')]:
        check('ray scalar gates '+label,ray_scalar_gates(denom,t),expected)
    check('AABBs touching on a face overlap', ordered_overlap((-10,-2,-3,0,2,3),(0,-2,-3,8,2,3)),True)
    check('signed negative AABB coordinates', ordered_overlap((-10,-2,-3,-2,2,3),(-1,-2,-3,8,2,3)),False)
    check('strict squared distance keeps first equal hit',choose_hit([4.0,4.0,9.0]),0)
    check('strict squared distance chooses later nearer hit',choose_hit([4.0,1.0,9.0]),1)
    check('unordered squared distance is not selected',choose_hit([float('nan'),1.0]),1)
    threshold=struct.unpack('<f',struct.pack('<f',1e14))[0]
    check('threshold is exclusive',choose_hit([threshold]),None)
    return dict(success=True, checks=len(results), cases=results,
        scope='Decision models from recorded native branches, assuming masked SSE exceptions for NaN. Not original instruction execution, complete collision simulation, native buffer safety or a live-game test.')
