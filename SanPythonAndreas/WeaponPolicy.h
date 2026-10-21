#pragma once

namespace spa
{
    inline constexpr bool SupportedWeapon(int id) noexcept
    {
        return (id >= 0 && id <= 18) || (id >= 22 && id <= 38) || (id >= 41 && id <= 43);
    }
    inline constexpr unsigned int MaxWeaponAmmo = 99999;
}
