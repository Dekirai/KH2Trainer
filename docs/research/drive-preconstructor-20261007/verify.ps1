$ErrorActionPreference='Stop'
$exe='E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'
$raw=[IO.File]::ReadAllBytes($exe)
$hash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
if($hash -ne '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'){throw 'Wrong original'}
$pe=[BitConverter]::ToInt32($raw,0x3c)
$count=[BitConverter]::ToUInt16($raw,$pe+6)
$sections=$pe+24+[BitConverter]::ToUInt16($raw,$pe+20)
function VerifyBytes([string]$address,[object[]]$bytes){
 $rva=[uint32]([Convert]::ToUInt64($address.Substring(2),16)-0x140000000L)
 $off=-1
 for($i=0;$i -lt $count;$i++){
  $s=$sections+40*$i;$va=[BitConverter]::ToUInt32($raw,$s+12)
  $n=[BitConverter]::ToUInt32($raw,$s+16)
  if($rva -ge $va -and ($rva-$va) -lt $n){$off=[BitConverter]::ToUInt32($raw,$s+20)+$rva-$va;break}
 }
 if($off -lt 0){throw "RVA unmapped $address"}
 for($j=0;$j -lt $bytes.Count;$j++){if($bytes[$j] -ne $raw[$off+$j]){throw "Byte mismatch $address +$j"}}
}
$ev=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence.json') -Raw|ConvertFrom-Json
$instructions=0;$bytesTotal=0
foreach($f in $ev.functions){
 $lines=@($f.pages|ForEach-Object{$_.asm.lines})
 if($lines.Count -ne $f.total_instructions -or $f.asm.lines.Count -ne $lines.Count -or -not $f.cursor.done -or $f.cursor.cancelled){throw "Incomplete $($f.addr)"}
 $joined=0
 foreach($p in $f.pages){
  if($p.instruction_count -ne $p.asm.lines.Count -or $p.total_instructions -ne $lines.Count){throw "Page count $($f.addr)"}
  $joined+=$p.asm.lines.Count
  if($p.cursor.cancelled -or (-not $p.cursor.done -and $p.cursor.next -ne $joined)){throw "Cursor $($f.addr)"}
 }
 if($f.instruction_count -ne $joined){throw "Aggregate count $($f.addr)"}
 $bytes=@($f.original_bytes|ForEach-Object{$_.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)}})
 if($bytes.Count -ne $f.size){throw "Size $($f.addr)"}
 VerifyBytes $f.addr $bytes
 $instructions+=$lines.Count;$bytesTotal+=$bytes.Count
}
$rangeInstructions=0;$rangeBytes=0
foreach($r in $ev.code_ranges){
 $start=[Convert]::ToUInt64($r.addr.Substring(2),16)
 $end=[Convert]::ToUInt64($r.end_exclusive.Substring(2),16)
 foreach($line in $r.asm.lines){$a=[Convert]::ToUInt64($line.addr,16);if($a -lt $start -or $a -ge $end){throw 'Out-of-range line'}}
 if($r.asm.lines.Count -ne $r.observed_line_count -or $r.asm.lines[-1].instruction -ne 'retn'){throw 'Callback range incomplete'}
 $bytes=@($r.original_bytes.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)})
 if($bytes.Count -ne $end-$start){throw 'Callback byte span'}
 VerifyBytes $r.addr $bytes
 $rangeInstructions+=$r.asm.lines.Count;$rangeBytes+=$bytes.Count
}
$dataBytes=0
foreach($r in $ev.data_regions){
 $bytes=@($r.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)})
 VerifyBytes $r.addr $bytes
 $dataBytes+=$bytes.Count
}
[pscustomobject]@{Result='PASS';OriginalSHA256=$hash;Functions=$ev.functions.Count;Instructions=$instructions;OriginalBytes=$bytesTotal;DataRegions=$ev.data_regions.Count;OriginalDataBytes=$dataBytes;CallbackRangeInstructions=$rangeInstructions;CallbackRangeBytes=$rangeBytes}|ConvertTo-Json
