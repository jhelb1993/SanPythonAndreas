# Downloads are build-time only. Nothing is installed into Windows.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem
$repoRoot = Split-Path -Parent $PSScriptRoot
$version = '3.11.9'
$deps = Join-Path $repoRoot 'dependencies'
$cache = Join-Path $deps 'downloads'
$sdk = Join-Path $deps 'python311-x86'
$runtime = Join-Path $repoRoot 'runtime\SanPythonAndreas\python'

function Assert-X86([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5A4D) { throw "Not a PE file: $Path" }
        $stream.Position = 0x3C
        $offset = $reader.ReadInt32()
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x14C) {
            throw "Expected Windows x86 binary: $Path"
        }
    } finally { $reader.Dispose() }
}

$required = @(
    (Join-Path $sdk 'include\Python.h'),
    (Join-Path $sdk 'include\patchlevel.h'),
    (Join-Path $sdk 'libs\python311.lib'),
    (Join-Path $runtime 'python311.dll'),
    (Join-Path $runtime 'python311.zip'),
    (Join-Path $runtime '_ctypes.pyd'),
    (Join-Path $runtime 'LICENSE.txt'),
    (Join-Path $runtime 'spa-python-version.txt')
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -eq 0 -and (Get-Content (Join-Path $runtime 'spa-python-version.txt') -Raw).Trim() -eq $version) {
    Assert-X86 (Join-Path $runtime 'python311.dll')
    Write-Host "Python $version x86 bundle and SDK already available."
    exit 0
}
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$embedZip = Join-Path $cache "python-$version-embed-win32.zip"
$embedUrl = "https://www.python.org/ftp/python/$version/python-$version-embed-win32.zip"
# Integrity checksum published on the official release page. HTTPS provides transport security.
$embedMd5 = '31E7648158376E92A4463AA6F22A78E1'
if (-not (Test-Path $embedZip) -or (Get-FileHash $embedZip -Algorithm MD5).Hash -ne $embedMd5) {
    Write-Host "Downloading official Python $version embeddable x86 runtime..."
    Invoke-WebRequest -UseBasicParsing -Uri $embedUrl -OutFile "$embedZip.part"
    if ((Get-FileHash "$embedZip.part" -Algorithm MD5).Hash -ne $embedMd5) {
        throw 'Python runtime download checksum mismatch.'
    }
    Move-Item -Force "$embedZip.part" $embedZip
}
$sdkZip = Join-Path $cache "pythonx86.$version.zip"
$sdkUrl = "https://api.nuget.org/v3-flatcontainer/pythonx86/$version/pythonx86.$version.nupkg"
if (-not (Test-Path $sdkZip)) {
    Write-Host "Downloading Python $version x86 build headers and import libraries..."
    Invoke-WebRequest -UseBasicParsing -Uri $sdkUrl -OutFile "$sdkZip.part"
    # Discover the SHA512 checksum from NuGet's package catalog metadata.
    $registration = Invoke-RestMethod -Uri "https://api.nuget.org/v3/registration5-gz-semver2/pythonx86/$version.json"
    $catalog = Invoke-RestMethod -Uri $registration.catalogEntry
    if ($catalog.packageHashAlgorithm -ne 'SHA512' -or -not $catalog.packageHash) {
        throw 'NuGet did not provide the expected package checksum.'
    }
    $expected = $catalog.packageHash
    $hash = [Security.Cryptography.SHA512]::Create()
    $stream = [IO.File]::OpenRead("$sdkZip.part")
    try { $actual = [Convert]::ToBase64String($hash.ComputeHash($stream)) }
    finally { $stream.Dispose(); $hash.Dispose() }
    if ($actual -ne $expected) { throw 'Python SDK download checksum mismatch.' }
    Move-Item -Force "$sdkZip.part" $sdkZip
}

# Extract into fresh temporary directories; do not alter user scripts.
$work = Join-Path $deps ('unpack-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $embedWork = Join-Path $work 'embed'
    $sdkWork = Join-Path $work 'sdk'
    [IO.Compression.ZipFile]::ExtractToDirectory($embedZip, $embedWork)
    [IO.Compression.ZipFile]::ExtractToDirectory($sdkZip, $sdkWork)
    Assert-X86 (Join-Path $embedWork 'python311.dll')
    $headers = Join-Path $sdkWork 'tools\include'
    $libraries = Join-Path $sdkWork 'tools\libs'
    if (-not (Test-Path (Join-Path $libraries 'python311.lib'))) { throw 'Python SDK import library missing.' }
    $patchlevel = Get-Content (Join-Path $headers 'patchlevel.h') -Raw
    if ($patchlevel -notmatch '#define\s+PY_VERSION\s+"3\.11\.9"') { throw 'Unexpected Python SDK version.' }
    New-Item -ItemType Directory -Force -Path $sdk, $runtime | Out-Null
    Copy-Item -Recurse -Force $headers $sdk
    Copy-Item -Recurse -Force $libraries $sdk
    Copy-Item -Force (Join-Path $embedWork '*') $runtime
    # Explicit PyConfig paths are used by the host. This also makes the bundled
    # python.exe useful for a standalone smoke test with the same local paths.
    @('python311.zip', '.', '..', '..\scripts') | Set-Content -Encoding ASCII (Join-Path $runtime 'python311._pth')
    $version | Set-Content -Encoding ASCII (Join-Path $runtime 'spa-python-version.txt')
} finally {
    Remove-Item -Recurse -Force $work
}
Write-Host "Python $version x86 ready: $runtime"
