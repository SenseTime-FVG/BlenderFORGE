#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'HELP'
Usage: generate.sh --asset-dir DIR --output-dir DIR [options]

  --config FILE        Generation config (default: config.json beside this script)
  --blender FILE       Blender executable (default: blender on PATH)
  --python FILE        Host Python 3.11+ executable (default: python)
  --num-samples N      Number of target sample IDs (default: 10)
  --start-id N         First target ID (default: 0)
  --mode MODE          parallel (default) or serial
  --concurrency N      Parallel Blender processes (default: 4; serial requires 1)
  --randomize-assets   Enable the generator's asset shuffling
  --jsonl FILE         Export all samples under output-dir after generation succeeds
  -h, --help           Show this help

Parallel mode fills missing target IDs and skips validated samples. Concurrency
1 still starts a new Blender process per sample. Serial mode keeps one Blender
process for the whole batch and requires unused target IDs.

Environment defaults: CONFIG_FILE, BLENDER_PATH, PYTHON_PATH, ASSET_DIR,
OUTPUT_DIR, NUM_SAMPLES, START_ID, MODE, CONCURRENCY, JSONL_PATH.
Relative paths are resolved from the caller's working directory.
HELP
}

fail() { echo "Error: $*" >&2; exit 2; }
value_required() { [[ $# -ge 2 && -n "$2" ]] || fail "Missing value for $1"; }

config="${CONFIG_FILE:-$SCRIPT_DIR/config.json}"
blender="${BLENDER_PATH:-blender}"
python="${PYTHON_PATH:-python}"
asset_dir="${ASSET_DIR:-}"
output_dir="${OUTPUT_DIR:-}"
num_samples="${NUM_SAMPLES:-10}"
start_id="${START_ID:-0}"
mode="${MODE:-parallel}"
concurrency="${CONCURRENCY:-}"
jsonl="${JSONL_PATH:-}"
randomize=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) value_required "$@"; config="$2"; shift 2 ;;
        --blender) value_required "$@"; blender="$2"; shift 2 ;;
        --python) value_required "$@"; python="$2"; shift 2 ;;
        --asset-dir) value_required "$@"; asset_dir="$2"; shift 2 ;;
        --output-dir) value_required "$@"; output_dir="$2"; shift 2 ;;
        --num-samples) value_required "$@"; num_samples="$2"; shift 2 ;;
        --start-id) value_required "$@"; start_id="$2"; shift 2 ;;
        --mode) value_required "$@"; mode="$2"; shift 2 ;;
        --concurrency) value_required "$@"; concurrency="$2"; shift 2 ;;
        --jsonl) value_required "$@"; jsonl="$2"; shift 2 ;;
        --randomize-assets) randomize=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ -n "$asset_dir" && -n "$output_dir" ]] || fail "--asset-dir and --output-dir are required"
[[ "$num_samples" =~ ^[1-9][0-9]*$ ]] || fail "--num-samples must be a positive integer"
[[ "$start_id" =~ ^(0|[1-9][0-9]*)$ ]] || fail "--start-id must be a nonnegative integer"
case "$mode" in
    parallel) concurrency="${concurrency:-4}" ;;
    serial)
        [[ -z "$concurrency" || "$concurrency" == 1 ]] || fail "serial mode requires --concurrency 1"
        concurrency=1 ;;
    *) fail "--mode must be parallel or serial" ;;
esac
[[ "$concurrency" =~ ^[1-9][0-9]*$ ]] || fail "--concurrency must be a positive integer"
command -v "$python" >/dev/null 2>&1 || fail "Python not found: $python"
command -v "$blender" >/dev/null 2>&1 || fail "Blender not found: $blender"

absolute_path() { "$python" -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$1"; }
config="$(absolute_path "$config")"
asset_dir="$(absolute_path "$asset_dir")"
output_dir="$(absolute_path "$output_dir")"
[[ "$blender" != */* ]] || blender="$(absolute_path "$blender")"
[[ -z "$jsonl" ]] || jsonl="$(absolute_path "$jsonl")"

# Validate inputs before starting Blender, including serial overwrite boundaries.
"$python" - "$config" "$asset_dir" "$output_dir" "$mode" "$num_samples" "$start_id" "$jsonl" <<'PY'
import json
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
config, assets, output, mode, count, start, jsonl = sys.argv[1:]
with Path(config).open() as stream:
    settings = json.load(stream)
filename = settings.get("asset_config", {}).get("blend_file_name", "scene_texture_packed.blend")
if not any(Path(assets).glob(f"*/{filename}")):
    raise SystemExit(f"No assets matching */{filename} in {assets}")
if jsonl and (Path(jsonl).exists() or Path(jsonl).is_symlink()):
    raise SystemExit(f"JSONL already exists: {jsonl}; choose a new filename")
if mode == "serial":
    for sample_id in range(int(start), int(start) + int(count)):
        path = Path(output) / f"sample_{sample_id:05d}"
        if path.exists() or path.is_symlink():
            raise SystemExit(f"Serial target already exists: {path}; use parallel mode to resume")
PY

echo "Placement: mode=$mode, samples=$num_samples, start_id=$start_id, concurrency=$concurrency"
echo "Output: $output_dir"

if [[ "$mode" == parallel ]]; then
    generation_cmd=("$python" "$SCRIPT_DIR/8_parallel_placement_gen.py"
        --config "$config" --asset_dir "$asset_dir" --dataset_output_path "$output_dir"
        --num_data "$num_samples" --start_id "$start_id" --concurrency "$concurrency"
        --blender_path "$blender" --existing_policy fill_gaps)
else
    generation_cmd=("$blender" --background --python-exit-code 1
        --python "$SCRIPT_DIR/6_placement_dataset_gen.py" -- --batch
        --config "$config" --asset_dir "$asset_dir" --output_dir "$output_dir"
        --num_samples "$num_samples" --start_id "$start_id")
fi
if [[ "$randomize" == 1 ]]; then generation_cmd+=(--randomize_assets); fi
"${generation_cmd[@]}"

if [[ -n "$jsonl" ]]; then
    "$python" "$SCRIPT_DIR/utils/export_dataset.py" "$output_dir" "$jsonl"
    echo "JSONL: $jsonl"
fi
echo "Generation report: $output_dir/generation_report.jsonl"
