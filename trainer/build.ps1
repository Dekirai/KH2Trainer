param(
    [switch]$FrameworkDependent,
    [string]$OutputDirectory,
    [string]$AssetGameDirectory
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $taskRoot "work\trainer\packages\$taskStamp" }
$taskPackage = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $taskPackage) { throw 'Choose a new output directory so stale files cannot enter the package.' }
$taskLogs = Join-Path $taskRoot "work\trainer\build-logs\$taskStamp"
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$LogName) {
    & $Program @Arguments 2>&1 | Tee-Object -FilePath (Join-Path $taskLogs $LogName) | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE. See $taskLogs\$LogName" }
}
function Get-NativeSourceFingerprint {
    return ((Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'Native') -File |
        Where-Object Extension -in @('.cpp','.h','.inl') | Sort-Object Name |
        ForEach-Object { $_.Name + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n")
}
$taskPython = Get-Command py -ErrorAction SilentlyContinue
$taskPythonArgs = @('-3')
if (-not $taskPython) { $taskPython = Get-Command python -ErrorAction Stop; $taskPythonArgs = @() }
Push-Location $taskRoot
try {
    $taskNativeFingerprint = Get-NativeSourceFingerprint
    Invoke-Checked (Join-Path $PSScriptRoot 'build-native.cmd') @() 'native-build.txt'
    Invoke-Checked $taskPython.Source ($taskPythonArgs + @((Join-Path $PSScriptRoot 'assemble_data.py'))) 'catalog.txt'
    $taskTests = Get-ChildItem -LiteralPath (Join-Path $taskRoot 'work\trainer\tests') -Filter 'build_*_tests.cmd' -File | Sort-Object Name
    foreach ($taskTest in $taskTests) { Invoke-Checked $taskTest.FullName @() ($taskTest.BaseName + '.txt') }
    $taskCoreArgs = @('run','--project', (Join-Path $PSScriptRoot 'KH2Trainer.Tests\KH2Trainer.Tests.csproj'), '-c','Release','--', (Join-Path $PSScriptRoot 'KH2Trainer\Data\features.json'))
    if($AssetGameDirectory) { $taskCoreArgs += [IO.Path]::GetFullPath($AssetGameDirectory) }
    Invoke-Checked 'dotnet' $taskCoreArgs 'core-tests.txt'
    Invoke-Checked 'dotnet' @('run','--project',(Join-Path $taskRoot 'work\trainer\ui-verification\UiVerification.csproj'),'-c','Release','--','--fixture',(Join-Path $taskLogs 'OffscreenUi')) 'offscreen-ui.txt'
    if ((Get-NativeSourceFingerprint) -ne $taskNativeFingerprint) { throw 'Native sources changed during compilation/tests. Run the build again from a stable source state.' }
    $taskSelfContained = if ($FrameworkDependent) { 'false' } else { 'true' }
    Invoke-Checked 'dotnet' @('publish', (Join-Path $PSScriptRoot 'KH2Trainer\KH2Trainer.csproj'), '-c','Release','-r','win-x64','--self-contained',$taskSelfContained,'-p:PublishSingleFile=true','-p:IncludeNativeLibrariesForSelfExtract=true','-p:DebugType=none','-p:DebugSymbols=false','-o',$taskPackage,'--nologo','-v:minimal') 'publish.txt'
    $taskSmoke = Join-Path $taskPackage 'PackageCheck.json'
    Invoke-Checked (Join-Path $taskPackage 'KH2_Trainer.exe') @('--verify-package', $taskSmoke) 'package-check.txt'
    $taskSmokeResult = Get-Content -LiteralPath $taskSmoke -Raw | ConvertFrom-Json
    $taskBridgeHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'Native\build\KH2Trainer.Bridge.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $taskSmokeResult.success -or $taskSmokeResult.embeddedBridgeSha256 -ne $taskBridgeHash) { throw 'Packaged native bridge checksum does not match the compiled DLL.' }
    Invoke-Checked $taskPython.Source ($taskPythonArgs + @((Join-Path $PSScriptRoot 'generate_manual.py'),'--output',(Join-Path $taskPackage 'UserGuide.html'))) 'manual.txt'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'BUILD.txt') -Destination $taskPackage
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'KH2Trainer\Data\features.json') -Destination (Join-Path $taskPackage 'FeatureEvidence.json')
    Copy-Item -LiteralPath $taskLogs -Destination (Join-Path $taskPackage 'Validation') -Recurse

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $taskSourceZip = [IO.Compression.ZipFile]::Open((Join-Path $taskPackage 'Source.zip'), [IO.Compression.ZipArchiveMode]::Create)
    try {
        $taskSources = @(Get-ChildItem -LiteralPath $PSScriptRoot -File -Recurse | Where-Object {
            $_.FullName -notmatch '[\\/](bin|obj|build)[\\/]' -and $_.Extension -in @('.cs','.csproj','.props','.xaml','.manifest','.cpp','.h','.inl','.json','.py','.ps1','.cmd','.txt')
        })
        $taskSources += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'work\trainer\tests') -File -Recurse | Where-Object {
            $_.FullName -notmatch '[\\/](bin|obj)[\\/]' -and $_.Extension -in @('.cpp','.cmd','.cs','.csproj')
        })
        $taskSources += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'work\trainer\ui-verification') -File | Where-Object Extension -in @('.cs','.csproj'))
        $taskSources += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'work\trainer\research') -File -Recurse | Where-Object Extension -in @('.json','.txt','.py'))
        foreach ($taskFile in $taskSources) {
            $taskRelative = $taskFile.FullName.Substring($taskRoot.Length + 1).Replace('\','/')
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($taskSourceZip, $taskFile.FullName, $taskRelative, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    } finally { $taskSourceZip.Dispose() }
    $taskChecks = [ordered]@{
        builtAt = (Get-Date).ToUniversalTime().ToString('o'); architecture = 'win-x64'; selfContained = -not $FrameworkDependent
        nativeTestSuites = @($taskTests.BaseName); syntheticTests = 'passed'; liveGameplay = 'not yet tested'; visualReview = 'Feature cards, Asset Explorer, asset fingerprints and Game Messages offscreen renders and binding checks; live UI/gameplay pending'
        scope = 'Synthetic tests and build validation do not prove live gameplay behavior.'
        nativeSourceFingerprint = $taskNativeFingerprint
    }
    $taskChecks | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskPackage 'Validation.json') -Encoding utf8
    $taskFiles = @(Get-ChildItem -LiteralPath $taskPackage -File -Recurse | ForEach-Object {
        [ordered]@{ path = $_.FullName.Substring($taskPackage.Length+1).Replace('\','/'); length = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $taskFiles | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskPackage 'Manifest.json') -Encoding utf8
    Set-Content -LiteralPath (Join-Path $taskRoot 'work\trainer\CURRENT_PACKAGE.txt') -Value $taskPackage -Encoding utf8
    Write-Host "Development package: $taskPackage"
} finally { Pop-Location }
