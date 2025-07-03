# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules

# Per includere l'icona in modalità onefile
ico_path = os.path.abspath("ocroute_icon.ico")

block_cipher = None

a = Analysis(
    ['cmr4_1.py'],
    pathex=[],

    binaries=[
        ('venv/Lib/site-packages/paddle/libs/mklml.dll', 'paddle/libs'),
        ('C:\Python312\python312.dll', '.'),
    ],
    datas=[
    ('C:/Users/donot/Desktop/Da tenere/OCRoute/venv/Lib/site-packages/paddleocr/tools', 'paddleocr/tools'),
    ('C:/Users/donot/Desktop/Da tenere/OCRoute/venv/Lib/site-packages/paddleocr/ppocr', 'paddleocr/ppocr'),
    ('C:/Users/donot/Desktop/Da tenere/OCRoute/venv/Lib/site-packages/Cython/Utility', 'Cython/Utility'),
    ('C:/Users/donot/.paddleocr', '.paddleocr'),
    ('C:/Users/donot/.paddleocr/whl/rec/latin/latin_PP-OCRv3_rec_infer/', '.paddleocr/whl/rec/latin/latin_PP-OCRv3_rec_infer'),
    ('C:/Users/donot/.paddleocr/whl/det/en/en_PP-OCRv3_det_infer/', '.paddleocr/whl/det/en/en_PP-OCRv3_det_infer'),
    ('C:/Users/donot/.paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer/', '.paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer'),
    ('C:/Users/donot/Desktop/Da tenere/OCRoute/venv/Lib/site-packages/paddleocr/ppstructure', 'paddleocr/ppstructure'),
    ('ocroute_icon.ico', '.'),
    ('LICENSE', '.'),             
    ('NOTICE.txt', '.'), 
    ('COPYING', '.'), 
    ],
    hiddenimports=['paddleocr', 'paddle', 'paddleocr.tools', 'paddleocr.ppocr', 'ppstructure', 'cv2', 'fitz', 'pdf2image', 'reportlab', 'PIL', 'setuptools', 'requests', 'PIL.ImageDraw', 'PIL.ImageFont', 'shapely', 'pyclipper', 'skimage', 'skimage.morphology._skeletonize', 'skimage.draw', 'skimage.measure','skimage.filters', 'albumentations', 'albumentations.augmentations.transforms', 'albumentations.core.composition', 'lmdb', 'docx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)	
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OCRoute',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
    icon=ico_path
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='OCRoute'
)