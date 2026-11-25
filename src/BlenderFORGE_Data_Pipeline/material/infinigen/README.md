# Derandomized Infinigen Materials

This backend uses the **derandomized material package**, bundled in
[`materials_static/`](materials_static/). Install this snapshot in the Infinigen
environment used by both dataset generation and sample replay. Installing only
an upstream Infinigen release does not provide the required implementation.

## Install or Replace

Use an Infinigen 1.19.1 environment compatible with Blender 4.2, then copy the
bundled folder into the installed package:

```text
<infinigen checkout>/
  infinigen/
    assets/
      materials/          # Keep the original package.
      materials_static/   # Install this repository's bundled folder here.
```

From the `src/BlenderFORGE_Data_Pipeline/` directory in BlenderFORGE:

```bash
set -euo pipefail
INFINIGEN_ROOT="/replace/with/your/infinigen"
STATIC_TARGET="$INFINIGEN_ROOT/infinigen/assets/materials_static"
test -d "$INFINIGEN_ROOT/infinigen/assets"

# Back up an existing static package so this installs a complete snapshot.
if [ -e "$STATIC_TARGET" ]; then
  mv -- "$STATIC_TARGET" "${STATIC_TARGET}.backup.$(date +%Y%m%d%H%M%S)"
fi
cp -a -- material/infinigen/materials_static "$STATIC_TARGET"
```

The target is `materials_static`, not `materials`. Some static modules import
utilities or shaders from the original `infinigen.assets.materials` package.
Replacing that original package would change those dependencies and the rendered
results. Install into the environment Blender actually imports, including remote
render workers and evaluation machines.

Keep the dataset's [`material_catalog.json`](material_catalog.json) unchanged.
It is the curated generation catalog; it is not the broader development catalog
from the original material-processing workspace. The snapshot excludes bytecode,
catalog-generation tools and the one-off randomness-removal scripts.

## Verify the Installation

This command checks the package path, all bundled Python source hashes and all
catalog shader imports in Blender's Python environment:

```bash
/replace/with/your/blender -b --python-use-system-env --python-exit-code 1 \
  --python material/utils/check_static_materials.py
```

Configure the same Python environment or `PYTHONPATH` that generation and replay
use. The checker is read-only: it does not install packages or change a scene.
Restart existing Blender workers after replacing the package to avoid cached
imports.

The pipeline also records the selected shader module hash and package version
in each sample and checks them when executing its procedural restoration code.
[`materials_static_manifest.json`](materials_static_manifest.json) records the
full bundled runtime snapshot. Preserve its Python files byte-for-byte, including
line endings, to keep source hashes stable.

## What Was Modified

This version replaces sampled shader defaults with constants. For example,
the concrete shader's seed, roughness and crack defaults are fixed rather than
sampled on each construction. It is the implementation used for the existing
material regression samples.

Generation and replay use the same package snapshot, recorded parameters and
construction seed, with START/GOAL state and image checks.

The snapshot is based on a locally modified Infinigen checkout reporting version
1.19.1, at revision `892947be71c4ff102c6a558d088ffe149561c11f`. That revision alone
does not identify the local static-material modifications; the bundled files and
manifest do. Original copyright notices and the upstream
[BSD 3-Clause license](materials_static/LICENSE) are retained.

See the [material pipeline README](../README.md) for generation commands and
sample-format details.
