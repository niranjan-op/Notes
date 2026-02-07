from setuptools import setup, Extension
import pybind11
import sys
import os

# --- CONFIGURATION: Adjust this path ---
# Typical path: C:\vcpkg\installed\x64-windows
vcpkg_root = r"C:\vcpkg\installed\x64-windows" 
# ---------------------------------------

ext_modules = [
    Extension(
        "secure_storage",
        ["secure_storage.cpp"],
        include_dirs=[
            pybind11.get_include(),
            os.path.join(vcpkg_root, "include"),
        ],
        library_dirs=[
            os.path.join(vcpkg_root, "lib"),
        ],
        libraries=[
            "sqlcipher",
            "libcrypto",  # Required for SQLCipher encryption logic
            "libssl",     # Often required alongside libcrypto
            "ws2_32",     # Windows socket library (dependency of OpenSSL)
            "advapi32",   # Windows security/registry library
            "crypt32",    # Windows cryptography API
            "user32",     # General Windows API
        ],
        define_macros=[('SQLITE_HAS_CODEC', '1')],
        language="c++",
        extra_compile_args=['/EHsc'], 
    ),
]

setup(
    name="secure_storage",
    version="0.1",
    ext_modules=ext_modules,
)