$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$setup=Join-Path $repo 'scripts/setup-toolchain.cmd'
$environment=& cmd.exe /d /c call $setup '>nul' '2>&1' '&&' set
if($LASTEXITCODE -ne 0){throw 'MSVC environment failed'}
foreach($line in $environment){$pos=$line.IndexOf('=');if($pos -gt 0){[Environment]::SetEnvironmentVariable($line.Substring(0,$pos),$line.Substring($pos+1),'Process')}}
$source=Join-Path $PSScriptRoot 'production_route_review.cpp'
$obj=Join-Path $PSScriptRoot 'production_route_review.obj'
$exe=Join-Path $PSScriptRoot 'production_route_review.exe'
$log=Join-Path $PSScriptRoot 'production-route.log'
& cl.exe /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE $source "/Fo$obj" "/Fe$exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT user32.lib 2>&1 | Tee-Object -FilePath $log
if($LASTEXITCODE -ne 0){throw 'Independent production fixture compile failed'}
& $exe 2>&1 | Tee-Object -FilePath $log -Append
if($LASTEXITCODE -ne 0){throw 'Independent production fixture failed'}
