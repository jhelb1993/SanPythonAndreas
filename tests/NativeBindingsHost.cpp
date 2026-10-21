// Test-only host: no GTA addresses, hooks or game process required.
#include "pch.h"
#include "PythonIncludes.h"
#include "Bindings.h"
#include "BuildInfo.h"
#include "WeaponPolicy.h"
#include "PlayerSeatWarp.h"
#include <vector>
#include <new>
#include <array>
#include <unordered_map>
#include <string>
#include <cmath>

namespace py = pybind11;
namespace
{
    bool onThread = true, ready = true;
    const DWORD hostThread = GetCurrentThreadId();
    float health = 25, maximum = 100;
    float armour = 10;
    int money = 500, wantedLevel = 1, wantedMaximum = 6;
    bool wantedBlocked = false;
    struct FakeModelLease { int model; bool pinned; };
    std::unordered_map<DWORD, FakeModelLease> modelLeases;
    std::unordered_map<int, bool> loadedModels;
    std::unordered_map<int, int> modelRefs;
    DWORD nextModelToken = 0;
    bool invalidModel = false;
    int __cdecl RequestModel(int model, DWORD* token)
    {
        if (!ready) return 1;
        if (invalidModel || model < 1 || model >= 20000) return 2;
        if (modelLeases.size() >= 256) return 3;
        *token = ++nextModelToken;
        modelLeases.emplace(*token, FakeModelLease{model, false});
        return 0;
    }
    int __cdecl ModelReady(DWORD token)
    {
        if (!ready) return -1;
        auto found = modelLeases.find(token);
        if (found == modelLeases.end()) return -1;
        auto& lease = found->second;
        if (lease.pinned && !loadedModels[lease.model]) return -1;
        if (!loadedModels[lease.model]) return 0;
        if (!lease.pinned) { ++modelRefs[lease.model]; lease.pinned = true; }
        return 1;
    }
    void __cdecl ReleaseModel(DWORD token)
    {
        auto found = modelLeases.find(token);
        if (found == modelLeases.end()) return;
        const auto& lease = found->second;
        if (lease.pinned && loadedModels[lease.model] && modelRefs[lease.model] > 0) --modelRefs[lease.model];
        modelLeases.erase(found);
    }
    DWORD gameTimeMs = 1000;
    DWORD __cdecl GameTimeMs() { return gameTimeMs; }
    int vehicleState = 0;
    SpaPlayerVehicle vehicleData{411, TRUE, 750, 10, 20, 30};
    struct FakeVehicleEntity {
        int generation; SpaPlayerVehicle data;
        bool damaged = true, burning = true, engineBroken = true;
        bool wrecked = false, unsupported = false;
    };
    struct FakeVehicleHandle { int entity; int generation; bool referenceAlive; };
    std::unordered_map<int, FakeVehicleEntity> handleVehicles;
    std::unordered_map<DWORD, FakeVehicleHandle> vehicleHandles;
    int currentVehicleId = 1;
    DWORD nextVehicleToken = 0;
    bool failVehicleReference = false;
    int __cdecl CaptureVehicle(DWORD* token)
    {
        if (!ready || vehicleState < 0) return -1;
        if (vehicleState == 0) return 0;
        if (vehicleHandles.size() >= 128 || failVehicleReference) return -2;
        auto inserted = handleVehicles.emplace(currentVehicleId, FakeVehicleEntity{0, vehicleData});
        auto& entity = inserted.first->second;
        entity.data = vehicleData;
        *token = ++nextVehicleToken;
        vehicleHandles.emplace(*token, FakeVehicleHandle{currentVehicleId, entity.generation, true});
        return 1;
    }
    BOOL __cdecl VehicleValid(DWORD token)
    {
        if (!ready) return FALSE;
        auto handle = vehicleHandles.find(token);
        if (handle == vehicleHandles.end() || !handle->second.referenceAlive) return FALSE;
        auto entity = handleVehicles.find(handle->second.entity);
        return entity != handleVehicles.end() && entity->second.generation == handle->second.generation ? TRUE : FALSE;
    }
    int __cdecl VehicleInfo(DWORD token, SpaPlayerVehicle* value)
    {
        if (!ready) return -1;
        if (!VehicleValid(token)) return -2;
        const auto& handle = vehicleHandles.at(token);
        *value = handleVehicles.at(handle.entity).data;
        if (handle.entity != currentVehicleId || vehicleState != 1) value->isDriver = FALSE;
        return 1;
    }
    void __cdecl CloseVehicle(DWORD token) { vehicleHandles.erase(token); }
    int __cdecl SetVehicleHealth(DWORD token, float value)
    {
        if (!ready) return 1;
        if (!VehicleValid(token)) return 2;
        auto& car = handleVehicles.at(vehicleHandles.at(token).entity);
        if (car.wrecked || car.unsupported || car.data.health <= 0) return 3;
        if (!std::isfinite(value) || value < 0 || value > 1000) return 4;
        car.data.health = value;
        return 0;
    }
    int __cdecl RepairVehicle(DWORD token)
    {
        if (!ready) return 1;
        if (!VehicleValid(token)) return 2;
        auto& car = handleVehicles.at(vehicleHandles.at(token).entity);
        if (car.wrecked || car.unsupported || car.data.health <= 0) return 3;
        car.data.health = 1000;
        car.damaged = car.burning = car.engineBroken = false;
        return 0;
    }
    std::unordered_map<int, bool> ownedVehicles; // value: occupied/attached
    int nextOwnedVehicle = 1000;
    int __cdecl SpawnVehicle(int model, float x, float y, float z, float, DWORD* token)
    {
        if (!ready || health <= 0) return 1;
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)
            || std::fabs(x) > 20000 || std::fabs(y) > 20000 || z < -1000 || z > 10000) return 7;
        if (model != 411 && model != 400) return 2;
        if (!loadedModels[model]) return 3;
        if (ownedVehicles.size() >= 32 || vehicleHandles.size() >= 128 || failVehicleReference) return 4;
        const int id = ++nextOwnedVehicle;
        handleVehicles.emplace(id, FakeVehicleEntity{0, {model, FALSE, 1000, x, y, z}});
        ownedVehicles.emplace(id, false);
        *token = ++nextVehicleToken;
        vehicleHandles.emplace(*token, FakeVehicleHandle{id, 0, true});
        return 0;
    }
    int __cdecl RemoveVehicle(DWORD token)
    {
        if (!ready) return 1;
        if (!VehicleValid(token)) return 2;
        const int id = vehicleHandles.at(token).entity;
        const auto owner = ownedVehicles.find(id);
        if (owner == ownedVehicles.end()) return 3;
        if (owner->second) return 4;
        handleVehicles.erase(id);
        ownedVehicles.erase(id);
        return 0;
    }
    void __cdecl CleanupOwnedVehicles()
    {
        for (const auto& owner : ownedVehicles)
            if (!owner.second) handleVehicles.erase(owner.first);
        ownedVehicles.clear();
    }
    int seatStatus = 0;
    bool exitPending = false;
    int __cdecl EnterVehicle(DWORD token, int seat)
    {
        if (!ready || health <= 0) return 1;
        if (!VehicleValid(token)) return 2;
        if (vehicleState == 1) return 3;
        if (seatStatus) return seatStatus;
        if (seat < -1 || seat > 2) return 5;
        auto& handle = vehicleHandles.at(token);
        currentVehicleId = handle.entity;
        vehicleData = handleVehicles.at(currentVehicleId).data;
        vehicleData.isDriver = seat == -1;
        vehicleState = 1;
        handleVehicles.at(currentVehicleId).data = vehicleData;
        if (ownedVehicles.count(currentVehicleId)) ownedVehicles[currentVehicleId] = true;
        return 0;
    }
    int __cdecl LeaveVehicle()
    {
        if (!ready || health <= 0) return 1;
        if (exitPending) return 0;
        if (vehicleState == 0) return 0;
        if (seatStatus) return seatStatus;
        exitPending = true; // request is asynchronous
        return 0;
    }
    int __cdecl ReadVehicle(SpaPlayerVehicle* value)
    {
        if (!ready) return -1;
        if (vehicleState == 1) *value = vehicleData;
        return vehicleState;
    }
    std::array<int, 13> weaponIds{};
    std::array<unsigned int, 13> weaponAmmo{};
    int activeSlot = 0, weaponStatus = 0;
    int WeaponSlot(int id)
    {
        if (id <= 1) return 0;
        if (id <= 9) return 1;
        if (id <= 15) return 10;
        if (id <= 18) return 8;
        if (id <= 24) return 2;
        if (id <= 27) return 3;
        if (id <= 29 || id == 32) return 4;
        if (id <= 31) return 5;
        if (id <= 34) return 6;
        if (id <= 38) return 7;
        return 9;
    }
    BOOL __cdecl ReadWeapon(int* id, unsigned int* ammo)
    {
        if (!ready) return FALSE;
        *id = weaponIds[activeSlot]; *ammo = weaponAmmo[activeSlot];
        return TRUE;
    }
    int __cdecl WeaponAction(int action, int id, unsigned int ammo, BOOL equip)
    {
        if (!ready || health <= 0) return 1;
        if (weaponStatus) return weaponStatus;
        if (action == 3)
        {
            weaponIds.fill(0); weaponAmmo.fill(0); activeSlot = 0;
            return 0;
        }
        const int slot = WeaponSlot(id);
        if (action == 0)
        {
            if (weaponAmmo[slot] > spa::MaxWeaponAmmo || ammo > spa::MaxWeaponAmmo - weaponAmmo[slot]) return 4;
            // GTA carries old ammunition across shotgun/SMG/rifle replacement.
            const bool carry = weaponIds[slot] == id || slot == 3 || slot == 4 || slot == 5;
            weaponAmmo[slot] = ammo + (carry ? weaponAmmo[slot] : 0);
            weaponIds[slot] = id;
            if (equip) activeSlot = slot;
        }
        else if (action == 1)
        {
            if (id != 0 && weaponIds[slot] != id) return 3;
            activeSlot = slot;
        }
        else if (action == 2 && weaponIds[slot] == id && id != 0)
        {
            weaponIds[slot] = 0; weaponAmmo[slot] = 0;
            if (activeSlot == slot) activeSlot = 0;
        }
        return 0;
    }
    BOOL __cdecl ReadMoney(int* value)
    {
        if (!ready) return FALSE;
        *value = money;
        return TRUE;
    }
    BOOL __cdecl WriteMoney(int value)
    {
        if (!ready || health <= 0 || value < 0 || value > 999999999) return FALSE;
        money = value;
        return TRUE;
    }
    BOOL __cdecl ReadWantedLevel(int* value)
    {
        if (!ready) return FALSE;
        *value = wantedLevel;
        return TRUE;
    }
    BOOL __cdecl WriteWantedLevel(int value)
    {
        if (!ready || health <= 0 || value < 0 || value > 6) return FALSE;
        if (!wantedBlocked) wantedLevel = value < wantedMaximum ? value : wantedMaximum;
        return TRUE;
    }
    BOOL __cdecl ReadArmour(float* value)
    {
        if (!ready) return FALSE;
        *value = armour;
        return TRUE;
    }
    BOOL __cdecl WriteArmour(float value)
    {
        if (!ready || health <= 0 || !std::isfinite(value) || value < 0 || value > 100) return FALSE;
        armour = value;
        return TRUE;
    }
    std::string lastText;
    bool positionAvailable = true;
    float positionX = 12.5f, positionY = -34.0f, positionZ = 8.0f;
    BOOL __cdecl IsReady() { return ready ? TRUE : FALSE; }
    BOOL __cdecl IsThread() { return onThread && GetCurrentThreadId() == hostThread ? TRUE : FALSE; }
    void __cdecl ShowText(const char* value) { lastText = value; }
    void __cdecl Log(const char*) {}
    BOOL __cdecl KeyDown(int key) { return key == VK_F5 ? TRUE : FALSE; }
    BOOL __cdecl Focus() { return TRUE; }
    BOOL __cdecl ReadHealth(float* current, float* max)
    {
        if (!ready) return FALSE;
        *current = health; *max = maximum;
        return TRUE;
    }
    BOOL __cdecl WriteHealth(float value)
    {
        if (!ready || health <= 0 || !std::isfinite(value) || value < 0 || value > maximum)
            return FALSE;
        health = value;
        return TRUE;
    }
    BOOL __cdecl ReadPosition(float* x, float* y, float* z)
    {
        if (!ready || !positionAvailable) return FALSE;
        *x = positionX; *y = positionY; *z = positionZ;
        return TRUE;
    }
    int teleportStatus = 0;
    int currentArea = 0;
    int __cdecl Interior() { return ready ? currentArea : -1; }
    int __cdecl Teleport(float x, float y, float z, int area)
    {
        if (!ready || health <= 0) return 1;
        if (teleportStatus) return teleportStatus;
        if (area != -1) currentArea = area;
        positionX = x; positionY = y; positionZ = z;
        return 0;
    }
    float heading = 45;
    int headingStatus = 0;
    int __cdecl ReadHeading(float* value)
    {
        if (!ready) return 1;
        if (headingStatus) return headingStatus;
        *value = heading;
        return 0;
    }
    int __cdecl WriteHeading(float value)
    {
        if (!ready || health <= 0) return 1;
        if (headingStatus) return headingStatus;
        heading = value;
        return 0;
    }
    const SpaHostApi api{sizeof(SpaHostApi), IsReady, IsThread, ShowText, Log,
        KeyDown, Focus, ReadHealth, WriteHealth, spa::HostApiVersion, spa::PackageVersion, ReadPosition, Interior, Teleport, ReadHeading, WriteHeading, ReadArmour, WriteArmour,
        ReadMoney, WriteMoney, ReadWantedLevel, WriteWantedLevel, ReadWeapon, WeaponAction, ReadVehicle, GameTimeMs,
        RequestModel, ModelReady, ReleaseModel, CaptureVehicle, VehicleValid, VehicleInfo, CloseVehicle,
        SpawnVehicle, RemoveVehicle, CleanupOwnedVehicles, EnterVehicle, LeaveVehicle,
        SetVehicleHealth, RepairVehicle};
    struct Init
    {
        Init() { bindings::SetHost(&api); }
    } initialize;
}

void InstallTestControls(py::module_& module)
{
    module.def("_test_vehicle_damage", [](DWORD token, bool wrecked, bool unsupported) {
        auto& car = handleVehicles.at(vehicleHandles.at(token).entity);
        car.damaged = car.burning = car.engineBroken = true;
        car.wrecked = wrecked; car.unsupported = unsupported;
    });
    module.def("_test_vehicle_damage_state", [](DWORD token) {
        const auto& car = handleVehicles.at(vehicleHandles.at(token).entity);
        return py::make_tuple(car.damaged, car.burning, car.engineBroken);
    });
    module.def("_test_player_seat_warp", [](bool completed, bool failProcessing) {
        struct Task { bool m_bWarpingInToCar; };
        std::vector<std::string> calls;
        int references = 0;
        bool restored = false, result = false, failed = false;
        try
        {
            result = spa::WarpPlayerSeat<Task>(
                [&](Task* task) {
                    new (task) Task{false};
                    ++references;
                    calls.emplace_back("construct");
                },
                [&](Task* task) {
                    if (!task->m_bWarpingInToCar) throw std::runtime_error("warp flag missing");
                    calls.emplace_back("warp");
                    if (failProcessing) throw std::runtime_error("processing failed");
                    return completed;
                },
                [&](Task* task) {
                    --references;
                    task->~Task();
                    calls.emplace_back("destroy");
                },
                [&] {
                    if (references != 0) throw std::runtime_error("temporary task reference leaked");
                    restored = true;
                    calls.emplace_back("restore_player_control");
                });
        }
        catch (const std::runtime_error&) { failed = true; }
        py::list sequence;
        for (const auto& call : calls) sequence.append(call);
        return py::make_tuple(result, restored, references, sequence, failed);
    });
    module.def("_test_reset", [] { onThread = ready = true; health = 25; maximum = 100; armour = 10; money = 500; wantedLevel = 1; wantedMaximum = 6; wantedBlocked = false; lastText.clear(); positionAvailable = true; positionX = 12.5f; positionY = -34; positionZ = 8; teleportStatus = 0; currentArea = 0; heading = 45; headingStatus = 0; });
    module.def("_test_wanted_maximum", [](int value) { wantedMaximum = value; });
    module.def("_test_wanted_blocked", [](bool value) { wantedBlocked = value; });
    module.def("_test_thread", [](bool value) { onThread = value; });
    module.def("_test_max_health", [](float value) { maximum = value; });
    module.def("_test_game_time", [](DWORD value) { gameTimeMs = value; });
    module.def("_test_reset_models", [] {
        modelLeases.clear(); loadedModels.clear(); modelRefs.clear(); nextModelToken = 0; invalidModel = false;
    });
    module.def("_test_model_loaded", [](int model, bool loaded) {
        loadedModels[model] = loaded;
        if (!loaded) modelRefs[model] = 0;
    });
    module.def("_test_model_invalid", [](bool value) { invalidModel = value; });
    module.def("_test_model_refs", [](int model) { return modelRefs[model]; });
    module.def("_test_weapon_status", [](int value) { weaponStatus = value; });
    module.def("_test_reset_weapons", [] { weaponIds.fill(0); weaponAmmo.fill(0); activeSlot = weaponStatus = 0; });
    module.def("_test_vehicle", [](int state, int model, float currentHealth, bool driver) {
        vehicleState = state;
        vehicleData = {model, driver ? TRUE : FALSE, currentHealth, 10, 20, 30};
    }, py::arg("state") = 0, py::arg("model") = 411, py::arg("health") = 750, py::arg("driver") = true);
    module.def("_test_vehicle_position", [](float x, float y, float z) {
        vehicleData.x = x; vehicleData.y = y; vehicleData.z = z;
    });
    module.def("_test_reset_vehicle_handles", [] {
        seatStatus = 0; exitPending = false;
        ownedVehicles.clear(); nextOwnedVehicle = 1000;
        handleVehicles.clear(); vehicleHandles.clear(); currentVehicleId = 1; nextVehicleToken = 0; failVehicleReference = false;
    });
    module.def("_test_handle_current", [](int id) {
        currentVehicleId = id;
        auto found = handleVehicles.find(id);
        if (found != handleVehicles.end()) vehicleData = found->second.data;
    });
    module.def("_test_handle_data", [](int id, float health, float x, float y, float z) {
        auto& data = handleVehicles.at(id).data;
        data.health = health; data.x = x; data.y = y; data.z = z;
    });
    module.def("_test_handle_remove_and_reuse", [](int id) {
        for (auto& item : vehicleHandles)
            if (item.second.entity == id) item.second.referenceAlive = false;
        // Reuse the exact same simulated slot/generation, testing CReference protection.
        auto& entity = handleVehicles.at(id);
        entity.data = {400, FALSE, 1000, 100, 200, 300};
        if (currentVehicleId == id) vehicleData = entity.data;
    });
    module.def("_test_handle_reference_failure", [](bool value) { failVehicleReference = value; });
    module.def("_test_owned_vehicle_busy", [](DWORD token, bool busy) {
        ownedVehicles.at(vehicleHandles.at(token).entity) = busy;
    });
    module.def("_test_owned_vehicle_count", [] { return ownedVehicles.size(); });
    module.def("_test_seat_status", [](int status) { seatStatus = status; });
    module.def("_test_finish_vehicle_exit", [] {
        if (!exitPending) return;
        if (ownedVehicles.count(currentVehicleId)) ownedVehicles[currentVehicleId] = false;
        vehicleData.isDriver = FALSE;
        handleVehicles.at(currentVehicleId).data.isDriver = FALSE;
        vehicleState = 0;
        exitPending = false;
    });
    module.def("_test_ready", [](bool value) { ready = value; });
    module.def("_test_position", [](float x, float y, float z) { positionX = x; positionY = y; positionZ = z; });
    module.def("_test_position_available", [](bool value) { positionAvailable = value; });
    module.def("_test_teleport_status", [](int value) { teleportStatus = value; });
    module.def("_test_heading_status", [](int value) { headingStatus = value; });
    module.def("_test_dead", [] { health = 0; });
    module.def("_test_last_text", [] { return lastText; });
}
