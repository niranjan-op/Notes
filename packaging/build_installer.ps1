<#
Builds the Secure Notes Windows installer.

  powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1

Steps: run tests -> PyInstaller (dist\NotesApp) -> Inno Setup (dist\installer\*.exe).
Requires the project venv (.venv) and Inno Setup 6 (winget install JRSoftware.InnoSetup).
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "==> Running tests" -ForegroundColor Cyan
& $python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed; installer not built." }

Write-Host "==> Freezing application with PyInstaller" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean NotesApp.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$iscc = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup" }

Write-Host "==> Compiling installer" -ForegroundColor Cyan
& $iscc "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

Get-ChildItem "dist\installer\*.exe" | ForEach-Object { Write-Host "Built $($_.FullName)" -ForegroundColor Green }

