# BlenderFORGE_Data_Pipeline

Blender scene-editing data pipelines for object placement, lighting, shape keys,
and materials, with a placement QA pipeline.

Run the commands below from this directory (`src/BlenderFORGE_Data_Pipeline/` in BlenderFORGE).

## Layout

```text
placement/
  generation/   # Placement samples, rendering, validation, and JSONL export
  qa/           # QA construction from placement samples
lighting/       # Lighting edits
shapekey/       # Shape-key edits
material/
  basic/        # Principled BSDF materials
  infinigen/    # Infinigen procedural materials
common/         # v1 state export, validation, rendering capture and schema
```

## Entry Points

| Pipeline | Sample generator | Batch launcher |
| --- | --- | --- |
| Placement | `placement/generation/6_placement_dataset_gen.py` | `placement/generation/generate.sh` |
| Placement QA | `placement/qa/1_current_scene.py` (Blender worker) | `placement/qa/generate.sh` |
| Lighting | `lighting/6_generate.py` | `lighting/generate.sh` |
| Shape keys | `shapekey/4_generate.py` | `shapekey/generate.sh` |
| Basic materials | `material/3_generate.py --backend basic` | `material/generate.sh --backend basic` |
| Infinigen materials | `material/3_generate.py --backend infinigen` | `material/generate.sh --backend infinigen` |

Each pipeline currently has its own configuration and launch arguments. Configure
the Blender executable, input assets, and output directory before generating data.
The `generate.sh` launchers accept explicit paths and work from any directory.
Inspect options with `--help`. Material backends share an entry point while
retaining their own configs, parameter samplers and quality metrics.

Placement follows the `8a70427` baseline: the original asset is the GOAL, the
perturbed scene is the START, the requested object count is an upper bound, and
the renderer does not add a camera fill light. See the
[placement documentation](placement/generation/README.md).

The [QA documentation](placement/qa/README.md) explains how START/GOAL pairs
become questions about progress after an edit. The method also applies to other
editing tasks with task-specific sampling and distance measures; this repository
currently implements placement QA only, using the legacy placement sample format.

## Sample Format

Placement, [shape keys](shapekey/README.md), [lighting](lighting/README.md) and
[both material backends](material/README.md) use the same v1 layout:

```text
sample_00000/
  metadata.json
  start.blend
  start.py
  start_info.json
  start_views/<camera_name>.png
  goal.blend
  goal.py
  goal_info.json
  goal_views/<camera_name>.png
  render_config.json
  .SUCCESS
```

Initialize START by opening `start.blend`, executing `start.py`, and applying
`common.blender_state.apply_render_config` to `render_config.json`. Executing
`goal.py` on initialized START reproduces the GOAL state. Procedural material
replay also requires the [derandomized material package](material/infinigen/README.md).

The [state schema](common/schemas/state.schema.json) defines `start_info.json`
and `goal_info.json`: `scene`, name-indexed `objects` and `materials`, and ordered
`views`. Image filenames are the complete camera names. Each object contains its
local transform and evaluated world matrix. Lengths are meters and angular values
use radians; `rotation_mode` identifies the rotation representation, with
quaternions in Blender's `[w, x, y, z]` order. `scene.units.meters_per_blender_unit`
records the native unit conversion. Camera intrinsics and task-specific properties
are in the same state.

`metadata.editable` identifies public candidates and editable properties.
`metadata.edit_summary` and GOAL values are ground truth and do not belong in the
model's START observation. Each pipeline README describes its task-specific fields.
`render_config.json` records both requested settings and their effective values;
null requested values inherit the source asset. Captured light values are scene
observations and must not overwrite edited lights when applying render settings.

`.SUCCESS` is a SHA256 manifest published after the producer's acceptance checks.
Validate samples with `python -m common.check_samples DATASET`. Batch reports and
logs live outside samples and are not required to load the data.

Each v1 pipeline's `utils/export_dataset.py DATASET OUTPUT.jsonl` writes the four
fields `image`, `scene`, `prompt`, and `reward_model`. JSONL paths are relative to
the JSONL directory; state image paths are relative to the sample. Distribute
the referenced sample directories with the JSONL file.

Placement QA retains its historical format and currently rejects v1 input;
see its [format requirements](placement/qa/README.md#format-status).
