[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$python = "$env:LOCALAPPDATA/SampleArranger/tools/ui-runtime/Scripts/pythonw.exe"
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts/setup-ui.ps1 first.' }
$entry = Join-Path $repository 'src/workspace.py'
Start-Process -FilePath $python -ArgumentList @('-B',"`"$entry`"") -WorkingDirectory $repository -WindowStyle Normal
