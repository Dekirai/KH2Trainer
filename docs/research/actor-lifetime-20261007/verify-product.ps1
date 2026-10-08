$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$e=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence.json') -Raw|ConvertFrom-Json
$p=Get-Content -LiteralPath (Join-Path $repo 'src/KH2Trainer.Bridge/ActorLifetimePins.inl') -Raw
$entries=[regex]::Matches($p,'constexpr BYTE pin_([0-9a-f]+)\[\]\s*=\s*\{([^}]*)\};')
$total=0
foreach($entry in $entries){
 $rva=$entry.Groups[1].Value
 $f=@($e.functions|Where-Object{ $_.rva -eq ('0x'+$rva) })
 if($f.Count -ne 1){throw "Missing unique full body $rva"}
 $actual=@([regex]::Matches($entry.Groups[2].Value,'0x([0-9a-fA-F]{2})')|ForEach-Object{[Convert]::ToByte($_.Groups[1].Value,16)})
 $expected=@($f[0].original_bytes|ForEach-Object{$_.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)}})
 if($actual.Count -ne $f[0].size -or $actual.Count -ne $expected.Count){throw "Size $rva"}
 for($i=0;$i -lt $actual.Count;$i++){if($actual[$i] -ne $expected[$i]){throw "Mismatch $rva +$i"}}
 $total+=$actual.Count
}
if($entries.Count -ne 12){throw 'Expected exactly12 complete-body pins'}
$nativeVerify=& (Join-Path $PSScriptRoot 'verify.ps1') | Out-String | ConvertFrom-Json
if($nativeVerify.Result -ne 'PASS'){throw 'Original PE verification failed'}
[pscustomobject]@{Result='PASS';CompleteBodyPins=$entries.Count;PinnedOriginalBytes=$total;OriginalSHA256=$nativeVerify.OriginalSHA256;SourceSHA256=(Get-FileHash -LiteralPath (Join-Path $repo 'src/KH2Trainer.Bridge/ActorLifetimeSupport.inl') -Algorithm SHA256).Hash;PinsSHA256=(Get-FileHash -LiteralPath (Join-Path $repo 'src/KH2Trainer.Bridge/ActorLifetimePins.inl') -Algorithm SHA256).Hash;TestsSHA256=(Get-FileHash -LiteralPath (Join-Path $repo 'tests/KH2Trainer.Bridge.Tests/ActorLifetimeTests.cpp') -Algorithm SHA256).Hash}|ConvertTo-Json
