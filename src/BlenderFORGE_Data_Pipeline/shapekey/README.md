# Shape-Key Generation

This pipeline generates shape-key editing tasks in the
[shared v1 sample format](../README.md#sample-format). It retains the original key
selection, renaming probabilities, value sampling and photometric acceptance
rule. START and GOAL values are sampled; this task does not use placement's
original-arrangement-as-GOAL rule.

## Layout

```text
1_key_sampling.py       # Key selection, values and renaming
2_rendering.py          # Camera renders and photometric comparison
3_sample_io.py          # Snapshots, state export, metadata and native replay
4_generate.py           # Blender producer with bounded retries
5_parallel_generate.py  # Host scheduler and optional JSONL export
generate.sh            # Unified serial/parallel launcher
config.json            # All asset cameras
resources/             # Tracked editable-key inventory and rename dictionaries
utils/                 # JSONL export and optional asset-dictionary preparation
test/                  # Local tests, ignored and not included in Git
```

The old generators, approximate render metadata writer and machine-specific
shell launchers have been replaced by these
entry points. Asset preparation tools remain in `utils`; the dictionaries in
`resources` are required inputs, not generated at runtime.

## Generate

Use Blender 4.2 with NumPy/Pillow, and host Python 3.11+ on a POSIX system. Replace
`/replace/with/your/...` paths in a config or supply explicit CLI paths. Resource
paths are resolved relative to the config file, not the working directory.

```bash
bash shapekey/generate.sh \
  --blender /replace/with/your/blender \
  --asset-dir /replace/with/your/shapekey_assets \
  --output-dir /replace/with/your/shapekey_dataset \
  --num-samples 100 --concurrency 4 --threads 4 \
  --jsonl /replace/with/your/shapekey_dataset/train.jsonl
```

Parallel mode starts one Blender process per sample, using seed
`random_seed + sample_id`. `--mode serial` runs the batch in one Blender process
with one random stream initialized from `random_seed`; these modes need not
produce identical later samples. `--start-id` selects the first target ID.
`BLENDER_PATH` and `PYTHON` select executables. A direct Blender invocation is:

```bash
blender -b --python-exit-code 1 --python shapekey/4_generate.py -- \
  --config /path/to/config.json --num-samples 1 --start-id 0
```

The producer publishes `.SUCCESS` only after acceptance. Complete samples are
validated and skipped on resume; corrupt or legacy sample directories are
rejected. Temporary failed attempts are isolated and replaced on retry. Per-key
value attempts use `Max_retry` (at least one attempt), and asset selection is
bounded by `max_asset_attempts`. Failures return a nonzero exit code and appear
in the parent `generation_report.jsonl`. The scheduler verifies completion and
never creates a success marker itself.

## Sampling and Rendering

`Max_num_of_key_displayed` limits the public editable subset. Up to
`num_of_key_change` of those keys are selected to change, with minimum proposed
delta `min_change_proportion * (slider_max - slider_min)`. Other displayed keys
receive equal START/GOAL values. Key names may be replaced using the tracked
rephrase dictionary. Collisions/swaps are resolved through actual Blender key
references, and the final native names are used everywhere.

The original producer applied values rounded to six decimals; that sampling
behavior is retained. State JSON and replay scripts record the resulting actual
Blender values at full precision. Missing objects/keys fail instead of silently
skipping assignments. The reported changed count comes from actual START/GOAL
differences rather than the requested key list.

The inherited asset cameras keep their names, poses and original Blender data
iteration order. Cameras outside the active scene are rejected. Default acceptance is
`max(mean(abs(START_RGB - GOAL_RGB))) > photometric_loss_threshold`, with RGB
normalized to [0,1] and the maximum taken across cameras. It does not require
every view to show a change. All asset camera views are retained in both states.

Rendering uses the shared `scene`/`devices` configuration, plus optional
`view_layer` properties. The common field names and nesting match placement's
config, including image settings, Cycles, display settings and view settings.
`null` explicitly means inherit the asset value without overriding it; the
sample's effective render snapshot records the actual value. Shapekey additionally
sets view-layer denoising. The default explicitly sets the original producer's
Cycles/GPU, 512x512, 128 samples, RGB PNG 8-bit and scene/view-layer denoising.
Other settings remain asset-owned: for example the frozen Drawer asset uses
AgX while the frozen table asset uses Filmic. They must not be replaced by one
asset's effective settings. Each sample's `render_config.json` records the full
common effective fields and all explicit properties for replay. Users can add
native Blender scalar/array properties without changing the renderer code.

The current profile supports static relative shape keys, including static
parents and packed Geometry Nodes backgrounds. Linked libraries, animation,
drivers, absolute keys, shared editable mesh data, muted editable keys,
simulation/cache dependencies and external image sequences are rejected.

## Output and Consumer Interface

Each sample contains `metadata.json`, `start.blend`, `start.py`, `start_info.json`,
`start_views/`, the corresponding GOAL files, `render_config.json` and `.SUCCESS`.
There are no per-sample edit/validation sidecars or `*_show_info.json` files.
Textures are packed; blends are real independent snapshots saved after render
configuration. Image filenames are exactly the camera names.

Initialize START by opening start.blend and executing start.py, then apply
`common.blender_state.apply_render_config`. Executing goal.py on initialized START
must reproduce goal.blend and goal_info.json. Every generated sample passes these
three native state checks before publication; render comparison is an additional
regression check, not repeated during every production attempt.

Read `objects[object_name].shapekeys[key_name]` for actual value, range, relative
key, mute/driver flags and editability. The object table includes editable mesh
objects, selected cameras and required parents. All keys on those meshes are
recorded as dependencies; Basis and keys outside the displayed subset are not
editable. `metadata.editable.shape_keys` gives the ordered public subset;
`metadata.edit_summary` is private ground truth and contains only edit identities
and counts. Object transforms are in meters/radians; key values retain Blender's
native scalar meaning.

## Audit and Export

```bash
python -m common.check_samples /path/to/dataset
python shapekey/utils/export_dataset.py /path/to/dataset /path/to/train.jsonl
```

The JSONL exporter validates samples, reads START values/ranges from state JSON,
and retains the historical prompt wording, tool definitions, image pairing and
four fields `image`, `scene`, `prompt`, `reward_model`. It includes only the
public displayed keys in their original order. GOAL values and changed-key
identities do not enter the prompt. GT references now contain v1 state documents;
readers must use the new schema and explicit editable flags. Export does not
modify sample files and refuses to overwrite an existing JSONL.

To prepare a new asset inventory, run Blender with
`--python shapekey/utils/extract_shapekeys.py -- --blend_dir /path/to/assets
--output_json /path/to/shape_keys_output.json`. Update the config to use that
inventory. `utils/rephrase_names.py` optionally builds alternative names using a
local language model; its Transformers/PyTorch dependencies are not required for
dataset generation with the shipped dictionaries.
