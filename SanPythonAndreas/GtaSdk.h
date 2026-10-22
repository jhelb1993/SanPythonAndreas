#pragma once
#include <Windows.h>
struct SpaPlayerVehicle;
struct SpaVehicleMotion;
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
    int SpawnVehicle(int model, float x, float y, float z, float heading, DWORD* token) noexcept;
    int RemoveVehicle(DWORD token) noexcept;
    void CleanupOwnedVehicles() noexcept;
    int EnterPlayerVehicle(DWORD token, int seat) noexcept;
    int LeavePlayerVehicle() noexcept;
    int SetVehicleHealth(DWORD token, float value) noexcept;
    int RepairVehicle(DWORD token) noexcept;
    int VehicleColors(DWORD token, int* primary, int* secondary) noexcept;
    int SetVehicleColor(DWORD token, int channel, int color) noexcept;
    int VehicleMotion(DWORD token, SpaVehicleMotion* value) noexcept;
    int SetVehicleHeading(DWORD token, float degrees) noexcept;
    int SetVehicleVelocity(DWORD token, float x, float y, float z) noexcept;
    int VehicleInterior(DWORD token, int* area) noexcept;
    int TeleportVehicle(DWORD token, float x, float y, float z, int interior) noexcept;
    bool ReadPlayerPosition(float* x, float* y, float* z) noexcept;
    int PlayerInterior() noexcept;
    int TeleportPlayer(float x, float y, float z, int interior) noexcept;
    int ReadPlayerHeading(float* degrees) noexcept;
    int WritePlayerHeading(float degrees) noexcept;
    void ShowText(const char* text) noexcept;
}
