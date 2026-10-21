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
#include <CPlayerInfo.h>
#include <CWanted.h>
#include <CWeaponInfo.h>
#include "WeaponPolicy.h"
#include "RuntimeApi.h"
#include <CBaseModelInfo.h>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <cstring>

// Pinned SDK headers validate the full CPed layout. Keep our supported-version
// assumptions explicit as well; a mismatching SDK must fail at compile time.
static_assert(sizeof(void*) == 4);
static_assert(offsetof(CPed, m_fHealth) == 0x540);
static_assert(offsetof(CPed, m_fMaxHealth) == 0x544);
static_assert(offsetof(CPed, m_fArmour) == 0x548);
static_assert(offsetof(CPlayerInfo, m_nMoney) == 0xB8);
static_assert(offsetof(CWanted, m_nWantedLevel) == 0x2C);
static_assert(offsetof(CVehicle, m_fHealth) == 0x4C0);

namespace
{
    struct ModelLease
    {
        DWORD token = 0;
        int model = 0;
        CBaseModelInfo* info = nullptr; // compared with current table; never blindly dereferenced
        unsigned int key = 0;
        short txd = -1;
        RwObject* rwObject = nullptr;
        bool pinned = false;
    };
    std::array<ModelLease, 256> modelLeases{};
    DWORD nextModelToken = 0;

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

    CBaseModelInfo* ModelInfo(int model) noexcept
    {
        if (model < 1 || model >= 20000) return nullptr;
        // Pinned CModelInfo.cpp: ms_modelInfoPtrs.
        auto* entry = reinterpret_cast<CBaseModelInfo**>(0xA9B0C8) + model;
        if (!Accessible(entry, sizeof(*entry)) || !*entry
            || !Accessible(*entry, sizeof(CBaseModelInfo), true)) return nullptr;
        return *entry;
    }

    CStreamingInfo* StreamingInfo(int model) noexcept
    {
        auto* info = reinterpret_cast<CStreamingInfo*>(0x8E4CC0) + model;
        return Accessible(info, sizeof(CStreamingInfo)) ? info : nullptr;
    }

    ModelLease* FindModelLease(DWORD token) noexcept
    {
        if (token == 0) return nullptr;
        for (auto& lease : modelLeases)
            if (lease.token == token) return &lease;
        return nullptr;
    }

    bool SameModel(const ModelLease& lease, const CBaseModelInfo* info) noexcept
    {
        return info && info == lease.info && info->m_nKey == lease.key && info->m_nTxdIndex == lease.txd;
    }

    CPlayerInfo* CurrentPlayerInfo() noexcept
    {
        if (!game::IsGameThread() || !game::IsReady()) return nullptr;
        // Pinned CWorld.cpp: PlayerInFocus and Players[2].
        const auto* focus = reinterpret_cast<const unsigned char*>(0xB7CD74);
        if (!Accessible(focus, sizeof(*focus)) || *focus > 1) return nullptr;
        auto* info = reinterpret_cast<CPlayerInfo*>(0xB7CD98) + *focus;
        if (!Accessible(info, sizeof(CPlayerInfo), true)
            || !info->m_pPed || info->m_pPed != FindCurrentPlayer()) return nullptr;
        return info;
    }

    CWanted* CurrentWanted(CPlayerInfo* info, bool writable = false) noexcept
    {
        if (!info) return nullptr;
        CWanted* wanted = info->m_PlayerData.m_pWanted;
        return wanted && Accessible(wanted, sizeof(CWanted), writable) ? wanted : nullptr;
    }

    bool LivingPlayer() noexcept
    {
        float health = 0, maximum = 0;
        return sdk::ReadPlayerHealth(&health, &maximum) && health > 0;
    }

    CWeaponInfo* WeaponInfo(int id) noexcept
    {
        auto* info = reinterpret_cast<decltype(&CWeaponInfo::GetWeaponInfo)>(0x743C60)(
            static_cast<eWeaponType>(id), WEAPSKILL_STD);
        return info && Accessible(info, sizeof(CWeaponInfo)) && info->m_nSlot < 13 ? info : nullptr;
    }

    bool LoadWeaponModels(const CWeaponInfo* info) noexcept
    {
        // Ordinary requests add no persistent mission/game/keep flags. Existing
        // flags belonging to GTA or other mods are never cleared by this API.
        const int models[]{info->m_nModelId1, info->m_nModelId2};
        for (int model : models)
        {
            if (model <= 0) continue;
            if (model >= 20000) return false;
            auto* state = reinterpret_cast<CStreamingInfo*>(0x8E4CC0) + model;
            if (!Accessible(state, sizeof(CStreamingInfo))) return false;
        }
        for (int model : models)
            if (model > 0)
                reinterpret_cast<decltype(&CStreaming::RequestModel)>(0x4087E0)(model, 0);
        reinterpret_cast<decltype(&CStreaming::LoadAllRequestedModels)>(0x40EA10)(false);
        for (int model : models)
            if (model > 0 && (reinterpret_cast<CStreamingInfo*>(0x8E4CC0) + model)->m_nLoadState != LOADSTATE_LOADED)
                return false;
        return true;
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
    const CPlayerInfo* info = CurrentPlayerInfo();
    if (!info) return false;
    const CPed* player = info->m_pPed;
    if (!Accessible(&player->m_fHealth, sizeof(float)))
        return false;
    *health = player->m_fHealth;
    // CPlayerInfo::AddHealth uses this player-specific limit. The raw
    // STAT_MAX_HEALTH uses different units; leave its conversion to GTA.
    *maximum = static_cast<float>(info->m_nMaxHealth);
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

bool sdk::ReadPlayerArmour(float* armour) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return false;
    const CPed* player = FindCurrentPlayer();
    if (!player || !Accessible(&player->m_fArmour, sizeof(float))) return false;
    *armour = player->m_fArmour;
    return std::isfinite(*armour) && *armour >= 0;
}

bool sdk::WritePlayerArmour(float value) noexcept
{
    // This API deliberately supports the standard 0..100 armour range.
    float health = 0, maximum = 0;
    if (!std::isfinite(value) || value < 0 || value > 100
        || !ReadPlayerHealth(&health, &maximum) || health <= 0) return false;
    CPed* player = FindCurrentPlayer();
    if (!player || !Accessible(&player->m_fArmour, sizeof(float), true)) return false;
    player->m_fArmour = value;
    return true;
}

bool sdk::ReadPlayerMoney(int* value) noexcept
{
    const auto* info = CurrentPlayerInfo();
    if (!info) return false;
    *value = info->m_nMoney;
    return true;
}

bool sdk::WritePlayerMoney(int value) noexcept
{
    if (value < 0 || value > 999999999 || !LivingPlayer()) return false;
    auto* info = CurrentPlayerInfo();
    if (!info) return false;
    info->m_nMoney = value;
    // Synchronize the HUD immediately instead of animating from the old value.
    info->m_nDisplayMoney = value;
    return true;
}

bool sdk::ReadPlayerWantedLevel(int* value) noexcept
{
    const auto* wanted = CurrentWanted(CurrentPlayerInfo());
    if (!wanted || wanted->m_nWantedLevel > 6) return false;
    *value = static_cast<int>(wanted->m_nWantedLevel);
    return true;
}

bool sdk::WritePlayerWantedLevel(int value) noexcept
{
    if (value < 0 || value > 6 || !LivingPlayer()) return false;
    auto* wanted = CurrentWanted(CurrentPlayerInfo(), true);
    if (!wanted) return false;
    // SetWantedLevel updates crime queue, chaos and pursuit parameters too.
    // Respect game/mission limits and cheats; never alter the global maximum.
    using SetWanted = void (__thiscall*)(CWanted*, int);
    reinterpret_cast<SetWanted>(0x562470)(wanted, value);
    return true;
}

bool sdk::ReadPlayerWeapon(int* id, unsigned int* ammo) noexcept
{
    const auto* info = CurrentPlayerInfo();
    if (!info || !Accessible(info->m_pPed, sizeof(CPed))) return false;
    const CPed* player = info->m_pPed;
    if (player->m_nActiveWeaponSlot >= 13) return false;
    const CWeapon& weapon = player->m_aWeapons[player->m_nActiveWeaponSlot];
    *id = static_cast<int>(weapon.m_eWeaponType);
    *ammo = weapon.m_nTotalAmmo;
    return true;
}

int sdk::PlayerWeaponAction(int action, int id, unsigned int ammo, bool equip) noexcept
{
    if (action < 0 || action > 3 || !spa::SupportedWeapon(id)
        || (action == 0 && id == 0) || ammo > spa::MaxWeaponAmmo) return 4;
    if (!LivingPlayer()) return 1;
    auto* info = CurrentPlayerInfo();
    if (!info || !Accessible(info->m_pPed, sizeof(CPed), true)) return 1;
    CPed* player = info->m_pPed;
    if (player->m_nPedFlags.bInVehicle || info->m_PlayerData.m_bInVehicleDontAllowWeaponChange
        || static_cast<unsigned int>(player->m_nSavedWeapon) != 55u // WEAPON_UNIDENTIFIED
        || reinterpret_cast<decltype(&CEntryExitManager::WeAreInInteriorTransition)>(0x43E400)()) return 2;
    if (player->m_nActiveWeaponSlot >= 13) return 1;
    if (action == 3)
    {
        using Clear = void (__thiscall*)(CPed*);
        reinterpret_cast<Clear>(0x5E6320)(player);
        return 0;
    }
    const CWeaponInfo* weaponInfo = WeaponInfo(id);
    if (!weaponInfo) return 4;
    const auto slot = weaponInfo->m_nSlot;
    const bool owned = id == 0 || static_cast<int>(player->m_aWeapons[slot].m_eWeaponType) == id;
    if (action == 2)
    {
        if (id == 0 || !owned) return 0; // Idempotent; never clear a different weapon in this slot.
        using Remove = void (__thiscall*)(CPed*, eWeaponType);
        reinterpret_cast<Remove>(0x5E62B0)(player, static_cast<eWeaponType>(id));
        return 0;
    }
    if (action == 1 && !owned) return 3;
    if (id != 0 && !LoadWeaponModels(weaponInfo)) return 5;
    // Loading is synchronous; resolve player again before mutating inventory.
    if (!LivingPlayer() || FindCurrentPlayer() != player) return 1;
    if (action == 0)
    {
        // Cap the addition as well as the Python argument, preventing overflow
        // when GTA carries ammunition over from a replaced weapon in this slot.
        const unsigned int existing = player->m_aWeapons[slot].m_nTotalAmmo;
        if (existing > spa::MaxWeaponAmmo || ammo > spa::MaxWeaponAmmo - existing) return 4;
        using Give = int (__thiscall*)(CPed*, eWeaponType, unsigned int, bool);
        reinterpret_cast<Give>(0x5E6080)(player, static_cast<eWeaponType>(id), ammo, true);
    }
    if (action == 1 || equip)
    {
        using Select = void (__thiscall*)(CPed*, eWeaponType);
        reinterpret_cast<Select>(0x5E6280)(player, static_cast<eWeaponType>(id));
    }
    return 0;
}

int sdk::ReadPlayerVehicle(SpaPlayerVehicle* value) noexcept
{
    const auto* info = CurrentPlayerInfo();
    if (!info || !Accessible(info->m_pPed, sizeof(CPed))) return -1;
    const CPed* player = info->m_pPed;
    // m_pVehicle can retain an old vehicle outside the vehicle state.
    if (!player->m_nPedFlags.bInVehicle) return 0;
    const CVehicle* vehicle = player->m_pVehicle;
    if (!vehicle || !Accessible(vehicle, sizeof(CVehicle))) return -1;
    const bool driver = vehicle->m_pDriver == player;
    bool passenger = false;
    for (const CPed* occupant : vehicle->m_apPassengers)
        if (occupant == player) passenger = true;
    if (!driver && !passenger) return -1; // Entering/exiting or inconsistent seat mapping.
    const CVector* position = vehicle->m_matrix ? &vehicle->m_matrix->pos : &vehicle->m_placement.m_vPosn;
    if (!Accessible(position, sizeof(CVector)) || !std::isfinite(vehicle->m_fHealth)
        || !std::isfinite(position->x) || !std::isfinite(position->y) || !std::isfinite(position->z)) return -1;
    *value = {static_cast<int>(vehicle->m_nModelIndex), driver ? TRUE : FALSE,
        vehicle->m_fHealth, position->x, position->y, position->z};
    return 1;
}

int sdk::RequestModel(int model, DWORD* token) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    auto* info = ModelInfo(model);
    const auto* streaming = info ? StreamingInfo(model) : nullptr;
    if (!info || !streaming || info->m_nTxdIndex < 0
        || (streaming->m_nLoadState != LOADSTATE_LOADED && streaming->m_nCdSize == 0)) return 2;
    ModelLease* slot = nullptr;
    for (auto& lease : modelLeases)
        if (lease.token == 0) { slot = &lease; break; }
    if (!slot || nextModelToken == 0x7FFFFFFF) return 3;
    *slot = {++nextModelToken, model, info, info->m_nKey, info->m_nTxdIndex, nullptr, false};
    // No LoadAllRequestedModels: GTA performs the I/O across subsequent frames.
    reinterpret_cast<decltype(&CStreaming::RequestModel)>(0x4087E0)(model, 0);
    *token = slot->token;
    return 0;
}

int sdk::ModelReady(DWORD token) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return -1;
    auto* lease = FindModelLease(token);
    if (!lease) return -1;
    auto* info = ModelInfo(lease->model);
    const auto* streaming = info ? StreamingInfo(lease->model) : nullptr;
    if (!SameModel(*lease, info) || !streaming) return -1;
    if (lease->pinned)
        return streaming->m_nLoadState == LOADSTATE_LOADED && info->m_pRwObject == lease->rwObject
            && info->m_nRefCount > 0 ? 1 : -1;
    if (streaming->m_nLoadState != LOADSTATE_LOADED)
    {
        reinterpret_cast<decltype(&CStreaming::RequestModel)>(0x4087E0)(lease->model, 0);
        return 0;
    }
    if (!info->m_pRwObject || info->m_nRefCount == 0xFFFF) return -1;
    // Pinned CBaseModelInfo.cpp: AddRef/RemoveRef include the TXD reference.
    using Ref = void (__thiscall*)(CBaseModelInfo*);
    reinterpret_cast<Ref>(0x4C4BA0)(info);
    lease->rwObject = info->m_pRwObject;
    lease->pinned = true;
    return 1;
}

void sdk::ReleaseModel(DWORD token) noexcept
{
    if (!game::IsGameThread()) return;
    auto* lease = FindModelLease(token);
    if (!lease) return;
    auto* info = ModelInfo(lease->model);
    const auto* streaming = info ? StreamingInfo(lease->model) : nullptr;
    if (lease->pinned && SameModel(*lease, info) && streaming
        && streaming->m_nLoadState == LOADSTATE_LOADED && info->m_pRwObject == lease->rwObject
        && info->m_nRefCount > 0)
    {
        using Ref = void (__thiscall*)(CBaseModelInfo*);
        reinterpret_cast<Ref>(0x4C4BB0)(info);
    }
    // Never RemoveModel/SetModelIsDeletable: those affect other consumers too.
    *lease = {};
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
