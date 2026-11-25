#!/usr/bin/env python3
import argparse
import importlib
import json
import os
import random
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Dict, List, Tuple

sample_io = importlib.import_module("2_sample_io")
list_samples = sample_io.list_samples
prepare_output_sample = sample_io.prepare_output_sample
run_blender = sample_io.run_blender
validate_sample = sample_io.validate_sample
write_success_marker = sample_io.write_success_marker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construct placement QA from legacy START/GOAL samples")
    parser.add_argument("--mode", choices=("parallel", "serial"), default="parallel",
                        help="parallel: sample with replacement to a success target; serial: visit each source once")
    parser.add_argument(
        "--input_root",
        type=str,
        required=True,
        help="Directory containing sample_xxxxx folders",
    )
    parser.add_argument(
        "--output_root",
        type=str,
        required=True,
        help="Directory to write QA outputs",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).resolve().parent / "config.json"),
        help="QA configuration path",
    )
    parser.add_argument(
        "--blender_path",
        type=str,
        default=os.environ.get("BLENDER_PATH", "blender"),
        help="Blender executable path or command (default: BLENDER_PATH or blender on PATH)",
    )
    parser.add_argument(
        "--sample_id",
        type=str,
        default=None,
        help="Optional single sample id, e.g. sample_00002",
    )
    parser.add_argument(
        "--num_of_samples",
        type=int,
        default=1,
        help="Parallel mode: target number of successful output scenes, not QA rows",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel worker processes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output sample directory",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling source samples with replacement",
    )
    parser.add_argument(
        "--max_attempt_multiplier",
        type=int,
        default=20,
        help="Maximum attempts = num_of_samples * multiplier",
    )
    return parser.parse_args()


def validate_success_artifact(out_dir: Path) -> Tuple[bool, int, str]:
    qa_items = out_dir / "qa_items.json"
    if qa_items.exists():
        try:
            with qa_items.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list) and len(payload) > 0:
                return True, len(payload), "qa_items.json"
            return False, 0, "qa_items.json is empty"
        except Exception as e:
            return False, 0, f"failed to read qa_items.json: {e}"

    qa_item = out_dir / "qa_item.json"
    if qa_item.exists():
        try:
            with qa_item.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and payload:
                return True, 1, "qa_item.json"
            return False, 0, "qa_item.json is empty"
        except Exception as e:
            return False, 0, f"failed to read qa_item.json: {e}"

    return False, 0, "missing qa_items.json/qa_item.json"


def process_single_sample(
    task_id: int,
    sample_dir_str: str,
    output_root_str: str,
    blender_path_str: str,
    blender_script_str: str,
    config_path_str: str,
    force: bool,
) -> Tuple[int, str, Dict]:
    sample_dir = Path(sample_dir_str)
    output_root = Path(output_root_str)
    blender_path = Path(blender_path_str)
    blender_script = Path(blender_script_str)
    config_path = Path(config_path_str)

    sample_name = sample_dir.name
    out_dir = output_root / f"run_{task_id:06d}__{sample_name}"

    try:
        missing = validate_sample(sample_dir)
        if missing:
            return task_id, sample_name, {
                "status": "skip",
                "reason": f"missing files: {missing}",
                "out_dir": str(out_dir),
                "source_sample": sample_name,
            }

        prepare_output_sample(sample_dir, out_dir, force=force)

        code = run_blender(
            blender_path=blender_path,
            blender_script=blender_script,
            sample_dir=sample_dir,
            out_dir=out_dir,
            config_path=config_path,
        )

        result_json = out_dir / "result_status.json"
        if result_json.exists():
            with result_json.open("r", encoding="utf-8") as f:
                result_obj = json.load(f)
        else:
            result_obj = {
                "status": "failed",
                "reason": "worker did not produce result_status.json",
                "exit_code": code,
            }

        if code != 0 and result_obj.get("status") != "skip":
            result_obj["status"] = "failed"
            result_obj.setdefault("reason", f"blender exit code {code}")

        if result_obj.get("status") == "success":
            ok, qa_count, qa_src = validate_success_artifact(out_dir)
            if not ok:
                result_obj["status"] = "failed"
                result_obj["reason"] = f"invalid success without usable QA artifact: {qa_src}"
            else:
                result_obj["qa_item_count"] = qa_count
                result_obj["qa_source"] = qa_src
                write_success_marker(out_dir)

        result_obj["out_dir"] = str(out_dir)
        result_obj["source_sample"] = sample_name
        return task_id, sample_name, result_obj
    except Exception as e:
        return task_id, sample_name, {
            "status": "failed",
            "reason": f"pipeline exception: {e}",
            "out_dir": str(out_dir),
            "source_sample": sample_name,
        }


def main() -> int:
    args = parse_args()

    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    config_path = Path(args.config).resolve()
    blender_path = Path(shutil.which(args.blender_path) or args.blender_path).resolve()
    blender_script = Path(__file__).resolve().parent / "1_current_scene.py"

    if output_root.exists() and any(output_root.glob("run_*")) and not args.force:
        raise FileExistsError(f"Output contains previous runs; use a fresh directory or --force: {output_root}")

    output_root.mkdir(parents=True, exist_ok=True)

    if not blender_path.exists():
        raise FileNotFoundError(f"Blender path does not exist: {blender_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config does not exist: {config_path}")
    if not blender_script.exists():
        raise FileNotFoundError(f"Worker script does not exist: {blender_script}")

    all_samples = list_samples(input_root, args.sample_id)
    if not all_samples:
        raise RuntimeError(f"No samples found in {input_root}")

    valid_samples = []
    invalid_samples = {}
    for sample in all_samples:
        missing = validate_sample(sample)
        if missing:
            invalid_samples[sample.name] = missing
        else:
            valid_samples.append(sample)

    if not valid_samples:
        raise RuntimeError(f"No valid samples found in {input_root}; invalid: {invalid_samples}")

    target_success = args.num_of_samples if args.mode == "parallel" else len(valid_samples)
    if target_success <= 0:
        raise ValueError("--num_of_samples must be > 0")

    workers = max(1, args.workers) if args.mode == "parallel" else 1
    start_time = time.time()
    random.seed(args.seed)
    max_attempts = target_success * max(1, args.max_attempt_multiplier) if args.mode == "parallel" else len(valid_samples)

    summary: Dict[str, Dict] = {
        "mode": args.mode,
        "input_root": str(input_root),
        "output_root": str(output_root),
        "config": str(config_path),
        "blender_path": str(blender_path),
        "worker_script": str(blender_script),
        "total_input_samples": len(all_samples),
        "valid_input_samples": len(valid_samples),
        "invalid_input_samples": invalid_samples,
        "target_success_samples": target_success,
        "max_attempts": max_attempts,
        "workers": workers,
        "attempts": [],
        "successful_outputs": [],
    }

    print(
        f"Found {len(valid_samples)} valid samples (from {len(all_samples)} total), "
        f"target success={target_success}, workers={workers}, max_attempts={max_attempts}"
    )

    attempts_submitted = 0
    attempts_done = 0
    success_count = 0
    skipped_count = 0
    failed_count = 0

    in_flight: Dict = {}

    def submit_one(executor: ProcessPoolExecutor) -> bool:
        nonlocal attempts_submitted
        if attempts_submitted >= max_attempts:
            return False
        sample = random.choice(valid_samples) if args.mode == "parallel" else valid_samples[attempts_submitted]
        task_id = attempts_submitted
        attempts_submitted += 1
        fut = executor.submit(
            process_single_sample,
            task_id,
            str(sample),
            str(output_root),
            str(blender_path),
            str(blender_script),
            str(config_path),
            args.force,
        )
        in_flight[fut] = {"task_id": task_id, "sample": sample.name}
        return True

    with ProcessPoolExecutor(max_workers=workers) as executor:
        while in_flight or (success_count < target_success and attempts_submitted < max_attempts):
            desired_inflight = min(workers, target_success - success_count)
            while len(in_flight) < desired_inflight and attempts_submitted < max_attempts:
                submit_one(executor)

            if not in_flight:
                break

            done, _ = wait(set(in_flight.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                meta = in_flight.pop(fut)
                attempts_done += 1
                task_id, sample_name, result_obj = fut.result()

                attempt_record = {
                    "task_id": task_id,
                    "source_sample": sample_name,
                    "status": result_obj.get("status"),
                    "reason": result_obj.get("reason", ""),
                    "out_dir": result_obj.get("out_dir", ""),
                    "qa_item_count": result_obj.get("qa_item_count", 0),
                }
                summary["attempts"].append(attempt_record)

                if result_obj.get("status") == "success":
                    success_count += 1
                    summary["successful_outputs"].append(
                        {
                            "output_index": success_count,
                            "task_id": task_id,
                            "source_sample": sample_name,
                            "out_dir": result_obj.get("out_dir", ""),
                            "qa_item_count": result_obj.get("qa_item_count", 0),
                        }
                    )
                elif result_obj.get("status") == "skip":
                    skipped_count += 1
                else:
                    failed_count += 1

                print(
                    f"[attempt {attempts_done}/{max_attempts}] task={task_id} sample={sample_name} -> "
                    f"{result_obj.get('status')} ({result_obj.get('reason', 'ok')}); "
                    f"success={success_count}/{target_success}"
                )

                if success_count >= target_success:
                    break

    summary["attempts_submitted"] = attempts_submitted
    summary["attempts_done"] = attempts_done
    summary["success"] = success_count
    summary["skipped"] = skipped_count
    summary["failed"] = failed_count
    summary["target_reached"] = success_count >= target_success
    summary["elapsed_sec"] = time.time() - start_time

    summary_path = output_root / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\nDone")
    print(f"  target_success: {target_success}")
    print(f"  success: {success_count}")
    print(f"  skipped: {skipped_count}")
    print(f"  failed : {failed_count}")
    print(f"  attempts: {attempts_done}/{max_attempts}")
    print(f"  target_reached: {summary['target_reached']}")
    print(f"  elapsed: {summary['elapsed_sec']:.2f}s")
    print(f"  summary: {summary_path}")
    return 0 if summary["target_reached"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
