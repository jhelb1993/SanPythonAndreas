"""Run with the bundled Windows python.exe, without a system installation."""
import ctypes
import pathlib
import runpy
import sqlite3
import ssl
import struct
import sys

assert sys.version_info[:3] == (3, 11, 9), sys.version
assert struct.calcsize('P') == 4, 'Expected an x86 interpreter'
assert sys.flags.isolated, 'Expected isolated interpreter configuration'
assert ctypes.windll.kernel32.GetCurrentProcessId() > 0
home = pathlib.Path(sys.executable).resolve().parent
assert (home / 'python311.zip').is_file()
assert pathlib.Path(pathlib.__file__).as_posix().startswith((home / 'python311.zip').as_posix())
print('Python 3.11.9 x86 bundle: OK (stdlib, ctypes, SSL, SQLite)')
print(sys.executable)
print(sys.path)
