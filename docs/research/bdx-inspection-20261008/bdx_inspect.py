"""Bounded stored-byte BDX CFG reader, derived from the retail native interpreter.

It never executes scripts. Edges are syntactic possibilities, not runtime traces.
Unvisited bytes are data/unknown; they are never searched for opcode-like words.
"""
import collections
import hashlib
import struct


def i32(value):
    return ((value + (1 << 31)) & 0xffffffff) - (1 << 31)


def instruction(data, pc):
    at = 16 + 2 * pc
    if at < 0 or at + 2 > len(data):
        raise ValueError('opcode outside payload')
    word, = struct.unpack_from('<H', data, at)
    group, mode, sub = word & 15, (word >> 4) & 3, word >> 6
    width = [3 if mode < 2 else 2, 2, 3, 2, 1, 1, 1, 2, 2, 1, 2, 3, 1, 1, 1, 1][group]
    if at + 2 * width > len(data):
        raise ValueError('truncated operand')
    operands = list(struct.unpack_from('<' + 'H' * (width - 1), data, at + 2))
    result = dict(pc=pc, fileOffset=at, word=word, group=group, mode=mode, sub=sub,
                  width=width, raw=data[at:at + 2 * width].hex(), operands=operands,
                  name=['push', 'store', 'copy', 'load', 'indirect-store', 'unary',
                        'binary', 'branch', 'call16', 'control', 'trap', 'call32',
                        'invalid', 'invalid', 'invalid', 'invalid'][group], edges=[], diagnostics=[])
    nxt = i32(pc + width)
    def edge(kind, target=None):
        result['edges'].append(dict(kind=kind, target=target))
    invalid = group >= 12
    if group == 5:
        invalid = (mode == 0 and sub not in {0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
                   or mode == 1 and sub not in {1, 2, 5, 6, 7, 8, 9, 10, 11}
                   or mode >= 2)
    elif group == 6:
        invalid = mode >= 2 or mode == 1 and sub > 4
        if mode == 0 and sub > 11:
            result['diagnostics'].append('native integer default: pop two, push unchanged left operand')
    elif group == 7:
        invalid = sub > 2
        if not invalid:
            relative, = struct.unpack_from('<h', data, at + 2)
            edge('branch' if sub == 0 else 'conditional-branch', i32(nxt + relative))
            if sub:
                edge('conditional-fallthrough', nxt)
    elif group in (8, 11):
        relative, = struct.unpack_from('<h' if group == 8 else '<i', data, at + 2)
        result['frameWords'] = sub
        edge('call', i32(nxt + relative))
        edge('call-continuation', nxt)
        if sub < 2:
            result['diagnostics'].append('frame words below return slots; native does not guard')
    elif group == 9:
        names = {0: 'halt', 1: 'exit', 2: 'return', 3: 'drop', 5: 'dup', 6: 'sin', 7: 'cos', 8: 'degrees-to-radians', 9: 'radians-to-degrees'}
        invalid = sub not in names
        result['name'] = names.get(sub, 'invalid-control')
        if sub == 0:
            edge('yield-resume', nxt)
        elif sub == 1:
            edge('status2-exit')
        elif sub == 2:
            edge('dynamic-return-or-status3')
    elif group == 10:
        result['bank'] = sub
        result['index'] = operands[0]
        known = {9: (3, '0x140431a70', '0x140411350'), 95: (2, '0x140431aa0', '0x1404112b0')}
        if sub == 2 and operands[0] in known:
            argc, adapter, native = known[operands[0]]
            result['trapDescriptor'] = dict(arguments=argc, returnsValue=False, adapter=adapter, native=native)
        edge('native-trap-continuation', nxt)
        edge('unknown-native-effects')
    if invalid:
        edge('status5-invalid-opcode')
    elif sub > 3 and (group in (1, 2) or group == 0 and mode == 3):
        result['diagnostics'].append('unsupported address selector; NULL source/destination; no normal continuation assumed')
        edge('unknown-invalid-address-effect')
    elif group not in (7, 8, 10, 11) and not (group == 9 and sub <= 2):
        edge('fallthrough', nxt)
    if group == 0 and mode == 2 and sub > 3:
        result['diagnostics'].append('unsupported selector yields NULL encoded as @ADR/0')
    if group == 2 and sub == 3:
        result['diagnostics'].append('retained native scratch destination; execution requires valid prior state')
    return result


def inspect(data, maximum_instructions=100000, maximum_events=4096):
    if len(data) < 36 or len(data) > 64 * 1024 * 1024:
        raise ValueError('payload must contain bounded header and terminator')
    work, stack, temp = struct.unpack_from('<iii', data, 16)
    events, diagnostics = [], []
    if min(work, stack, temp) < 0:
        diagnostics.append(dict(problem='negative declared allocation size; stored code may still be inspected'))
    seen_ids = set()
    for ordinal in range(maximum_events + 1):
        off = 28 + 8 * ordinal
        if off + 8 > len(data):
            raise ValueError('event table truncated or missing terminator')
        event, pc = struct.unpack_from('<ii', data, off)
        if pc == 0:
            header_end = off + 8
            terminator_id = event
            break
        if ordinal == maximum_events:
            raise ValueError('event count limit')
        events.append(dict(id=event, pc=pc, fileOffset=off, shadowed=event in seen_ids))
        seen_ids.add(event)
    def valid_pc(pc):
        return pc > 0 and header_end <= 16 + 2 * pc <= len(data) - 2
    for e in events:
        if not valid_pc(e['pc']):
            raise ValueError('event PC outside code region')
    roots = [e['pc'] for e in events if not e['shadowed']]
    pending = collections.deque(roots)
    decoded, occupied = {}, {}
    while pending:
        pc = pending.popleft()
        if pc in decoded:
            continue
        if not valid_pc(pc):
            diagnostics.append(dict(pc=pc, problem='edge outside code region'))
            continue
        if pc in occupied:
            diagnostics.append(dict(pc=pc, problem='edge enters operand', owner=occupied[pc]))
            continue
        if len(decoded) >= maximum_instructions:
            diagnostics.append(dict(pc=pc, problem='instruction limit'))
            break
        try:
            one = instruction(data, pc)
        except ValueError as e:
            diagnostics.append(dict(pc=pc, problem=str(e)))
            continue
        collision = next((j for j in range(pc, pc + one['width']) if j in occupied), None)
        if collision is not None:
            diagnostics.append(dict(pc=pc, problem='overlapping instruction', owner=occupied[collision]))
            continue
        decoded[pc] = one
        for j in range(pc, pc + one['width']):
            occupied[j] = pc
        for edge in one['edges']:
            if edge['target'] is not None:
                pending.append(edge['target'])
    return dict(schema=1, scope='stored bytes; event-rooted syntactic CFG; no execution proof',
                sha256=hashlib.sha256(data).hexdigest(), length=len(data),
                header=dict(nameRaw=data[:16].hex(), name=data[:16].split(b'\0')[0].decode('ascii', 'backslashreplace'),
                            workSize=work, stackSize=stack, tempSize=temp, end=header_end,
                            terminatorId=terminator_id, events=events),
                instructions=[decoded[k] for k in sorted(decoded)], diagnostics=diagnostics,
                uncoveredWords=(len(data) - header_end) // 2 - len(occupied))


def path_to(document, start, target):
    """Return a CFG path, retaining conditional edge kinds; never a dynamic trace."""
    ins = {x['pc']: x for x in document['instructions']}
    seen = {start: None}
    pending = collections.deque([start])
    while pending:
        pc = pending.popleft()
        if pc == target:
            path = []
            while seen[pc] is not None:
                previous, kind = seen[pc]
                path.append(dict(fromPc=previous, edge=kind, toPc=pc))
                pc = previous
            return list(reversed(path))
        for edge in ins.get(pc, {}).get('edges', []):
            dest = edge['target']
            if dest is not None and dest in ins and dest not in seen:
                seen[dest] = (pc, edge['kind'])
                pending.append(dest)
    return None
