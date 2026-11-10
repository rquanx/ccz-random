[CmdletBinding()]
param(
    [string]$GameDir = $env:CCZ_GAME_DIR,
    [string]$SpecPath = "packaging\CCZ_真实随机内存快筛版.spec",
    [string]$OutputName = "2.2随机工具.exe",
    [switch]$Clean,
    [switch]$RunTests,
    [switch]$SkipCopy
)

$ErrorActionPreference = "Stop"

function Get-ReleaseHash([string]$Path) {
    # Works in both Windows PowerShell and PowerShell without module auto-load.
    $Algorithm = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.File]::OpenRead($Path)
    try {
        return [BitConverter]::ToString($Algorithm.ComputeHash($Stream)).Replace("-", "")
    }
    finally {
        $Stream.Dispose()
        $Algorithm.Dispose()
    }
}

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $ProjectRoot ".venv-win10-py314\Scripts\python.exe"
$Version = (Get-Content (Join-Path $ProjectRoot "VERSION") -Raw).Trim()
$SpecCandidate = if ([IO.Path]::IsPathRooted($SpecPath)) {
    $SpecPath
}
else {
    Join-Path $ProjectRoot $SpecPath
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Build environment not found: $Python"
}
if (-not (Test-Path -LiteralPath $SpecCandidate -PathType Leaf)) {
    throw "PyInstaller spec not found: $SpecCandidate"
}
$Spec = Get-Item -LiteralPath $SpecCandidate

$BuildLock = $null
Push-Location $ProjectRoot
try {
    $LockDirectory = Join-Path $ProjectRoot "build"
    New-Item -ItemType Directory -Path $LockDirectory -Force | Out-Null
    $BuildLock = [IO.File]::Open((Join-Path $LockDirectory ".release.lock"),
        [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if (-not $SkipCopy) {
        if ([string]::IsNullOrWhiteSpace($GameDir)) {
            throw "Specify -GameDir or CCZ_GAME_DIR. Automatic game directory selection is disabled."
        }
        & $Python "tools/release_support.py" $GameDir
        if ($LASTEXITCODE -ne 0) { throw "Game fingerprint validation failed." }
    }
    if ([IO.Path]::GetFileName($OutputName) -ne $OutputName -or -not $OutputName.EndsWith(".exe")) {
        throw "OutputName must be an executable file name."
    }
    $OutputPath = Join-Path $ProjectRoot "dist/$OutputName"
    # A failed or misconfigured build must never reuse an earlier executable.
    if (Test-Path -LiteralPath $OutputPath) { Remove-Item -LiteralPath $OutputPath }
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

    if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
        throw "Expected build executable not found: $OutputPath"
    }
    $Output = Get-Item -LiteralPath $OutputPath
    foreach ($Smoke in @("--smoke-startup", "--smoke-windowed-output", "--smoke-imports", "--smoke-changelog")) {
        $Process = Start-Process -FilePath $Output.FullName -ArgumentList $Smoke -WindowStyle Hidden -PassThru
        if (-not $Process.WaitForExit(60000)) {
            $Process.Kill()
            throw "Executable smoke timed out: $Smoke"
        }
        if ($Process.ExitCode -ne 0) { throw "Executable smoke failed: $Smoke" }
    }
    $Hash = Get-ReleaseHash $Output.FullName
    if (-not $SkipCopy) {
        & $Python "tools/release_support.py" $GameDir
        if ($LASTEXITCODE -ne 0) { throw "Game fingerprint changed during build." }
        $Targets = @(
            (Join-Path $GameDir $Output.Name),
            (Join-Path $GameDir "$($Output.BaseName)-$Version.exe")
        )
        foreach ($Target in $Targets) {
            Copy-Item -LiteralPath $Output.FullName `
                -Destination $Target -Force
            if ((Get-ReleaseHash $Target) -ne $Hash) {
                throw "Copied executable checksum mismatch: $Target"
            }
        }
    }

    $Elapsed = (Get-Date) - $StartedAt
    Write-Host (
        "Built: {0}; elapsed: {1:N1}s; SHA-256: {2}" -f
        $Output.FullName,
        $Elapsed.TotalSeconds,
        $Hash
    )
}
finally {
    if ($null -ne $BuildLock) { $BuildLock.Dispose() }
    Pop-Location
}
