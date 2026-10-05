import json,pathlib
root=pathlib.Path(__file__).resolve().parents[3]
out=root/'work/trainer/research/gummi_round5_implementation_generated_pins.txt'
old=json.load(open(root/'work/trainer/research/gummi_round5_original_bytes.json'))
new=json.load(open(root/'work/trainer/research/gummi_round5_implementation_evidence.json'))
more=json.load(open(root/'work/trainer/research/gummi_round5_implementation_supplement.json'))
allbytes={int(x['Address'],16)-0x140000000:x for x in old['functions']}
for p in [new,more]:
 for a,v in p['functions'].items():allbytes[int(a,16)-0x140000000]=v['original_bytes']
pins=[0x290900,0x290c60,0x2641d0,0x264150,0x282fa0,0x24b1d0,0x24b220,0x19ce90,0x19dde0,0x13fce0,0x13fcc0,0x13fd20,0x142280,0x1a8e60,0x1a8ef0,0x1aae60,0x1ac110,0x1a90c0,0x1411b0,0x141270,0x141320,0x13f850,0x1abf00,0x1a94c0,0x1ac0a0,0x13f900]
s='// REFERENCE FRAGMENT ONLY. This script never writes product source.\n// Original-byte pins; integrated module also contains separately captured constant pins.\n'
for r in pins:
 v=allbytes[r];b=[int(t,16) for c in v['chunks'] for t in c['data'].split()]
 assert len(b)==v['size']
 s+=f'constexpr BYTE code_{r:X}[]={{'+','.join(f'0x{x:02x}' for x in b)+'};\n'
s+='struct Signature { uintptr_t rva; const BYTE* bytes; size_t size; };\nconstexpr Signature signatures[]={\n'
for r in pins:s+=f'    {{0x{r:X},code_{r:X},sizeof(code_{r:X})}},\n'
s+='};\n'
out.write_text(s,encoding='utf-8')
print(f'Generated {len(pins)} full function pins, '+str(sum(allbytes[r]['size'] for r in pins))+' bytes')
