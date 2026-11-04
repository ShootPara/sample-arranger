param([Parameter(Mandatory=$true)][string]$Package)
$ErrorActionPreference = 'Stop'
$packagePath = (Resolve-Path -LiteralPath $Package).Path
$manifestPath = Join-Path $packagePath 'build-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.format -ne 'sample-arranger-private-build' -or $manifest.schema -ne 1) { throw 'Not an app build manifest' }
$productRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'SampleArranger'))
$destination = Join-Path $productRoot 'app'
foreach ($process in (Get-Process -Name 'Sample Arranger','arranger-cli','arranger-vst3','arranger-playback' -ErrorAction SilentlyContinue)) {
    if ($process.Path -and $process.Path.StartsWith($destination + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Close the installed arranger before replacing it; projects and settings are preserved' }
}
if ((Test-Path -LiteralPath $destination) -and -not (Test-Path -LiteralPath (Join-Path $destination 'local-deployment.json'))) { throw 'Existing app directory is not an owned deployment; preserved' }
$stage = Join-Path $productRoot ('app-stage-' + [guid]::NewGuid().ToString())
[IO.Directory]::CreateDirectory($stage) | Out-Null
foreach ($entry in $manifest.files) {
    $sourceFile = [IO.Path]::GetFullPath((Join-Path $packagePath $entry.path))
    $targetFile = [IO.Path]::GetFullPath((Join-Path $stage $entry.path))
    if (-not $sourceFile.StartsWith($packagePath + '\',[StringComparison]::OrdinalIgnoreCase) -or -not $targetFile.StartsWith($stage + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Build manifest path escaped its directory' }
    if ((Get-Item -LiteralPath $sourceFile).Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Build content changed: $($entry.path)" }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $targetFile)) | Out-Null
    Copy-Item -LiteralPath $sourceFile -Destination $targetFile
}
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $stage 'build-manifest.json')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../docs/QUICKSTART.md') -Destination (Join-Path $stage 'START-HERE.md')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '../docs/KNOWN_ISSUES.md') -Destination (Join-Path $stage 'KNOWN_ISSUES.md')
[IO.Directory]::CreateDirectory((Join-Path $stage 'docs')) | Out-Null
foreach ($document in (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../docs') -File -Filter '*.md')) {
    if ($document.Name -ne 'EVIDENCE.md') { Copy-Item -LiteralPath $document.FullName -Destination (Join-Path $stage 'docs' $document.Name) }
}
@{ format='sample-arranger-local-deployment'; source_commit=$manifest.git_commit; installed_utc=[DateTime]::UtcNow.ToString('o'); personal_local_build=$true } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'local-deployment.json') -Encoding utf8
if (Test-Path -LiteralPath $destination) {
    $previous = Join-Path $productRoot ('app-previous-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
    Move-Item -LiteralPath $destination -Destination $previous
}
Move-Item -LiteralPath $stage -Destination $destination
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('DesktopDirectory'),[Environment]::GetFolderPath('Programs'))) {
    $linkPath = Join-Path $folder 'Sample Arranger.lnk'
    $link = $shell.CreateShortcut($linkPath)
    if ((Test-Path -LiteralPath $linkPath) -and $link.TargetPath -and -not $link.TargetPath.StartsWith($productRoot + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unrelated existing shortcut preserved' }
    $link.TargetPath=Join-Path $destination 'Sample Arranger.exe';$link.WorkingDirectory=$destination;$link.Description='Local sample arrangement, MIDI, VST3 and MP3 rendering';$link.Save()
}
Write-Output $destination
