<#
.SYNOPSIS
  Builds and runs the native bridge test suites with the MSVC toolchain.
.DESCRIPTION
  Each suite compiles one test source, which includes the bridge sources it checks,
  and runs it against synthetic memory. Some suites also compile the production
  variant of their feature to prove it builds without the test hooks.
  Outputs go to bin\. Returns one object per suite and throws if any suite fails.
.PARAMETER LogDirectory
  Optional folder that receives one native-<suite>.txt log per suite.
.PARAMETER Suite
  Optional suite names to run; all suites run by default.
#>
param(
    [string]$LogDirectory,
    [string[]]$Suite
)
$ErrorActionPreference = 'Stop'

# ProductionSource/ProductionDefine: extra compile-only check of the shipping code path.
$suites = @(
    @{ Name = 'ActorMovementGuardTests' }
    @{ Name = 'AudioGuardTests' }
    @{ Name = 'CameraExtraGuardTests' }
    @{ Name = 'CollisionGuardTests' }
    @{ Name = 'CombatGuardTests' }
    @{ Name = 'DamageTuningTests' }
    @{ Name = 'DisplayGuardTests'; ProductionSource = 'DisplayProductionCompile.cpp' }
    @{ Name = 'DriveGuardTests' }
    @{ Name = 'GummiEditorGuardTests' }
    @{ Name = 'GummiExtraGuardTests' }
    @{ Name = 'GummiGuardTests' }
    @{ Name = 'GummiHistoryGuardTests' }
    @{ Name = 'GummiProjectileGuardTests' }
    @{ Name = 'LootGuardTests' }
    @{ Name = 'MissionEventGuardTests' }
    @{ Name = 'MissionGuardTests' }
    @{ Name = 'MotionGuardTests' }
    @{ Name = 'PlayerBridgeTests'; Libraries = @('user32.lib') }
    @{ Name = 'ProgressionTests' }
    @{ Name = 'RenderGuardTests' }
    @{ Name = 'RendererAaTests'; ProductionDefine = 'AA_PRODUCTION_COMPILE' }
    @{ Name = 'RendererDiagnosticsTests'; ProductionDefine = 'RENDERER_PRODUCTION_COMPILE' }
    @{ Name = 'ShortcutTests'; Libraries = @('user32.lib') }
    @{ Name = 'SpatialAudioGuardTests' }
    @{ Name = 'TargetingGuardTests' }
    @{ Name = 'WindowDisplayTests'; ProductionDefine = 'WINDOW_DISPLAY_PRODUCTION_COMPILE' }
    @{ Name = 'WorldGuardTests'; Libraries = @('user32.lib') }
)
if ($Suite) {
    $unknown = @($Suite | Where-Object { $_ -notin $suites.Name })
    if ($unknown) { throw "Unknown native test suite: $($unknown -join ', ')" }
    $suites = @($suites | Where-Object { $_.Name -in $Suite })
}

$root = $PSScriptRoot
$output = Join-Path $root 'bin'
New-Item -ItemType Directory -Path $output -Force | Out-Null
if ($LogDirectory) { New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null }

# Runs a native program, mirrors its output to the console and a log, and returns its exit code.
function Invoke-Native([string]$Program, [string[]]$Arguments, [string]$Log) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue' # Compiler diagnostics on stderr are not script errors.
    try {
        & $Program @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log -Append | Write-Host
        return $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
}

# Imports the MSVC developer environment (cl, link, INCLUDE, LIB) into this process once.
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    $toolchain = [IO.Path]::GetFullPath((Join-Path $root '..\..\scripts\setup-toolchain.cmd'))
    $environment = & cmd.exe /d /c call $toolchain '>nul' '2>&1' '&&' set
    if ($LASTEXITCODE -ne 0) { throw 'The MSVC toolchain was not found. Install Visual Studio Build Tools with the C++ workload and a Windows SDK.' }
    foreach ($line in $environment) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) { [Environment]::SetEnvironmentVariable($line.Substring(0, $separator), $line.Substring($separator + 1), 'Process') }
    }
}

$common = @('/nologo', '/std:c++17', '/O2', '/W4', '/MT', '/EHsc', '/DUNICODE', '/D_UNICODE')
$linker = @('/link', '/INCREMENTAL:NO', '/DYNAMICBASE', '/NXCOMPAT')
$results = foreach ($test in $suites) {
    $name = $test.Name
    $log = if ($LogDirectory) { Join-Path $LogDirectory "native-$name.txt" } else { Join-Path $output "$name.log" }
    Set-Content -LiteralPath $log -Value "Native test suite $name" -Encoding utf8
    Write-Host "== $name"
    $source = Join-Path $root "$name.cpp"
    $exe = Join-Path $output "$name.exe"
    $code = 0
    if ($test.ProductionSource) {
        $code = Invoke-Native 'cl.exe' ($common + @('/c', (Join-Path $root $test.ProductionSource), "/Fo$(Join-Path $output "$name.Production.obj")")) $log
    }
    elseif ($test.ProductionDefine) {
        $code = Invoke-Native 'cl.exe' ($common + @("/D$($test.ProductionDefine)", '/c', $source, "/Fo$(Join-Path $output "$name.Production.obj")")) $log
    }
    if ($code -eq 0) { $code = Invoke-Native 'cl.exe' ($common + @($source, "/Fo$(Join-Path $output "$name.obj")", "/Fe$exe") + $linker + @($test.Libraries | Where-Object { $_ })) $log }
    if ($code -eq 0) { $code = Invoke-Native $exe @() $log }
    [pscustomobject]@{ Name = $name; Passed = ($code -eq 0); ExitCode = $code; Log = $log }
}

$failed = @($results | Where-Object { -not $_.Passed })
$results
if ($failed) { throw "Native test suites failed: $($failed.Name -join ', ')" }
Write-Host "All $(@($results).Count) native test suites passed."
