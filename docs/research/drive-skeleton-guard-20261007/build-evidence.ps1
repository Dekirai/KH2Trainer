$ErrorActionPreference='Stop'
# Research-only export. This script never writes product sources or game files.
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$prior=Join-Path $repo 'artifacts/next-research/drive-resource-content'
$e=Get-Content -LiteralPath (Join-Path $prior 'evidence.json') -Raw | ConvertFrom-Json
$archived='C:\Users\shinz\Documents\Codex\2026-10-01\e-steamlibrary-steamapps-common-kingdom-hearts-2\work\trainer\research\drive_locked_crash_bar_evidence.json'
$bar=Get-Content -LiteralPath $archived -Raw | ConvertFrom-Json
$exe='E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'
$raw=[IO.File]::ReadAllBytes($exe)
if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ne '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'){throw 'Wrong original EXE'}
$pe=[BitConverter]::ToInt32($raw,0x3c)
$nsections=[BitConverter]::ToUInt16($raw,$pe+6)
$sections=$pe+24+[BitConverter]::ToUInt16($raw,$pe+20)
foreach($address in '0x1403E6010','0x1403A6840') {
 $f=$bar.functions.$address
 if($f.asm.lines.Count -ne $f.total_instructions -or $f.instruction_count -ne $f.total_instructions -or -not $f.cursor.done){throw 'Incomplete archived body'}
 if($f.asm.lines[-1].instruction -ne 'retn'){throw 'Expected final RET'}
 $start=[Convert]::ToUInt64($address.Substring(2),16)
 $end=[Convert]::ToUInt64($f.asm.lines[-1].addr,16)+1
 $rva=$start-0x140000000L
 $offset=-1
 for($i=0;$i -lt $nsections;$i++) {
  $s=$sections+40*$i;$va=[BitConverter]::ToUInt32($raw,$s+12);$size=[BitConverter]::ToUInt32($raw,$s+16)
  if($rva -ge $va -and $rva-$va+($end-$start) -le $size){$offset=[BitConverter]::ToUInt32($raw,$s+20)+$rva-$va;break}
 }
 if($offset -lt 0 -or $raw[$offset+$end-$start-1] -ne 0xc3){throw 'Archived extent does not end in original RET'}
 $bytes=for($i=0;$i -lt $end-$start;$i++){'0x{0:x2}' -f $raw[$offset+$i]}
 $e.functions+= [pscustomobject]@{
  addr=$address;rva=('{0:X}' -f $rva);size=($end-$start)
  provenance="Archived complete IDA body from $archived; original PE bytes extracted anew 2026-10-07. Not a new IDA capture."
  instruction_count=$f.total_instructions;total_instructions=$f.total_instructions;cursor=$f.cursor
  asm=$f.asm;pages=@([pscustomobject]@{asm=$f.asm;instruction_count=$f.total_instructions;total_instructions=$f.total_instructions;cursor=$f.cursor})
  pseudocode=$f.decompile;original_bytes=@([pscustomobject]@{addr=$address;data=($bytes -join ' ')})
 }
}
$e | Add-Member -NotePropertyName implementation_revalidation -NotePropertyValue ([pscustomobject]@{
 date='2026-10-07';original_sha256='9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'
 input='Existing 45 complete bodies plus two archived BAR owner/fixup bodies. Original file re-read and verified; no new worker, IDB edit or live game access.'
 session='2b15f387';health='Session present but auto_analysis_ready=false on recheck; no new IDA body claims.'
}) -Force
$e | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence.json') -Encoding utf8
Copy-Item -LiteralPath (Join-Path $prior 'verify.ps1') -Destination (Join-Path $PSScriptRoot 'verify-evidence.ps1')
