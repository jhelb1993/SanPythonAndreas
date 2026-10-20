#pragma once
// pybind11 handles release Python headers in MSVC Debug builds, preserving the
// C++ runtime's debug settings. Never put Python objects in DLL static storage.
#include <pybind11/embed.h>
