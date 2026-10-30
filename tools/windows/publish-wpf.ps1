param([string]$GameDirectory)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$output = Join-Path $repo ('artifacts/wpf-release-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
dotnet publish (Join-Path $repo 'src/CczRandomizer.Wpf/CczRandomizer.Wpf.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -o $output
if ($LASTEXITCODE -ne 0) { throw 'WPF publish failed' }
Set-Content -LiteralPath (Join-Path $output '.ccz-wpf-release') -Value '1' -Encoding utf8
foreach ($required in @('CczRandomizer.Wpf.exe', 'CczRandomizer.Core.dll', 'coreclr.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $output $required))) { throw "Missing $required" }
}
if (-not (Get-ChildItem -LiteralPath (Join-Path $output 'native') -Filter '*.dll')) { throw 'Native controller is missing' }
if ($GameDirectory) {
    $game = (Resolve-Path -LiteralPath $GameDirectory).Path
    if (-not (Test-Path -LiteralPath (Join-Path $game 'Ekd5.exe'))) { throw 'Select a game directory containing Ekd5.exe' }
    # A new version directory keeps both the existing tool and the last WPF build recoverable.
    $destination = Join-Path $game ('随机工具-WPF-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $output -Destination $destination -Recurse
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $game '2.2随机工具-WPF.lnk'))
    $shortcut.TargetPath = Join-Path $destination 'CczRandomizer.Wpf.exe'
    $shortcut.WorkingDirectory = $game
    $shortcut.Description = '曹操传加强版 2.2 随机工具（C# WPF）'
    $shortcut.Save()
    Write-Output "Deployed: $destination"
} else { Write-Output "Published: $output" }
