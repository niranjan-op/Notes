from setuptools import setup, Extension
import pybind11
import os

is_windows = os.name == "nt"
vcpkg_root = os.environ.get("VCPKG_ROOT", r"C:\vcpkg")
triplet = os.environ.get("VCPKG_DEFAULT_TRIPLET", "x64-windows")
vcpkg_installed = os.path.join(vcpkg_root, "installed", triplet)

ext_modules = [
    Extension(
        "secure_storage",
        [os.path.join("extensions", "secure_storage.cpp")],
        include_dirs=[pybind11.get_include()] + ([os.path.join(vcpkg_installed, "include")] if is_windows else []),
        library_dirs=[os.path.join(vcpkg_installed, "lib")] if is_windows else [],
        libraries=(
            ["sqlcipher", "libcrypto", "libssl", "ws2_32", "advapi32", "crypt32", "user32"]
            if is_windows else ["sqlcipher", "crypto", "ssl"]
        ),
        define_macros=[('SQLITE_HAS_CODEC', '1')],
        language="c++",
        extra_compile_args=['/EHsc', '/std:c++17', '/Zc:__cplusplus'] if is_windows else ['-std=c++17'],
    ),
]

setup(
    name="secure_storage",
    version="0.1",
    ext_modules=ext_modules,
)
