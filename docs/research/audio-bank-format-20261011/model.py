"""Finite synthetic models; no game code is executed or game asset stored."""
import struct
def i32(n):return (n+2**31)%2**32-2**31
def f32(n):return struct.unpack('<f',struct.pack('<f',n))[0]
def selected(index,count):return i32(index) if i32(index)<count else 0
def first_id(ids,key):return next((i for i,x in enumerate(ids) if x==(key&0xffffffff)%1000),None)
def basic_size(version):return {1:8,2:16,3:16,4:32}.get(version,0)
def stride(kind):return 8 if (((kind-2)&255)&0xf5)==0 and kind!=10 else 4
def sequence_layout(version,flags,extended,optional_lengths):
    # Each native accumulator is32 bits, then zero-extended before pointer add.
    pos=basic_size(version);locations={}
    if flags&0x100:locations['100']=pos;pos=(pos+optional_lengths['100'])&0xffffffff
    for mask,label in [(0x400,'400'),(0x800,'800'),(0x8000,'8000'),(0x2000,'2000')]:
        if flags&mask:locations[label]=pos;pos=(pos+optional_lengths[label])&0xffffffff
    if version>=4 and extended&1:
        locations['extended']=pos;pos=(pos+optional_lengths['extended'])&0xffffffff
    locations['entries']=pos
    return locations
def checked_span(offset,length,total):return offset>=0 and length>=0 and offset<=total and length<=total-offset
def scan_step(data,cursor,acc,targets):
    # Mirrors the selected B78F0 offset arithmetic, but refuses out-of-buffer reads.
    # This diagnostic model is not the native reader and has no playback semantics.
    def read(fmt,p):
        n=struct.calcsize(fmt)
        if not checked_span(p,n,len(data)):raise ValueError('truncated')
        return struct.unpack_from(fmt,data,p)[0]
    op=read('<H',cursor);p=i32(cursor+2)
    if op>63:return dict(status='unknown',cursor=p,acc=acc)
    target=targets[op]
    if target==0xb79d9:return dict(status='stop',cursor=p,acc=acc)
    if target==0xb79ea:return dict(status='unknown',cursor=p,acc=acc)
    if target==0xb798c:acc=i32(acc+read('<I',p));p=i32(p+4)
    elif target in {0xb7910,0xb7993,0xb799b,0xb79a3,0xb79ab,0xb79c1}:
        p=i32(p+{0xb7910:0,0xb7993:4,0xb799b:8,0xb79a3:12,0xb79ab:16,0xb79c1:2}[target])
    elif target==0xb79c9:p=i32(p+2*read('<H',p))
    elif target==0xb79b3:p=i32(p+4+2*read('<H',p+2))
    elif target==0xb793a:p=i32(p+read('<h',p+2)+4*read('<h',p+4))
    elif target==0xb7950:
        count=read('<h',p+4);p=i32(p+read('<h',p+2))
        for _ in range(max(count,0)):p=i32(p+read('<h',p+2)+4*read('<h',p+4))
    else:raise AssertionError('unknown native dispatch target')
    return dict(status='continue',cursor=p,acc=acc)
def run(evidence):
    results=[]
    def check(group,inputs,actual,expected):
        if actual!=expected:raise AssertionError((group,inputs,actual,expected))
        results.append(dict(group=group,input=inputs,result=actual))
    for count in [0,1,2,65535]:
        for value in [-2147483648,-1,0,1,2,65534,65535,2147483647]:
            want=value if value<count else 0
            check('signed_index',[value,count],selected(value,count),want)
    for k in range(256):check('sequence_entry_stride',[k],stride(k),8 if k in [2,4,12] else 4)
    for version in [0,1,2,3,4,5,0xffffffff]:
        check('version_basic_size',[version],basic_size(version),[0,8,16,16,32,0,0][[0,1,2,3,4,5,0xffffffff].index(version)])
    ids=[0,5,999,5,1000,65535]
    for key,want in [(0,0),(5,1),(999,2),(1005,1),(2005,1),(1000,0),(65535,None),(0xffffffff,None)]:
        check('first_matching_id',[key],first_id(ids,key),want)
    labels=['100','400','800','8000','2000','extended'];masks=[0x100,0x400,0x800,0x8000,0x2000]
    sizes=dict(zip(labels,[12,7,10,20,8,24]))
    for version in [1,2,3,4]:
        for bits in range(64):
            flags=sum(mask for n,mask in enumerate(masks) if bits&(1<<n));ext=bool(bits&32)
            got=sequence_layout(version,flags,int(ext),sizes)
            expected={};cursor=basic_size(version)
            for n,label in enumerate(labels):
                if bits&(1<<n) and (n!=5 or version>=4):expected[label]=cursor;cursor+=sizes[label]
            expected['entries']=cursor
            check('optional_sections',[version,bits],got,expected)
    overflow=dict(sizes);overflow['100']=0xfffffff0
    check('native_uint32_wrap',[4,0x100],sequence_layout(4,0x100,0,overflow),{'100':32,'entries':16})
    for total in [0,1,32,0xffffffff]:
        for off,size in [(-1,1),(0,0),(0,1),(total,0),(total,1),(total-1,1),(2**63-1,4)]:
            check('safe_reader_span',[off,size,total],checked_span(off,size,total),0<=off<=total and 0<=size<=total-off)
    scale=f32(.001)
    for n in [0,1,1000,0x7fffffff,0x80000000,0xffffffff]:
        u=f32(f32(n)*scale);s=f32(f32(i32(n))*scale)
        check('duration_signedness',[n],u>=0 and (s<0)==(n>=0x80000000),True)
    for values,want in [([-2.,-1.],0.),([0.,1.],1.),([2.,-1.],2.),([3.,4.],4.)]:
        result=0.
        for value in values:result=max(value,result)
        check('duration_max_includes_zero',values,result,want)
    targets=[int(x['target'],16)-0x140000000 for x in evidence['opcodeTargets']]
    fixed={0xb7910:0,0xb7993:4,0xb799b:8,0xb79a3:12,0xb79ab:16,0xb79c1:2}
    for op in range(64):
        data=bytearray(128);struct.pack_into('<H',data,0,op);t=targets[op]
        if t in fixed:want={'status':'continue','cursor':2+fixed[t],'acc':0}
        elif t==0xb79d9:want={'status':'stop','cursor':2,'acc':0}
        elif t==0xb79ea:want={'status':'unknown','cursor':2,'acc':0}
        elif t==0xb798c:struct.pack_into('<I',data,2,1000);want={'status':'continue','cursor':6,'acc':1000}
        elif t==0xb79c9:struct.pack_into('<H',data,2,3);want={'status':'continue','cursor':8,'acc':0}
        elif t==0xb79b3:struct.pack_into('<H',data,4,3);want={'status':'continue','cursor':12,'acc':0}
        elif t==0xb793a:struct.pack_into('<hh',data,4,6,2);want={'status':'continue','cursor':16,'acc':0}
        elif t==0xb7950:struct.pack_into('<hh',data,4,10,0);want={'status':'continue','cursor':12,'acc':0}
        else:raise AssertionError(t)
        check('opcode_dispatch',[op],scan_step(data,0,0,targets),want)
    # Signed descriptor fields permit a backwards step in the native arithmetic.
    data=bytearray(16);struct.pack_into('<H',data,0,61);struct.pack_into('<hh',data,4,-2,0)
    check('nonprogressing_scan',[61,-2,0],scan_step(data,0,0,targets),{'status':'continue','cursor':0,'acc':0})
    # Dynamic case63 performs its internal steps without adding an opcode size.
    data=bytearray(48);struct.pack_into('<H',data,0,63);struct.pack_into('<hh',data,4,10,2)
    struct.pack_into('<hh',data,14,4,1);struct.pack_into('<hh',data,22,2,2)
    check('nested_scan',[63,2],scan_step(data,0,0,targets),{'status':'continue','cursor':30,'acc':0})
    data=bytearray(8);struct.pack_into('<HI',data,0,3,0xffffffff)
    check('signed_accumulator_wrap',[3,1,0xffffffff],scan_step(data,0,1,targets),{'status':'continue','cursor':6,'acc':0})
    for data in [b'',b'\x03',b'\x03\0',b'\x3d\0\0\0',b'\x3f\0']:
        try:scan_step(data,0,0,targets);rejected=False
        except ValueError:rejected=True
        check('model_only_span_guard',[data.hex()],rejected,True)
    return dict(status='PASS',cases=len(results),results=results,scope='Finite synthetic arithmetic/offset models. Model-only bounds checks are not native protection; malformed examples are not observed retail failures.')
