# Lighting

Generate light-energy and light-color editing tasks from Blender scenes. START
uses the asset's original lighting; GOAL changes up to the configured number of
lights. Camera placement, light sampling and the paper JSONL prompt are retained.
This direction differs from placement, where the original asset is GOAL.

## Layout

| File | Responsibility |
| --- | --- |
| `1_light_analyzer.py` | Discover lights and scene bounds |
| `2_light_modifier.py` | Sample energy/color changes |
| `3_camera_region_calculator.py` | Compute observation regions |
| `4_camera_placement.py` | Select and create cameras |
| `5_rendering.py` | Render views and measure image differences |
| `6_generate.py` | Generate one complete sample in Blender |
| `7_sample_io.py` | Export state, snapshots and scripts; verify replay |
| `8_parallel_generate.py` | Schedule workers and validate completion |
| `utils/export_dataset.py` | Export JSONL with the paper prompt |
| `generate.sh` | Batch entry point, from any working directory |

Local tests belong in ignored `test/`; baseline comparisons and generated
experiments belong in the pipeline's ignored `experimental/`. The single-view
rebuttal pipeline, instruction/image-generation tools and progress notes have
been removed from production.

Light sampling returns planned GOAL values without temporarily editing START.
The camera module owns camera deletion and collision-cache reset. Unused analysis
exports, summaries, compatibility aliases and image histograms have been removed;
the greedy camera algorithm and the RGB L1 acceptance rule are retained.

## Generate

Use Blender with Cycles, NumPy and Pillow available in its Python environment.
Generation packs image resources; replay needs `bpy`, not the original asset
directory. Input assets are subdirectories containing `normalized_scene.blend`.

Set paths in `config.json`, or override them on the command line:

```bash
bash lighting/generate.sh \
  --blender /replace/with/your/blender \
  --asset-dir /replace/with/your/lighting_assets \
  --output-dir /replace/with/your/lighting_dataset \
  --num-samples 100 --concurrency 4 --threads 4 \
  --jsonl /replace/with/your/lighting_dataset/train.jsonl
```

`--mode serial` runs one worker at a time. Assets are sorted, optionally shuffled
with `--shuffle-assets`, and reused cyclically. A failed asset advances to the
next asset, bounded by `max_asset_attempts`. Each worker seeds Python and NumPy;
its seed is recorded in metadata. Scheduling does not give every sample the same
random stream.

`max_retries` counts retries after the first attempt on the same asset when a
view has insufficient image change. Other failures return to the batch launcher.
Existing valid samples are checked and reused; invalid existing samples raise
an error and are not silently overwritten. Hidden temporary sample directories
are not published as complete data. Logs and generation reports remain outside
samples. Do not run two writers against the same sample indices.

To generate a fixed asset directly:

```bash
/replace/with/your/blender -b -t 4 --python-exit-code 1 \
  --python lighting/6_generate.py -- \
  --config lighting/config.json \
  --blend-file /replace/with/your/asset/normalized_scene.blend \
  --output-dir /replace/with/your/lighting_dataset/sample_00000 --seed 42
```

The default config edits color only. For energy tasks, set `modify_energy=true`
and `modify_color=false` under `light_modification`; choose the energy ratio
range there. `max_lights_to_modify` is an upper bound, not an exact count.

## Rendering and Acceptance

`render_config.scene`, `view_layer` and `devices` use the same format as placement
and shapekey. All renderer assignments live in config. Explicit legacy values
are Cycles, 512x512 RGB PNG, 128 samples, denoising, eight maximum bounces and no
caustics. Other fields set to `null` retain the loaded asset's values. In
particular, asset color management and view-layer settings are not replaced by
a placement preset. GPU backend and CPU fallback are configurable.

All requested views must render successfully. The original acceptance statistic
is the **minimum** RGB L1 difference across views, using float64 pixels divided
by 255. Every view must meet `validation_config.min_photometric_difference`;
two entirely black images form an invalid pair. Historical comments called this
statistic a maximum, but the executed code used a minimum. Brightness/color
diagnostics were not acceptance gates; unused toggles have been removed.
The old `camera_config.min_camera_separation_ratio` was never read, and the
region wrapper never forwarded `use_absolute_distances`. Both fields were removed
from the shipped config without changing the existing camera behavior.

The v1 producer verifies START initialization, START-to-GOAL script replay and
the GOAL snapshot in Blender before publishing `.SUCCESS`. The marker hashes
all required files. Rendering replay is covered by regression tests rather than
performed a second time for every production sample.

## Public Sample and JSONL

Samples use the [common v1 format](../README.md#sample-format). Light candidates
and cameras appear in both state files, along with necessary static parents.
Positions are in each object's `transform`; energy, color, type and node state
are in `objects[name].light`. No consumer needs GOAL or metadata to recover a
START light position. The ordered public candidate list is
`metadata.editable.object_names`; actual changes are separate in `edit_summary`.

Shared editable light datablocks, animations, drivers and object constraints
are rejected. Packed static Geometry Nodes can remain as background; simulation
or external-cache dependencies are rejected. Node graphs are preserved, not
rewritten: this task edits `Light.energy` and `Light.color` only.

`render_config.json.effective.lights` is a START observation, not a light-reset
command. Apply renderer settings without applying that observation to GOAL.
The complete GOAL light values are in `goal_info.json` and `goal.blend`.

```bash
python -m common.check_samples /replace/with/your/lighting_dataset
python lighting/utils/export_dataset.py \
  /replace/with/your/lighting_dataset \
  /replace/with/your/lighting_dataset/train.jsonl
```

The exporter refuses to overwrite an existing JSONL and validates every sample.
The original system/user text, tool definitions, three-decimal formatting,
START/GOAL image interleaving and four top-level fields are preserved. Scene
text now reads START directly; it never borrows GOAL light locations. Camera
pairs join by the full name. Prompt positions retain the paper's native Blender
unit display; v1 state JSON uses meters without rounding.

Legacy samples require their old reader or regeneration.
