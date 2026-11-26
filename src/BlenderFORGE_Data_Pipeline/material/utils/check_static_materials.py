"""Verify the static shader snapshot installed in Blender's Infinigen environment."""
import argparse
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]/'infinigen'


def verify(manifest_path=HERE/'materials_static_manifest.json', catalog_path=HERE/'material_catalog.json'):
    manifest = json.loads(Path(manifest_path).read_text())
    catalog = json.loads(Path(catalog_path).read_text())
    infinigen = importlib.import_module('infinigen')
    if infinigen.__version__ != manifest['infinigen_version']:
        raise ValueError(f"Expected Infinigen {manifest['infinigen_version']}, found {infinigen.__version__}")
    package = importlib.import_module(manifest['package'])
    root = Path(package.__file__).resolve().parent
    errors = []
    for relative,expected in manifest['files'].items():
        path = root/relative
        if not path.is_file():
            errors.append(f'Missing source: {relative}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f'Source hash differs: {relative}')
    if errors:
        raise ValueError('\n'.join(errors))
    modules,shaders = 0,0
    for category in catalog.values():
        for entry in category.values():
            module = importlib.import_module(entry['import_path'])
            source = Path(inspect.getsourcefile(module)).resolve()
            if not source.is_relative_to(root):
                raise ValueError(f"Catalog module resolves outside the static package: {entry['import_path']}")
            relative = source.relative_to(root).as_posix()
            if relative not in manifest['files']:
                raise ValueError(f'Catalog module is not in the bundled manifest: {relative}')
            for shader in entry['shaders']:
                if not callable(getattr(module,shader['name'],None)):
                    raise ValueError(f"Missing shader: {entry['import_path']}.{shader['name']}")
                shaders += 1
            modules += 1
    return {'package_path':str(root),'infinigen_version':infinigen.__version__,
            'verified_python_files':len(manifest['files']),'catalog_modules':modules,'catalog_shaders':shaders}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=HERE/'materials_static_manifest.json')
    parser.add_argument('--catalog',type=Path,default=HERE/'material_catalog.json')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    print(json.dumps(verify(args.manifest,args.catalog),indent=2))


if __name__ == '__main__':
    main()
