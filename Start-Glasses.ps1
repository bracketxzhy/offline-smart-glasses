$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/.ai-env/Scripts/python.exe" "$PSScriptRoot/scripts/run.py" start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output 'Open http://127.0.0.1:8765 after startup; see logs/launcher.log.'
