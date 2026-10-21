#pragma once
#include <Windows.h>

// Private host/runtime ABI. Keep both binaries from the same build together.
struct SpaPlayerVehicle
{
    int modelId;
    BOOL isDriver;
    float health;
    float x, y, z;
};

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
    BOOL (__cdecl* playerArmour)(float*);
    BOOL (__cdecl* setPlayerArmour)(float);
    BOOL (__cdecl* playerMoney)(int*);
    BOOL (__cdecl* setPlayerMoney)(int);
    BOOL (__cdecl* playerWantedLevel)(int*);
    BOOL (__cdecl* setPlayerWantedLevel)(int);
    BOOL (__cdecl* playerWeapon)(int*, unsigned int*);
    // Actions: 0 give, 1 select, 2 remove one, 3 clear all.
    // Status: 0 success, 1 unavailable/dead, 2 restricted state, 3 not owned,
    // 4 invalid arguments, 5 model loading failed.
    int (__cdecl* playerWeaponAction)(int, int, unsigned int, BOOL);
    // -1 unavailable player/invalid vehicle state; 0 on foot; 1 snapshot filled.
    int (__cdecl* playerVehicle)(SpaPlayerVehicle*);
    DWORD (__cdecl* gameTimeMs)(); // CTimer game clock, modulo 2^32; readable while paused.
    // request: 0 success, 1 inactive, 2 invalid model, 3 lease limit. token > 0.
    int (__cdecl* requestModel)(int, DWORD*);
    int (__cdecl* modelReady)(DWORD); // 1 ready (own reference held), 0 pending, -1 unavailable/stale
    void (__cdecl* releaseModel)(DWORD); // own reference only; safe while paused
};
using SpaTickFunction = void (__cdecl*)(HMODULE, BOOL, const SpaHostApi*);
