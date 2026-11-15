$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/.ai-env/Scripts/python.exe" "$PSScriptRoot/scripts/run.py" stop
