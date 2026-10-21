#include "pch.h"
#include "GameBridge.h"
#include "RuntimeApi.h"
#include "GtaSdk.h"
#include "BuildInfo.h"
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <filesystem>
#include <cmath>

static_assert(sizeof(void*) == 4, "GTA San Andreas requires an x86 build.");

namespace
{
    // GTA SA 1.0 US only. Address references documented in README.md.
    constexpr std::uintptr_t ProcessCall = 0x53E981;
    constexpr std::uintptr_t ProcessGame = 0x53BEE0;
    HMODULE ownModule = nullptr;
    DWORD gameThread = 0;
    bool pinned = false;
    constexpr wchar_t startupLogPath[] = L"C:\\log.txt";

    bool Readable(std::uintptr_t address, SIZE_T size) noexcept
    {
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery(reinterpret_cast<void*>(address), &info, sizeof(info)))
            return false;
        return info.State == MEM_COMMIT && !(info.Protect & (PAGE_NOACCESS | PAGE_GUARD))
            && address + size <= reinterpret_cast<std::uintptr_t>(info.BaseAddress) + info.RegionSize;
    }

    BOOL __cdecl HostReady() { return game::IsReady() ? TRUE : FALSE; }
    BOOL __cdecl HostThread() { return game::IsGameThread() ? TRUE : FALSE; }
    BOOL __cdecl HostKeyDown(int key)
    {
        return game::IsGameThread() && key > 0 && key < 255
            && (GetAsyncKeyState(key) & 0x8000) ? TRUE : FALSE;
    }
    BOOL __cdecl HostFocus()
    {
        DWORD process = 0;
        GetWindowThreadProcessId(GetForegroundWindow(), &process);
        return process == GetCurrentProcessId() ? TRUE : FALSE;
    }
    BOOL __cdecl HostPlayerHealth(float* health, float* maximum)
    {
        return sdk::ReadPlayerHealth(health, maximum) ? TRUE : FALSE;
    }
    BOOL __cdecl HostSetPlayerHealth(float value)
    {
        return sdk::WritePlayerHealth(value) ? TRUE : FALSE;
    }
    BOOL __cdecl HostPlayerPosition(float* x, float* y, float* z)
    {
        return sdk::ReadPlayerPosition(x, y, z) ? TRUE : FALSE;
    }
    BOOL __cdecl HostPlayerArmour(float* value)
    {
        return sdk::ReadPlayerArmour(value) ? TRUE : FALSE;
    }
    BOOL __cdecl HostSetPlayerArmour(float value)
    {
        return sdk::WritePlayerArmour(value) ? TRUE : FALSE;
    }
    BOOL __cdecl HostPlayerMoney(int* value) { return sdk::ReadPlayerMoney(value) ? TRUE : FALSE; }
    BOOL __cdecl HostSetPlayerMoney(int value) { return sdk::WritePlayerMoney(value) ? TRUE : FALSE; }
    BOOL __cdecl HostPlayerWantedLevel(int* value) { return sdk::ReadPlayerWantedLevel(value) ? TRUE : FALSE; }
    BOOL __cdecl HostSetPlayerWantedLevel(int value) { return sdk::WritePlayerWantedLevel(value) ? TRUE : FALSE; }
    const SpaHostApi hostApi{sizeof(SpaHostApi), HostReady, HostThread,
        game::ShowText, game::StartupLog, HostKeyDown, HostFocus,
        HostPlayerHealth, HostSetPlayerHealth, spa::HostApiVersion, spa::PackageVersion, HostPlayerPosition, sdk::PlayerInterior, sdk::TeleportPlayer, sdk::ReadPlayerHeading, sdk::WritePlayerHeading, HostPlayerArmour, HostSetPlayerArmour,
        HostPlayerMoney, HostSetPlayerMoney, HostPlayerWantedLevel, HostSetPlayerWantedLevel};
    SpaTickFunction runtimeTick = nullptr;
    bool runtimeAttempted = false;

    void LoadRuntime() noexcept
    {
        runtimeAttempted = true;
        try
        {
            wchar_t path[32768]{};
            const DWORD length = GetModuleFileNameW(ownModule, path, 32768);
            if (!length || length >= 32768)
            {
                game::StartupLog("ERROR: Cannot determine ASI path.");
                return;
            }
            const auto root = std::filesystem::path(path).parent_path() / L"SanPythonAndreas";
            // Keep this directory registered for Python extension dependencies.
            if (!AddDllDirectory((root / L"python").c_str()))
            {
                game::StartupLog("ERROR: Cannot register bundled Python DLL directory.");
                return;
            }
            const auto libraryPath = root / L"SanPythonRuntime.dll";
            HMODULE library = LoadLibraryExW(libraryPath.c_str(), nullptr,
                LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
            if (!library)
            {
                char error[200]{};
                std::snprintf(error, sizeof(error),
                    "ERROR: Cannot load SanPythonAndreas/SanPythonRuntime.dll (Windows error %lu). Check bundled python folder and x86 architecture.",
                    static_cast<unsigned long>(GetLastError()));
                game::StartupLog(error);
                return;
            }
            runtimeTick = reinterpret_cast<SpaTickFunction>(GetProcAddress(library, "SpaTick"));
            if (!runtimeTick)
                game::StartupLog("ERROR: SanPythonRuntime.dll has no SpaTick export; deploy matching binaries.");
            else
                game::StartupLog("Bundled Python runtime DLL loaded.");
            // Keep the DLL loaded: callbacks and Python objects live until exit.
        }
        catch (...)
        {
            game::StartupLog("ERROR: Exception while loading bundled runtime.");
        }
    }

    void __cdecl ProcessHook()
    {
        reinterpret_cast<void(__cdecl*)()>(ProcessGame)();
        if (!gameThread)
        {
            game::StartupLog("First CGame::Process callback reached.");
            gameThread = GetCurrentThreadId();
            // Code hooks require this module to stay loaded until process exit.
            HMODULE handle = nullptr;
            pinned = GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                GET_MODULE_HANDLE_EX_FLAG_PIN, reinterpret_cast<LPCWSTR>(ownModule), &handle) != FALSE;
            if (!pinned)
                game::StartupLog("ERROR: Could not pin ASI module.");
        }
        if (pinned)
        {
            const bool ready = game::IsReady();
            static bool reportedReady = false;
            if (ready && !reportedReady)
            {
                reportedReady = true;
                game::StartupLog("Player ready; starting Python runtime.");
            }
            if (ready && !runtimeAttempted)
                LoadRuntime();
            if (runtimeTick)
                runtimeTick(ownModule, ready ? TRUE : FALSE, &hostApi);
        }
    }
}

void game::StartupLog(const char* message) noexcept
{
    OutputDebugStringA("SanPythonAndreas: ");
    OutputDebugStringA(message);
    OutputDebugStringA("\n");
    // Kernel32-only file operations also work before Python or its directories
    // exist. No Python, streams, worker threads or loader-dependent UI here.
    HANDLE file = CreateFileW(startupLogPath, FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE)
    {
        const DWORD rootError = GetLastError();
        wchar_t fallback[MAX_PATH]{};
        const DWORD length = GetTempPathW(MAX_PATH, fallback);
        constexpr wchar_t filename[] = L"SanPythonAndreas.log";
        if (!length || length + sizeof(filename) / sizeof(filename[0]) > MAX_PATH)
            return;
        std::memcpy(fallback + length, filename, sizeof(filename));
        file = CreateFileW(fallback, FILE_APPEND_DATA,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE)
            return;
        char error[160]{};
        std::snprintf(error, sizeof(error), "C:\\log.txt could not be opened (Windows error %lu); using TEMP.\r\n",
            static_cast<unsigned long>(rootError));
        DWORD written = 0;
        WriteFile(file, error, static_cast<DWORD>(std::strlen(error)), &written, nullptr);
    }
    DWORD written = 0;
    WriteFile(file, message, static_cast<DWORD>(std::strlen(message)), &written, nullptr);
    WriteFile(file, "\r\n", 2, &written, nullptr);
    CloseHandle(file);
}

bool game::Install(HMODULE module) noexcept
{
    StartupLog("--- ASI loaded: host API 8; Python 3.11 + SDK + pybind11 + money + wanted level ---");
    StartupLog(spa::PackageVersion);
    StartupLog(spa::SdkRevision);
    if (reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)) != 0x400000 ||
        !Readable(0x401000, 4) || !Readable(ProcessCall, 5))
    {
        StartupLog("ERROR: Unsupported executable base or inaccessible game addresses. Hook not installed.");
        return false;
    }

    std::uint32_t signature = 0;
    std::memcpy(&signature, reinterpret_cast<void*>(0x401000), sizeof(signature));
    char details[160]{};
    std::snprintf(details, sizeof(details), "Executable signature at 0x401000: 0x%08lX",
        static_cast<unsigned long>(signature));
    StartupLog(details);
    if (signature != 0x53EC8B55 && signature != 0x16197BE9)
    {
        StartupLog("ERROR: Only GTA SA 1.0 US Compact/Hoodlum is supported. Hook not installed.");
        return false;
    }

    auto* call = reinterpret_cast<unsigned char*>(ProcessCall);
    std::int32_t oldOffset = 0;
    std::memcpy(&oldOffset, call + 1, sizeof(oldOffset));
    std::snprintf(details, sizeof(details), "Call at 0x53E981: opcode=0x%02X target=0x%08lX",
        static_cast<unsigned>(call[0]), static_cast<unsigned long>(ProcessCall + 5 + oldOffset));
    StartupLog(details);
    if (call[0] != 0xE8 || ProcessCall + 5 + oldOffset != ProcessGame)
    {
        StartupLog("ERROR: Unexpected game call or conflicting hook; not patched.");
        return false;
    }

    DWORD protection = 0;
    if (!VirtualProtect(call, 5, PAGE_EXECUTE_READWRITE, &protection))
    {
        StartupLog("ERROR: VirtualProtect failed; hook not installed.");
        return false;
    }
    ownModule = module;
    const auto offset = static_cast<std::int32_t>(
        reinterpret_cast<std::uintptr_t>(&ProcessHook) - (ProcessCall + 5));
    std::memcpy(call + 1, &offset, sizeof(offset));
    FlushInstructionCache(GetCurrentProcess(), call, 5);
    DWORD ignored = 0;
    VirtualProtect(call, 5, protection, &ignored);
    StartupLog("Hook installed; waiting for first game callback.");
    return true;
}

bool game::IsGameThread() noexcept
{
    return gameThread != 0 && gameThread == GetCurrentThreadId();
}

bool game::IsReady() noexcept
{
    // FindPlayerPed(-1); exclude user/code pauses (including loading).
    return !*reinterpret_cast<const bool*>(0xB7CB48)
        && !*reinterpret_cast<const bool*>(0xB7CB49)
        && sdk::HasPlayer();
}

void game::ShowText(const char* text) noexcept
{
    sdk::ShowText(text);
}
