$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path 'artifacts/status-bootstrap-contract-tests' -Force | Out-Null
    $buildCommand = 'call scripts\setup-toolchain.cmd >nul 2>&1 && cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /c tests\KH2Trainer.Bridge.Tests\StatusBootstrapContractProductionCompile.cpp /Foartifacts\status-bootstrap-contract-tests\production.obj && cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE tests\KH2Trainer.Bridge.Tests\StatusBootstrapContractTests.cpp /Foartifacts\status-bootstrap-contract-tests\tests.obj /Feartifacts\status-bootstrap-contract-tests\tests.exe /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT && artifacts\status-bootstrap-contract-tests\tests.exe'
    & cmd.exe /d /c $buildCommand *> 'artifacts/status-bootstrap-contract-tests/run.txt'
    $result = $LASTEXITCODE
    Get-Content -LiteralPath 'artifacts/status-bootstrap-contract-tests/run.txt'
    if ($result -ne 0) { throw "STATUS bootstrap contract tests failed ($result)." }
}
finally { Pop-Location }
