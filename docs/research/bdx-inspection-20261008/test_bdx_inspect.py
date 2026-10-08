"""Synthetic controls for the research prototype; no VM execution/emulation."""
import struct
from bdx_inspect import inspect, instruction, path_to

def run():
    checks = []
    def check(value, name):
        assert value, name
        checks.append(name)
    def fixture(words, events=((0, 14),), terminator=0):
        head = b'test\0'.ljust(16,b'\0') + struct.pack('<iii', 16,64,64)
        for event, pc in events: head += struct.pack('<ii',event,pc)
        head += struct.pack('<ii',terminator,0)
        return head+struct.pack('<'+'H'*len(words),*words)
    def one(word, operands=(0,0), pc=14):
        return instruction(b'\0'*(16+2*pc)+struct.pack('<HHH',word,*operands),pc)
    def edges(i): return [(e['kind'],e['target']) for e in i['edges']]
    d=inspect(fixture([0x008a,9,0x0049],terminator=31337))
    check(d['header']['terminatorId']==31337 and len(d['header']['events'])==1,'PC-only terminator and ID0 event')
    check(d['instructions'][0]['trapDescriptor']['arguments']==3,'bank2 index9 metadata')
    check(one(0x008a,(95,0))['trapDescriptor']['arguments']==2,'bank2 index95 metadata')
    check(one(0x008a,(65535,0))['index']==65535,'trap index unsigned16')
    check(one(0xfffa)['bank']==1023,'trap bank unsigned shift6')
    check(one(0x0000)['width']==3 and one(0x0010)['width']==3 and one(0x0020)['width']==2,'push widths')
    check(one(0x0001)['width']==2 and one(0x0002)['width']==3 and one(0x0003)['width']==2,'memory widths')
    check(edges(one(7,(0xfffc,0)))==[('branch',12)],'signed branch offset')
    check(edges(one(0x47,(1,0)))==[('conditional-branch',17),('conditional-fallthrough',16)],'conditional branch has both edges')
    check(edges(one(0x108,(0xfffe,0)))==[('call',14),('call-continuation',16)],'call16 signed target and continuation')
    check(edges(one(0x10b,(0,1)))[0]==('call',65553),'call32 no ushort wrapping')
    check(edges(one(0x10b,(0xfffb,0xffff)))[0]==('call',12),'call32 negative relative offset')
    check(edges(one(0x138,(0,0)))==edges(one(0x108,(0,0))),'call16 ignores bits4/5')
    check(edges(one(0x0009))==[('yield-resume',15)],'halt is resume edge')
    check(edges(one(0x0049))==[('status2-exit',None)],'exit terminal')
    check(edges(one(0x0089))==[('dynamic-return-or-status3',None)],'return does not invent fallthrough')
    for word in [0x00c7,0x0109,0x0025,0x0045,0x0015,0x0305,0x0156,0x0026,0x000c,0x000f]:
        check(edges(one(word))==[('status5-invalid-opcode',None)],f'invalid opcode {word:04x}')
    check(edges(one(0x0306))==[('fallthrough',15)],'integer binary unknown subselector is nonterminal native default')
    check(edges(one(0x0034))==[('fallthrough',15)] and one(0xfff4)['width']==1,'group4 all length1')
    check(edges(one(0x0120))==[('fallthrough',16)],'invalid address selector can push NULL')
    check(edges(one(0x0130))==[('unknown-invalid-address-effect',None)],'invalid selector load has no normal continuation')
    check(edges(one(0x0101))==[('unknown-invalid-address-effect',None)],'invalid selector store has no normal continuation')
    check(edges(one(0x00c2))==[('fallthrough',17)],'copy selector3 depends on retained scratch')
    d=inspect(fixture([0,0x008a,9,0x0049,0x008a,95]))
    check(not any(i['group']==10 for i in d['instructions']),'trap-like immediate and unreachable bytes are not traps')
    d=inspect(fixture([0x47,1,0,0x008a,9,0x0049]))
    check(bool(d['diagnostics']),'overlapping branch interpretation diagnosed')
    dup=fixture([0x0049,0x008a,9,0x0049],events=((7,18),(7,19)))
    d=inspect(dup)
    check(d['header']['events'][1]['shadowed'] and len(d['instructions'])==1,'duplicate event first match only')
    d=inspect(fixture([0x108,2,0x49,0x49,0x8a,95,0x89]))
    route=path_to(d,14,18)
    check(route==[{'fromPc':14,'edge':'call','toPc':18}],'path preserves edge kind')
    for data in [b'', b'\0'*35, fixture([0]), fixture([0x49],events=((0,-1),)), fixture([0x49],events=((0,1),))]:
        try:
            doc=inspect(data)
            check(bool(doc['diagnostics']),'truncated instruction diagnosed')
        except ValueError:
            check(True,'malformed header/entry rejected')
    d=inspect(fixture([7,0xfffe]))
    check(len(d['instructions'])==1 and not d['diagnostics'],'loop bounded by visited PCs')
    bad_size=bytearray(fixture([0x49]));struct.pack_into('<i',bad_size,16,-1)
    d=inspect(bytes(bad_size))
    check(d['header']['workSize']==-1 and len(d['instructions'])==1 and d['diagnostics'],'negative sizes visible without native allocation')
    d=inspect(fixture([0x18a,1,0x49]),maximum_instructions=1)
    check(any(x['problem']=='instruction limit' for x in d['diagnostics']),'instruction budget explicit')
    return dict(checkCount=len(checks), checks=checks, limitations='Tests exercise static reader policy, not native VM execution or all operands.')

if __name__=='__main__':
    print('PASS',run()['checkCount'])
