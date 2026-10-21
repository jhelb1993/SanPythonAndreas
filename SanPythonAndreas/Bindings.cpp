#include "pch.h"
#include "PythonIncludes.h"
#include "Bindings.h"
#include "BuildInfo.h"
#include "Vector3.h"
#include "WeaponPolicy.h"
#include <pybind11/operators.h>
#include <cmath>
#include <stdexcept>
#include <string>

namespace py = pybind11;
#ifdef SPA_BINDINGS_TEST
void InstallTestControls(py::module_& module);
#endif
namespace
{
    const SpaHostApi* host = nullptr;
    struct InvalidVehicle : std::runtime_error { using std::runtime_error::runtime_error; };

    struct VehicleInfo
    {
        int modelId;
        bool isDriver;
        float health;
        Vector3 position;
    };

    void RequireGameThread()
    {
        if (!host || !host->isGameThread())
            throw std::runtime_error("GTA API requires the game thread");
    }

    py::object PlayerHealth()
    {
        RequireGameThread();
        float health = 0, maximum = 0;
        if (!host->playerHealth(&health, &maximum))
            return py::none();
        return py::make_tuple(health, maximum);
    }

    py::object PlayerPosition()
    {
        RequireGameThread();
        float x = 0, y = 0, z = 0;
        if (!host->playerPosition(&x, &y, &z))
            return py::none();
        return py::cast(Vector3(x, y, z));
    }

    void HeadingStatus(int status)
    {
        if (status == 3)
            throw std::runtime_error("heading requires the driver seat of a vehicle without trailers; trains are unsupported");
        if (status != 0)
            throw std::runtime_error("no active player or heading unavailable (setting requires a living player)");
    }

    void SetPlayerHealth(py::handle value)
    {
        RequireGameThread();
        if (py::isinstance<py::bool_>(value))
            throw py::type_error("health must be a number, not bool");
        const double number = PyFloat_AsDouble(value.ptr());
        if (PyErr_Occurred())
            throw py::error_already_set();
        float health = 0, maximum = 0;
        if (!host->playerHealth(&health, &maximum))
            throw std::runtime_error("no active player");
        if (!std::isfinite(number) || number < 0 || number > maximum)
            throw py::value_error("health must be finite and between 0 and player.max_health");
        if (!host->setPlayerHealth(static_cast<float>(number)))
            throw std::runtime_error("player is dead or health cannot be changed");
    }

    void ShowText(py::handle value)
    {
        RequireGameThread();
        if (!host->isReady())
            throw std::runtime_error("show_text requires an active game callback on the game thread");
        if (!py::isinstance<py::str>(value))
            throw py::type_error("text must be a string");
        py::object encoded = py::reinterpret_steal<py::object>(PyUnicode_AsASCIIString(value.ptr()));
        if (!encoded)
            throw py::error_already_set();
        const auto text = py::cast<std::string>(encoded);
        if (text.empty() || text.size() > 200 || text.find('\0') != std::string::npos)
            throw py::value_error("text must contain 1 to 200 ASCII characters without NUL");
        host->showText(text.c_str());
    }

    int BoundedInteger(py::handle value, long maximum, const char* name)
    {
        if (py::isinstance<py::bool_>(value) || !py::isinstance<py::int_>(value))
            throw py::type_error(std::string(name) + " must be an integer, not bool");
        const long number = PyLong_AsLong(value.ptr());
        if (PyErr_Occurred()) throw py::error_already_set();
        if (number < 0 || number > maximum)
            throw py::value_error(std::string(name) + " must be between 0 and " + std::to_string(maximum));
        return static_cast<int>(number);
    }

    int WeaponId(py::handle value)
    {
        const int id = BoundedInteger(value, 46, "weapon");
        if (!spa::SupportedWeapon(id))
            throw py::value_error("unsupported weapon ID; supported: 0..18, 22..38, 41..43");
        return id;
    }

    void WeaponAction(int action, int id, unsigned int ammo = 0, bool equip = false)
    {
        switch (host->playerWeaponAction(action, id, ammo, equip ? TRUE : FALSE))
        {
        case 0: return;
        case 2: throw std::runtime_error("weapon changes require being on foot, outside vehicle/jetpack/cutscene/door transitions");
        case 3: throw std::runtime_error("player does not own this weapon");
        case 4: throw py::value_error("invalid weapon or ammo; slot total must not exceed 99999");
        case 5: throw std::runtime_error("weapon models could not be loaded; inventory unchanged");
        default: throw std::runtime_error("no active living player or weapons unavailable");
        }
    }
}

void bindings::SetHost(const SpaHostApi* api) noexcept
{
    host = api;
}

// Explicitly registered by Start(), outside DllMain. PYBIND11_MODULE avoids an
// embedded-module static initializer invoking CPython under the loader lock.
PYBIND11_MODULE(sanandreas, module)
{
    if (!host || host->size != sizeof(SpaHostApi) || host->version != spa::HostApiVersion)
        throw std::runtime_error("ASI/runtime API mismatch; deploy the complete matching package");
    module.doc() = "GTA San Andreas scripting API";
    module.attr("__version__") = spa::PackageVersion;
    module.attr("_host_api_version") = spa::HostApiVersion;
    module.attr("_binding_backend") = spa::BindingBackend;
    module.attr("_sdk_revision") = spa::SdkRevision;
    py::class_<Vector3>(module, "Vector3", "Immutable 3D value; detached from game memory")
        .def(py::init<double, double, double>(), py::arg("x") = 0, py::arg("y") = 0, py::arg("z") = 0)
        .def_readonly("x", &Vector3::x)
        .def_readonly("y", &Vector3::y)
        .def_readonly("z", &Vector3::z)
        .def(py::self + py::self)
        .def(py::self - py::self)
        .def(-py::self)
        .def(py::self * double())
        .def(double() * py::self)
        .def(py::self == py::self)
        .def(py::self != py::self)
        .def("__truediv__", [](const Vector3& self, double scalar) {
            if (scalar == 0)
            {
                PyErr_SetString(PyExc_ZeroDivisionError, "cannot divide Vector3 by zero");
                throw py::error_already_set();
            }
            return self / scalar;
        }, py::is_operator())
        .def("length", &Vector3::Length)
        .def("distance_to", &Vector3::DistanceTo, py::arg("other"))
        .def("__iter__", [](const Vector3& self) { return py::iter(py::make_tuple(self.x, self.y, self.z)); })
        .def("__repr__", [](const Vector3& self) {
            return py::str("Vector3({!r}, {!r}, {!r})").format(self.x, self.y, self.z);
        });
    py::register_exception<InvalidVehicle>(module, "InvalidVehicleError", PyExc_RuntimeError);
    py::class_<VehicleInfo>(module, "VehicleInfo", "Immutable vehicle snapshot; no game pointers")
        .def_readonly("model_id", &VehicleInfo::modelId)
        .def_readonly("is_driver", &VehicleInfo::isDriver)
        .def_readonly("health", &VehicleInfo::health)
        .def_readonly("position", &VehicleInfo::position);
    module.def("_player_vehicle", []() -> py::object {
        RequireGameThread();
        SpaPlayerVehicle value{};
        const int state = host->playerVehicle(&value);
        if (state == 0) return py::none();
        if (state != 1) throw std::runtime_error("no active player or vehicle seat/position unavailable; retry after entering or exiting");
        if (value.modelId < 0 || !std::isfinite(value.health))
            throw std::runtime_error("invalid vehicle snapshot");
        return py::cast(VehicleInfo{value.modelId, value.isDriver != FALSE, value.health,
            Vector3(value.x, value.y, value.z)});
    });
    module.def("_capture_player_vehicle", []() -> py::object {
        RequireGameThread();
        DWORD token = 0;
        const int state = host->capturePlayerVehicle(&token);
        if (state == 0) return py::none();
        if (state == -2) throw std::runtime_error("vehicle handle/reference limit reached; close unused handles");
        if (state != 1) throw std::runtime_error("no active player or vehicle seat unavailable");
        return py::int_(token);
    });
    module.def("_vehicle_handle_valid", [](py::handle token) {
        RequireGameThread();
        return host->vehicleHandleValid(BoundedInteger(token, 0x7FFFFFFF, "vehicle token")) != FALSE;
    });
    module.def("_vehicle_info", [](py::handle token) {
        RequireGameThread();
        SpaPlayerVehicle value{};
        const int state = host->vehicleHandleInfo(BoundedInteger(token, 0x7FFFFFFF, "vehicle token"), &value);
        if (state == -2) throw InvalidVehicle("vehicle was removed, its slot reused, or the handle closed");
        if (state != 1) throw std::runtime_error("vehicle data requires active gameplay and finite vehicle state");
        return VehicleInfo{value.modelId, value.isDriver != FALSE, value.health, Vector3(value.x, value.y, value.z)};
    });
    module.def("_close_vehicle_handle", [](py::handle token) {
        RequireGameThread();
        host->closeVehicleHandle(BoundedInteger(token, 0x7FFFFFFF, "vehicle token"));
    });
    module.def("show_text", &ShowText, py::arg("text"), py::pos_only());
    module.def("_is_key_down", [](py::handle value) {
        RequireGameThread();
        const long key = PyLong_AsLong(value.ptr());
        if (PyErr_Occurred())
            throw py::error_already_set();
        if (key < 1 || key > 254)
            throw py::value_error("virtual key must be between 1 and 254");
        return host->keyDown(static_cast<int>(key)) != FALSE;
    });
    module.def("_has_focus", [] {
        RequireGameThread();
        return host->hasFocus() != FALSE;
    });
    module.def("_player_health", &PlayerHealth);
    module.def("_require_game_thread", &RequireGameThread);
    module.def("_request_model", [](py::handle model) {
        RequireGameThread();
        const int id = BoundedInteger(model, 19999, "model_id");
        if (id == 0) throw py::value_error("model_id must be between 1 and 19999");
        DWORD token = 0;
        switch (host->requestModel(id, &token))
        {
        case 0: return token;
        case 2: throw py::value_error("model does not exist or has no streamable resource");
        case 3: throw std::runtime_error("model lease limit reached; release unused models");
        default: throw std::runtime_error("model loading requires active gameplay");
        }
    }, py::arg("model_id"));
    module.def("_model_ready", [](py::handle token) {
        RequireGameThread();
        const int state = host->modelReady(BoundedInteger(token, 0x7FFFFFFF, "model token"));
        if (state < 0) throw std::runtime_error("model lease unavailable or invalidated; reload the model");
        return state == 1;
    });
    module.def("_release_model", [](py::handle token) {
        RequireGameThread();
        host->releaseModel(BoundedInteger(token, 0x7FFFFFFF, "model token"));
    });
    module.def("_game_time_ms", [] {
        RequireGameThread();
        return host->gameTimeMs();
    });
    module.def("_player_weapon", [] {
        RequireGameThread();
        int id = 0;
        unsigned int ammo = 0;
        if (!host->playerWeapon(&id, &ammo)) throw std::runtime_error("no active player or weapons unavailable");
        return py::make_tuple(id, ammo);
    });
    module.def("_give_player_weapon", [](py::handle weapon, py::handle ammo, py::handle equip) {
        RequireGameThread();
        const int id = WeaponId(weapon);
        if (id == 0) throw py::value_error("cannot give UNARMED; use select_weapon(0)");
        const int count = BoundedInteger(ammo, spa::MaxWeaponAmmo, "ammo");
        if (!py::isinstance<py::bool_>(equip)) throw py::type_error("equip must be bool");
        WeaponAction(0, id, count, py::cast<bool>(equip));
    }, py::arg("weapon"), py::arg("ammo") = 100, py::kw_only(), py::arg("equip") = true);
    module.def("_select_player_weapon", [](py::handle weapon) {
        RequireGameThread();
        WeaponAction(1, WeaponId(weapon));
    }, py::arg("weapon"));
    module.def("_remove_player_weapon", [](py::handle weapon) {
        RequireGameThread();
        WeaponAction(2, WeaponId(weapon));
    }, py::arg("weapon"));
    module.def("_clear_player_weapons", [] {
        RequireGameThread();
        WeaponAction(3, 0);
    });
    module.def("_player_money", [] {
        RequireGameThread();
        int value = 0;
        if (!host->playerMoney(&value)) throw std::runtime_error("no active player or money unavailable");
        return value;
    });
    module.def("_set_player_money", [](py::handle value) {
        RequireGameThread();
        const int number = BoundedInteger(value, 999999999, "money");
        if (!host->setPlayerMoney(number)) throw std::runtime_error("no active living player or money cannot be changed");
    }, py::arg("value"));
    module.def("_player_wanted_level", [] {
        RequireGameThread();
        int value = 0;
        if (!host->playerWantedLevel(&value)) throw std::runtime_error("no active player or wanted level unavailable");
        return value;
    });
    module.def("_set_player_wanted_level", [](py::handle value) {
        RequireGameThread();
        const int number = BoundedInteger(value, 6, "wanted_level");
        if (!host->setPlayerWantedLevel(number)) throw std::runtime_error("no active living player or wanted level cannot be changed");
    }, py::arg("value"));
    module.def("_player_armour", [] {
        RequireGameThread();
        float value = 0;
        if (!host->playerArmour(&value))
            throw std::runtime_error("no active player or armour unavailable");
        return value;
    });
    module.def("_set_player_armour", [](py::handle value) {
        RequireGameThread();
        if (py::isinstance<py::bool_>(value))
            throw py::type_error("armour must be a number, not bool");
        const double number = PyFloat_AsDouble(value.ptr());
        if (PyErr_Occurred()) throw py::error_already_set();
        if (!std::isfinite(number) || number < 0 || number > 100)
            throw py::value_error("armour must be finite and between 0 and 100");
        if (!host->setPlayerArmour(static_cast<float>(number)))
            throw std::runtime_error("no active living player or armour cannot be changed");
    }, py::arg("value"));
    module.def("_player_position", &PlayerPosition);
    module.def("_player_heading", [] {
        RequireGameThread();
        float degrees = 0;
        HeadingStatus(host->playerHeading(&degrees));
        return degrees;
    });
    module.def("_set_player_heading", [](py::handle value) {
        RequireGameThread();
        if (py::isinstance<py::bool_>(value))
            throw py::type_error("heading must be a number, not bool");
        const double number = PyFloat_AsDouble(value.ptr());
        if (PyErr_Occurred()) throw py::error_already_set();
        if (!std::isfinite(number)) throw py::value_error("heading must be finite");
        double normalized = std::fmod(number, 360.0);
        if (normalized < 0) normalized += 360.0;
        float degrees = static_cast<float>(normalized);
        if (degrees >= 360) degrees = 0;
        HeadingStatus(host->setPlayerHeading(degrees));
    }, py::arg("degrees"));
    module.def("_player_interior", [] {
        RequireGameThread();
        const int area = host->playerInterior();
        if (area < 0) throw std::runtime_error("no active player interior");
        return area;
    });
    module.def("_teleport_player", [](const Vector3& target, py::object interior) {
        RequireGameThread();
        int area = -1;
        if (!interior.is_none())
        {
            if (py::isinstance<py::bool_>(interior) || !py::isinstance<py::int_>(interior))
                throw py::type_error("interior must be an integer or None");
            const long number = PyLong_AsLong(interior.ptr());
            if (PyErr_Occurred()) throw py::error_already_set();
            if (number < 0 || number > 255) throw py::value_error("interior must be between 0 and 255");
            area = static_cast<int>(number);
        }
        if (std::fabs(target.x) > 20000 || std::fabs(target.y) > 20000
            || target.z < -1000 || target.z > 10000)
            throw py::value_error("target outside supported bounds: x/y +/-20000, z -1000..10000");
        switch (host->teleportPlayer(static_cast<float>(target.x), static_cast<float>(target.y),
                                    static_cast<float>(target.z), area))
        {
        case 0: return;
        case 2: throw std::runtime_error("interior transition in progress; wait until the door transition finishes");
        case 3: throw std::runtime_error("teleport requires the driver seat of a vehicle without trailers; trains are unsupported");
        case 4: throw py::value_error("invalid teleport target");
        default: throw std::runtime_error("no active living player or teleport unavailable");
        }
    }, py::arg("target"), py::arg("interior") = py::none());
    module.def("_set_player_health", &SetPlayerHealth);
#ifdef SPA_BINDINGS_TEST
    InstallTestControls(module);
#endif
}
