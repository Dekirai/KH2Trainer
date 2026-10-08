$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'scripts\package-research.ps1')
$fixture = Join-Path $root ('artifacts\research-package-test-' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $fixture 'docs'
$destination = Join-Path $fixture 'Research'
$keep = @('report.md', 'research\evidence.json', 'research\original.patch', 'research\baseline.zip', 'research\LICENSE')
$omit = @('scratch.i64', 'scratch.id0', 'research\scratch.ID1', 'research\scratch.id2', 'research\scratch.nam',
    'research\scratch.til', 'research\scratch.idb', 'research\test.exe', 'research\module.dll',
    'research\module.obj', 'research\module.pdb', 'research\artifacts\trace.json',
    'research\__pycache__\verify.pyc', 'research\bin\test.txt', 'research\obj\cache.json')
foreach ($relative in @($keep) + @($omit)) {
    $path = Join-Path $source $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, 'fixture: ' + $relative)
}
Copy-ResearchPackage -Source $source -Destination $destination
$checks = 0
foreach ($relative in $keep) {
    $checks++
    $original = Join-Path $source $relative
    $copy = Join-Path $destination $relative
    if (-not (Test-Path -LiteralPath $copy) -or
        (Get-FileHash -LiteralPath $original).Hash -ne (Get-FileHash -LiteralPath $copy).Hash) { throw "Evidence missing or changed: $relative" }
}
foreach ($relative in $omit) {
    $checks++
    if (Test-Path -LiteralPath (Join-Path $destination $relative)) { throw "Working file entered package: $relative" }
    if (-not (Test-Path -LiteralPath (Join-Path $source $relative))) { throw "Original was removed: $relative" }
}
$checks++
if (@(Get-ChildItem -LiteralPath $destination -File -Recurse).Count -ne $keep.Count) { throw 'Unexpected packaged files.' }
$rejected = $false
try { Copy-ResearchPackage -Source $source -Destination $destination } catch { $rejected = $true }
$checks++
if (-not $rejected) { throw 'Existing destination was accepted.' }
Write-Output "Research package: $checks checks, 0 failures. Fixture retained at $fixture"
