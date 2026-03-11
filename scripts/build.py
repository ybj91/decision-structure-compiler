"""Build DSC as a standalone executable.

Usage:
    python scripts/build.py          # build for current platform
    python scripts/build.py --test   # build and run smoke test
"""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT / "dsc.spec"
DIST_DIR = ROOT / "dist"


def build():
    print(f"Building DSC executable for {platform.system()} {platform.machine()}...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC_FILE),
        "--distpath", str(DIST_DIR),
        "--workpath", str(ROOT / "build"),
        "--noconfirm",
        "--clean",
    ]
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    exe_name = "dsc.exe" if platform.system() == "Windows" else "dsc"
    exe_path = DIST_DIR / exe_name

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"\nError: executable not found at {exe_path}", file=sys.stderr)
        sys.exit(1)

    return exe_path


def smoke_test(exe_path: Path):
    print("\nRunning smoke tests...")

    # Test --help
    result = subprocess.run([str(exe_path), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"--help failed: {result.stderr}"
    assert "Decision Structure Compiler" in result.stdout
    print("  --help: OK")

    # Test analyze --help
    result = subprocess.run([str(exe_path), "analyze", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"analyze --help failed: {result.stderr}"
    assert "code" in result.stdout
    assert "logs" in result.stdout
    print("  analyze --help: OK")

    print("\nSmoke tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build DSC executable")
    parser.add_argument("--test", action="store_true", help="Run smoke test after build")
    args = parser.parse_args()

    exe = build()
    if args.test:
        smoke_test(exe)
