from pathlib import Path
import json,sys
H=Path(__file__).resolve().parent
j=json.loads((H/'capture.json').read_bytes())
for f in j['functions']:
 if f['addr'][5:] in sys.argv or f['addr'] in sys.argv:
  print(f['addr'])
  if '--asm' in sys.argv:
   for row in f['disassembly']['asm']['lines']:print(row['addr'],row['instruction'])
  else:print(f['pseudocode']['code'])
