[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem
$repoRoot = Split-Path -Parent $PSScriptRoot
$deps = Join-Path $repoRoot 'dependencies'
$cache = Join-Path $deps 'downloads'
$manifest = Get-Content (Join-Path $repoRoot 'bindings-dependencies.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $cache | Out-Null
foreach ($name in @('pybind11', 'plugin-sdk')) {
    $spec = $manifest.$name
    $destination = Join-Path $deps $spec.directory
    $marker = Join-Path $destination 'spa-source-ref.txt'
    $header = if ($name -eq 'pybind11') { 'include\pybind11\embed.h' } else { 'plugin_sa\game_sa\CPed.h' }
    if ((Test-Path $marker) -and (Test-Path (Join-Path $destination $header)) -and
        (Get-Content $marker -Raw).Trim() -eq $spec.ref) {
        Write-Host "$name $($spec.ref) already available."
        continue
    }
    $archive = Join-Path $cache "$name-$($spec.ref).zip"
    if (-not (Test-Path $archive)) {
        $uri = "https://codeload.github.com/$($spec.repository)/zip/$($spec.ref)"
        Write-Host "Downloading $name at pinned ref $($spec.ref)..."
        Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile "$archive.part"
        Move-Item -Force "$archive.part" $archive
    }
    $work = Join-Path $deps ('bindings-unpack-' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.Compression.ZipFile]::ExtractToDirectory($archive, $work)
        $roots = @(Get-ChildItem -LiteralPath $work -Directory)
        if ($roots.Count -ne 1 -or -not (Test-Path (Join-Path $roots[0].FullName $header))) {
            throw "Unexpected $name archive layout. Remove $archive and retry."
        }
        # Preserve attribution files supplied by the pinned upstream archive.
        # Keep the complete upstream tree, including license/attribution comments.
        # Older SDK snapshots may provide notices in README or subdirectories.
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item -Recurse -Force (Join-Path $roots[0].FullName '*') $destination
        $spec.ref | Set-Content -Encoding ASCII $marker
        (Get-FileHash $archive -Algorithm SHA256).Hash | Set-Content -Encoding ASCII (Join-Path $destination 'spa-archive-sha256.txt')
    } finally {
        if (Test-Path $work) { Remove-Item -Recurse -Force $work }
    }
}
