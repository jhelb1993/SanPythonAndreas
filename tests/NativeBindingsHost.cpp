// Test-only host: no GTA addresses, hooks or game process required.
#include "pch.h"
#include "PythonIncludes.h"
#include "Bindings.h"
#include "BuildInfo.h"
#include <string>
#include <cmath>

namespace py = pybind11;
namespace
{
    bool onThread = true, ready = true;
    float health = 25, maximum = 100;
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
    int __cdecl Interior() { return ready ? 0 : -1; }
    int __cdecl Teleport(float x, float y, float z, int area)
    {
        if (!ready || health <= 0) return 1;
        if (area != -1 && area != 0) return 2;
        if (teleportStatus) return teleportStatus;
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
        KeyDown, Focus, ReadHealth, WriteHealth, spa::HostApiVersion, spa::PackageVersion, ReadPosition, Interior, Teleport, ReadHeading, WriteHeading};
    struct Init
    {
        Init() { bindings::SetHost(&api); }
    } initialize;
}

void InstallTestControls(py::module_& module)
{
    module.def("_test_reset", [] { onThread = ready = true; health = 25; maximum = 100; lastText.clear(); positionAvailable = true; positionX = 12.5f; positionY = -34; positionZ = 8; teleportStatus = 0; heading = 45; headingStatus = 0; });
    module.def("_test_thread", [](bool value) { onThread = value; });
    module.def("_test_ready", [](bool value) { ready = value; });
    module.def("_test_position", [](float x, float y, float z) { positionX = x; positionY = y; positionZ = z; });
    module.def("_test_position_available", [](bool value) { positionAvailable = value; });
    module.def("_test_teleport_status", [](int value) { teleportStatus = value; });
    module.def("_test_heading_status", [](int value) { headingStatus = value; });
    module.def("_test_dead", [] { health = 0; });
    module.def("_test_last_text", [] { return lastText; });
}
