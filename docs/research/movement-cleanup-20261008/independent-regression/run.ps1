$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$root=[IO.Path]::GetFullPath($PSScriptRoot)
$suites=@('CombatGuardTests','GameplayStateGuardTests','MovementTransactionTests','PlayerBridgeTests')
$copied=@()
foreach($variant in @('fixed','regressed')) {
    $bridge=Join-Path $root "$variant/src/KH2Trainer.Bridge"
    $tests=Join-Path $root "$variant/tests/KH2Trainer.Bridge.Tests"
    New-Item -ItemType Directory -Path $bridge,$tests,(Join-Path $root "$variant/bin") -Force | Out-Null
    foreach($file in Get-ChildItem -LiteralPath (Join-Path $repo 'src/KH2Trainer.Bridge') -File | Where-Object { $_.Extension -in @('.cpp','.h','.inl') }) {
        $target=Join-Path $bridge $file.Name
        Copy-Item -LiteralPath $file.FullName -Destination $target
        if($variant -eq 'fixed') {
            $copied += [ordered]@{path='src/KH2Trainer.Bridge/'+$file.Name;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()}
        }
    }
    foreach($suite in $suites) {
        $source=Join-Path $repo "tests/KH2Trainer.Bridge.Tests/$suite.cpp"
        $target=Join-Path $tests "$suite.cpp"
        Copy-Item -LiteralPath $source -Destination $target
        if($variant -eq 'fixed') {
            $copied += [ordered]@{path="tests/KH2Trainer.Bridge.Tests/$suite.cpp";sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()}
        }
    }
}
$mutant=Join-Path $root 'regressed/src/KH2Trainer.Bridge/MovementTransactionSupport.inl'
$text=[IO.File]::ReadAllText($mutant)
$needle='access==Access::Cleanup?gameplay_state::InspectNative(c):gameplay_state::Inspect(c)'
$replacement='access==Access::Cleanup?gameplay_state::Inspect(c):gameplay_state::Inspect(c)'
if(([regex]::Matches($text,[regex]::Escape($needle))).Count -ne 1){throw 'Mutation site must be unique'}
$mutated=$text.Replace($needle,$replacement)
[IO.File]::WriteAllText($mutant,$mutated,[Text.UTF8Encoding]::new($false))
$mismatches=@()
foreach($entry in $copied) {
    $fixed=Join-Path $root ('fixed/'+$entry.path)
    $regressed=Join-Path $root ('regressed/'+$entry.path)
    if((Get-FileHash -LiteralPath $fixed).Hash -ne (Get-FileHash -LiteralPath $regressed).Hash){$mismatches+=$entry.path}
}
if($mismatches.Count -ne 1 -or $mismatches[0] -ne 'src/KH2Trainer.Bridge/MovementTransactionSupport.inl'){throw 'Unexpected variant difference'}

$saved=[Environment]::GetEnvironmentVariables('Process')
$results=@()
try {
    $toolchain=Join-Path $repo 'scripts/setup-toolchain.cmd'
    $environment=& cmd.exe /d /c call $toolchain '>nul' '2>&1' '&&' set
    if($LASTEXITCODE -ne 0){throw 'MSVC toolchain setup failed'}
    foreach($line in $environment){$n=$line.IndexOf('=');if($n -gt 0){[Environment]::SetEnvironmentVariable($line.Substring(0,$n),$line.Substring($n+1),'Process')}}
    $common=@('/nologo','/std:c++17','/O2','/W4','/MT','/EHsc','/DUNICODE','/D_UNICODE')
    foreach($variant in @('fixed','regressed')) {
        $selected=if($variant -eq 'fixed'){$suites}else{@('CombatGuardTests')}
        foreach($suite in $selected) {
            $source=Join-Path $root "$variant/tests/KH2Trainer.Bridge.Tests/$suite.cpp"
            $obj=Join-Path $root "$variant/bin/$suite.obj"
            $exe=Join-Path $root "$variant/bin/$suite.exe"
            $compileLog=Join-Path $root "$variant-$suite-compile.txt"
            $runLog=Join-Path $root "$variant-$suite-run.txt"
            $libraries=@(if($suite -in @('CombatGuardTests','PlayerBridgeTests')){'user32.lib'})
            & cl.exe @common $source "/Fo$obj" "/Fe$exe" '/link' '/INCREMENTAL:NO' '/DYNAMICBASE' '/NXCOMPAT' @libraries 2>&1 | Tee-Object -FilePath $compileLog
            $compileExit=$LASTEXITCODE
            if($compileExit -ne 0){throw "Compile failed: $variant $suite"}
            & $exe 2>&1 | Tee-Object -FilePath $runLog
            $runExit=$LASTEXITCODE
            $results += [ordered]@{variant=$variant;suite=$suite;compileExitCode=$compileExit;exitCode=$runExit;binarySha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLower();compileLog=[IO.Path]::GetRelativePath($root,$compileLog);runLog=[IO.Path]::GetRelativePath($root,$runLog)}
            if($variant -eq 'fixed' -and $runExit -ne 0){throw "Fixed suite failed: $suite"}
            if($variant -eq 'regressed' -and $runExit -eq 0){throw 'Regression mutation was not detected'}
        }
    }
} finally {
    foreach($name in @([Environment]::GetEnvironmentVariables('Process').Keys)) {
        if(-not $saved.Contains($name)){[Environment]::SetEnvironmentVariable($name,$null,'Process')}
    }
    foreach($entry in $saved.GetEnumerator()){[Environment]::SetEnvironmentVariable($entry.Key,$entry.Value,'Process')}
}
[ordered]@{date='2026-10-08';kind='Isolated current-source regression mutation, not a historical release build';mutation=[ordered]@{path='src/KH2Trainer.Bridge/MovementTransactionSupport.inl';from=$needle;to=$replacement;variantDifferences=$mismatches;regressedSha256=(Get-FileHash -LiteralPath $mutant -Algorithm SHA256).Hash.ToLower()};copiedSources=$copied;results=$results} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $root 'result.json') -Encoding utf8
