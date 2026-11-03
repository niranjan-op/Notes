# -*- mode: python ; coding: utf-8 -*-
import glob
import os
import subprocess
import sys

from PyInstaller.utils.hooks import collect_all

is_windows = os.name == "nt"
is_macos = sys.platform == "darwin"

datas = [('assets', 'assets')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

if is_windows:
    # Package the freshly compiled extension explicitly. The source app can keep an
    # older .pyd locked while a new distributable is built.
    vcpkg_bin = os.path.join(
        os.environ.get('VCPKG_ROOT', r'C:/vcpkg'),
        'installed',
        os.environ.get('VCPKG_DEFAULT_TRIPLET', 'x64-windows'),
        'bin',
    )
    extension = 'build/lib.win-amd64-cpython-313/secure_storage.cp313-win_amd64.pyd'
    if not os.path.exists(extension):  # 'setup.py build_ext --inplace' (CI) builds into the project root
        matches = glob.glob('secure_storage*.pyd') or glob.glob('build/lib*/secure_storage*.pyd')
        extension = matches[0] if matches else 'secure_storage.cp313-win_amd64.pyd'
    binaries += [
        (extension, '.'),
        (os.path.join(vcpkg_bin, 'sqlcipher.dll'), '.'),
        (os.path.join(vcpkg_bin, 'libcrypto-3-x64.dll'), '.'),
        (os.path.join(vcpkg_bin, 'libssl-3-x64.dll'), '.'),
        (os.path.join(vcpkg_bin, 'legacy.dll'), '.'),
    ]
else:
    matches = glob.glob('secure_storage*.so') or glob.glob('build/lib*/secure_storage*.so')
    if matches:
        binaries.append((matches[0], '.'))
    if is_macos:
        for pkg in ('sqlcipher', 'openssl@3'):
            try:
                prefix = subprocess.check_output(['brew', '--prefix', pkg], text=True).strip()
                for dylib in glob.glob(os.path.join(prefix, 'lib', '*.dylib')):
                    if not os.path.islink(dylib):
                        binaries.append((dylib, '.'))
            except (OSError, subprocess.CalledProcessError):
                pass


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['secure_storage'],
    # Onedir avoids a self-extracting executable and lets the OS page code on demand.
    noarchive=True,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name='NotesApp',
    debug=False,
    bootloader_ignore_signals=False,
    exclude_binaries=True,
    strip=os.name != "nt",
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='assets/notes.ico' if is_windows else ('assets/notes.png' if os.path.exists('assets/notes.png') else None),
    version='packaging/version_info.txt' if is_windows else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=os.name != "nt",
    upx=False,
    name='NotesApp',
)

if is_macos:
    app = BUNDLE(
        coll,
        name='Secure Notes.app',
        icon='assets/notes.png',
        bundle_identifier='com.securenotes.desktop',
        info_plist={
            'CFBundleDisplayName': 'Secure Notes',
            'CFBundleName': 'Secure Notes',
            'CFBundleShortVersionString': '1.2.1',
            'CFBundleVersion': '1.2.1',
            'NSHighResolutionCapable': True,
        },
    )
