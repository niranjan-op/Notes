from setuptools import setup, Extension
import pybind11
import os
import subprocess
import sys

is_windows = os.name == "nt"
is_macos = sys.platform == "darwin"

include_dirs = [pybind11.get_include()]
library_dirs = []
extra_link_args = []

if is_windows:
    vcpkg_root = os.environ.get("VCPKG_ROOT", r"C:\vcpkg")
    triplet = os.environ.get("VCPKG_DEFAULT_TRIPLET", "x64-windows")
    vcpkg_installed = os.path.join(vcpkg_root, "installed", triplet)
    include_dirs.append(os.path.join(vcpkg_installed, "include"))
    library_dirs.append(os.path.join(vcpkg_installed, "lib"))
elif is_macos:
    for pkg in ("sqlcipher", "openssl@3"):
        try:
            prefix = subprocess.check_output(["brew", "--prefix", pkg], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            prefix = "/opt/homebrew" if os.path.exists("/opt/homebrew") else "/usr/local"
        inc = os.path.join(prefix, "include")
        lib = os.path.join(prefix, "lib")
        if os.path.isdir(inc) and inc not in include_dirs:
            include_dirs.append(inc)
        if os.path.isdir(lib) and lib not in library_dirs:
            library_dirs.append(lib)
            extra_link_args.append(f"-Wl,-rpath,{lib}")

ext_modules = [
    Extension(
        "secure_storage",
        [os.path.join("extensions", "secure_storage.cpp")],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
        libraries=(
            ["sqlcipher", "libcrypto", "libssl", "ws2_32", "advapi32", "crypt32", "user32"]
            if is_windows else ["sqlcipher", "crypto", "ssl"]
        ),
        define_macros=[('SQLITE_HAS_CODEC', '1')],
        language="c++",
        extra_compile_args=['/EHsc', '/std:c++17', '/Zc:__cplusplus'] if is_windows else ['-std=c++17'],
        extra_link_args=extra_link_args,
    ),
]

setup(
    name="secure_storage",
    version="0.1",
    ext_modules=ext_modules,
)
