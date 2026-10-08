"""Generate the secret-free Lambda asset. Never writes source or Git metadata."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependencies", default=".local/phase3-dependencies-aarch64")
    parser.add_argument("--refresh", action="store_true", help="Refresh only generated HawaHawai source files, not dependencies")
    args = parser.parse_args()
    dependencies = (ROOT / args.dependencies).resolve()
    target = ROOT / ".local/phase3-lambda-bundle"
    if target.exists() and not args.refresh:
        raise RuntimeError("Bundle already exists; use a new explicit bundle directory for updates")
    if not (dependencies / "strands").exists(): raise RuntimeError("Prepare ARM64 runtime dependencies first")
    if not target.exists():
        shutil.copytree(dependencies, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bin"))
    for name in ("environmental", "safety", "advisory"):
        shutil.copytree(ROOT / "backend" / name, target / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "agent", target / "agent", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "backend/app.py", target / "app.py")
    size = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    if size >= 250 * 1024 * 1024: raise RuntimeError("Lambda uncompressed asset too large")
    native = list(target.rglob('*.so'))
    for library in native:
        header = library.read_bytes()[:20]
        if header[:4] != b'\x7fELF' or int.from_bytes(header[18:20], 'little') != 183:
            raise RuntimeError('Non-ARM64 native library in Lambda bundle: ' + library.name)
    if any(p.name.startswith(".env") for p in target.rglob("*")): raise RuntimeError("Unsafe asset")
    print(f"Packaged Linux ARM64 runtime: {size/1024/1024:.1f} MiB; {len(native)} native libraries architecture-verified")

if __name__ == "__main__": main()
