#pragma once
#include <Windows.h>
namespace game
{
    bool Install(HMODULE module) noexcept;
    void StartupLog(const char* message) noexcept;
    bool IsReady() noexcept;
    bool IsGameThread() noexcept;
    void ShowText(const char* text) noexcept;
}
