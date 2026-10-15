"""The only interpreter additions needed for the selected constructor/cleanup."""
import hashlib,pathlib
H=pathlib.Path(__file__).resolve().parent
ROOT=next(p for p in H.parents if (p/'src/KH2Trainer.Core').is_dir())
SOURCE=ROOT/'docs/research/collision-position-dispatch-20261011/machine.py'
def derived():
 s=SOURCE.read_text(encoding='utf-8-sig')
 old="            elif op=='bt':self.flags['c']=bool((self.value(i,x[0])>>(self.value(i,x[1])%(x[0].size*8)))&1)"
 new="""            elif op=='not':self.assign(i,x[0],~self.value(i,x[0]))
            elif op in ('bt','bts'):
                assert x[0].type==X86_OP_REG, 'Selected BT/BTS supports register destination only'
                value=self.value(i,x[0]);bit=self.value(i,x[1])%(x[0].size*8)
                self.flags['c']=bool((value>>bit)&1)
                if op=='bts':self.assign(i,x[0],value|(1<<bit))"""
 assert s.count(old)==1
 return s.replace(old,new)
if __name__=='__main__':
 (H/'machine.py').write_text(derived(),encoding='utf-8')
 print(hashlib.sha256(SOURCE.read_bytes()).hexdigest())
