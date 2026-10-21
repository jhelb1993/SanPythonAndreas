#pragma once
namespace sdk
{
    bool HasPlayer() noexcept;
    bool ReadPlayerHealth(float* health, float* maximum) noexcept;
    bool WritePlayerHealth(float value) noexcept;
    bool ReadPlayerArmour(float* armour) noexcept;
    bool WritePlayerArmour(float value) noexcept;
    bool ReadPlayerPosition(float* x, float* y, float* z) noexcept;
    int PlayerInterior() noexcept;
    int TeleportPlayer(float x, float y, float z, int interior) noexcept;
    int ReadPlayerHeading(float* degrees) noexcept;
    int WritePlayerHeading(float degrees) noexcept;
    void ShowText(const char* text) noexcept;
}
