# Edit Progress QA

QA construction turns a START/GOAL editing pair into questions about a proposed
CURRENT state: did the edit move the scene closer to its target? This method can
also be used for lighting, shape keys and materials. Each task needs its own
CURRENT-state sampler, validity checks, distance measure and question wording.
**This repository currently implements placement QA only.** Other tasks are
not enabled by changing the input directory or render config.

## Format Status

This implementation consumes **legacy placement samples**. The v1 samples now
produced by `placement/generation` are explicitly rejected pending the QA format
migration. Rearranging these scripts does not change the historical QA prompt,
label rule or output format. QA `.SUCCESS` is a plain `OK` marker, not the v1
integrity manifest. See the [shared format](../../README.md#sample-format).

## Layout

```text
1_current_scene.py       # Blender: sample CURRENT, render, compute per-object QA
2_sample_io.py           # Source checks, output preparation, Blender invocation
3_generate.py            # One scheduler with serial and parallel modes
generate.sh              # Thin launcher; all arguments go to 3_generate.py
config.json              # QA retry setting and explicit render preset
utils/export_dataset.py # Legacy training JSONL exporter
test/                   # Local tests; ignored, not included in a Git checkout
```

Host-side generation and export use Python 3.11+ and the standard library.
Rendering uses Blender 4.2. No model/API is called: coordinates determine the
labels. Render settings use the shared `common.blender_state` application code,
with the `scene`/`devices` structure described in the
[placement rendering documentation](../generation/README.md#render-configuration).
QA owns its config; changing placement's config does not silently change QA.
START/GOAL images are reused, so choose CURRENT render settings consistent with
those source images. The preset uses Cycles/CUDA, 512x512, 128 samples and
OpenImageDenoise, without adding camera lights.

## Construction and Labels

For each object recorded in legacy `metadata.task.moved_objects`, define:

- `A = new_pos`: its START position after the placement perturbation.
- `B = orig_pos`: its GOAL position in the original asset arrangement.
- `C`: a proposed CURRENT position.

The distance is 3D Euclidean distance between object origins, in the source
scene's native Blender units. It is not assumed to be meters or bottom-center
distance. Rotation does not enter the label. The worker opens START and changes
target positions; it retains the snapshot's rotations and other scene content.

The historical sampler rejects any target with `distance(A, B) < 0.5`. It samples
XY around B using a radius of either 0.12-0.49 or 1.05-2.0 times the START/GOAL
distance, and samples Z separately. The final 3D ratio
`r = distance(C, B) / distance(A, B)` must satisfy `r < 0.5` or `r > 1.0`.
Intermediate cases are discarded. `Yes` means `distance(C, B) < distance(A, B)`;
otherwise the answer is `No`. Accepted outputs are not guaranteed class-balanced.

Each target gets at most `min(config.object_movement.target_move_retries, 50)`
attempts. Bounds use the scene's mesh bounding box, collisions use world AABBs,
and visibility checks whether the object's origin is inside every camera's
frustum, with a 2% border margin. This is not an occlusion test or full-object
visibility guarantee. All targets must succeed in the same CURRENT scene;
CURRENT is rendered once, then one question is emitted per target.

## Run

Use a source group containing `sample_*` directories. Each source needs
`metadata.json`, START/GOAL info and scripts, `start.blend`, START/GOAL view
directories and `.SUCCESS`. Metadata must have the legacy moved-object records;
images must have the camera names present in START info.

```bash
bash placement/qa/generate.sh \
  --input_root /data/legacy-placement/1m3v \
  --output_root /data/placement-qa/1m3v \
  --blender_path /path/to/blender \
  --workers 4 --num_of_samples 100

# Visit each valid source once, with one worker.
bash placement/qa/generate.sh \
  --mode serial --input_root /data/legacy-placement/1m3v \
  --output_root /data/placement-qa/serial \
  --blender_path /path/to/blender
```

Paths work from any working directory when the launcher path is supplied.
`BLENDER_PATH` and `PYTHON` can select the executables; `--config` selects a QA
config. `--sample_id sample_00000` restricts source selection to one sample.

Parallel mode draws sources **with replacement** until it reaches the requested
number of successful output scenes or exhausts
`num_of_samples * max_attempt_multiplier` attempts. Each output can yield several
QA rows. `--workers 1` keeps these sampling semantics; `--mode serial` visits the
valid sources once instead. `--seed` seeds source selection only, not Blender's
CURRENT-position sampler. Every attempt uses a separate Blender process.

Use a fresh output directory. Existing run directories require `--force`, which
replaces colliding attempt directories; it is not a resume/whole-dataset cleanup
option. Unreached success targets return a nonzero exit code, and already-started
attempts are collected even when the attempt limit has been reached.

## Outputs and JSONL

```text
output_root/
  summary.json
  run_000000__sample_00000/
    metadata.json             # Copied source metadata
    start.py, goal.py         # Copied source scripts
    start_info.json, goal_info.json
    start_views/, goal_views/ # Copied source images
    current_info.json, current_views/
    qa_items.json             # Per-target question, answer and distance metrics
    result_status.json
    .SUCCESS                 # Only on accepted attempts
```

Failed attempts may leave diagnostic files without a marker. No new blend
snapshot is written; copied scripts do not make the QA output a replay bundle.
Both execution modes use the same output layout and validation path.

```bash
python placement/qa/utils/export_dataset.py \
  --base_path /data/placement-qa/1m3v --output_jsonl_name train.jsonl
```

The exporter writes one row per target, with `image` and `conversations` fields.
Images are START/GOAL pairs by camera, followed by CURRENT views. The prompt
contains START scene information and the target object's question; the assistant
answer is an empty `<think>` block followed by `Yes` or `No`. CURRENT/GOAL
coordinates and distance metrics do not enter the prompt. Paths are relative to
the output root. The exporter overwrites the chosen JSONL filename; it does not
render images or change the samples.

## Verification

The cleanup was checked against the previous worker/exporter on a fixed legacy
1m2v sample and sampling seed. CURRENT coordinates, distance metrics, labels and
normalized JSONL records matched exactly; the two CURRENT images had maximum
normalized mean pixel error `1.2466330933415033e-7`. One serial output and two
parallel outputs passed real Blender generation and JSONL export. Six local
tests cover exhausted attempt budgets with tasks still running, failed/empty
worker results, serial source coverage, v1 rejection and existing-output protection.
Local logs, before/after snapshots and comparison reports are ignored under
`experimental/qa_cleanup/`.
