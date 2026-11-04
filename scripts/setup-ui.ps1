[CmdletBinding()]
param([string]$ToolsRoot = "$env:LOCALAPPDATA/SampleArranger/tools")
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$version = & python --version
if ($version -notmatch '^Python 3\.12\.') { throw 'This wheel lock targets Python3.12 Windows x64.' }
$runtime = Join-Path $ToolsRoot 'ui-runtime'
$python = Join-Path $runtime 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & python -m venv $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Private UI runtime creation failed.' }
}
& $python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r (Join-Path $repository 'requirements-ui-windows.lock')
if ($LASTEXITCODE -ne 0) { throw 'Pinned UI dependency installation failed.' }
Write-Output "UI runtime ready in $runtime"
