# Material

The basic and Infinigen backends share sample IO, validation, batch scheduling
and JSONL export. Their parameter samplers and quality metrics remain separate.
Both generate the [common v1 sample format](../README.md#sample-format).

## Layout

| File | Responsibility |
| --- | --- |
| `1_rendering.py` | Render one asset camera; evaluate each backend's original quality metric |
| `2_sample_io.py` | Material construction, native bindings, snapshots and replay checks |
| `3_generate.py` | Blender worker for either backend |
| `4_parallel_generate.py` | Bounded host scheduler and validated resume |
| `generate.sh` | Shared batch entry point |
| `utils/export_dataset.py` | Original paper JSONL template over v1 samples |
| `basic/1_sampling.py` | Principled BSDF parameter sampling |
| `basic/2_script.py` | Original Principled construction code with safely quoted names |
| `infinigen/1_sampling.py` | Catalog shader selection and parameter sampling |

Each backend keeps its own `config.json` and `base_scene.blend`. Infinigen also keeps
its shader catalog. Local tests are in ignored `test/`; experiments and frozen
comparisons are in the pipeline's ignored `experimental/material_v1/`.
The old plan, duplicate launchers, optional instruction/imagine workflow and
single-view rebuttal config have been removed.

## Generate

Use Blender with Cycles, NumPy and Pillow in its Python environment. Basic needs
no external shader package. Infinigen additionally needs the catalog's modules
importable in Blender Python, including `infinigen.assets.materials_static`.
The derandomized shader package is bundled in `infinigen/materials_static/`.
Follow the [installation/replacement instructions](infinigen/README.md) to put it
in the environment used by Blender, while keeping the original `materials/`.
The validated dependency reports version 1.19.1; each procedural sample records
the exact shader module SHA256 and package version and checks them on replay.

```bash
bash material/generate.sh --backend basic \
  --blender /replace/with/your/blender \
  --output-dir /replace/with/your/basic_material_dataset \
  --num-samples 100 --concurrency 4 --threads 4 \
  --jsonl /replace/with/your/basic_material_dataset/train.jsonl

bash material/generate.sh --backend infinigen \
  --blender /replace/with/your/blender \
  --output-dir /replace/with/your/infinigen_material_dataset \
  --num-samples 100 --concurrency 4 --threads 4
```

`--config` selects a custom config, with its relative paths resolved relative to
that file. `--blend-file`, `--seed`, `--start-id` and `--mode serial` are available.
The launcher works from any directory. Do not run two writers for the same indices.

Set `material_modification.modification_type` to `single_param` or `multi_param`.
Basic uses its configured `multi_param.min_params/max_params`; Infinigen retains
its original two-to-three-parameter selection rule. Removed Infinigen min/max and
mode-enabled fields never controlled that sampler. Its shader category/name and
parameter strategy are now read directly from config.

Basic retains the original sample-index seed sequence with default base seed 0;
`--seed` explicitly offsets it. Within a basic sample, START stays fixed while
GOAL is resampled up to `max_goal_attempts` (originally hardcoded to 100).
Infinigen makes one plan per worker invocation. Batch retries use a new seed,
bounded by `batch_generation.max_attempts`. Actual seeds are recorded.

Existing complete samples are verified and reused; invalid existing samples raise
an error. The producer publishes a sample only after validation. Logs, attempt
reports and batch summaries are outside the sample directories.

## Rendering and Quality

Rendering uses the same `render_config.scene/view_layer/devices` structure as
placement, lighting and shapekey. Explicit defaults preserve Cycles, CUDA,
512x512, 128 samples, denoising, maximum bounces 4 and diffuse/glossy/transmission
bounces 2. Other null fields inherit the asset, including color management,
image color/depth and view-layer settings. Basic explicitly selects PNG;
Infinigen inherits the source format and rejects a non-PNG configuration.

Quality metrics retain their original meanings:

| Backend | Metric | Default acceptance threshold |
| --- | --- | --- |
| Basic | Mean absolute RGB PNG difference divided by 255 | 0.01 |
| Infinigen | Fraction of Blender-loaded pixels with any RGB channel difference greater than 0.01 | 0.001 |

These numbers are not interchangeable. Infinigen's optional gray-image check is
retained. Its old config-only flags that did not affect generation were removed.

Every sample also executes and renders three routes: START plus start.py,
START plus start.py plus goal.py, and the GOAL snapshot. Native state tolerance
is 1e-6; rendered RGB L1 must be at most `replay_image_tolerance` (0.0005).
Temporary replay images are removed after successful validation. `.SUCCESS`
contains the hashes of all required sample files; the host never creates it.

## State and Parameters

`objects[name].material_slots` contains the actual material names. The target
mesh, selected camera and necessary parents include complete shared transforms.
`materials[material_name].parameters` describes the public values and bindings:

- Basic: actual RNA values, configured ranges and a real Principled node/input
  identity. Unknown or linked sockets are rejected.
- Infinigen: the shader construction arguments, with a `shader_argument` binding,
  argument type, module/function, source hash and construction seed. Bounds that
  are not established by the shader interface are null. The native node graph
  is separately observed; a function argument is not mislabeled as a socket.

The parameter record describes construction provenance for Infinigen. A consumer
that directly edits nodes cannot treat the old constructor arguments as an inverse
description of those edits; it must observe the nodes or rebuild through the
declared shader interface. The packed blend remains the complete native graph.

`metadata.editable` lists public object/slot/material bindings and parameter pairs.
`edit_summary` contains only private changed identities, with values in START/GOAL.
Neither metadata nor GOAL supplies missing START state fields.

The profile supports a single independent target mesh/material slot, static
parents and packed static geometry. Shared editable meshes/materials, animation,
drivers, object constraints and simulated dependencies are rejected. Procedural
shaders that load external image files during construction are also rejected;
pre-existing packed scene textures remain supported.

Infinigen uses one stable target material name and releases only its unused
generated node groups when rebuilding. This fixes the old disagreement among
runtime IDs, fabricated JSON names and START/GOAL-suffixed script names.

## JSONL

```bash
python -m common.check_samples /replace/with/your/material_dataset
python material/utils/export_dataset.py \
  /replace/with/your/material_dataset \
  /replace/with/your/material_dataset/train.jsonl
```

Both backends use the paper material prompt: START/GOAL image pairs plus executable
START construction code. System/user template, tool definitions, image ordering
and the four-field JSONL envelope are retained. The exporter refuses overwrite.

Basic's complete JSONL matches the frozen baseline. Infinigen's code block changes
because its executable reconstruction was corrected; its surrounding template and
GT envelope match. The exporter does not substitute obsolete code merely to make
a text comparison pass. All GT scene-info references now resolve to v1 JSON.
