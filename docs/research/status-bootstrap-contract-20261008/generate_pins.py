"""Generate exact normal STATUS closure pins from byte-verified retail evidence."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ORIGINAL=Path(r'E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe')
SHA='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
def build():
    data=ORIGINAL.read_bytes();assert hashlib.sha256(data).hexdigest()==SHA
    pe=struct.unpack_from('<I',data,0x3c)[0];fh=pe+4;op=fh+20
    count=struct.unpack_from('<H',data,fh+2)[0];opt_size=struct.unpack_from('<H',data,fh+16)[0]
    sections=[]
    for i in range(count):
        o=op+opt_size+40*i;vs,rva,rs,fp=struct.unpack_from('<IIII',data,o+8);sections.append((rva,rs,fp))
    def at(rva,n):
        for start,size,fp in sections:
            if start<=rva and rva+n<=start+size:return data[fp+rva-start:fp+rva-start+n]
        raise ValueError(hex(rva))
    def cstring(rva):
        out=bytearray()
        while (ch:=at(rva+len(out),1)[0]):
            assert len(out)<512;out.append(ch)
        return out.decode('ascii')
    previous=HERE.parent/'status-bootstrap-20261007/evidence.json'
    ev=json.loads(previous.read_text(encoding='utf-8-sig'));functions={int(f['addr'],16):f for f in ev['functions']}
    roots=[int(a,16) for a in ev['writerRoots']]
    def octets(value):return bytes(int(x,16) for x in value.replace(',',' ').split()) if isinstance(value,str) else bytes(value)
    bodies=[]
    for addr in map(lambda a:int(a,16),ev['specializedWriterClosure']):
        f=functions[addr];blob=octets(f['originalBytes']);rva=addr-0x140000000
        assert len(blob)==f['size'] and blob==at(rva,len(blob))
        bodies.append((rva,blob,roots.index(addr) if addr in roots else -1))
    assert len(bodies)==25 and [i for _,_,i in bodies[:5]]==list(range(5))
    decoder=Cs(CS_ARCH_X86,CS_MODE_64);decoder.detail=True
    helper_instructions={}
    for addr in (0x140439fc8,0x14043a028):
        helper_instructions.update({i.address:i for i in decoder.disasm(octets(functions[addr]['originalBytes']),addr)})
    slots={0x140439fcc:0x142af9b50,0x14043a02e:0x142af9b50,
        0x140439fd8:0x1407591f8,0x14043a03a:0x1407591f8,
        0x140439fe1:0x142af9b60,0x14043a04d:0x142af9b58,
        0x140439ff9:0x14057bca0,0x14043a066:0x14057bca0}
    for site,target in slots.items():
        insn=helper_instructions[site]
        memory=[o for o in insn.operands if o.type==X86_OP_MEM]
        assert len(memory)==1 and memory[0].mem.base==X86_REG_RIP
        assert insn.address+insn.size+memory[0].mem.disp==target
    for site,target in ((0x140439fd6,0x14043a000),(0x14043a038,0x14043a06d)):
        insn=helper_instructions[site]
        assert insn.mnemonic=='jne' and insn.operands[0].type==X86_OP_IMM and insn.operands[0].imm==target
    assert (helper_instructions[0x140439fd3].mnemonic,helper_instructions[0x140439fd3].op_str)==('test','rcx, rcx')
    assert helper_instructions[0x14043a02e].mnemonic=='cmp' and helper_instructions[0x14043a02e].operands[1].imm==0
    for site in (0x140439fdf,0x14043a048):assert (helper_instructions[site].mnemonic,helper_instructions[site].op_str)==('mov','ecx, eax')
    for site in (0x140439fe8,0x14043a054):assert (helper_instructions[site].mnemonic,helper_instructions[site].op_str)==('and','ecx, 0x3f')
    for site in (0x140439feb,0x14043a057):assert (helper_instructions[site].mnemonic,helper_instructions[site].op_str)==('ror','rax, cl')
    for site in (0x140439fe1,0x14043a04d):assert helper_instructions[site].mnemonic=='xor'
    fresh=json.loads((HERE/'evidence.json').read_text(encoding='utf-8'))
    assert fresh['functions'][0]['asm']['lines']==[{'addr':'1405669f0','instruction':'jmp rax','label':'_guard_dispatch_icall_nop'}]
    assert at(0x5669f0,2)==b'\xff\xe0'
    bodies.append((0x5669f0,b'\xff\xe0',-1))
    reloc_rva,reloc_size=struct.unpack_from('<II',data,op+112+5*8)
    off=0;relocations=[]
    while off<reloc_size:
        page,size=struct.unpack('<II',at(reloc_rva+off,8));assert size>=8 and size%2==0
        for (word,) in struct.iter_unpack('<H',at(reloc_rva+off+8,size-8)):
            kind=word>>12
            if kind:
                assert kind==10;relocations.append(page+(word&0xfff))
        off+=size
    assert off==reloc_size
    for rva,blob,_ in bodies:assert not any(rva<q+8 and q<rva+len(blob) for q in relocations)
    assert 0x57bca0 in relocations
    imports={};d=struct.unpack_from('<I',data,op+120)[0]
    while True:
        oft,stamp,chain,name,ft=struct.unpack('<IIIII',at(d,20))
        if not any((oft,stamp,chain,name,ft)):break
        dll=cstring(name);i=0
        while (v:=struct.unpack('<Q',at((oft or ft)+8*i,8))[0]):
            if not v>>63:imports[ft+8*i]=(dll,cstring(v+2))
            i+=1
        d+=20
    chosen=[(0x57b2d8,'KERNEL32.dll','EnterCriticalSection'),(0x57b2d0,'KERNEL32.dll','LeaveCriticalSection'),
        (0x57b150,'KERNEL32.dll','WaitForSingleObjectEx'),(0x57b280,'KERNEL32.dll','SetEvent'),
        (0x57b2c0,'KERNEL32.dll','ResetEvent'),(0x57bb80,'api-ms-win-crt-utility-l1-1-0.dll','bsearch')]
    assert all(imports[rva]==(module,name) for rva,module,name in chosen)
    image_size=struct.unpack_from('<I',data,op+56)[0];dll_flags=struct.unpack_from('<H',data,op+70)[0]
    assert dll_flags==0x8160 and not dll_flags&0x4000
    assert struct.unpack('<Q',at(0x57bca0,8))[0]==0x1405669f0
    lines=['// Generated by docs/research/status-bootstrap-contract-20261008/generate_pins.py.',
        '// Original PE SHA256: '+SHA,'// 25 normal-closure bodies plus the two-byte native dispatch thunk.',
        f'inline constexpr uint32_t PeOffset=0x{pe:x},ImageSize=0x{image_size:x},TimeStamp=0x{struct.unpack_from("<I",data,fh+4)[0]:x};',
        f'inline constexpr uint16_t DllCharacteristics=0x{dll_flags:x};']
    for rva,blob,root in bodies:
        lines.append(f'inline constexpr unsigned char Pin{rva:X}[]={{')
        lines.extend('    '+','.join(f'0x{x:02x}' for x in blob[i:i+16])+',' for i in range(0,len(blob),16))
        lines.append('};')
    lines.append('inline constexpr BodyPin Bodies[]={')
    lines.extend(f'    {{0x{rva:x},sizeof(Pin{rva:X}),{root},Pin{rva:X}}},' for rva,blob,root in bodies)
    lines+=['};','inline constexpr ImportPin Imports[]={']
    lines.extend(f'    {{0x{rva:x},L"{module}","{name}"}},' for rva,module,name in chosen)
    lines+=['};','']
    manifest={'originalSha256':SHA,'closureEvidenceSha256':hashlib.sha256(previous.read_bytes()).hexdigest(),
        'functions':len(bodies),'normalClosureFunctions':25,'bodyBytes':sum(len(b) for _,b,_ in bodies),
        'aslrCodeRelocations':0,'dispatchSlotHasDir64Relocation':True,'dllCharacteristics':hex(dll_flags),
        'configurationOperandsVerified':{hex(k):hex(v) for k,v in slots.items()},'nonzeroEventBranchBypassesEncodedSlots':True,
        # This is the declaring DLL of an imported symbol, not the evidence's
        # module/domain. Keep that distinction explicit for coverage consumers.
        'imports':[{'rva':hex(r),'declaringDll':m,'name':n} for r,m,n in chosen],
        'bodies':[{'rva':hex(r),'size':len(b),'rootIndex':i,'sha256':hashlib.sha256(b).hexdigest()} for r,b,i in bodies]}
    return '\n'.join(lines),manifest
if __name__=='__main__':
    source,manifest=build();target=ROOT/'src/KH2Trainer.Bridge/StatusBootstrapPins.inl'
    if '--check' in sys.argv:assert target.read_text(encoding='utf-8')==source
    else:target.write_text(source,encoding='utf-8',newline='\n')
    manifest['pinsSha256']=hashlib.sha256(source.encode()).hexdigest()
    (HERE/'pins-verification.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('imports','bodies')}))
