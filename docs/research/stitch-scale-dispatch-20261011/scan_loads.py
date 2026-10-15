from pathlib import Path
import runpy,json,capstone
m=runpy.run_path(str(Path(__file__).with_name('scan.py')))
b,o,n,sz,st,H,base=(m[x] for x in ('b','o','n','sz','struct','H','base'))
out=[]
for k in range(n):
 s=o+sz+40*k;vs,r,l,p=st.unpack_from('<4I',b,s+8)
 if b[s:s+8].rstrip(b'\0')!=b'.text':continue
 c=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);c.skipdata=True
 ins=list(c.disasm_lite(b[p:p+l],base+r))
 for i,(a,z,mn,op) in enumerate(ins):
  if mn=='mov' and ', qword ptr [' in op and '+ 0x50]' in op and 'rsp' not in op and any(x[2] in ('call','jmp') for x in ins[i+1:i+8]):
   out.append({'addr':hex(a),'context':[{'addr':hex(v[0]),'asm':v[2]+' '+v[3]} for v in ins[max(0,i-3):i+8]]})
(H/'slot80-load-candidates.json').write_text(json.dumps({'scope':'Positive linear Capstone discovery only; IDA boundaries and object identities still require validation.','matches':out},indent=2)+'\n')
print(json.dumps({'candidateCount':len(out)}))
