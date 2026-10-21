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
#include <CVehicleModelInfo.h>
#include <CPedIntelligence.h>
#include <CTaskComplexLeaveCar.h>
#include <CTaskSimpleCarSetPedInAsDriver.h>
#include <CTaskSimpleCarSetPedInAsPassenger.h>
#include <CAutomobile.h>
#include <CFire.h>
#include "PlayerSeatWarp.h"
#include <array>
#include <CHeli.h>
#include <CPool.h>
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
    using VehiclePool = CPool<CVehicle, CHeli>;
    struct VehicleHandle
    {
        DWORD token = 0;
        CEntity* entity = nullptr; // Stable address registered in GTA's CReference list.
        VehiclePool* pool = nullptr;
        CHeli* objects = nullptr;
        int ref = 0;
    };
    std::array<VehicleHandle, 128> vehicleHandles{};
    std::array<VehicleHandle, 32> ownedVehicles{}; // independent of public handle closure
    DWORD nextVehicleToken = 0;

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

    VehiclePool* CheckedVehiclePool() noexcept
    {
        auto** address = reinterpret_cast<VehiclePool**>(0xB74494);
        if (!Accessible(address, sizeof(*address))) return nullptr;
        VehiclePool* pool = *address;
        if (!pool || !Accessible(pool, sizeof(VehiclePool)) || !pool->m_pObjects || !pool->m_byteMap
            || pool->m_nSize <= 0 || pool->m_nSize > 100000) return nullptr;
        return pool;
    }

    bool HasVehicleReference(const CVehicle* vehicle, CEntity** target) noexcept
    {
        const CReference* ref = vehicle->m_pReferences;
        for (int count = 0; ref && count < 4096; ++count)
        {
            if (!Accessible(ref, sizeof(CReference))) return false;
            if (ref->m_ppEntity == target) return true;
            ref = ref->m_pNext;
        }
        return false;
    }

    VehicleHandle* FindVehicleHandle(DWORD token) noexcept
    {
        if (!token) return nullptr;
        for (auto& entry : vehicleHandles)
            if (entry.token == token) return &entry;
        return nullptr;
    }

    CVehicle* ResolveVehicleHandle(VehicleHandle* entry) noexcept
    {
        if (!entry || !entry->entity) return nullptr;
        auto* pool = CheckedVehiclePool();
        if (!pool || pool != entry->pool || pool->m_pObjects != entry->objects) return nullptr;
        const int index = entry->ref >> 8;
        if (index < 0 || index >= pool->m_nSize
            || !Accessible(pool->m_byteMap + index, sizeof(tPoolObjectFlags))) return nullptr;
        auto& flag = pool->m_byteMap[index];
        if (flag.bEmpty || flag.IntValue() != (entry->ref & 0xFF)) return nullptr;
        auto* vehicle = reinterpret_cast<CVehicle*>(pool->m_pObjects + index);
        if (entry->entity != vehicle || !Accessible(vehicle, sizeof(CVehicle))
            || vehicle->m_nType != ENTITY_TYPE_VEHICLE
            || !HasVehicleReference(vehicle, &entry->entity)) return nullptr;
        return vehicle;
    }

    bool ReadVehicleData(const CVehicle* vehicle, SpaPlayerVehicle* value) noexcept
    {
        const CVector* position = vehicle->m_matrix ? &vehicle->m_matrix->pos : &vehicle->m_placement.m_vPosn;
        if (!Accessible(position, sizeof(CVector)) || !std::isfinite(vehicle->m_fHealth)
            || !std::isfinite(position->x) || !std::isfinite(position->y) || !std::isfinite(position->z)) return false;
        *value = {static_cast<int>(vehicle->m_nModelIndex), vehicle->m_pDriver == FindCurrentPlayer() ? TRUE : FALSE,
            vehicle->m_fHealth, position->x, position->y, position->z};
        return true;
    }

    void UnregisterVehicle(VehicleHandle& entry) noexcept
    {
        if (auto* vehicle = ResolveVehicleHandle(&entry))
        {
            using Reference = void (__thiscall*)(CEntity*, CEntity**);
            reinterpret_cast<Reference>(0x571A00)(vehicle, &entry.entity);
        }
        entry = {};
    }

    int RegisterVehicle(CVehicle* vehicle, VehicleHandle& entry) noexcept
    {
        auto* pool = CheckedVehiclePool();
        if (!pool || nextVehicleToken == 0x7FFFFFFF) return -2;
        const auto address = reinterpret_cast<std::uintptr_t>(vehicle);
        const auto base = reinterpret_cast<std::uintptr_t>(pool->m_pObjects);
        if (address < base || (address - base) % sizeof(CHeli)) return -1;
        const auto index = (address - base) / sizeof(CHeli);
        if (index >= static_cast<unsigned int>(pool->m_nSize)
            || !Accessible(pool->m_byteMap + index, sizeof(tPoolObjectFlags))
            || pool->m_byteMap[index].bEmpty || vehicle->m_nType != ENTITY_TYPE_VEHICLE) return -1;
        entry = {++nextVehicleToken, vehicle, pool, pool->m_pObjects,
            (static_cast<int>(index) << 8) | pool->m_byteMap[index].IntValue()};
        using Reference = void (__thiscall*)(CEntity*, CEntity**);
        reinterpret_cast<Reference>(0x571B70)(vehicle, &entry.entity);
        if (!HasVehicleReference(vehicle, &entry.entity))
        {
            entry = {};
            return -2;
        }
        return 1;
    }

    bool VehicleBusy(const CVehicle* vehicle) noexcept
    {
        if (vehicle->m_pDriver || vehicle->m_pTractor || vehicle->m_pTrailer
            || vehicle->m_nNumPassengers || vehicle->m_nNumGettingIn
            || vehicle->m_nGettingInFlags || vehicle->m_nGettingOutFlags) return true;
        for (const auto* passenger : vehicle->m_apPassengers)
            if (passenger) return true;
        // Seat pointers can lag during entry/exit. Never delete the player's target.
        const auto* player = FindCurrentPlayer();
        return player && player->m_pVehicle == vehicle
            && (player->m_nPedFlags.bInVehicle || player->m_nPedState == PEDSTATE_ENTER_CAR
                || player->m_nPedState == PEDSTATE_EXIT_CAR || player->m_nPedState == PEDSTATE_CARJACK);
    }

    void DeleteVehicle(CVehicle* vehicle) noexcept
    {
        // CWorld::Remove, followed by CEntity's scalar deleting destructor (vtable slot 0).
        reinterpret_cast<void (__cdecl*)(CEntity*)>(0x563280)(vehicle);
        auto** table = *reinterpret_cast<void***>(vehicle);
        reinterpret_cast<void (__thiscall*)(CVehicle*, unsigned int)>(table[0])(vehicle, 1);
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

    bool PedChangingVehicle(const CPed* player) noexcept
    {
        switch (player->m_nPedState)
        {
        case PEDSTATE_OPEN_DOOR: case PEDSTATE_CARJACK: case PEDSTATE_DRAGGED_FROM_CAR:
        case PEDSTATE_ENTER_CAR: case PEDSTATE_STEAL_CAR: case PEDSTATE_EXIT_CAR:
            return true;
        default: return false;
        }
    }

    bool StationaryAutomobile(const CVehicle* vehicle) noexcept
    {
        const auto& speed = vehicle->m_vecMoveSpeed;
        return vehicle->m_nVehicleSubClass == VEHICLE_AUTOMOBILE
            && !vehicle->m_pTractor && !vehicle->m_pTrailer
            && !vehicle->m_nNumGettingIn && !vehicle->m_nGettingInFlags && !vehicle->m_nGettingOutFlags
            && std::isfinite(vehicle->m_fHealth) && vehicle->m_fHealth > 0
            && std::isfinite(speed.x) && std::isfinite(speed.y) && std::isfinite(speed.z)
            && speed.x * speed.x + speed.y * speed.y + speed.z * speed.z <= 0.0001f;
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
    return ReadVehicleData(vehicle, value) ? 1 : -1;
}

int sdk::CapturePlayerVehicle(DWORD* token) noexcept
{
    SpaPlayerVehicle snapshot{};
    const int state = ReadPlayerVehicle(&snapshot);
    if (state != 1) return state;
    auto* player = FindCurrentPlayer();
    CVehicle* vehicle = player->m_pVehicle;
    VehicleHandle* entry = nullptr;
    for (auto& slot : vehicleHandles)
        if (!slot.token) { entry = &slot; break; }
    if (!entry) return -2;
    const int result = RegisterVehicle(vehicle, *entry);
    if (result != 1) return result;
    *token = entry->token;
    return 1;
}

BOOL sdk::VehicleHandleValid(DWORD token) noexcept
{
    return game::IsGameThread() && game::IsReady() && ResolveVehicleHandle(FindVehicleHandle(token)) ? TRUE : FALSE;
}

int sdk::VehicleHandleInfo(DWORD token, SpaPlayerVehicle* value) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return -1;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return -2;
    return ReadVehicleData(vehicle, value) ? 1 : -1;
}

void sdk::CloseVehicleHandle(DWORD token) noexcept
{
    if (!game::IsGameThread()) return;
    auto* entry = FindVehicleHandle(token);
    if (!entry) return;
    UnregisterVehicle(*entry);
}

int sdk::SpawnVehicle(int model, float x, float y, float z, float heading, DWORD* token) noexcept
{
    float health = 0, maximum = 0;
    if (!ReadPlayerHealth(&health, &maximum) || health <= 0) return 1;
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z) || !std::isfinite(heading)
        || std::fabs(x) > 20000 || std::fabs(y) > 20000 || z < -1000 || z > 10000) return 7;
    if (PlayerInterior() != 0
        || reinterpret_cast<bool (__cdecl*)()>(0x43E400)()) return 6;
    auto* info = ModelInfo(model);
    // GetModelType is vtable slot 4 in the pinned CBaseModelInfo.cpp.
    if (!info) return 2;
    auto** table = *reinterpret_cast<void***>(info);
    if (reinterpret_cast<ModelInfoType (__thiscall*)(CBaseModelInfo*)>(table[4])(info) != MODEL_INFO_VEHICLE
        || !Accessible(info, sizeof(CVehicleModelInfo))
        || static_cast<CVehicleModelInfo*>(info)->m_nVehicleType != VEHICLE_AUTOMOBILE) return 2;
    auto* streaming = StreamingInfo(model);
    if (!streaming || streaming->m_nLoadState != LOADSTATE_LOADED || !info->m_pRwObject) return 3;

    VehicleHandle* handle = nullptr;
    for (auto& slot : vehicleHandles)
        if (!slot.token) { handle = &slot; break; }
    VehicleHandle* owner = nullptr;
    for (auto& slot : ownedVehicles)
    {
        if (slot.token && !ResolveVehicleHandle(&slot)) UnregisterVehicle(slot);
        if (!slot.token && !owner) owner = &slot;
    }
    if (!handle || !owner || nextVehicleToken >= 0x7FFFFFFE || !CheckedVehiclePool()) return 4;
    auto* pool = CheckedVehiclePool();
    bool freeSlot = false;
    for (int i = 0; i < pool->m_nSize; ++i)
    {
        if (!Accessible(pool->m_byteMap + i, sizeof(tPoolObjectFlags))) return 4;
        if (pool->m_byteMap[i].bEmpty) { freeSlot = true; break; }
    }
    if (!freeSlot) return 5;
    // Use the game's script factory (no SCM mission cleanup registration).
    // It sets up physics, world membership and the mission-created vehicle count.
    CVector position = FindCurrentPlayer()->m_placement.m_vPosn;
    position.x = x; position.y = y; position.z = z;
    using Factory = CVehicle* (__cdecl*)(int, CVector, unsigned char);
    CVehicle* vehicle = reinterpret_cast<Factory>(0x431F80)(model, position, 0);
    if (!vehicle) return 5;
    vehicle->m_nAreaCode = 0;
    reinterpret_cast<void (__thiscall*)(CPlaceable*, float)>(0x43E0C0)(
        vehicle, std::fmod(heading, 360.0f) * 0.017453292519943295f);
    // Both registrations must succeed before exposing anything to Python.
    if (RegisterVehicle(vehicle, *owner) != 1 || RegisterVehicle(vehicle, *handle) != 1)
    {
        UnregisterVehicle(*owner);
        UnregisterVehicle(*handle);
        DeleteVehicle(vehicle);
        return 4;
    }
    *token = handle->token;
    return 0;
}

int sdk::RemoveVehicle(DWORD token) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    VehicleHandle* owner = nullptr;
    for (auto& slot : ownedVehicles)
        if (ResolveVehicleHandle(&slot) == vehicle) { owner = &slot; break; }
    if (!owner) return 3;
    if (VehicleBusy(vehicle) || reinterpret_cast<bool (__cdecl*)()>(0x43E400)()) return 4;
    UnregisterVehicle(*owner);
    DeleteVehicle(vehicle); // GTA nulls all other CReference pointers.
    return 0;
}

void sdk::CleanupOwnedVehicles() noexcept
{
    if (!game::IsGameThread()) return;
    for (auto& owner : ownedVehicles)
    {
        auto* vehicle = ResolveVehicleHandle(&owner);
        if (vehicle)
        {
            if (VehicleBusy(vehicle))
            {
                // Do not evict occupants during reset/error cleanup. GTA owns its
                // lifetime again; SetVehicleCreatedBy adjusts creation counters.
                reinterpret_cast<void (__thiscall*)(CVehicle*, int)>(0x6D5D70)(vehicle, RANDOM_VEHICLE);
            }
            else
            {
                UnregisterVehicle(owner);
                DeleteVehicle(vehicle);
            }
        }
        UnregisterVehicle(owner);
    }
}

int sdk::EnterPlayerVehicle(DWORD token, int seat) noexcept
{
    if (!LivingPlayer()) return 1;
    auto* player = FindCurrentPlayer();
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (!Accessible(player, sizeof(CPed), true) || !player->m_pIntelligence
        || !Accessible(player->m_pIntelligence, sizeof(CPedIntelligence), true)) return 1;
    if (player->m_nPedFlags.bInVehicle || PedChangingVehicle(player)
        || player->m_nPedFlags.bIsBeingArrested
        || static_cast<unsigned int>(player->m_nSavedWeapon) != 55u
        || reinterpret_cast<bool (__cdecl*)()>(0x43E400)()
        || reinterpret_cast<bool (__thiscall*)(CPedIntelligence*)>(0x602350)(player->m_pIntelligence)
        || reinterpret_cast<void* (__thiscall*)(CPedIntelligence*)>(0x601110)(player->m_pIntelligence))
        return 3;
    if (!StationaryAutomobile(vehicle)) return 4;
    if (seat < -1 || seat > 2
        || (seat == -1 ? vehicle->m_pDriver != nullptr
            : seat >= vehicle->m_nMaxPassengers || vehicle->m_apPassengers[seat] != nullptr)) return 5;
    if (vehicle->m_nAreaCode != player->m_nAreaCode) return 7;
    SpaPlayerVehicle snapshot{};
    float x = 0, y = 0, z = 0;
    if (!ReadVehicleData(vehicle, &snapshot) || !ReadPlayerPosition(&x, &y, &z)) return 1;
    const double dx = snapshot.x - x, dy = snapshot.y - y, dz = snapshot.z - z;
    if (dx * dx + dy * dy + dz * dz > 2500) return 8;
    // The passenger task takes a door ID, rather than a passenger index.
    const int door = seat == -1 ? 10
        : reinterpret_cast<int (__cdecl*)(const CVehicle*, int)>(0x64F190)(vehicle, seat);
    if (door < 0 || (seat >= 0
        && reinterpret_cast<int (__cdecl*)(const CVehicle*, int)>(0x64F1E0)(vehicle, door) != seat)) return 5;
    // Run the same immediate seat tasks without SetPedInCarDirect's additional
    // autonomous DriveWander task. ClearTasks(true, false) then uses GTA's normal
    // in-car task/event path and preserves secondary tasks.
    const auto restoreControl = [player] {
        reinterpret_cast<void (__thiscall*)(CPedIntelligence*, bool, bool)>(0x601420)(
            player->m_pIntelligence, true, false);
    };
    const auto destroyTask = [](auto* task) {
        auto** table = *reinterpret_cast<void***>(task);
        reinterpret_cast<void (__thiscall*)(void*, unsigned int)>(table[0])(task, 0);
    };
    bool completed;
    if (seat == -1)
    {
        using Task = CTaskSimpleCarSetPedInAsDriver;
        completed = spa::WarpPlayerSeat<Task>(
            [vehicle](Task* task) {
                reinterpret_cast<void (__thiscall*)(Task*, CVehicle*, CTaskUtilityLineUpPedWithCar*)>(0x6470E0)(
                    task, vehicle, nullptr);
            },
            [player](Task* task) {
                return reinterpret_cast<bool (__thiscall*)(Task*, CPed*)>(0x64B950)(task, player);
            }, destroyTask, restoreControl);
    }
    else
    {
        using Task = CTaskSimpleCarSetPedInAsPassenger;
        completed = spa::WarpPlayerSeat<Task>(
            [vehicle, door](Task* task) {
                reinterpret_cast<void (__thiscall*)(Task*, CVehicle*, int, CTaskUtilityLineUpPedWithCar*)>(0x646FE0)(
                    task, vehicle, door, nullptr);
            },
            [player](Task* task) {
                return reinterpret_cast<bool (__thiscall*)(Task*, CPed*)>(0x64B5D0)(task, player);
            }, destroyTask, restoreControl);
    }
    if (!completed) return 3;
    return player->m_nPedFlags.bInVehicle && player->m_pVehicle == vehicle
        && (seat == -1 ? vehicle->m_pDriver == player : vehicle->m_apPassengers[seat] == player) ? 0 : 3;
}

int sdk::LeavePlayerVehicle() noexcept
{
    if (!LivingPlayer()) return 1;
    auto* player = FindCurrentPlayer();
    if (!Accessible(player, sizeof(CPed), true) || !player->m_pIntelligence
        || !Accessible(player->m_pIntelligence, sizeof(CPedIntelligence), true)) return 1;
    if (reinterpret_cast<bool (__cdecl*)()>(0x43E400)() || player->m_nPedFlags.bIsBeingArrested) return 3;
    // An already scheduled leave task is idempotent, including before its first frame.
    using FindTask = CTask* (__thiscall*)(CPedIntelligence*, int);
    if (reinterpret_cast<FindTask>(0x600EE0)(player->m_pIntelligence, TASK_COMPLEX_LEAVE_CAR)) return 0;
    if (PedChangingVehicle(player)) return 3;
    if (!player->m_nPedFlags.bInVehicle) return 0;
    SpaPlayerVehicle snapshot{};
    if (ReadPlayerVehicle(&snapshot) != 1) return 1;
    auto* vehicle = player->m_pVehicle;
    if (!StationaryAutomobile(vehicle)) return 4;
    const int door = reinterpret_cast<int (__cdecl*)(const CVehicle*, const CPed*)>(0x64F110)(vehicle, player);
    if (door < 0) return 4;
    // Allocate in GTA's task pool; the task manager owns this object after submission.
    auto* task = reinterpret_cast<CTaskComplexLeaveCar* (__cdecl*)(unsigned int)>(0x61A5A0)(
        sizeof(CTaskComplexLeaveCar));
    if (!task) return 6;
    reinterpret_cast<void (__thiscall*)(CTaskComplexLeaveCar*, CVehicle*, int, int, bool, bool)>(0x63B8C0)(
        task, vehicle, door, 0, true, false);
    reinterpret_cast<void (__thiscall*)(CTaskManager*, CTask*, int, bool)>(0x681AF0)(
        &player->m_pIntelligence->m_TaskMgr, task, TASK_PRIMARY_PRIMARY, false);
    return 0;
}

int sdk::SetVehicleHealth(DWORD token, float value) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    if (!std::isfinite(value) || value < 0 || value > 1000) return 4;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (!Accessible(vehicle, sizeof(CAutomobile), true)
        || vehicle->m_nVehicleSubClass != VEHICLE_AUTOMOBILE
        || vehicle->m_nStatus == STATUS_WRECKED || !std::isfinite(vehicle->m_fHealth)
        || vehicle->m_fHealth <= 0 || vehicle->m_nGettingInFlags || vehicle->m_nGettingOutFlags
        || vehicle->m_nNumGettingIn || reinterpret_cast<bool (__cdecl*)()>(0x43E400)()) return 3;
    vehicle->m_fHealth = value;
    return 0;
}

int sdk::RepairVehicle(DWORD token) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (vehicle->m_nVehicleSubClass != VEHICLE_AUTOMOBILE
        || !Accessible(vehicle, sizeof(CAutomobile), true)
        || vehicle->m_nStatus == STATUS_WRECKED || !std::isfinite(vehicle->m_fHealth)
        || vehicle->m_fHealth <= 0 || !vehicle->m_pRwClump || !vehicle->m_pHandlingData
        || vehicle->m_nGettingInFlags || vehicle->m_nGettingOutFlags || vehicle->m_nNumGettingIn
        || reinterpret_cast<bool (__cdecl*)()>(0x43E400)()) return 3;
    auto* fire = vehicle->m_pFire;
    if (fire && (!Accessible(fire, sizeof(CFire), true) || fire->m_pEntityTarget != vehicle)) return 3;
    // CVehicle::Fix uses vtable slot 50 in the pinned SDK. Its automobile
    // implementation restores body/components, doors, windows and tyre states.
    auto** table = *reinterpret_cast<void***>(vehicle);
    reinterpret_cast<void (__thiscall*)(CVehicle*)>(table[50])(vehicle);
    if (fire) reinterpret_cast<void (__thiscall*)(CFire*)>(0x5393F0)(fire);
    static_cast<CAutomobile*>(vehicle)->m_fBurningTimer = 0;
    vehicle->m_nVehicleFlags.bEngineBroken = false;
    vehicle->m_fHealth = 1000;
    return 0;
}

int sdk::VehicleColors(DWORD token, int* primary, int* secondary) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (vehicle->m_nVehicleSubClass != VEHICLE_AUTOMOBILE) return 3;
    *primary = vehicle->m_nPrimaryColor;
    *secondary = vehicle->m_nSecondaryColor;
    return 0;
}

int sdk::SetVehicleColor(DWORD token, int channel, int color) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    if (channel < 0 || channel > 1 || color < 0 || color > 127) return 4;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (vehicle->m_nVehicleSubClass != VEHICLE_AUTOMOBILE
        || !Accessible(vehicle, sizeof(CVehicle), true)) return 3;
    // Per-entity palette indices; never change the shared model/color table.
    if (channel == 0) vehicle->m_nPrimaryColor = static_cast<unsigned char>(color);
    else vehicle->m_nSecondaryColor = static_cast<unsigned char>(color);
    return 0;
}

namespace
{
    bool CanChangeVehicleMotion(CVehicle* vehicle) noexcept
    {
        return Accessible(vehicle, sizeof(CVehicle), true)
            && vehicle->m_nVehicleSubClass == VEHICLE_AUTOMOBILE
            && vehicle->m_nStatus != STATUS_WRECKED && vehicle->m_fHealth > 0
            && std::isfinite(vehicle->m_fHealth)
            && !vehicle->m_pTractor && !vehicle->m_pTrailer
            && !vehicle->m_nPhysicalFlags.bAttachedToEntity
            && !vehicle->m_nGettingInFlags && !vehicle->m_nGettingOutFlags && !vehicle->m_nNumGettingIn
            && (!vehicle->m_pDriver || vehicle->m_pDriver == FindCurrentPlayer())
            && !reinterpret_cast<bool (__cdecl*)()>(0x43E400)()
            && (!vehicle->m_matrix || Accessible(vehicle->m_matrix, sizeof(CMatrix), true));
    }

    void WakeVehicle(CVehicle* vehicle) noexcept
    {
        // Keep STATUS_PLAYER intact: changing it would hand driving control to AI.
        if (vehicle->m_nStatus == STATUS_SIMPLE)
            reinterpret_cast<void (__cdecl*)(CVehicle*)>(0x423FC0)(vehicle);
        vehicle->m_bIsStatic = false;
        reinterpret_cast<void (__thiscall*)(CPhysical*)>(0x542800)(vehicle);
    }
}

int sdk::VehicleMotion(DWORD token, SpaVehicleMotion* value) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (vehicle->m_nVehicleSubClass != VEHICLE_AUTOMOBILE) return 3;
    if (vehicle->m_matrix && !Accessible(vehicle->m_matrix, sizeof(CMatrix))) return 1;
    const float radians = reinterpret_cast<float (__thiscall*)(CPlaceable*)>(0x441DB0)(vehicle);
    const auto& velocity = vehicle->m_vecMoveSpeed;
    if (!std::isfinite(radians) || !std::isfinite(velocity.x)
        || !std::isfinite(velocity.y) || !std::isfinite(velocity.z)) return 1;
    double degrees = std::fmod(static_cast<double>(radians) * 180.0 / 3.14159265358979323846, 360.0);
    if (degrees < 0) degrees += 360;
    *value = {static_cast<float>(degrees), velocity.x * 50.0f, velocity.y * 50.0f, velocity.z * 50.0f};
    if (value->heading >= 360) value->heading = 0;
    return std::isfinite(value->x) && std::isfinite(value->y) && std::isfinite(value->z) ? 0 : 1;
}

int sdk::SetVehicleHeading(DWORD token, float degrees) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    if (!std::isfinite(degrees) || degrees < 0 || degrees >= 360) return 4;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (!CanChangeVehicleMotion(vehicle)) return 3;
    reinterpret_cast<void (__thiscall*)(CPlaceable*, float)>(0x43E0C0)(
        vehicle, degrees * 0.017453292519943295f);
    vehicle->m_vecTurnSpeed.x = vehicle->m_vecTurnSpeed.y = vehicle->m_vecTurnSpeed.z = 0;
    if (vehicle->m_pRwObject)
    {
        reinterpret_cast<void (__thiscall*)(CEntity*)>(0x446F90)(vehicle);
        reinterpret_cast<void (__thiscall*)(CEntity*)>(0x532B00)(vehicle);
    }
    WakeVehicle(vehicle);
    return 0;
}

int sdk::SetVehicleVelocity(DWORD token, float x, float y, float z) noexcept
{
    if (!game::IsGameThread() || !game::IsReady()) return 1;
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)
        || static_cast<double>(x) * x + static_cast<double>(y) * y + static_cast<double>(z) * z > 40000) return 4;
    auto* vehicle = ResolveVehicleHandle(FindVehicleHandle(token));
    if (!vehicle) return 2;
    if (!CanChangeVehicleMotion(vehicle)) return 3;
    vehicle->m_vecMoveSpeed.x = x / 50.0f;
    vehicle->m_vecMoveSpeed.y = y / 50.0f;
    vehicle->m_vecMoveSpeed.z = z / 50.0f;
    WakeVehicle(vehicle);
    return 0;
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
