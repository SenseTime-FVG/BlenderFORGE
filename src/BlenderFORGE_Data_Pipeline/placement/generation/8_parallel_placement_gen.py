#!/usr/bin/env python3
"""
Module 8: Parallel Placement Dataset Generator
Parallel wrapper for 6_placement_dataset_gen.py to generate multiple samples concurrently.

Usage:
    python 8_parallel_placement_gen.py \
        --config config.json \
        --num_data 100 \
        --concurrency 4 \
        --dataset_output_path output/batch \
        --asset_dir test_assets \
        --blender_path /path/to/blender

Author: 3D-Front Placement Pipeline
Date: 2024
"""

import asyncio
import argparse
import json
import os
import sys
import time
import signal
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.contract import is_complete


def get_existing_sample_ids(base_path: str, config_path: str) -> set:
    """Only v1 samples passing the shared completion check can be resumed."""
    with open(config_path) as stream:
        num_views = json.load(stream)["camera_config"]["num_views"]
    return {int(path.name.removeprefix("sample_")) for path in Path(base_path).glob("sample_*")
            if re.fullmatch(r"sample_\d{5,}", path.name) and is_complete(path, num_views, task="placement")}


def cleanup_incomplete_samples(base_path: str, dry_run: bool = False) -> int:
    """
    Clean up incomplete sample directories (those without .SUCCESS marker).
    
    This is useful for cleaning up samples that were interrupted during generation.
    
    Args:
        base_path: Root output directory
        dry_run: If True, only report what would be deleted without actually deleting
        
    Returns:
        Number of incomplete samples found/cleaned
    """
    if not os.path.exists(base_path):
        return 0
    
    pattern = re.compile(r'sample_(\d{5})$')
    incomplete_samples = []
    
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path):
            match = pattern.match(item)
            if match:
                success_marker = os.path.join(item_path, ".SUCCESS")
                if not os.path.exists(success_marker):
                    files_in_dir = os.listdir(item_path)
                    if files_in_dir:
                        incomplete_samples.append((item, item_path, len(files_in_dir)))
    
    if incomplete_samples:
        print(f"\n{'='*80}")
        print(f"INCOMPLETE SAMPLES DETECTED")
        print(f"{'='*80}")
        print(f"Found {len(incomplete_samples)} incomplete sample(s):\n")
        
        for sample_name, sample_path, file_count in incomplete_samples:
            print(f"  • {sample_name} ({file_count} files)")
        
        if dry_run:
            print(f"\n[DRY RUN] Would delete {len(incomplete_samples)} incomplete sample(s)")
        else:
            import shutil
            print(f"\nCleaning up {len(incomplete_samples)} incomplete sample(s)...")
            for sample_name, sample_path, _ in incomplete_samples:
                try:
                    shutil.rmtree(sample_path)
                    print(f"  ✓ Deleted: {sample_name}")
                except Exception as e:
                    print(f"  ✗ Failed to delete {sample_name}: {e}")
        
        print(f"{'='*80}\n")
    
    return len(incomplete_samples)


async def run_task(task_id, blender_executable, script_path, asset_dir, output_root, config_path, randomize_assets=False):
    """
    Run a single placement dataset generation task using Blender.
    
    The task will generate one sample with the specified task_id.
    Verifies the producer's v1 contract and integrity manifest.
    Blender replay checks run inside the producer before publication.
    Only the Blender producer may write .SUCCESS.
    
    The .SUCCESS marker ensures that partially-generated samples (e.g., from
    interrupted retries) are not mistakenly treated as valid samples.
    """
    sample_dir = os.path.join(output_root, f"sample_{task_id:05d}")
    success_marker = os.path.join(sample_dir, ".SUCCESS")
    with open(config_path) as stream:
        num_views = json.load(stream)["camera_config"]["num_views"]
    if is_complete(sample_dir, num_views, task="placement"):
        print(f"[Task {task_id:05d}] Already complete, skipping.")
        return True
    if os.path.exists(success_marker):
        print(f"[Task {task_id:05d}] Refusing to overwrite a marked legacy/corrupt sample: {sample_dir}")
        return False

    if os.path.exists(sample_dir):
        import shutil
        print(f"[Task {task_id:05d}] Cleaning up incomplete sample directory...")
        shutil.rmtree(sample_dir)
    
    cmd = [
        blender_executable,
        "--background",
        "--python-exit-code", "1",
        "--python", script_path,
        "--",
        "--batch",
        "--asset_dir", asset_dir,
        "--output_dir", output_root,
        "--config", config_path,
        "--num_samples", "1",
        "--start_id", str(task_id)
    ]
    
    if randomize_assets:
        cmd.append("--randomize_assets")

    print(f"[Task {task_id:05d}] Starting generation...")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        # Only the producer can publish .SUCCESS after Blender replay validation.
        valid = is_complete(sample_dir, num_views, task="placement")
        print(f"[Task {task_id:05d}] v1 acceptance: {valid}")
        return valid
    else:
        print(f"[Task {task_id:05d}] ❌ Failed with return code {process.returncode}.")
        if stderr:
            error_output = stderr.decode().strip()
            # Only print last 500 chars of error to avoid flooding
            if len(error_output) > 500:
                error_output = "..." + error_output[-500:]
            print(f"[Task {task_id:05d}] Error: {error_output}")
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Parallel Placement Dataset Generator Wrapper")
    parser.add_argument("--config", required=True,
                        help="Path to config.json containing 6_placement_dataset_gen.py configuration.")
    parser.add_argument("--num_data", type=int, default=10,
                        help="Total number of samples to generate.")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Number of parallel tasks.")
    parser.add_argument("--dataset_output_path", required=True,
                        help="Root directory for the dataset.")
    parser.add_argument("--asset_dir", required=True,
                        help="Directory containing 3D-Front assets.")
    parser.add_argument("--blender_path", default="blender",
                        help="Path to the blender executable.")
    parser.add_argument("--auto_cleanup", action="store_true",
                        help="Automatically clean up incomplete samples without prompting.")
    parser.add_argument("--randomize_assets", action="store_true",
                        help="Randomize asset selection for each sample instead of deterministic order.")
    parser.add_argument("--existing_policy", choices=("ask", "fill_gaps"), default="ask",
                        help="Use fill_gaps for unattended generation of the requested ID range.")
    parser.add_argument("--start_id", type=int, default=0,
                        help="First target sample ID; nonzero values require --existing_policy fill_gaps.")
    args = parser.parse_args()
    if args.num_data < 1 or args.concurrency < 1 or args.start_id < 0:
        parser.error("num_data and concurrency must be positive; start_id must be nonnegative")
    if args.existing_policy == "ask" and args.start_id != 0:
        parser.error("A nonzero start_id requires --existing_policy fill_gaps")

    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    if not os.path.exists(args.asset_dir):
        print(f"Error: Asset directory not found: {args.asset_dir}")
        sys.exit(1)

    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)

    script_path = os.path.join(os.path.dirname(__file__), "6_placement_dataset_gen.py")
    
    if not os.path.exists(script_path):
        print(f"Error: 6_placement_dataset_gen.py not found at: {script_path}")
        sys.exit(1)

    os.makedirs(args.dataset_output_path, exist_ok=True)

    if args.existing_policy == "fill_gaps":
        existing_sample_ids = get_existing_sample_ids(args.dataset_output_path, args.config)
        target_ids = range(args.start_id, args.start_id + args.num_data)
        task_ids_to_generate = [sample_id for sample_id in target_ids if sample_id not in existing_sample_ids]
        if not task_ids_to_generate:
            print("All requested samples are complete; nothing to generate.")
            return
        print(f"Generating {len(task_ids_to_generate)} missing samples in the requested ID range.")
    else:
        incomplete_count = cleanup_incomplete_samples(args.dataset_output_path, dry_run=True)
        if incomplete_count > 0:
            if args.auto_cleanup:
                print(f"\n🧹 Auto-cleanup enabled: Removing {incomplete_count} incomplete sample(s)...")
                cleanup_incomplete_samples(args.dataset_output_path, dry_run=False)
            else:
                response = input(f"\nClean up these {incomplete_count} incomplete sample(s)? (y/n): ").lower().strip()
                if response == 'y':
                    cleanup_incomplete_samples(args.dataset_output_path, dry_run=False)
                else:
                    print("Incomplete samples will be left as-is (they will not be counted as valid).")

        existing_sample_ids = get_existing_sample_ids(args.dataset_output_path, args.config)
        num_already_existing_samples = len(existing_sample_ids)

        task_ids_to_generate = []

        if num_already_existing_samples > 0:
            print(f"\033[93m⚠️  Warning: Found {num_already_existing_samples} existing samples.\033[0m")
            if existing_sample_ids:
                max_existing = max(existing_sample_ids)
                min_existing = min(existing_sample_ids)
                print(f"Existing sample IDs range: {min_existing:05d} to {max_existing:05d}")
            
                expected_ids = set(range(min_existing, max_existing + 1))
                missing_ids = expected_ids - existing_sample_ids
                if missing_ids:
                    missing_list = sorted(list(missing_ids))
                    preview = [f"{id:05d}" for id in missing_list[:10]]
                    print(f"\033[93m⚠️  Warning: Found {len(missing_ids)} gaps in existing samples: {preview}{'...' if len(missing_ids) > 10 else ''}\033[0m")
        
            print("\nOptions:")
            print("  (o) Overwrite - Delete all existing samples and start fresh")
            print("  (c) Continue - Generate new samples starting after the highest existing ID")
            print("  (f) Fill gaps - Fill missing IDs and continue to reach target")
            print("  (q) Quit - Exit without doing anything")
        
            response = input("\nYour choice (o/c/f/q): ").lower().strip()
        
            if response == 'q':
                print("Exiting.")
                sys.exit(0)
            elif response == 'c':
                if num_already_existing_samples >= args.num_data:
                    print(f"Already have {num_already_existing_samples} samples, which is >= requested {args.num_data}. Nothing to do.")
                    sys.exit(0)
            
                start_offset = max(existing_sample_ids) + 1 if existing_sample_ids else 0
                num_to_generate = args.num_data - num_already_existing_samples
                task_ids_to_generate = list(range(start_offset, start_offset + num_to_generate))
            
                print(f"\nContinuing from sample_{start_offset:05d}...")
                print(f"Will generate {num_to_generate} more samples to reach total of {args.num_data}.")
            elif response == 'f':
                # Fill gaps and continue to reach target
                all_needed_ids = set(range(args.num_data))
                task_ids_to_generate = sorted(list(all_needed_ids - existing_sample_ids))
            
                if not task_ids_to_generate:
                    print(f"Already have {num_already_existing_samples} samples covering 0 to {args.num_data-1}. Nothing to do.")
                    sys.exit(0)
            
                print(f"\nWill generate {len(task_ids_to_generate)} samples to fill gaps and reach total of {args.num_data}.")
                preview = [f"{id:05d}" for id in task_ids_to_generate[:10]]
                print(f"Sample IDs to generate: {preview}{'...' if len(task_ids_to_generate) > 10 else ''}")
            elif response == 'o':
                print("\n⚠️  Overwriting existing samples...")
                import shutil
                if os.path.exists(args.dataset_output_path):
                    shutil.rmtree(args.dataset_output_path)
                    os.makedirs(args.dataset_output_path)
                task_ids_to_generate = list(range(args.num_data))
            else:
                print("Invalid input. Exiting.")
                sys.exit(0)
        else:
            task_ids_to_generate = list(range(args.num_data))
            print(f"\nNo existing samples found. Will generate {args.num_data} samples starting from sample_00000.")

    # Use a queue to ensure IDs are handed out in strict sequential order
    queue = asyncio.Queue()
    for task_id in task_ids_to_generate:
        queue.put_nowait(task_id)

    start_time = time.time()
    num_to_generate = len(task_ids_to_generate)
    results = {
        "total_requested": num_to_generate,
        "completed": 0,
        "failed": 0,
        "start_time": datetime.now().isoformat(),
        "config_file": args.config,
        "asset_dir": args.asset_dir,
        "blender_path": args.blender_path,
        "concurrency": args.concurrency
    }

    def save_metadata():
        results["end_time"] = datetime.now().isoformat()
        results["duration_seconds"] = time.time() - start_time
        meta_path = os.path.join(args.dataset_output_path, "batch_metadata.json")
        with open(meta_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📊 Metadata saved to {meta_path}")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (
            print("\n⚠️  Interrupted. Saving metadata..."), 
            save_metadata(), 
            sys.exit(1)
        ))

    async def worker():
        while not queue.empty():
            try:
                task_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            success = await run_task(
                task_id, 
                args.blender_path, 
                script_path,
                args.asset_dir,
                args.dataset_output_path,
                args.config,
                randomize_assets=args.randomize_assets
            )
            
            if success:
                results["completed"] += 1
            else:
                results["failed"] += 1

            completed_total = results['completed'] + results['failed']
            elapsed = time.time() - start_time
            avg_time = elapsed / completed_total if completed_total > 0 else 0
            eta = avg_time * (num_to_generate - completed_total) if completed_total > 0 else 0
            
            print(f"\n{'='*80}")
            print(f"Overall Progress: {completed_total}/{num_to_generate} "
                  f"(✅ Success: {results['completed']}, ❌ Failed: {results['failed']})")
            print(f"Elapsed: {elapsed/60:.1f}m | Avg: {avg_time:.1f}s/sample | ETA: {eta/60:.1f}m")
            print(f"{'='*80}\n")
            
            queue.task_done()

    try:
        print(f"\n{'='*80}")
        print(f"STARTING PARALLEL GENERATION")
        print(f"{'='*80}")
        print(f"Concurrency: {args.concurrency} workers")
        print(f"Samples to generate: {num_to_generate}")
        print(f"Output directory: {args.dataset_output_path}")
        print(f"{'='*80}\n")
        
        workers = [asyncio.create_task(worker()) for _ in range(args.concurrency)]
        await asyncio.gather(*workers)
    finally:
        save_metadata()
        
        print(f"\n{'='*80}")
        print(f"BATCH GENERATION COMPLETE")
        print(f"{'='*80}")
        print(f"Total samples: {num_to_generate}")
        print(f"Successful: {results['completed']}")
        print(f"Failed: {results['failed']}")
        print(f"Duration: {(time.time() - start_time)/60:.1f} minutes")
        print(f"{'='*80}\n")
        
    # Do not suppress worker exceptions by exiting successfully from finally.
    if results['failed'] > 0:
        print(f"⚠️  {results['failed']} samples failed. Check logs for details.")
        sys.exit(1)
    print(f"✅ All {results['completed']} samples generated successfully!")


if __name__ == "__main__":
    asyncio.run(main())
