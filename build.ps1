<#
.SYNOPSIS
  Builds, tests and packages the trainer.
.DESCRIPTION
  Compiles the native bridge, runs the native, core, Twitch and offscreen UI tests,
  publishes a single-file x64 executable and writes a validated package to
  artifacts\packages\<timestamp> (or -OutputDirectory).
.PARAMETER FrameworkDependent
  Publish without the .NET runtime (the target needs the .NET 8 Desktop Runtime).
.PARAMETER OutputDirectory
  A new folder for the package.
.PARAMETER AssetGameDirectory
  Optional KH collection folder for read-only retail asset checks.
#>
[CmdletBinding()]
param(
    [switch]$FrameworkDependent,
    [string]$OutputDirectory,
    [string]$AssetGameDirectory
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. (Join-Path $root 'scripts\package-research.ps1')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$artifacts = Join-Path $root 'artifacts'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $artifacts "packages\$stamp" }
# Relative paths are relative to the PowerShell location, not the process directory.
$package = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if (Test-Path -LiteralPath $package) { throw 'Choose a new output directory so stale files cannot enter the package.' }
$logs = Join-Path $artifacts "build-logs\$stamp"
New-Item -ItemType Directory -Path $logs -Force | Out-Null

$app = Join-Path $root 'src\KH2Trainer'
$bridge = Join-Path $root 'src\KH2Trainer.Bridge'
$features = Join-Path $app 'Data\features.json'

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$LogName) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue' # Tool output on stderr is not a script error; the exit code decides.
    try { & $Program @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath (Join-Path $logs $LogName) | Write-Host }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE. See $logs\$LogName" }
}
function Get-NativeSourceFingerprint {
    return ((Get-ChildItem -LiteralPath $bridge -File |
        Where-Object Extension -in @('.cpp', '.h', '.inl') | Sort-Object Name |
        ForEach-Object { $_.Name + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n")
}
$python = Get-Command py -ErrorAction SilentlyContinue
$pythonArgs = @('-3')
if (-not $python) { $python = Get-Command python -ErrorAction Stop; $pythonArgs = @() }

Push-Location $root
try {
    & (Join-Path $root 'tests\Test-ResearchPackage.ps1') | Tee-Object -FilePath (Join-Path $logs 'research-package-test.txt') | Write-Host
    $nativeFingerprint = Get-NativeSourceFingerprint
    Invoke-Checked (Join-Path $bridge 'build.cmd') @() 'native-build.txt'
    $nativeResults = & (Join-Path $root 'tests\KH2Trainer.Bridge.Tests\run-tests.ps1') -LogDirectory $logs

    $coreArgs = @('run', '--project', (Join-Path $root 'tests\KH2Trainer.Core.Tests\KH2Trainer.Core.Tests.csproj'), '-c', 'Release', '--', $features)
    if ($AssetGameDirectory) { $coreArgs += $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AssetGameDirectory) }
    Invoke-Checked 'dotnet' $coreArgs 'core-tests.txt'
    Invoke-Checked 'dotnet' @('run', '--project', (Join-Path $root 'tests\KH2Trainer.Twitch.Tests\KH2Trainer.Twitch.Tests.csproj'), '-c', 'Release', '--', $features) 'twitch-tests.txt'
    Invoke-Checked 'dotnet' @('run', '--project', (Join-Path $root 'tests\KH2Trainer.UiTests\KH2Trainer.UiTests.csproj'), '-c', 'Release', '--', '--fixture', (Join-Path $logs 'OffscreenUi')) 'offscreen-ui.txt'
    if ((Get-NativeSourceFingerprint) -ne $nativeFingerprint) { throw 'Native sources changed during compilation/tests. Run the build again from a stable source state.' }

    $selfContained = if ($FrameworkDependent) { 'false' } else { 'true' }
    Invoke-Checked 'dotnet' @('publish', (Join-Path $app 'KH2Trainer.csproj'), '-c', 'Release', '-r', 'win-x64', '--self-contained', $selfContained, '-p:SkipNativeBridgeBuild=true',
        '-p:PublishSingleFile=true', '-p:IncludeNativeLibrariesForSelfExtract=true', '-p:DebugType=none', '-p:DebugSymbols=false', '-o', $package, '--nologo', '-v:minimal') 'publish.txt'
    $smoke = Join-Path $package 'PackageCheck.json'
    Invoke-Checked (Join-Path $package 'KH2_Trainer.exe') @('--verify-package', $smoke) 'package-check.txt'
    $smokeResult = Get-Content -LiteralPath $smoke -Raw | ConvertFrom-Json
    $bridgeHash = (Get-FileHash -LiteralPath (Join-Path $bridge 'bin\KH2Trainer.Bridge.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $smokeResult.success -or $smokeResult.embeddedBridgeSha256 -ne $bridgeHash) { throw 'Packaged native bridge checksum does not match the compiled DLL.' }

    Invoke-Checked $python.Source ($pythonArgs + @((Join-Path $root 'scripts\generate-manual.py'), '--output', (Join-Path $package 'UserGuide.html'))) 'manual.txt'
    Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $package
    Copy-Item -LiteralPath $features -Destination (Join-Path $package 'FeatureEvidence.json')
    Copy-ResearchPackage -Source (Join-Path $root 'docs') -Destination (Join-Path $package 'Research')
    Copy-Item -LiteralPath $logs -Destination (Join-Path $package 'Validation') -Recurse

    # Source archive: the solution, scripts, sources and tests, without build outputs.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $sourceZip = [IO.Compression.ZipFile]::Open((Join-Path $package 'Source.zip'), [IO.Compression.ZipArchiveMode]::Create)
    try {
        $extensions = @('.sln', '.md', '.ps1', '.props', '.cs', '.csproj', '.xaml', '.manifest', '.cpp', '.h', '.inl', '.json', '.jsonl', '.py', '.cmd', '.html', '.zip', '.txt')
        $sources = @(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Extension -in $extensions -or $_.Name -eq '.gitignore' })
        foreach ($folder in 'src', 'tests', 'scripts', 'docs') {
            $sources += @(Get-ChildItem -LiteralPath (Join-Path $root $folder) -File -Recurse | Where-Object {
                $_.FullName -notmatch '[\\/](bin|obj|artifacts|__pycache__|\.git|\.vs)[\\/]' -and
                ($_.Extension -in $extensions -or $_.Name -in @('LICENSE', 'NOTICE')) })
        }
        foreach ($file in $sources) {
            $relative = $file.FullName.Substring($root.Length + 1).Replace('\', '/')
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($sourceZip, $file.FullName, $relative, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    } finally { $sourceZip.Dispose() }

    $checks = [ordered]@{
        builtAt = (Get-Date).ToUniversalTime().ToString('o'); architecture = 'win-x64'; selfContained = -not $FrameworkDependent
        nativeTestSuites = @($nativeResults.Name); syntheticTests = 'passed'; liveGameplay = 'not yet tested'
        visualReview = 'Feature pages, Twitch page, Asset Explorer, BDX script inspection, asset fingerprints and Game Messages offscreen renders and binding checks; live UI/gameplay and live Twitch pending'
        scope = 'Synthetic tests and build validation do not prove live gameplay behavior.'
        nativeSourceFingerprint = $nativeFingerprint
    }
    $checks | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'Validation.json') -Encoding utf8
    $files = @(Get-ChildItem -LiteralPath $package -File -Recurse | ForEach-Object {
        [ordered]@{ path = $_.FullName.Substring($package.Length + 1).Replace('\', '/'); length = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $files | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'Manifest.json') -Encoding utf8
    Set-Content -LiteralPath (Join-Path $artifacts 'CURRENT_PACKAGE.txt') -Value $package -Encoding utf8
    Write-Host "Development package: $package"
} finally { Pop-Location }
