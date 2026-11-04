# Optional development validation. No global PATH/settings changes or app dependency.
$ErrorActionPreference='Stop'
$sourceRoot=Split-Path -Parent $PSScriptRoot
$runtime=Join-Path $env:LOCALAPPDATA 'SampleArranger/tools/schema-runtime'
$compatible=& python -c 'import sys,struct; print(sys.version_info[:2]==(3,12) and struct.calcsize("P")==8)'
if ($LASTEXITCODE -ne 0 -or $compatible -ne 'True') { throw 'Use Python3.12 x64 for this wheel lock, or deliberately review/update the validation lock.' }
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'Scripts/python.exe'))) {
    & python -m venv $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Could not create private schema-validation runtime' }
}
$interpreter=Join-Path $runtime 'Scripts/python.exe'
& $interpreter -m pip --isolated install --index-url https://pypi.org/simple --require-hashes -r (Join-Path $sourceRoot 'requirements-schema-windows.lock')
if ($LASTEXITCODE -ne 0) { throw 'Pinned schema validation dependencies could not be installed' }
& $interpreter -m unittest discover -s (Join-Path $sourceRoot 'tests') -p test_schema_independent.py -v
if ($LASTEXITCODE -ne 0) { throw 'Independent request-schema validation failed' }
Write-Output "Development schema validator ready in $runtime"
