from setuptools import setup, Extension
import pybind11
import sys

# --- CONFIGURATION: Adjust this path ---
# Typical path: C:\vcpkg\installed\x64-windows
vcpkg_root = r"C:\vcpkg\installed\x64-windows" 
# ---------------------------------------

ext_modules = [
    Extension(
        "pysqlcipher",
        ["pysqlcipher.cpp"],
        include_dirs=[
            pybind11.get_include(),
            f"{vcpkg_root}\\include",
        ],
        library_dirs=[
            f"{vcpkg_root}\\lib",
        ],
        libraries=[
            "sqlcipher", 
            "libcrypto", 
            "libssl", 
            "ws2_32", 
            "crypt32", 
            "User32", 
            "Gdi32", 
            "Advapi32"
        ],
        language="c++",
    ),
]

setup(
    name="pysqlcipher",
    version="0.1",
    ext_modules=ext_modules,
)