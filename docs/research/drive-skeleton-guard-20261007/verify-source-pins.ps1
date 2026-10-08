$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$source=Get-Content -LiteralPath (Join-Path $repo 'src/KH2Trainer.Bridge/DriveWeaponSupport.inl') -Raw
$e=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'evidence.json') -Raw | ConvertFrom-Json
# First independently compare all stored original bytes to the original PE.
$base=& (Join-Path $PSScriptRoot 'verify-evidence.ps1') | ConvertFrom-Json
$pins=@{
 kSkeletonKeyBytes='3B5C10';kSkeletonJointBytes='3D7620';kSkeletonCompareBytes='3EAAD0'
 kSkeletonFindBytes='3EAAE0';kSkeletonInstallBytes='3EAB20'
}
$total=0
foreach($name in $pins.Keys) {
 $m=[regex]::Match($source,([regex]::Escape($name)+'\[\]\s*=\s*\{([^}]+)\}'))
 if(-not $m.Success){throw "Missing pin $name"}
 $bytes=@([regex]::Matches($m.Groups[1].Value,'0x[0-9a-fA-F]+')|ForEach-Object{[Convert]::ToByte($_.Value.Substring(2),16)})
 $f=$e.functions | Where-Object rva -eq $pins[$name]
 $original=@($f.original_bytes|ForEach-Object{$_.data.Split(' ',[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{[Convert]::ToByte($_.Substring(2),16)}})
 if($bytes.Count -ne $f.size -or $bytes.Count -ne $original.Count){throw "Pin not full body: $name"}
 for($i=0;$i -lt $bytes.Count;$i++){if($bytes[$i] -ne $original[$i]){throw "Pin byte mismatch: $name +$i"}}
 $total+=$bytes.Count
}
$base | Add-Member -NotePropertyName RuntimePins -NotePropertyValue $pins.Count
$base | Add-Member -NotePropertyName RuntimePinBytes -NotePropertyValue $total
$base | ConvertTo-Json
