#pragma once
#include <Windows.h>

// Private host/runtime ABI. Keep both binaries from the same build together.
struct SpaHostApi
{
    DWORD size;
    BOOL (__cdecl* isReady)();
    BOOL (__cdecl* isGameThread)();
    void (__cdecl* showText)(const char*);
    void (__cdecl* log)(const char*);
    BOOL (__cdecl* keyDown)(int);
    BOOL (__cdecl* hasFocus)();
    BOOL (__cdecl* playerHealth)(float*, float*);
    BOOL (__cdecl* setPlayerHealth)(float);
    DWORD version;
    const char* packageVersion;
    BOOL (__cdecl* playerPosition)(float*, float*, float*);
    int (__cdecl* playerInterior)(); // -1 if unavailable
    // 0 success; 1 unavailable/dead; 2 door transition active; 3 unsupported vehicle; 4 invalid target
    int (__cdecl* teleportPlayer)(float, float, float, int); // interior -1 = current
    int (__cdecl* playerHeading)(float*); // degrees; status codes as above
    int (__cdecl* setPlayerHeading)(float);
};
using SpaTickFunction = void (__cdecl*)(HMODULE, BOOL, const SpaHostApi*);
