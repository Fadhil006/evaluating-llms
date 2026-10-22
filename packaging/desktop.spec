import sys
from pathlib import Path

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / "backend"))

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    (str(root / "backend" / "alembic.ini"), "backend"),
    (str(root / "backend" / "alembic"), "backend/alembic"),
    (str(root / "frontend" / "dist"), "frontend/dist"),
    (str(root / "datasets" / "original_demo_v1.jsonl"), "datasets"),
]
hiddenimports = collect_submodules("app")
binaries = []
for package in ("app", "alembic", "uvicorn", "sqlalchemy"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(root / "packaging" / "desktop.py")],
    pathex=[str(root / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LLMComparisonLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
