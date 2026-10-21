#include "pch.h"
#include "GtaSdk.h"
#include "GameBridge.h"
#include <CPed.h>
#include <CHud.h>
#include <CVehicle.h>
#include <CStreaming.h>
#include <CCamera.h>
#include <CEntryExitManager.h>
#include <CTimeCycle.h>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <cstring>

// Pinned SDK headers validate the full CPed layout. Keep our supported-version
// assumptions explicit as well; a mismatching SDK must fail at compile time.
static_assert(sizeof(void*) == 4);
static_assert(offsetof(CPed, m_fHealth) == 0x540);
static_assert(offsetof(CPed, m_fMaxHealth) == 0x544);

namespace
{
    CPed* FindCurrentPlayer() noexcept
    {
        return plugin::CallAndReturn<CPed*, 0x56E210, int>(-1);
    }

    bool Accessible(const void* address, SIZE_T size, bool writable = false) noexcept
    {
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery(address, &info, sizeof(info)) || info.State != MEM_COMMIT
            || (info.Protect & (PAGE_GUARD | PAGE_NOACCESS)))
            return false;
        if (reinterpret_cast<std::uintptr_t>(address) + size
            > reinterpret_cast<std::uintptr_t>(info.BaseAddress) + info.RegionSize)
            return false;
        return !writable || (info.Protect & (PAGE_READWRITE | PAGE_WRITECOPY
            | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY));
    }

    int ControlledEntity(CPed* player, CPhysical*& entity) noexcept
    {
        if (!player || !Accessible(player, sizeof(CPed), true)) return 1;
        entity = player;
        if (player->m_nPedFlags.bInVehicle)
        {
            CVehicle* vehicle = player->m_pVehicle;
            if (!vehicle || !Accessible(vehicle, sizeof(CVehicle), true)
                || vehicle->m_pDriver != player || vehicle->m_pTractor || vehicle->m_pTrailer
                || vehicle->m_nVehicleSubClass == VEHICLE_TRAIN
                || vehicle->m_nVehicleSubClass == VEHICLE_TRAILER
                || vehicle->m_nAreaCode != player->m_nAreaCode)
                return 3;
            entity = vehicle;
        }
        return 0;
    }
}

bool sdk::HasPlayer() noexcept
{
    return FindCurrentPlayer() != nullptr;
}

bool sdk::ReadPlayerHealth(float* health, float* maximum) noexcept
{
    if (!game::IsGameThread() || !game::IsReady())
        return false;
    const CPed* player = FindCurrentPlayer();
    if (!player || !Accessible(&player->m_fHealth, sizeof(float))
        || !Accessible(&player->m_fMaxHealth, sizeof(float)))
        return false;
    *health = player->m_fHealth;
    *maximum = player->m_fMaxHealth;
    return std::isfinite(*health) && *health >= 0
        && std::isfinite(*maximum) && *maximum > 0;
}

bool sdk::WritePlayerHealth(float value) noexcept
{
    float health = 0, maximum = 0;
    if (!ReadPlayerHealth(&health, &maximum) || health <= 0
        || !std::isfinite(value) || value < 0 || value > maximum)
        return false;
    CPed* player = FindCurrentPlayer();
    if (!player || !Accessible(&player->m_fHealth, sizeof(float), true))
        return false;
    player->m_fHealth = value;
    return true;
}

bool sdk::ReadPlayerPosition(float* x, float* y, float* z) noexcept
{
    if (!game::IsGameThread() || !game::IsReady())
        return false;
    CPed* player = FindCurrentPlayer();
    if (!player || !Accessible(&player->m_matrix, sizeof(player->m_matrix)))
        return false;
    // SDK GetPosition() uses matrix->pos if present, otherwise placement.m_vPosn.
    // Validate the selected storage before calling that inline accessor.
    const CVector* storage = player->m_matrix ? &player->m_matrix->pos : &player->m_placement.m_vPosn;
    if (!Accessible(storage, sizeof(CVector)))
        return false;
    const CVector& position = player->GetPosition();
    if (!std::isfinite(position.x) || !std::isfinite(position.y) || !std::isfinite(position.z))
        return false;
    *x = position.x;
    *y = position.y;
    *z = position.z;
    return true;
}

int sdk::PlayerInterior() noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return -1;
    CPed* player = FindCurrentPlayer();
    return player && Accessible(&player->m_nAreaCode, sizeof(player->m_nAreaCode))
        ? player->m_nAreaCode : -1;
}

int sdk::TeleportPlayer(float x, float y, float z, int interior) noexcept
{
    // Deliberately bounded: this is a map teleport, not an arbitrary memory write.
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)
        || std::fabs(x) > 20000 || std::fabs(y) > 20000 || z < -1000 || z > 10000
        || interior < -1 || interior > 255)
        return 4;
    float health = 0, maximum = 0;
    if (!ReadPlayerHealth(&health, &maximum) || health <= 0) return 1;
    const int area = PlayerInterior();
    if (area < 0) return 1;
    const int targetArea = interior == -1 ? area : interior;
    // Do not interfere with the game's door/fade transition, even within an area.
    if (reinterpret_cast<decltype(&CEntryExitManager::WeAreInInteriorTransition)>(0x43E400)())
        return 2;
    CPed* player = FindCurrentPlayer();
    CPhysical* entity = nullptr;
    const int status = ControlledEntity(player, entity);
    if (status) return status;
    // Avoid out-of-line SDK vector constructors: copying is inline in this SDK.
    const CVector* storage = entity->m_matrix ? &entity->m_matrix->pos : &entity->m_placement.m_vPosn;
    if (!Accessible(storage, sizeof(CVector))) return 1;
    auto table = *reinterpret_cast<void***>(entity);
    if (!Accessible(table, 15 * sizeof(void*)) || !table[14]) return 1;
    CVector target(*storage);
    target.x = x; target.y = y; target.z = z;
    auto* worldArea = reinterpret_cast<int*>(0xB72914); // CGame::currArea
    if (!Accessible(worldArea, sizeof(*worldArea), true)) return 1;
    // Validate every occupant before changing anything. The driver vehicle moves
    // with its occupants; their area codes must agree with the new world area.
    CVehicle* vehicle = entity != player ? static_cast<CVehicle*>(entity) : nullptr;
    if (vehicle)
        for (CPed* passenger : vehicle->m_apPassengers)
            if (passenger && !Accessible(passenger, sizeof(CPed), true)) return 1;
    const bool changingArea = targetArea != area;
    auto* entryStackSize = reinterpret_cast<int*>(0x96A7C4);
    if (changingArea && !Accessible(entryStackSize, sizeof(*entryStackSize), true)) return 1;
    *worldArea = targetArea;
    player->m_nAreaCode = static_cast<unsigned char>(targetArea);
    entity->m_nAreaCode = static_cast<unsigned char>(targetArea);
    if (vehicle)
        for (CPed* passenger : vehicle->m_apPassengers)
            if (passenger) passenger->m_nAreaCode = static_cast<unsigned char>(targetArea);
    if (changingArea)
    {
        // A coordinate teleport does not traverse an entry/exit portal. Discard
        // the previous portal context (also used by radar world coordinates).
        *entryStackSize = 0;
        player->m_pEnex = nullptr;
        if (vehicle)
            for (CPed* passenger : vehicle->m_apPassengers)
                if (passenger) passenger->m_pEnex = nullptr;
        // Pinned CStreaming.cpp: unload the old area's buildings before loading
        // the target. Extra interior colour must not leak into the next area.
        reinterpret_cast<decltype(&CStreaming::RemoveBuildingsNotInArea)>(0x4094B0)(targetArea);
        reinterpret_cast<decltype(&CTimeCycle::StopExtraColour)>(0x55FF20)(false);
    }
    // Verified against pinned CStreaming.cpp; synchronous scene/collision load.
    reinterpret_cast<decltype(&CStreaming::LoadSceneCollision)>(0x40ED80)(&target);
    reinterpret_cast<decltype(&CStreaming::LoadScene)>(0x40EB70)(&target);
    // CEntity.cpp dispatches Teleport via vtable slot 14 for peds and vehicles.
    using Teleport = void (__thiscall*)(CEntity*, CVector, bool);
    reinterpret_cast<Teleport>(table[14])(entity, target, false);
    entity->m_vecMoveSpeed.x = entity->m_vecMoveSpeed.y = entity->m_vecMoveSpeed.z = 0;
    entity->m_vecTurnSpeed.x = entity->m_vecTurnSpeed.y = entity->m_vecTurnSpeed.z = 0;
    player->m_vecMoveSpeed.x = player->m_vecMoveSpeed.y = player->m_vecMoveSpeed.z = 0;
    player->m_vecTurnSpeed.x = player->m_vecTurnSpeed.y = player->m_vecTurnSpeed.z = 0;
    if (changingArea)
    {
        // TheCamera, RestoreWithJumpCut: pinned CCamera.cpp.
        using RestoreCamera = void (__thiscall*)(CCamera*);
        reinterpret_cast<RestoreCamera>(0x50BAB0)(reinterpret_cast<CCamera*>(0xB6F028));
    }
    return 0;
}

int sdk::ReadPlayerHeading(float* degrees) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    CPhysical* entity = nullptr;
    const int status = ControlledEntity(FindCurrentPlayer(), entity);
    if (status) return status;
    if (entity->m_matrix && !Accessible(entity->m_matrix, sizeof(CMatrix))) return 1;
    // Pinned CPlaceable.cpp: GetHeading returns radians, SetHeading consumes radians.
    using GetHeading = float (__thiscall*)(CPlaceable*);
    const float radians = reinterpret_cast<GetHeading>(0x441DB0)(entity);
    if (!std::isfinite(radians)) return 1;
    double angle = std::fmod(static_cast<double>(radians) * 180.0 / 3.14159265358979323846, 360.0);
    if (angle < 0) angle += 360.0;
    *degrees = static_cast<float>(angle);
    if (*degrees >= 360) *degrees = 0;
    return 0;
}

int sdk::WritePlayerHeading(float degrees) noexcept
{
    if (!std::isfinite(degrees) || degrees < 0 || degrees >= 360) return 4;
    float health = 0, maximum = 0;
    if (!ReadPlayerHealth(&health, &maximum) || health <= 0) return 1;
    CPed* player = FindCurrentPlayer();
    CPhysical* entity = nullptr;
    const int status = ControlledEntity(player, entity);
    if (status) return status;
    if (entity->m_matrix && !Accessible(entity->m_matrix, sizeof(CMatrix), true)) return 1;
    const float radians = static_cast<float>(degrees * (3.14159265358979323846 / 180.0));
    using SetHeading = void (__thiscall*)(CPlaceable*, float);
    reinterpret_cast<SetHeading>(0x43E0C0)(entity, radians);
    if (entity == player)
    {
        // Keep the ped's movement/aiming controller from restoring the old yaw.
        player->m_fCurrentRotation = radians;
        player->m_fAimingRotation = radians;
    }
    entity->m_vecTurnSpeed.x = entity->m_vecTurnSpeed.y = entity->m_vecTurnSpeed.z = 0;
    if (entity->m_pRwObject)
    {
        // CEntity.cpp: synchronize the visible RenderWare object immediately.
        using Update = void (__thiscall*)(CEntity*);
        reinterpret_cast<Update>(0x446F90)(entity); // UpdateRwMatrix
        reinterpret_cast<Update>(0x532B00)(entity); // UpdateRwFrame
    }
    return 0;
}

void sdk::ShowText(const char* text) noexcept
{
    // Use the SDK's exact function type; the address remains specific to 1.0 US.
    // A local mutable copy supports older SDK declarations taking char* as well.
    if (!text)
        return;
    const auto length = std::strlen(text);
    if (length > 200)
        return;
    char message[201]{};
    std::memcpy(message, text, length);
    reinterpret_cast<decltype(&CHud::SetHelpMessage)>(0x588BE0)(message, false, false, false);
}
