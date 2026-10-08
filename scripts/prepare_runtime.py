"""Reproducible Linux ARM64 dependency build in one isolated owned container."""
import argparse
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-image", default=BASE)
    parser.add_argument("--output", default=".local/lambda-dependencies-aarch64")
    args = parser.parse_args()
    target = (ROOT / args.output).resolve()
    if not target.is_relative_to(ROOT / '.local') or target.exists(): raise RuntimeError("Choose a new dependency directory within .local")
    subprocess.run(['docker','info','--format','{{.ServerVersion}}'], check=True)
    # No image pull, retag, cleanup or deletion. On a different machine explicitly
    # provide an already available compatible Python 3.12 image.
    subprocess.run(['docker','image','inspect',args.base_image], check=True, stdout=subprocess.DEVNULL)
    name = 'hawahawai-runtime-packager-' + uuid.uuid4().hex[:10]
    command = ['docker','run','--rm','--pull','never','--name',name,'--cpus','1','--memory','768m',
               '--mount','type=bind,source='+str(ROOT)+',target=/workspace','-w','/workspace',args.base_image,
               'python','-m','pip','install','--target',str(target.relative_to(ROOT)).replace('\\','/'),
               '--platform','manylinux2014_aarch64','--python-version','3.12','--implementation','cp',
               '--only-binary=:all:','--no-compile','-r','backend/requirements-runtime.txt']
    subprocess.run(command, check=True)
    print('Prepared locked Linux ARM64 dependencies in '+str(target.relative_to(ROOT)))
if __name__ == '__main__': main()
