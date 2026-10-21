// Test-only host: no GTA addresses, hooks or game process required.
#include "pch.h"
#include "PythonIncludes.h"
#include "Bindings.h"
#include "BuildInfo.h"
#include "WeaponPolicy.h"
#include <array>
#include <string>
#include <cmath>

namespace py = pybind11;
namespace
{
    bool onThread = true, ready = true;
    float health = 25, maximum = 100;
    float armour = 10;
    int money = 500, wantedLevel = 1, wantedMaximum = 6;
    bool wantedBlocked = false;
    DWORD gameTimeMs = 1000;
    DWORD __cdecl GameTimeMs() { return gameTimeMs; }
    int vehicleState = 0;
    SpaPlayerVehicle vehicleData{411, TRUE, 750, 10, 20, 30};
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
    BOOL __cdecl IsThread() { return onThread ? TRUE : FALSE; }
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
        ReadMoney, WriteMoney, ReadWantedLevel, WriteWantedLevel, ReadWeapon, WeaponAction, ReadVehicle, GameTimeMs};
    struct Init
    {
        Init() { bindings::SetHost(&api); }
    } initialize;
}

void InstallTestControls(py::module_& module)
{
    module.def("_test_reset", [] { onThread = ready = true; health = 25; maximum = 100; armour = 10; money = 500; wantedLevel = 1; wantedMaximum = 6; wantedBlocked = false; lastText.clear(); positionAvailable = true; positionX = 12.5f; positionY = -34; positionZ = 8; teleportStatus = 0; currentArea = 0; heading = 45; headingStatus = 0; });
    module.def("_test_wanted_maximum", [](int value) { wantedMaximum = value; });
    module.def("_test_wanted_blocked", [](bool value) { wantedBlocked = value; });
    module.def("_test_thread", [](bool value) { onThread = value; });
    module.def("_test_max_health", [](float value) { maximum = value; });
    module.def("_test_game_time", [](DWORD value) { gameTimeMs = value; });
    module.def("_test_weapon_status", [](int value) { weaponStatus = value; });
    module.def("_test_reset_weapons", [] { weaponIds.fill(0); weaponAmmo.fill(0); activeSlot = weaponStatus = 0; });
    module.def("_test_vehicle", [](int state, int model, float currentHealth, bool driver) {
        vehicleState = state;
        vehicleData = {model, driver ? TRUE : FALSE, currentHealth, 10, 20, 30};
    }, py::arg("state") = 0, py::arg("model") = 411, py::arg("health") = 750, py::arg("driver") = true);
    module.def("_test_vehicle_position", [](float x, float y, float z) {
        vehicleData.x = x; vehicleData.y = y; vehicleData.z = z;
    });
    module.def("_test_ready", [](bool value) { ready = value; });
    module.def("_test_position", [](float x, float y, float z) { positionX = x; positionY = y; positionZ = z; });
    module.def("_test_position_available", [](bool value) { positionAvailable = value; });
    module.def("_test_teleport_status", [](int value) { teleportStatus = value; });
    module.def("_test_heading_status", [](int value) { headingStatus = value; });
    module.def("_test_dead", [] { health = 0; });
    module.def("_test_last_text", [] { return lastText; });
}
