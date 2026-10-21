#pragma once
#include <Windows.h>
struct SpaPlayerVehicle;
namespace sdk
{
    bool HasPlayer() noexcept;
    bool ReadPlayerHealth(float* health, float* maximum) noexcept;
    bool WritePlayerHealth(float value) noexcept;
    bool ReadPlayerArmour(float* armour) noexcept;
    bool WritePlayerArmour(float value) noexcept;
    bool ReadPlayerMoney(int* value) noexcept;
    bool WritePlayerMoney(int value) noexcept;
    bool ReadPlayerWantedLevel(int* value) noexcept;
    bool WritePlayerWantedLevel(int value) noexcept;
    bool ReadPlayerWeapon(int* id, unsigned int* ammo) noexcept;
    int PlayerWeaponAction(int action, int id, unsigned int ammo, bool equip) noexcept;
    int ReadPlayerVehicle(SpaPlayerVehicle* value) noexcept;
    int RequestModel(int model, DWORD* token) noexcept;
    int ModelReady(DWORD token) noexcept;
    void ReleaseModel(DWORD token) noexcept;
    int CapturePlayerVehicle(DWORD* token) noexcept;
    BOOL VehicleHandleValid(DWORD token) noexcept;
    int VehicleHandleInfo(DWORD token, SpaPlayerVehicle* value) noexcept;
    void CloseVehicleHandle(DWORD token) noexcept;
    bool ReadPlayerPosition(float* x, float* y, float* z) noexcept;
    int PlayerInterior() noexcept;
    int TeleportPlayer(float x, float y, float z, int interior) noexcept;
    int ReadPlayerHeading(float* degrees) noexcept;
    int WritePlayerHeading(float degrees) noexcept;
    void ShowText(const char* text) noexcept;
}
