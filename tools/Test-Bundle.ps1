[CmdletBinding()]
param([ValidateSet('Release', 'Debug')][string] $Configuration = 'Release')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $repoRoot $Configuration
foreach ($file in @('SanPythonAndreas.asi', 'SanPythonAndreas\SanPythonRuntime.dll',
    'SanPythonAndreas\_spa_runtime.py', 'SanPythonAndreas\scripts\main.py',
    'SanPythonAndreas\python\python.exe')) {
    if (-not (Test-Path (Join-Path $bundle $file))) { throw "Missing bundle file: $file" }
}
$asiBytes = [IO.File]::ReadAllBytes((Join-Path $bundle 'SanPythonAndreas.asi'))
$asiText = [Text.Encoding]::ASCII.GetString($asiBytes)
if ($asiText.Contains('python38.dll')) {
    throw 'Outdated ASI: imports Python 3.8. Rebuild SanPythonAndreas.vcxproj, not just PythonRuntime.vcxproj.'
}
if (-not $asiText.Contains('host API 22')) {
    throw 'Outdated ASI: current vehicle teleport host API marker missing. Rebuild the host project.'
}
$runtimeBytes = [IO.File]::ReadAllBytes((Join-Path $bundle 'SanPythonAndreas\SanPythonRuntime.dll'))
$runtimeText = [Text.Encoding]::ASCII.GetString($runtimeBytes)
foreach ($marker in @('python311.dll', '_is_key_down', '_player_health', '_set_player_health', 'pybind11-2.13.6', '_player_position', '_teleport_player', '_player_interior', '_player_heading', '_set_player_heading', '_player_armour', '_set_player_armour', '_player_money', '_set_player_money', '_player_wanted_level', '_set_player_wanted_level', '_player_weapon', '_give_player_weapon', '_select_player_weapon', '_remove_player_weapon', '_clear_player_weapons', '_player_vehicle', 'VehicleInfo', '_game_time_ms', '_require_game_thread', '_request_model', '_model_ready', '_release_model', '_capture_player_vehicle', '_vehicle_handle_valid', '_vehicle_info', '_close_vehicle_handle', 'InvalidVehicleError', '_spawn_vehicle', '_remove_vehicle', '_cleanup_owned_vehicles', '_enter_player_vehicle', '_leave_player_vehicle', '_set_vehicle_health', '_repair_vehicle', '_vehicle_colors', '_set_vehicle_color', '_vehicle_motion', '_set_vehicle_heading', '_set_vehicle_velocity', '_vehicle_interior', '_teleport_vehicle')) {
    if (-not $runtimeText.Contains($marker)) { throw "Outdated runtime DLL: missing $marker" }
}
if (-not (Test-Path (Join-Path $bundle 'SanPythonAndreas\bindings-dependencies.json'))) {
    throw 'Missing binding dependency manifest in bundle.'
}
$bootstrap = Get-Content (Join-Path $bundle 'SanPythonAndreas\_spa_runtime.py') -Raw
if (-not $bootstrap.Contains('BOOTSTRAP_API_VERSION = 22')) { throw 'Outdated Python bootstrap API.' }
if ($runtimeText.Contains('_test_reset')) { throw 'Test-only controls found in production runtime DLL.' }
$python = Join-Path $bundle 'SanPythonAndreas\python\python.exe'
& $python -I -S (Join-Path $PSScriptRoot 'check_bundle.py')
if ($LASTEXITCODE -ne 0) { throw "Bundled Python smoke test failed: $LASTEXITCODE" }
