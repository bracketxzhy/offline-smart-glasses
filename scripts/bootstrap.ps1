$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.ai-env/Scripts/python.exe')) {
    py -3.12 -m venv .ai-env
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required to create the environment.' }
}
& '.ai-env/Scripts/python.exe' -m pip install -r requirements-runtime.txt 'ultralytics==8.4.204' 'onnx==1.23.2' 'pytest==9.2.0'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.ai-env/Scripts/python.exe' scripts/setup_models.py
if ($LASTEXITCODE -ne 0) { throw 'Model download or verification failed.' }
& '.ai-env/Scripts/python.exe' scripts/export_detector.py
if ($LASTEXITCODE -ne 0) { throw 'Detector export failed.' }
& '.ai-env/Scripts/python.exe' scripts/warm_audio.py
if ($LASTEXITCODE -ne 0) { throw 'Audio cache preparation failed.' }
Write-Output 'Bootstrap complete. Start with Start-Glasses.ps1.'
