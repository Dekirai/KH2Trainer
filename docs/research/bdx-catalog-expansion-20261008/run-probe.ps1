param([string]$OutputDirectory, [switch]$Check)
$ErrorActionPreference = 'Stop'
$studyDirectory = $PSScriptRoot
$repositoryRoot = [System.IO.DirectoryInfo]::new($studyDirectory)
while ($null -ne $repositoryRoot -and -not (Test-Path -LiteralPath (Join-Path $repositoryRoot.FullName 'Directory.Build.props'))) { $repositoryRoot = $repositoryRoot.Parent }
if ($null -eq $repositoryRoot) { throw 'Repository root not found.' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repositoryRoot.FullName 'artifacts/bdx-catalog-expansion-study-probe' }
$probeOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($probeOutput.StartsWith([System.IO.Path]::GetFullPath($studyDirectory) + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or $probeOutput -eq [System.IO.Path]::GetFullPath($studyDirectory)) { throw 'Build outputs must remain outside the frozen study.' }
[void](New-Item -ItemType Directory -Path $probeOutput -Force)
$probeIntermediate = (Join-Path $probeOutput 'obj') + [System.IO.Path]::DirectorySeparatorChar
$probeBinary = Join-Path $probeOutput 'bin'
$buildOutput = & dotnet build (Join-Path $studyDirectory 'Probe.csproj') --configuration Release --output $probeBinary "-p:BaseIntermediateOutputPath=$probeIntermediate" "-p:MSBuildProjectExtensionsPath=$probeIntermediate" --nologo 2>&1
$buildExit = $LASTEXITCODE
$buildOutput | Set-Content -LiteralPath (Join-Path $probeOutput 'build.log') -Encoding utf8
if ($buildExit -ne 0) { throw "Probe build failed; see $probeOutput/build.log" }
$productData = Join-Path $repositoryRoot.FullName 'src/KH2Trainer.Core/Data/BdxNativeCalls.json'
$probeText = (& dotnet (Join-Path $probeBinary 'Probe.dll') $productData) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Compiled probe failed.' }
$observed = $probeText | ConvertFrom-Json
if ($observed.success -ne $true -or $observed.checks -ne 1692) { throw 'Unexpected probe result.' }
$probeText | Set-Content -LiteralPath (Join-Path $probeOutput 'result.json') -Encoding utf8
if ($Check) {
    $expected = Get-Content -Raw -LiteralPath (Join-Path $studyDirectory 'compiled-probe.json') | ConvertFrom-Json
    if (($expected | ConvertTo-Json -Depth 10 -Compress) -ne ($observed | ConvertTo-Json -Depth 10 -Compress)) { throw 'Compiled probe differs from the frozen receipt.' }
}
Write-Output $probeText
