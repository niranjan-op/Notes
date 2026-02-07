import os

# Add the path where your vcpkg DLLs are located
vcpkg_bin = r'C:\vcpkg\installed\x64-windows\bin'
os.add_dll_directory(vcpkg_bin)

try:
    import secure_storage
    print("Success! Module loaded.")
except ImportError as e:
    print(f"Failed to load: {e}")