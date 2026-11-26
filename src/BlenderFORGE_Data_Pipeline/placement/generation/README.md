# Placement Generation

This producer writes the [shared v1 sample format](../../README.md#sample-format).
The original asset arrangement is GOAL; the perturbed arrangement is START.
`num_of_objects_change` is an upper bound: requesting 2 can produce 1 or 2
actual changes. Movement, dual-position camera regions and greedy camera
selection follow the `8a70427` paper baseline. Rendering adds no camera light.

## Layout

```text
1_scene_analyzer.py             # Scene analysis
2_object_movement.py            # Object selection and movement
3_camera_region_calculator.py   # Valid camera regions
4_camera_placement.py           # Camera selection and placement
5_rendering_visibility.py       # Rendering and visibility
6_placement_dataset_gen.py      # Complete single-sample and batch pipeline
7_sample_io.py                 # Sample snapshots, metadata and replay acceptance
8_parallel_placement_gen.py     # Host scheduler
config.json                    # Generation settings
generate.sh                    # Unified launcher; optional JSONL export
test/                         # Local tests and launchers; ignored, not distributed
utils/
  check_samples.py            # Read-only contract and integrity audit
  export_dataset.py           # Paper JSONL rendering over v1 storage
```

Modules 1-6 follow the existing test numbering. Module 7 handles artifact output
and acceptance checks for the pipeline orchestrated by Module 6. Module 8
schedules parallel Blender processes. Numbered modules
are loaded using `importlib.import_module("1_scene_analyzer")` and similar calls.

Shared state export, render capture/application, validation and the machine
schema live in repository-root `common/`. They do not change the task's sampling
algorithm. The paper analyzer excludes structural objects and source objects
whose local location and Euler rotation are both zero within 1e-7. Candidate
identity is fixed before movement; neither state export nor prompt construction
reclassifies an object based on its perturbed pose. The later experimental
mobility classification table is not used. Old post-hoc cleanup scripts were removed.

The internal Python API no longer includes the unused adaptive batch-retry and
segmentation-node helpers, or the inert `max_retries` argument of
`generate_single_sample`, `prefix` of `render_all_cameras`, and `render_seg` of
`render_camera_view`. CLI options, actual movement retry settings, sample output
and paper JSONL formatting are unchanged. Contract acceptance runs once during
completion publication; consumers still verify the published integrity manifest.

## Generate

Use Blender 4.2 with NumPy and Pillow available to its Python interpreter.
The host scheduler requires Python 3.11 or newer on a POSIX system, with no
third-party packages. Shared report writes use flock with bounded contention retries.
Replace the `/replace/with/your/...` paths in config.json with your Blender
executable, 3D-Front asset directory and dataset output directory. The launcher
takes these paths through `--blender`, `--asset-dir` and `--output-dir` (or their
environment variables); it does not read these three paths from config.json.
The rendering and sampling preset values are ready to use.

From `src/BlenderFORGE_Data_Pipeline/`, generate samples and export JSONL in one command:

```bash
bash placement/generation/generate.sh \
  --asset-dir /assets --output-dir /dataset/1m3v \
  --config /configs/placement.json --blender /path/to/blender \
  --num-samples 100 --concurrency 4 \
  --jsonl /dataset/1m3v/train.jsonl
```

The target ID range is `[start-id, start-id + num-samples)`, with `--start-id 0`
by default. Parallel mode skips complete samples and regenerates missing or
unmarked partial samples in that range without prompting. Marked corrupt/legacy
samples are rejected. Concurrency 1 still starts one Blender process per sample.
For one Blender process handling the whole batch, use `--mode serial`; this mode
requires unused target IDs and concurrency 1. Both modes use the same generator.

`--jsonl` is optional. Export runs only after generation succeeds, validates every
sample under the output directory and refuses to overwrite an existing JSONL.
For a resumed run, omit this option or choose a new JSONL filename. Asset, output,
config and executable paths can be supplied through CLI options or the documented
environment defaults; see `generate.sh --help`. The launcher works from any
working directory and supports paths containing spaces.

The underlying Python entry points remain available for direct use:

```bash
blender -b --python-exit-code 1 \
  --python placement/generation/6_placement_dataset_gen.py -- \
  --blend_file /assets/room/scene_texture_packed.blend \
  --output_dir /dataset/1m3v/sample_00000 \
  --config /configs/placement.json

python placement/generation/8_parallel_placement_gen.py \
  --config /configs/placement.json --blender_path /path/to/blender \
  --asset_dir /assets --dataset_output_path /dataset/1m3v \
  --num_data 100 --concurrency 4 --existing_policy fill_gaps
```

Both `save_blend_files` and `save_restore_scripts` must be true for this profile.
An optional `random_seed` initializes Python and NumPy once at CLI startup;
retries and subsequent batch samples advance the same random stream. Metadata
records `seed_scope=invocation`. Set it for run reproduction; omit it for fresh
stochastic runs. Direct Python callers manage their own RNG initialization.
Failed attempts cannot leave a valid completion marker. A marked legacy/corrupt
sample is not overwritten by the scheduler; use a separate v1 output directory.

## Render Configuration

The preset lives entirely in `config.json.render_config`. `scene` mirrors
`bpy.context.scene`: nested objects traverse Blender properties, scalar/array
values are assigned directly, and omitted/null values leave the asset unchanged.
There is no parameter whitelist or hidden engine, resolution, sampling, denoising
or image-format preset in the renderer. Use the installed Blender's real property
names; for example:

```json
{
  "scene": {
    "render": {
      "engine": "CYCLES",
      "resolution_x": 512,
      "resolution_y": 512,
      "resolution_percentage": 100,
      "image_settings": {"file_format": "PNG", "color_mode": "RGB"}
    },
    "cycles": {"device": "GPU", "samples": 128, "use_denoising": true}
  },
  "devices": {
    "compute_device_type": "CUDA",
    "use_cpu": false,
    "fallback_to_cpu": true
  }
}
```

The shipped config explicitly pins every listed setting to the effective values
of the current production-preset sample (source asset
`00004f89-9aa5-43c2-ae3c-129586be8aaa_0`). It contains no null values: denoising is
enabled with OpenImageDenoise, the view transform is Filmic, and CPU participation
is disabled. These settings now also override assets with different inherited
values. The example above is abbreviated; use config.json for the full preset.
Additional parameters
such as `scene.render.use_persistent_data`, `scene.cycles.max_bounces` and
`scene.view_settings.exposure` require only a JSON edit. Properties are applied
in JSON order: put the engine before engine-specific settings, and
`view_transform` before `look`. Invalid names/types fail with the property path;
Blender determines enum availability and numeric limits. Collections and node
graph construction are not part of this scalar/array configuration interface.

`devices` handles Cycles preferences separately from scene data. The requested
backend's devices are enabled; optional `use_cpu` controls CPU participation.
`fallback_to_cpu: true` allows CPU fallback on device initialization errors.
Without that explicit option, errors propagate. For CPU rendering, set
`scene.cycles.device` to `CPU`. EEVEE uses its actual engine identifier and any
engine properties supported by the installed Blender; no engine alias/preset
is applied. Legacy flat generation configs must migrate to this structure.

The shared setter does not force an image format or color mode. Placement's
sample protocol still requires PNG camera files, checked before rendering.
World, lights, compositor graphs and color curves remain native scene content;
Cycles denoising and an inherited compositor Denoise node remain separate.

Each sample records `requested` and `effective`. Existing common render fields
remain available; `effective.configured_scene` additionally records actual
values for every explicitly configured property, including new properties
outside the common fields. Replay applies those values too. Older sample render
snapshots without `configured_scene` remain readable.

## Output and Initialization

Each sample has `metadata.json`, `start.blend`, `start.py`, `start_info.json`,
`start_views/`, `goal.blend`, `goal.py`, `goal_info.json`, `goal_views/`,
`render_config.json` and `.SUCCESS`.
Both blends are real snapshots with packed image resources and the generated
cameras. PNG filenames exactly match camera object names. Internal image paths
are relative to the sample. UUID sample IDs remain unique across config groups.

Initialize START by opening start.blend and executing start.py; execute goal.py
on initialized START to replay GOAL. Apply `render_config.json` using
`common.blender_state.apply_render_config`, then update the scene. Rendering on
another device may require an explicit device override. World, light and
compositor graphs remain in each snapshot; config capture records their state,
it does not replace a blend with a universal node-graph reconstruction format.

State JSON contains all editable candidates and the selected cameras only.
Walls, floors and other fixed background stay in the blend for rendering and
collision checks. State numbers are full-precision numeric arrays in meters/radians. Read
`objects[name].transform.location_local` for local object-origin position and
`matrix_world_evaluated` for world pose. Do not assume bottom center. Actual
material bindings and camera parameters are exported with no placeholder values.
Only referenced materials are included, with `use_nodes` and `diffuse_color`;
placement does not export shader graphs. `metadata.edit_summary` records private
changed-object names, requested maximum and actual count. START/GOAL values stay
in their state files. Public candidates are separate from the changed set.

The placement mover supports static, unparented Euler candidates without delta
transforms or children. Unsupported constraints/animation, linked libraries,
external image sequences and simulated/cached geometry are rejected explicitly.
The shared exporter can represent static parent transforms and other rotation
modes; that does not make the paper mover support them.

## Validate and Export

The test commands below refer to local, ignored files under `test/`, which are
not included in a Git checkout. The validation and export utilities are tracked.

```bash
python placement/generation/utils/check_samples.py /dataset/1m3v
python placement/generation/utils/export_dataset.py /dataset/1m3v /dataset/placement_v1.jsonl

blender -b --python-exit-code 1 \
  --python placement/generation/test/test_state_io.py

BLENDER_PATH=/path/to/blender bash placement/generation/test/run_test_module6.sh \
  --sample /dataset/1m3v/sample_00000 --output /tmp/placement_replay
```

JSONL rendering is pinned to `8a704`: exactly four top-level fields, `image`,
`scene`, `prompt`, `reward_model`. The original system/user text, including tool
definitions, whitespace, quoted three-decimal vectors and single FOV value, is
preserved. Images remain START then GOAL for each camera. Candidate order comes
from the producer. There is no added coordinate-convention paragraph, observation
wrapper, top-level ground_truth, or new sample/version field in the JSONL.

The adapter reads v1 START state but converts metric local positions back to
native Blender units for the paper prompt. Rotations remain Euler radians.
GOAL coordinates never enter the prompt. V1 JSON itself remains full precision
and metric; this presentation adapter does not change the sample protocol.

`reward_model.style` remains `rule`. Its `ground_truth` retains the paper keys:
`goal_script`, `goal_image_list`, `start_image_list`, `scene_info`,
`goal_scene_info`. The last two now point to v1 `start_info.json` and
`goal_info.json`, replacing the old `*_GT_info.json` artifacts. Their contents
follow the new state schema; existing reward readers need the documented schema
migration. The JSONL renderer does not open Blender or recreate legacy sidecars.
Metadata and rendering configuration remain in their agreed sample files.

Paths are relative to the JSONL and `scene` is computed from the actual sample
directory, including nested configuration groups. Export fails on incomplete
samples and refuses to overwrite an existing JSONL.

JSONL export uses the existing `utils/export_dataset.py`; it does not render
images or require Blender. It validates `.SUCCESS` and file hashes, reads each
sample's START/GOAL information, pairs images by camera name, and writes one
paper-format record per sample. Image, blend, script and GT files remain in the
sample directories; JSONL stores their relative paths. For distribution, include
the sample directories alongside the JSONL rather than copying the JSONL alone.

Production acceptance checks quality, all requested views, image dimensions,
named references, GT direction, native START/GOAL replay and GOAL snapshot.
Only then is an atomic `.SUCCESS` manifest written, with SHA256 for required
files and PNGs. `check_samples.py` also verifies those hashes. Replay-image
comparison is explicitly optional in production; the integration test renders
START, replayed GOAL and snapshot GOAL, comparing every view with normalized
mean absolute error <= 1/255. `--baseline` additionally compares old placement
transforms, camera poses and rendered images against a legacy raw sample.

Detailed success/failure checks are appended to `generation_report.jsonl` in
the sample's parent directory. Every asset attempt is recorded, including
failures before rendering. POSIX file locking serializes concurrent writes;
workers no longer overwrite a shared `batch_report.json`. The report is for
production diagnostics and is not required to load, export or resume a complete
sample. Per-sample `edits.json` and `validation.json` are no longer generated.

The module 1-5 tests retain their historical asset fixtures under
`placement/generation/test_assets/` and output under `test/test_output/` (ignored).
Override these with `PLACEMENT_TEST_ASSETS` and `PLACEMENT_TEST_OUTPUT` to keep
local experiments together, for example under `experimental/placement_v1/`.
`test/run_all_tests.sh` runs them; set `SAMPLE_DIR` to include v1 replay checks.
New contract tests run with `PLACEMENT_TEST_SAMPLE=/path/to/sample` and
`PLACEMENT_TEST_ROOT=/path/to/ignored/test-output` via
`python -m unittest discover -s placement/generation/test -p test_contract.py`.
The local paper-format regression suite uses a fixture generated by the
pinned exporter: `python -m unittest discover -s placement/generation/test -p test_paper_export.py`.
Launcher dispatch tests run with
`python -m unittest discover -s placement/generation/test -p test_generate_launcher.py`.

`placement/qa/` still consumes its historical format and rejects v1 samples
explicitly. QA will migrate separately; no downstream fallback is
needed to repair v1 fields.
