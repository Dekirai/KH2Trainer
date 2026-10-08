# Documentation packages include evidence and reports, without local analysis/build state.
# Source files are never removed or changed by these functions.
function Get-ResearchPackageFiles {
    param([Parameter(Mandatory = $true)][string]$Source)
    $researchRoot = (Resolve-Path -LiteralPath $Source).ProviderPath.TrimEnd([char[]]'\/')
    if (-not (Test-Path -LiteralPath $researchRoot -PathType Container)) { throw 'Research source must be a directory.' }
    $workingExtensions = @('.i64', '.idb', '.id0', '.id1', '.id2', '.nam', '.til', '.pyc', '.pyo', '.exe', '.dll', '.obj', '.pdb')
    Get-ChildItem -LiteralPath $researchRoot -File -Recurse | Where-Object {
        $relative = $_.FullName.Substring($researchRoot.Length + 1)
        $relative -notmatch '(^|[\\/])(artifacts|bin|obj|__pycache__|\.git|\.vs)([\\/]|$)' -and
            $_.Extension -notin $workingExtensions
    } | Sort-Object FullName
}

function Copy-ResearchPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $researchRoot = (Resolve-Path -LiteralPath $Source).ProviderPath.TrimEnd([char[]]'\/')
    $researchTarget = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
    if (Test-Path -LiteralPath $researchTarget) { throw 'Research destination must be new.' }
    $files = @(Get-ResearchPackageFiles -Source $researchRoot)
    New-Item -ItemType Directory -Path $researchTarget -ErrorAction Stop | Out-Null
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($researchRoot.Length + 1)
        $target = Join-Path $researchTarget $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target
    }
}
