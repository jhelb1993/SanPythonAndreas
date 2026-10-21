[CmdletBinding()]
param([Parameter(Mandatory = $true)][string] $OutputRoot)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'runtime\SanPythonAndreas'
$destination = Join-Path $OutputRoot 'SanPythonAndreas'
$scripts = Join-Path $destination 'scripts'
New-Item -ItemType Directory -Force -Path $scripts | Out-Null
Copy-Item -Force (Join-Path $source '_spa_runtime.py') $destination
Copy-Item -Force (Join-Path $source 'sanandreas.pyi') $destination
Copy-Item -Force (Join-Path $source 'scripts\example_heal.py') (Join-Path $scripts 'example_heal.py')
Copy-Item -Force (Join-Path $source 'scripts\diagnose_f5.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_position.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_teleport.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_armour.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_money_wanted.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_weapons.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_vehicle.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_timers.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_tasks.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_models.py') $scripts
Copy-Item -Force (Join-Path $source 'scripts\example_background.py') $scripts
$main = Join-Path $scripts 'main.py'
if (-not (Test-Path -LiteralPath $main)) {
    Copy-Item (Join-Path $source 'scripts\main.py') $main
}
Write-Host "Updated scripting API and F5 example in $destination (existing main.py preserved)."

$licenseRoot = Join-Path $destination 'licenses'
$manifest = Get-Content (Join-Path $repoRoot 'bindings-dependencies.json') -Raw | ConvertFrom-Json
foreach ($name in @('pybind11', 'plugin-sdk')) {
    $dependency = Join-Path $repoRoot ('dependencies\' + $manifest.$name.directory)
    $licenseDestination = Join-Path $licenseRoot $name
    New-Item -ItemType Directory -Force -Path $licenseDestination | Out-Null
    foreach ($notice in @(Get-ChildItem -LiteralPath $dependency -Recurse -File | Where-Object { $_.Name -like 'LICENSE*' })) {
        $relative = $notice.FullName.Substring($dependency.Length).TrimStart([char]'\')
        $target = Join-Path $licenseDestination $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -Force $notice.FullName $target
    }
    $noticeText = "$name - upstream: https://github.com/$($manifest.$name.repository) - ref: $($manifest.$name.ref)"
    $noticeText | Set-Content -Encoding UTF8 (Join-Path $licenseDestination 'UPSTREAM-NOTICE.txt')
    $readme = Join-Path $dependency 'README.md'
    if (Test-Path $readme) { Copy-Item -Force $readme (Join-Path $licenseDestination 'UPSTREAM-README.md') }
}
Copy-Item -Force (Join-Path $repoRoot 'bindings-dependencies.json') $destination
