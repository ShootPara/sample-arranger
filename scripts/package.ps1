$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$productRoot = Join-Path $env:LOCALAPPDATA 'SampleArranger'
$packagePython = Join-Path $productRoot 'tools/package-runtime/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $packagePython)) {
    & python -m venv (Join-Path $productRoot 'tools/package-runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create private packaging runtime' }
}
& $packagePython -m pip --isolated install --index-url https://pypi.org/simple --require-hashes -r (Join-Path $sourceRoot 'requirements-package-windows.lock') -r (Join-Path $sourceRoot 'requirements-ui-windows.lock')
if ($LASTEXITCODE -ne 0) { throw 'Pinned packaging prerequisites failed' }
& (Join-Path $PSScriptRoot 'setup-native.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
$buildRoot = Join-Path $productRoot ('packages/build-' + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $buildRoot | Out-Null
$assets = Join-Path $buildRoot 'assets'
& $packagePython -B (Join-Path $PSScriptRoot 'build_icon.py') (Join-Path $sourceRoot 'assets/arranger.svg') $assets
if ($LASTEXITCODE -ne 0) { throw 'App icon rendering failed' }
$values = @{
    ARRANGER_SOURCE_ROOT = $sourceRoot
    ARRANGER_NATIVE_BUILD = (Join-Path $productRoot 'tools/arranger-native')
    ARRANGER_PACKAGE_ASSETS = $assets
    PYINSTALLER_CONFIG_DIR = (Join-Path $buildRoot 'cache')
    ARRANGER_FFMPEG = (Get-Item -LiteralPath (Get-Command ffmpeg).Source).ResolveLinkTarget($true).FullName
    ARRANGER_FFPROBE = (Get-Item -LiteralPath (Get-Command ffprobe).Source).ResolveLinkTarget($true).FullName
    ARRANGER_FFPLAY = (Get-Item -LiteralPath (Get-Command ffplay).Source).ResolveLinkTarget($true).FullName
    # Keep unrelated coding/document tool DLLs out of dependency discovery.
    PATH = ((Split-Path -Parent $packagePython), (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot, (Join-Path $env:SystemRoot 'System32/Wbem')) -join ';'
}
# Non-link installations have no link target; retain their actual selected executable.
foreach ($name in @('FFMPEG','FFPROBE','FFPLAY')) {
    if (-not $values["ARRANGER_$name"]) { $values["ARRANGER_$name"] = (Get-Command ($name.ToLowerInvariant())).Source }
}
& $packagePython -B (Join-Path $PSScriptRoot 'verify_audio_tools.py') (Join-Path $sourceRoot 'docs/FFMPEG_WINDOWS.lock.json') $values.ARRANGER_FFMPEG $values.ARRANGER_FFPROBE $values.ARRANGER_FFPLAY
if ($LASTEXITCODE -ne 0) { throw 'Selected audio tools differ from the reviewed private build inputs' }
$previous = @{}
try {
    foreach ($key in $values.Keys) { $previous[$key] = [Environment]::GetEnvironmentVariable($key,'Process'); [Environment]::SetEnvironmentVariable($key,$values[$key],'Process') }
    & $packagePython -m PyInstaller --clean --distpath (Join-Path $buildRoot 'dist') --workpath (Join-Path $buildRoot 'work') (Join-Path $PSScriptRoot 'arranger.spec') *> (Join-Path $buildRoot 'build.log')
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed; inspect $buildRoot/build.log" }
    & $packagePython -B (Join-Path $PSScriptRoot 'verify_package_inputs.py') $sourceRoot $buildRoot
    if ($LASTEXITCODE -ne 0) { throw 'Dependency discovery included an unexpected source; private build is rejected' }
} finally {
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key,$previous[$key],'Process') }
}
$destination = Join-Path $buildRoot 'dist/SampleArranger'
@'
PRIVATE DEVELOPMENT BUILD — NOT CLEARED FOR DISTRIBUTION
Includes the existing free FFmpeg build and Qt/Python runtime for local testing.
Publication, complete transitive notices/corresponding source and clean-machine
acceptance remain gated. No user plugins, jobs, catalog, settings or credentials
are included. App source is AGPLv3; dependency/asset terms remain distinct.
'@ | Set-Content -LiteralPath (Join-Path $destination 'PRIVATE-DEVELOPMENT.txt') -Encoding utf8
& $packagePython -B (Join-Path $PSScriptRoot 'package_manifest.py') $sourceRoot $destination
if ($LASTEXITCODE -ne 0) { throw 'Build provenance generation failed' }
Write-Output $destination
