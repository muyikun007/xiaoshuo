# -*- mode: python ; coding: utf-8 -*-
import os

# Collect data files
datas = [
    ('使用说明.txt', '.'),
    ('用户配置指南.txt', '.'),
]

# Include config.example.json as the default config
if os.path.exists('config.example.json'):
    datas.append(('config.example.json', '.'))

# Include actual config.json if it exists (for development)
if os.path.exists('config.json'):
    datas.append(('config.json', '.'))

# Include payment QR codes if they exist
if os.path.exists('wechat_pay_qr.png'):
    datas.append(('wechat_pay_qr.png', '.'))
if os.path.exists('wechat_pay_qr.jpg'):
    datas.append(('wechat_pay_qr.jpg', '.'))

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'google.genai',
        'google.genai.types',
        'tkinter',
        'ttkbootstrap',
        'pymysql',
        'requests',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='小说大纲生成器',
    version='file_version_info.txt' if os.path.exists('file_version_info.txt') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon file here if you have one
)
