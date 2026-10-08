param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repo 'artifacts\allocator-blocks-probe-20261008' }
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $output -Force | Out-Null
& py -3 -B (Join-Path $PSScriptRoot 'verify.py')
if ($LASTEXITCODE -ne 0) { throw 'Original-body verification failed.' }
$saved = [Environment]::GetEnvironmentVariables('Process')
try {
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue) -or $env:VSCMD_ARG_TGT_ARCH -ne 'x64') {
        $toolchain = Join-Path $repo 'scripts\setup-toolchain.cmd'
        $environment = & cmd.exe /d /c call $toolchain '>nul' '2>&1' '&&' set
        if ($LASTEXITCODE -ne 0) { throw 'MSVC x64 toolchain setup failed.' }
        foreach ($line in $environment) {
            $separator = $line.IndexOf('=')
            if ($separator -gt 0) { [Environment]::SetEnvironmentVariable($line.Substring(0,$separator),$line.Substring($separator+1),'Process') }
        }
    }
    $exe = Join-Path $output 'AllocatorProbe.exe'
    $obj = Join-Path $output 'AllocatorProbe.obj'
    $log = Join-Path $output 'probe.log'
    & cl.exe /nologo /std:c++17 /O2 /W4 /WX /MT /EHsc (Join-Path $PSScriptRoot 'AllocatorProbe.cpp') "/Fe:$exe" "/Fo:$obj" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT 2>&1 | Tee-Object -FilePath (Join-Path $output 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Allocator probe build failed.' }
    & $exe 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw 'Allocator probe failed.' }
    Copy-Item -LiteralPath $log -Destination (Join-Path $PSScriptRoot 'probe.log')
}
finally {
    $current = [Environment]::GetEnvironmentVariables('Process')
    foreach ($key in $current.Keys) { if (-not $saved.Contains($key)) { [Environment]::SetEnvironmentVariable($key,$null,'Process') } }
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
}
