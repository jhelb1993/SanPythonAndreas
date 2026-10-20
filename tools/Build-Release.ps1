[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio Installer/vswhere.exe not found.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.Component.MSBuild -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'Visual Studio with MSBuild not found.' }
$msbuild = Join-Path ($installation | Select-Object -First 1) 'MSBuild\Current\Bin\MSBuild.exe'
$project = Join-Path $repoRoot 'SanPythonAndreas\SanPythonAndreas.vcxproj'
Write-Host "Building current project from disk: $project"
Write-Host 'Host intermediates: obj/Host/Release (separate from old Python 3.8 objects).'
# Build the host project explicitly, including its runtime ProjectReference.
# This avoids accidentally rebuilding only the SanPythonRuntime project in VS.
& $msbuild $project /nologo /t:Rebuild /p:Configuration=Release /p:Platform=Win32 /p:BuildProjectReferences=true /verbosity:minimal
if ($LASTEXITCODE -ne 0) { throw "Release rebuild failed: $LASTEXITCODE" }
$testProject = Join-Path $repoRoot 'SanPythonAndreas\BindingsTests.vcxproj'
& $msbuild $testProject /nologo /t:Rebuild /p:Configuration=Release /p:Platform=Win32 /verbosity:minimal
if ($LASTEXITCODE -ne 0) { throw "Native binding test build failed: $LASTEXITCODE" }
$python = Join-Path $repoRoot 'Release\SanPythonAndreas\python\python.exe'
& $python -I -S (Join-Path $PSScriptRoot 'test_native_bindings.py') (Join-Path $repoRoot 'Release\tests\sanandreas.pyd')
if ($LASTEXITCODE -ne 0) { throw "Native binding tests failed: $LASTEXITCODE" }
& (Join-Path $PSScriptRoot 'Test-Bundle.ps1') -Configuration Release
Write-Host ''
Write-Host 'Complete Release bundle verified. Deploy BOTH:'
Write-Host (Join-Path $repoRoot 'Release\SanPythonAndreas.asi')
Write-Host (Join-Path $repoRoot 'Release\SanPythonAndreas')
