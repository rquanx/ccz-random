[CmdletBinding()]
param(
    [string]$GameDir = $env:CCZ_GAME_DIR,
    [switch]$Clean,
    [switch]$RunTests,
    [switch]$SkipCopy
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $ProjectRoot ".venv-win10-py314\Scripts\python.exe"
$Version = (Get-Content (Join-Path $ProjectRoot "VERSION") -Raw).Trim()
$Spec = Get-ChildItem (Join-Path $ProjectRoot "packaging") -Filter "*.spec" |
    Sort-Object Length -Descending |
    Select-Object -First 1

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Build environment not found: $Python"
}
if ($null -eq $Spec) {
    throw "PyInstaller spec not found."
}

Push-Location $ProjectRoot
try {
    if ($RunTests) {
        & $Python "run_tests.py" "unit"
        if ($LASTEXITCODE -ne 0) {
            throw "Unit tests failed. Build stopped."
        }
    }

    $BuildArguments = @("-m", "PyInstaller", "--noconfirm")
    if ($Clean) {
        $BuildArguments += "--clean"
    }
    $BuildArguments += $Spec.FullName

    $StartedAt = Get-Date
    & $Python @BuildArguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $Output = Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "*.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $Output) {
        throw "Built executable not found."
    }

    if (-not $SkipCopy) {
        if ([string]::IsNullOrWhiteSpace($GameDir)) {
            $ExistingTarget = Get-ChildItem "E:\game\ccz" `
                -Recurse -File -Filter "2.10*.exe" -ErrorAction SilentlyContinue |
                Where-Object {
                    Test-Path -LiteralPath (
                        Join-Path $_.DirectoryName "Ekd5.exe"
                    )
                } |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($null -ne $ExistingTarget) {
                $GameDir = $ExistingTarget.DirectoryName
            }
        }
        if (
            [string]::IsNullOrWhiteSpace($GameDir) -or
            -not (Test-Path -LiteralPath $GameDir -PathType Container)
        ) {
            throw "Game directory not found. Set CCZ_GAME_DIR and retry."
        }

        $Targets = @(
            (Join-Path $GameDir $Output.Name),
            (Join-Path $GameDir "$($Output.BaseName)-$Version.exe")
        )
        foreach ($Target in $Targets) {
            Copy-Item -LiteralPath $Output.FullName `
                -Destination $Target -Force
        }
    }

    $Elapsed = (Get-Date) - $StartedAt
    $Hash = (
        Get-FileHash -LiteralPath $Output.FullName -Algorithm SHA256
    ).Hash
    Write-Host (
        "Built: {0}; elapsed: {1:N1}s; SHA-256: {2}" -f
        $Output.FullName,
        $Elapsed.TotalSeconds,
        $Hash
    )
}
finally {
    Pop-Location
}
