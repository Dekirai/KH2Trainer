param(
 [string]$GameExe='E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe'
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$source=[IO.File]::ReadAllText((Join-Path $root 'src\KH2Trainer.Bridge\GameplayStateSupport.inl'))
$raw=[IO.File]::ReadAllBytes($GameExe)
$sha=[Security.Cryptography.SHA256]::Create()
try {$hash=([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant()} finally {$sha.Dispose()}
if($hash -ne '9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed'){throw "Wrong original EXE hash: $hash"}
$pe=[BitConverter]::ToInt32($raw,0x3c)
$count=[BitConverter]::ToUInt16($raw,$pe+6)
$optionalSize=[BitConverter]::ToUInt16($raw,$pe+20)
$sections=$pe+24+$optionalSize
function Offset([uint32]$rva) {
 for($i=0;$i -lt $count;$i++){
  $s=$sections+40*$i;$va=[BitConverter]::ToUInt32($raw,$s+12)
  $n=[BitConverter]::ToUInt32($raw,$s+16);$file=[BitConverter]::ToUInt32($raw,$s+20)
  if($rva -ge $va -and ($rva-$va) -lt $n){return [int]($file+$rva-$va)}
 }
 throw "RVA is not raw-backed: $rva"
}
$pinCount=0;$pinBytes=0
foreach($match in [regex]::Matches($source,'static const BYTE pin_([0-9A-F]+)\[\] = \{([\s\S]*?)\};')){
 $rva=[Convert]::ToUInt32($match.Groups[1].Value,16)
 $bytes=@([regex]::Matches($match.Groups[2].Value,'0x([0-9a-f]{2})')|ForEach-Object{[Convert]::ToByte($_.Groups[1].Value,16)})
 $off=Offset $rva
 for($j=0;$j -lt $bytes.Count;$j++){if($raw[$off+$j] -ne $bytes[$j]){throw "Pin differs RVA $($match.Groups[1].Value) byte$j"}}
 $pinCount++;$pinBytes+=$bytes.Count
}
$evidence=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'gameplay_state_evidence.json') -Raw|ConvertFrom-Json
$instructions=0;$evidenceBytes=0
foreach($f in $evidence.functions){
 $joined=@($f.pages|ForEach-Object{$_.asm.lines})
 if($joined.Count -ne $f.total_instructions -or $joined.Count -ne $f.asm.lines.Count){throw "Incomplete ASM: $($f.addr)"}
 if(-not $f.cursor.done -or $f.cursor.cancelled){throw "Incomplete outer cursor: $($f.addr)"}
 $next=0
 foreach($page in $f.pages){
  if($page.cursor.cancelled){throw "Cancelled page: $($f.addr)"}
  $next+=$page.asm.lines.Count
  if(-not $page.cursor.done -and $page.cursor.next -ne $next){throw "Page cursor mismatch: $($f.addr)"}
 }
 $bytes=@($f.original_bytes|ForEach-Object{ $_.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)}})
 if($bytes.Count -ne $f.size){throw "Evidence size: $($f.addr)"}
 $off=Offset ([Convert]::ToUInt32($f.rva,16))
 for($j=0;$j -lt $bytes.Count;$j++){if($bytes[$j] -ne $raw[$off+$j]){throw "Evidence differs: $($f.addr) byte$j"}}
 $instructions+=$joined.Count;$evidenceBytes+=$bytes.Count
}
$dataBytes=0
foreach($span in $evidence.data_spans){
 $rva=[uint32]([Convert]::ToUInt64($span.addr.Substring(2),16)-0x140000000L)
 $off=Offset $rva
 $bytes=@($span.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)})
 for($j=0;$j -lt $bytes.Count;$j++){if($bytes[$j] -ne $raw[$off+$j]){throw "Data evidence differs: $($span.addr) byte$j"}}
 $dataBytes+=$bytes.Count
}
[pscustomobject]@{OriginalSHA256=$hash;NativePins=$pinCount;PinnedBytes=$pinBytes;EvidenceFunctions=$evidence.functions.Count;Instructions=$instructions;EvidenceBytes=$evidenceBytes;DataBytes=$dataBytes;Result='PASS'}|ConvertTo-Json
