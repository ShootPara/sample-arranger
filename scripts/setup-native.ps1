# Reproducible user-space native build. Does not change global PATH or OS settings.
[CmdletBinding()]
param([string]$ToolsRoot = "$env:LOCALAPPDATA/SampleArranger/tools")
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT') {
    throw 'Windows x64 is required.'
}
$repository = Split-Path -Parent $PSScriptRoot
$portable = Join-Path $ToolsRoot '2.11.0'
$archive = Join-Path $portable 'w64devkit-x64-2.11.0.7z.exe'
$toolBin = Join-Path $portable 'w64devkit/bin'
# Exact archive digest from the installed, previously verified official asset.
$archiveHash = '54c2bb9962e8a30c8270e34c5efc3d5fee579f53087fa7d435b95fbba2af7b2b'
New-Item -ItemType Directory -Path $portable -Force | Out-Null
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri 'https://github.com/skeeto/w64devkit/releases/download/v2.11.0/w64devkit-x64-2.11.0.7z.exe' -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveHash) {
    throw 'Portable toolchain archive checksum mismatch; do not execute it.'
}
if (-not (Test-Path -LiteralPath (Join-Path $toolBin 'g++.exe'))) {
    & tar -xf $archive -C $portable
    if ($LASTEXITCODE -ne 0) { throw 'Toolchain extraction failed.' }
}
$sdk = Join-Path $ToolsRoot 'vst3sdk-3.8.1'
if (-not (Test-Path -LiteralPath $sdk)) {
    & git clone --recursive --branch v3.8.1_build_84 --depth 1 'https://github.com/steinbergmedia/vst3sdk.git' $sdk
    if ($LASTEXITCODE -ne 0) { throw 'SDK checkout failed.' }
}
$revision = & git -C $sdk rev-parse HEAD
if ($revision -ne '3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96') { throw 'SDK commit mismatch.' }
& git -C $sdk submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'Pinned SDK submodules unavailable.' }
$allocation = Join-Path $sdk 'public.sdk/source/vst/utility/alignedalloc.h'
$text = [IO.File]::ReadAllText($allocation)
if ($text.Contains('_MSC_VER')) {
    if ([regex]::Matches($text,'_MSC_VER').Count -ne 3) { throw 'Unexpected allocation header; review before patching.' }
    [IO.File]::WriteAllText($allocation,$text.Replace('_MSC_VER','_WIN32'))
}
$originalPath = $env:PATH
try {
    $env:PATH = "$toolBin;$originalPath"
    $build = Join-Path $ToolsRoot 'arranger-native'
    & cmake -S (Join-Path $repository 'native') -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DVST3_SDK_ROOT=$sdk"
    if ($LASTEXITCODE -ne 0) { throw 'Native configuration failed.' }
    & cmake --build $build --target arranger-vst3 arranger-delay-fixture arranger-playback arranger-loopback-probe arranger-lifecycle-fixture
    if ($LASTEXITCODE -ne 0) { throw 'Native compilation failed.' }
    Write-Output "Native tools ready in $build"
} finally { $env:PATH = $originalPath }
