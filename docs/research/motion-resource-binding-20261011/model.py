"""Small, explicit design counterexamples and checked-range cases; no game execution.

These are policy models, not an emulator or proof of installed observer coverage.
Native statements are separately checked against complete ASM and original bytes.
"""
U64=(1<<64)-1

def span(base,length,start,count):
    return (all(isinstance(x,int) and 0<=x<=U64 for x in (base,length,start,count))
            and length>0 and base+length<=U64 and start>=base
            and start+count<=U64 and start+count<=base+length)

def payload(base,reservation,nested,nested_length,motion,entry_length,payload_pointer):
    if not span(base,reservation,nested,nested_length): return None
    if not span(nested,nested_length,motion,entry_length): return None
    if entry_length<144 or payload_pointer!=motion+144: return None
    return (payload_pointer,entry_length-144)

def run(evidence):
    decoded={int(i['addr'],16):i for f in evidence['functions'] for i in f['independentDecode']}
    anchors=[
      (0x1401c3847,'mov','qword ptr [rcx + 8], rdx','Payload base stored without a length'),
      (0x1403c8aff,'mov','qword ptr [rbx + 0x18], rax','Motion pointer publication'),
      (0x1403c8b09,'call','qword ptr [rdx + 8]','Duration consumer after Motion store'),
      (0x1403c8bd3,'call','qword ptr [rax + 0x20]','Bounds consumer inside bind'),
      (0x1403c8ca6,'call','0x1403c73c0','Conditional pose preparation before bind returns'),
      (0x1403c7325,'dec','dword ptr [rax]','Borrowed counter released in cleanup'),
      (0x1403c7327,'mov','qword ptr [rcx + 0x1b0], rbp','Borrowed counter pointer cleared'),
      (0x1403c73a2,'call','rax','Cleanup callback after counter release'),
      (0x1403c66d2,'mov','qword ptr [rdi + 0x148], rax','Alternate root context before bind'),
      (0x1403c6708,'call','0x1403c8a40','Alternate binding call'),
      (0x1403c6733,'inc','dword ptr [rax]','Borrowed source acquisition after bind'),
      (0x1403c8d0d,'mov','qword ptr [rdi + 0x148], rax','Normal root context before bind'),
      (0x1403c8d5b,'call','0x1403c8a40','Normal binding call'),
      (0x14039e138,'mov','qword ptr [rax + 0x50], rsi','Rounded reservation stored'),
      (0x14039d855,'mov','qword ptr [rbx + 0x58], rcx','Cache destination publication'),
      (0x14039e794,'call','0x1403a62b0','Unfix before relocation copy'),
      (0x14039e87f,'call','0x1403a6120','Fixup after relocation copy'),
      (0x14039e8a0,'mov','qword ptr [rbx + 0x60], rax','Previous base replaced'),
      (0x1403e61aa,'mov','qword ptr [rbx + 0x20], rax','Holder motion bank pointer'),
    ]
    out=[]
    for addr,mn,op,why in anchors:
        i=decoded[addr];assert (i['mnemonic'],i['operands'])==(mn,op),(hex(addr),i)
        out.append({'addr':hex(addr),'bytes':i['bytes'],'instruction':mn+' '+op,'meaning':why})
    by={int(f['addr'],16):f for f in evidence['functions']}
    cleanup=by[0x1403c7300]['independentDecode']
    # Full body confirms there is no direct C+24 publication in this cleanup.
    assert not any(i['mnemonic']=='mov' and i['operands'].startswith(('qword ptr [rcx + 0x18],','qword ptr [rdi + 0x18],')) for i in cleanup)
    cases=[]
    def check(name,actual,expected):
        assert actual==expected,(name,actual,expected)
        cases.append({'case':name,'result':actual,'expected':expected,'status':'PASS'})
    good=(0x1000,0x1000,0x1100,0x800,0x1200,0x200,0x1290)
    check('Rounded outer reservation plus exact child gives bounded payload',payload(*good),(0x1290,0x170))
    check('Child may end exactly at nested end',payload(0x1000,0x1000,0x1100,0x800,0x1800,0x100,0x1890),(0x1890,0x70))
    check('One byte past nested end is rejected',payload(0x1000,0x1000,0x1100,0x800,0x1800,0x101,0x1890),None)
    check('Nested BAR beyond reservation is rejected',payload(0x1000,0x1000,0x1800,0x801,0x1800,0x100,0x1890),None)
    check('Entry shorter than runtime prefix is rejected',payload(0x1000,0x1000,0x1100,0x800,0x1200,143,0x1290),None)
    check('Different live Motion payload pointer is rejected',payload(*good[:-1],0x12A0),None)
    check('Qword end overflow is rejected',span(U64-15,32,U64-15,1),False)
    check('Zero reservation is rejected',span(0x1000,0,0x1000,0),False)
    check('Negative child count is rejected',span(0x1000,0x1000,0x1100,-1),False)
    # Explicit logical counterexamples grounded by the release/acquire instructions above.
    motion=0x1200;counter=1;before=(motion,counter)
    counter=(counter-1)&0xffffffff;counter=(counter+1)&0xffffffff
    check('Same pointer and restored counter can conceal release/rebind',(motion,counter)==before,True)
    old=(0x1000,0x1200);after=(0x1800,old[1])
    check('Primary setter can change bank while current Motion stays equal',old[1]==after[1] and old[0]!=after[0],True)
    check('Entry invalidation precedes callback but return invalidation does not',0x1403c7300<0x1403c73a2<0x1403c73bf,True)
    return {'status':'PASS','scope':'19 original-byte/Capstone instruction anchors, one complete cleanup-store check, and 12 explicit policy/counterexample cases. No native function execution, no installed hook, no live allocation read.',
            'instructionAnchors':out,'cleanupDirectMotionStoreAbsent':True,'cases':cases,
            'summary':{'instructionAnchors':len(out),'policyCases':len(cases),'failures':0}}
