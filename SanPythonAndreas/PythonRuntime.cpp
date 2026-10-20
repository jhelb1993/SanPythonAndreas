#include "pch.h"
#include "PythonIncludes.h"
#include "Bindings.h"
#include "BuildInfo.h"
#include "PythonRuntime.h"
#include "RuntimeApi.h"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <cmath>
#include <cstddef>

PyMODINIT_FUNC PyInit_sanandreas();

namespace
{
    const SpaHostApi* host = nullptr;
    bool attempted = false;
    bool ownsInterpreter = false;
    PyObject* tickFunction = nullptr; // Owned until process exit.
    std::filesystem::path logPath;

    void Log(const char* message) noexcept
    {
        host->log(message);
        try
        {
            if (!logPath.empty())
                std::ofstream(logPath, std::ios::app) << message << '\n';
        }
        catch (...) {}
    }

    void ReportPythonError()
    {
        // PyErr_Print would terminate GTA on an unhandled SystemExit.
        PyObject *type = nullptr, *value = nullptr, *trace = nullptr;
        PyErr_Fetch(&type, &value, &trace);
        PyErr_NormalizeException(&type, &value, &trace);
        PyObject* description = value ? PyObject_Str(value) : nullptr;
        const char* text = description ? PyUnicode_AsUTF8(description) : nullptr;
        Log(text ? text : "Python operation failed");
        // Fatal startup/tick errors must be visible even if no log is found.
        // This runs on the game thread, never under the loader lock.
        wchar_t* visible = description ? PyUnicode_AsWideCharString(description, nullptr) : nullptr;
        MessageBoxW(nullptr, visible ? visible : L"Python operation failed; check the runtime files.",
            L"SanPythonAndreas - Python-Fehler", MB_OK | MB_ICONERROR);
        if (visible)
            PyMem_Free(visible);
        Py_XDECREF(description);
        PyObject* traceback = PyImport_ImportModule("traceback");
        if (traceback && type)
        {
            PyObject* result = PyObject_CallMethod(traceback, "print_exception", "OOO",
                type, value ? value : Py_None, trace ? trace : Py_None);
            Py_XDECREF(result);
        }
        Py_XDECREF(traceback);
        Py_XDECREF(type);
        Py_XDECREF(value);
        Py_XDECREF(trace);
        PyErr_Clear();
    }

    bool Start(HMODULE module)
    {
        wchar_t path[32768]{};
        const DWORD length = GetModuleFileNameW(module, path, 32768);
        if (!length || length >= 32768)
            throw std::runtime_error("Cannot determine ASI directory");
        const auto root = std::filesystem::path(path).parent_path() / L"SanPythonAndreas";
        std::filesystem::create_directories(root);
        logPath = root / L"SanPythonAndreas.log";
        Log("SanPythonAndreas: starting bundled Python 3.11 on the game thread");
        Log(spa::PackageVersion);
        Log(spa::BindingBackend);
        Log(spa::SdkRevision);
        const auto rootUtf8 = root.u8string();
        Log(reinterpret_cast<const char*>(rootUtf8.c_str()));
        if (Py_IsInitialized())
            throw std::runtime_error("Another plugin already initialized this Python runtime");
        if (PyImport_AppendInittab("sanandreas", PyInit_sanandreas) == -1)
            throw std::runtime_error("Cannot register sanandreas module");

        PyConfig config;
        PyConfig_InitIsolatedConfig(&config);
        config.install_signal_handlers = 0;
        config.parse_argv = 0;
        config.write_bytecode = 0;
        const auto pythonHome = root / L"python";
        config.site_import = 0;
        config.module_search_paths_set = 1;
        PyStatus status = PyConfig_SetString(&config, &config.home, pythonHome.c_str());
        for (const auto& searchPath : {pythonHome / L"python311.zip", pythonHome, root, root / L"scripts"})
        {
            if (!PyStatus_Exception(status))
                status = PyWideStringList_Append(&config.module_search_paths, searchPath.c_str());
        }
        if (PyStatus_Exception(status))
        {
            Log(status.err_msg ? status.err_msg : "Python configuration failed");
            PyConfig_Clear(&config);
            return false;
        }
        // pybind11 consumes/clears PyConfig. Do not initialize or finalize a
        // second interpreter, and do not inject the working directory into sys.path.
        pybind11::initialize_interpreter(&config, 0, nullptr, false);
        ownsInterpreter = true;

        PyObject* bootstrap = PyImport_ImportModule("_spa_runtime");
        if (!bootstrap)
        {
            ReportPythonError();
            Log("Cannot load _spa_runtime; check the deployed SanPythonAndreas directory");
            return false;
        }
        tickFunction = PyObject_GetAttrString(bootstrap, "_tick");
        Py_DECREF(bootstrap);
        if (!tickFunction || !PyCallable_Check(tickFunction))
        {
            Py_CLEAR(tickFunction);
            Log("Runtime does not provide a callable _tick");
            return false;
        }
        return true;
    }
}

void python::Tick(HMODULE module, bool ready) noexcept
{
    try
    {
        if (!attempted)
        {
            if (!ready)
                return;
            attempted = true;
            bool started = false;
            try { started = Start(module); }
            catch (...)
            {
                if (ownsInterpreter)
                    PyEval_SaveThread();
                throw;
            }
            if (ownsInterpreter)
                PyEval_SaveThread(); // Release the GIL even if bootstrap failed.
            if (!started)
            {
                Log("Python startup failed; scripting disabled until game restart");
                return;
            }
        }
        if (!tickFunction)
            return;
        const PyGILState_STATE gil = PyGILState_Ensure();
        PyObject* result = PyObject_CallFunctionObjArgs(tickFunction, ready ? Py_True : Py_False, nullptr);
        if (!result)
        {
            ReportPythonError();
            Py_CLEAR(tickFunction);
            Log("Runtime tick failed; scripting disabled until game restart");
        }
        Py_XDECREF(result);
        PyGILState_Release(gil);
    }
    catch (const std::exception& error) { Log(error.what()); }
    catch (...) { Log("Unexpected native runtime error"); }
}

// This DLL is loaded explicitly by the ASI after logging is available.
extern "C" void __cdecl SpaTick(HMODULE module, BOOL ready, const SpaHostApi* api)
{
    if (!api)
        return;
    if (api->size != sizeof(SpaHostApi) || api->version != spa::HostApiVersion)
    {
        static bool mismatchReported = false;
        if (!mismatchReported)
        {
            mismatchReported = true;
            if (api->size >= offsetof(SpaHostApi, log) + sizeof(api->log) && api->log)
                api->log("ERROR: ASI/runtime API mismatch; replace both SanPythonAndreas.asi and SanPythonRuntime.dll.");
            MessageBoxW(nullptr, L"ASI/runtime API mismatch. Replace ASI, runtime DLL and bootstrap together.",
                L"SanPythonAndreas", MB_OK | MB_ICONERROR);
        }
        return;
    }
    host = api;
    bindings::SetHost(api);
    python::Tick(module, ready != FALSE);
}
