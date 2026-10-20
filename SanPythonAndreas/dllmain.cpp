#include "pch.h"
#include "GameBridge.h"

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(module);
        // ASI startup only: install before the game loop starts. No Python,
        // worker threads, waits or file access under the loader lock.
        return game::Install(module) ? TRUE : FALSE;
    }
    // Interpreter and hook live until process exit. No Python under loader lock.
    return TRUE;
}
