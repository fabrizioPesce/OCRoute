# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cmr3.py'],
    pathex=[],

    binaries=[
        ('venv/Lib/site-packages/paddle/libs/mklml.dll', 'paddle/libs'),
    ],
    datas=[
    ('/venv/Lib/site-packages/paddleocr/tools', 'paddleocr/tools'),
    ('/venv/Lib/site-packages/paddleocr/ppocr', 'paddleocr/ppocr'),
    ('/venv/Lib/site-packages/Cython/Utility', 'Cython/Utility'),
    ('~/.paddleocr', '.paddleocr'),
    ('/Desktop/Da tenere/OCRoute/venv/Lib/site-packages/paddleocr/ppstructure', 'paddleocr/ppstructure')
    ],
    hiddenimports=['paddleocr', 'paddle', 'paddleocr.tools', 'paddleocr.ppocr', 'ppstructure', 'cv2', 'fitz', 'pdf2image', 'reportlab', 'PIL', 'setuptools', 'requests', 'PIL.ImageDraw', 'PIL.ImageFont', 'shapely', 'pyclipper', 'skimage', 'skimage.morphology._skeletonize', 'skimage.draw', 'skimage.measure','skimage.filters', 'albumentations', 'albumentations.augmentations.transforms', 'albumentations.core.composition', 'lmdb', 'docx'],
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
    [],
    exclude_binaries=True,
    name='cmr3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name='cmr3',
)