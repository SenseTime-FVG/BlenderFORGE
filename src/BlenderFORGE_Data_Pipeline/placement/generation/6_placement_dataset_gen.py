#!/usr/bin/env python3
"""
Module 6: Complete Data Generation Pipeline
Integrated 3D-Front placement dataset generation.

Pipeline:
1. Load and analyze the scene (Module 1).
2. Select and move objects (Module 2).
3. Compute valid camera regions (Module 3).
4. Place cameras (Module 4).
5. Render START and GOAL states (Module 5).
6. Validate sample quality.
7. Save metadata and artifacts.

Author: 3D-Front Placement Pipeline
Date: 2024
"""

import importlib
import bpy
import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import shutil
import math
import mathutils
import numpy as np
import traceback
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
save_scene_state = importlib.import_module('7_sample_io').save_scene_state
finalize_sample = importlib.import_module('7_sample_io').finalize_sample
check_supported_scene = importlib.import_module('7_sample_io').check_supported_scene
from common.contract import append_report


def report_attempt(output_dir, source, result, validation):
    """Keep per-attempt diagnostics in the dataset report, outside the sample."""
    root = Path(output_dir)
    append_report(root.parent / "generation_report.jsonl", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sample_directory": root.name,
        "sample_id": result.get("metadata", {}).get("sample_id"),
        "source_asset": str(source),
        "success": result["success"],
        "errors": result["errors"],
        "validation": validation,
    })

SceneAnalyzer = importlib.import_module('1_scene_analyzer').SceneAnalyzer
compute_scene_boundaries = importlib.import_module('1_scene_analyzer').compute_scene_boundaries
select_objects_to_move = importlib.import_module('2_object_movement').select_objects_to_move
batch_move_objects = importlib.import_module('2_object_movement').batch_move_objects
place_cameras_for_objects = importlib.import_module('4_camera_placement').place_cameras_for_objects
render_all_cameras = importlib.import_module('5_rendering_visibility').render_all_cameras
analyze_visibility_simple = importlib.import_module('5_rendering_visibility').analyze_visibility_simple


def generate_single_sample(
    blend_file_path: str,
    output_dir: str,
    config: Dict
) -> Dict:
    """
    Generate one dataset sample.
    
    Pipeline:
    1. Load and analyze the scene.
    2. Preserve the GOAL state.
    3. Move objects to create START.
    4. Compute camera regions and place cameras.
    5. Render START and GOAL views.
    6. Analyze visibility and validate quality.
    7. Save metadata and artifacts.
    
    Args:
        blend_file_path: Path to the .blend file.
        output_dir: Output directory.
        config: Complete configuration dictionary.
    
    Returns:
        {
            'success': bool,
            'output_dir': str,
            'metadata': dict,
            'errors': list
        }
    """
    errors = []
    validation = {"profile": "placement-v1", "checks": []}
    
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / ".SUCCESS").unlink(missing_ok=True)
        for obsolete in ("edits.json", "validation.json"):
            (Path(output_dir) / obsolete).unlink(missing_ok=True)
        output_config = config.get('output_config', {})
        if not output_config.get('save_blend_files', True) or not output_config.get('save_restore_scripts', True):
            raise ValueError("v1 requires both scene snapshots and restore scripts")
        # A retry must not leave cameras/images from a previous incomplete attempt.
        for state in ('start', 'goal'):
            view_dir = Path(output_dir) / f'{state}_views'
            if view_dir.exists():
                shutil.rmtree(view_dir)
        
        print("\n" + "="*80)
        print("PLACEMENT DATASET GENERATION")
        print("="*80)
        print(f"Blend file: {blend_file_path}")
        print(f"Output dir: {output_dir}")
        print("="*80)
        
        print("\n[Step 1/7] Loading and analyzing scene...")
        
        analyzer = SceneAnalyzer()
        analysis_result = analyzer.analyze_scene(blend_file_path)
        
        scene_structure = analysis_result['scene_structure']
        movable_objs = analysis_result['object_metadata']
        check_supported_scene([obj['name'] for obj in movable_objs])
        scene_bounds = analysis_result['scene_bounds']
        
        margin = config.get('scene_margin', 0.0)
        if margin != 0.0:
            scene_bounds = compute_scene_boundaries(scene_structure, margin=margin)
        
        if not movable_objs:
            raise ValueError("No movable objects found in scene")
        
        print(f"✓ Found {len(movable_objs)} movable objects")
        
        # The full GOAL snapshot is saved after rendering, not at this step.
        print("\n[Step 2/7] GOAL state will be saved after rendering...")
        
        print("\n[Step 3/7] Moving objects to create START state...")
        
        movement_config = config.get('object_movement', {}).copy()
        num_objects = movement_config.get('num_of_objects_change', 1)
        
        room_width = scene_bounds['x_max'] - scene_bounds['x_min']
        room_depth = scene_bounds['y_max'] - scene_bounds['y_min']
        
        print(f"Room dimensions: {room_width:.2f}m × {room_depth:.2f}m")
        
        # If none of the selected objects can move, retry with other candidates.
        max_selection_retries = 5
        failed_objects = set()
        batch_result = None
        movement_results = []
        
        for selection_attempt in range(max_selection_retries):
            available_objs = [obj for obj in movable_objs if obj['name'] not in failed_objects]
            
            if not available_objs:
                print(f"⚠ No more objects available to try (all {len(movable_objs)} objects failed)")
                break
            
            print(f"\n{'='*60}")
            print(f"Selection attempt {selection_attempt + 1}/{max_selection_retries}")
            print(f"{'='*60}")
            print(f"Available objects: {len(available_objs)}/{len(movable_objs)}")
            
            objects_to_move = select_objects_to_move(
                available_objs,
                num_objects,
                scene_bounds
            )
            
            if not objects_to_move:
                print("⚠ Could not select objects to move")
                break
            
            print(f"✓ Selected {len(objects_to_move)} objects to move:")
            for obj_name in objects_to_move:
                print(f"   - {obj_name}")
            
            all_object_names = [obj['name'] for obj in movable_objs]
            
            use_ratio = movement_config.get('use_ratio_based_movement', True)
            
            if use_ratio:
                print(f"\n📏 Computing ratio-based movement ranges:")
                
                object_sizes = []
                for obj_name in objects_to_move:
                    if obj_name not in bpy.data.objects:
                        continue
                    
                    obj = bpy.data.objects[obj_name]
                    
                    if obj.type == 'MESH' and obj.data.vertices:
                        bbox_corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
                    else:
                        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
                    
                    xs = [c.x for c in bbox_corners]
                    ys = [c.y for c in bbox_corners]
                    
                    obj_width = max(xs) - min(xs)
                    obj_depth = max(ys) - min(ys)
                    
                    object_sizes.append({
                        'name': obj_name,
                        'width': obj_width,
                        'depth': obj_depth
                    })
                    
                    available_x = room_width - obj_width
                    available_y = room_depth - obj_depth
                    
                    print(f"   {obj_name}:")
                    print(f"     Object size: {obj_width:.2f}m × {obj_depth:.2f}m")
                    print(f"     Available space: {available_x:.2f}m × {available_y:.2f}m")
                    
                    if available_x < 0.1 or available_y < 0.1:
                        print(f"     ⚠️  WARNING: Very limited space for this object!")
                
                # Use average object dimensions for the batch movement configuration.
                if object_sizes:
                    avg_width = sum(s['width'] for s in object_sizes) / len(object_sizes)
                    avg_depth = sum(s['depth'] for s in object_sizes) / len(object_sizes)
                    
                    avg_available_x = room_width - avg_width
                    avg_available_y = room_depth - avg_depth
                    
                    min_x_ratio = movement_config.get('target_move_min_x_ratio', 0.1)
                    max_x_ratio = movement_config.get('target_move_max_x_ratio', 0.6)
                    min_y_ratio = movement_config.get('target_move_min_y_ratio', 0.1)
                    max_y_ratio = movement_config.get('target_move_max_y_ratio', 0.6)
                    
                    movement_config['target_move_min_x'] = max(0.05, avg_available_x * min_x_ratio)
                    movement_config['target_move_max_x'] = min(avg_available_x * 0.95, avg_available_x * max_x_ratio)
                    movement_config['target_move_min_y'] = max(0.05, avg_available_y * min_y_ratio)
                    movement_config['target_move_max_y'] = min(avg_available_y * 0.95, avg_available_y * max_y_ratio)
                    
                    print(f"\n   Batch configuration (based on avg object size):")
                    print(f"     Avg object: {avg_width:.2f}m × {avg_depth:.2f}m")
                    print(f"     Avg available: {avg_available_x:.2f}m × {avg_available_y:.2f}m")
                    print(f"     Movement X: [{movement_config['target_move_min_x']:.2f}, {movement_config['target_move_max_x']:.2f}]m")
                    print(f"     Movement Y: [{movement_config['target_move_min_y']:.2f}, {movement_config['target_move_max_y']:.2f}]m")
                else:
                    # Use fallback values if object dimensions are unavailable.
                    print(f"   ⚠️  Could not determine object sizes, using fallback values")
                    movement_config['target_move_min_x'] = movement_config.get('fallback_min_distance', 0.1)
                    movement_config['target_move_max_x'] = movement_config.get('fallback_max_distance', 2.0)
                    movement_config['target_move_min_y'] = movement_config.get('fallback_min_distance', 0.1)
                    movement_config['target_move_max_y'] = movement_config.get('fallback_max_distance', 2.0)
            
            batch_result = batch_move_objects(
                objects_to_move,
                movement_config,
                scene_bounds,
                all_object_names,
                max_retries=movement_config.get('target_move_retries', 50),
                use_feedback_mechanism=True
            )
            
            movement_results = []
            for result in batch_result['results']:
                if result['success']:
                    obj_name = result['object']
                    obj = bpy.data.objects[obj_name]
                    
                    movement_results.append({
                        'object': obj_name,
                        'success': True,
                        'original_position': result['original_position'],
                        'new_position': result['new_position'],
                        'original_rotation': result['original_rotation'],
                        'new_rotation': result['new_rotation'],
                        'distance_moved': math.sqrt(sum(
                            (a - b)**2 for a, b in zip(
                                result['new_position'], 
                                result['original_position']
                            )
                        ))
                    })
                else:
                    failed_objects.add(result['object'])
                    errors.append(f"Failed to move {result['object']}: {result.get('reason', 'Unknown')}")
            
            print(f"\n✓ Movement complete: {batch_result['successful']}/{batch_result['total']} objects moved")
            if batch_result['immovable_objects']:
                print(f"⚠ {len(batch_result['immovable_objects'])} objects could not be moved:")
                for obj in batch_result['immovable_objects']:
                    print(f"   - {obj}")
            
            # Stop retrying once at least one object has moved successfully.
            if batch_result['successful'] > 0:
                print(f"✅ Successfully moved {batch_result['successful']} object(s), proceeding to next step")
                break
            else:
                print(f"⚠ Attempt {selection_attempt + 1} failed: No objects moved")
                print(f"   Failed objects added to exclusion list: {batch_result['immovable_objects']}")
        
        if not batch_result or batch_result['successful'] == 0:
            raise ValueError(
                f"No objects were successfully moved after {max_selection_retries} selection attempts. "
                f"Tried {len(failed_objects)} different objects: {list(failed_objects)}"
            )
        
        print("\n[Step 4/7] Computing camera regions and placing cameras...")
        print("Strategy: Computing regions that can observe objects in BOTH START and GOAL states")
        
        camera_config = config.get('camera_config', {})
        num_cameras = camera_config.get('num_views', 3)
        
        successfully_moved_objects = [r['object'] for r in movement_results]
        
        obj_movement_pairs = []
        for result in movement_results:
            obj_movement_pairs.append({
                'object': result['object'],
                'start_position': result['new_position'],      # Current position in START.
                'goal_position': result['original_position']   # Original position in GOAL.
            })
        
        print(f"Computing dual-position regions for {len(obj_movement_pairs)} moved objects...")
        
        compute_valid_regions_for_dual_positions = importlib.import_module('3_camera_region_calculator').compute_valid_regions_for_dual_positions
        
        # Intersect regions that can observe both positions.
        regions = compute_valid_regions_for_dual_positions(
            obj_movement_pairs,
            scene_bounds,
            camera_config
        )
        
        if not regions:
            raise ValueError("Could not compute valid camera regions for dual positions. "
                           "Objects may have moved too far apart or constraints are too strict.")
        
        print(f"✓ Computed dual-position regions for {len(regions)} objects")
        
        camera_result = place_cameras_for_objects(
            regions,
            scene_bounds,
            num_cameras=num_cameras,
            placement_strategy='greedy',
            camera_config=camera_config
        )
        
        if len(camera_result['cameras']) != num_cameras:
            raise ValueError("Could not place all requested cameras")
        
        camera_names = [cam['name'] for cam in camera_result['cameras']]
        print(f"✓ Placed {len(camera_names)} cameras")
        
        print("\n[Step 5/7] Rendering START state...")
        
        render_config = config.get('render_config', {})
        
        start_render_dir = os.path.join(output_dir, "start_views")
        start_renders = render_all_cameras(
            camera_names,
            start_render_dir,
            render_config
        )
        
        print(f"✓ Rendered {len(start_renders)} START views")
        
        # Analyze START visibility for successfully moved objects only.
        start_visibility = analyze_visibility_simple(start_renders, successfully_moved_objects)
        
        save_scene_state(
            "start",
            movable_objs,
            camera_result['cameras'],
            output_dir,
            config
        )
        
        print("\n[Step 6/7] Restoring and rendering GOAL state...")
        
        for result in movement_results:
            obj_name = result['object']
            if obj_name in bpy.data.objects:
                obj = bpy.data.objects[obj_name]
                obj.location = result['original_position']
                obj.rotation_euler = result['original_rotation']
        
        goal_render_dir = os.path.join(output_dir, "goal_views")
        goal_renders = render_all_cameras(
            camera_names,
            goal_render_dir,
            render_config
        )
        
        print(f"✓ Rendered {len(goal_renders)} GOAL views")
        
        goal_visibility = analyze_visibility_simple(goal_renders, successfully_moved_objects)
        
        # Save the restored GOAL with the same generated cameras.
        save_scene_state(
            "goal",
            movable_objs,
            camera_result['cameras'],
            output_dir,
            config
        )
        
        print("\n[Step 7/7] Validating sample quality...")
        
        is_valid, error_msg = validate_sample_quality(
            output_dir,
            config,
            start_renders,
            goal_renders,
            start_visibility,
            goal_visibility
        )
        
        if not is_valid:
            errors.append(f"Quality validation failed: {error_msg}")
            print(f"⚠️  {error_msg}")
        else:
            print("✓ Sample quality validated")
        
        metadata = finalize_sample(
            output_dir, config, blend_file_path, movable_objs,
            is_valid, error_msg, start_visibility, goal_visibility, validation
        )

        print("\n" + "="*80)
        print("✅ SAMPLE GENERATION COMPLETED")
        print("="*80)
        
        result = {
            'success': is_valid,
            'output_dir': output_dir,
            'metadata': metadata,
            'errors': errors
        }
        report_attempt(output_dir, blend_file_path, result, validation)
        return result
        
    except Exception as e:
        error_msg = f"Sample generation failed: {str(e)}"
        errors.append(error_msg)
        print(f"\n❌ ERROR: {error_msg}")
        traceback.print_exc()
        
        (Path(output_dir) / ".SUCCESS").unlink(missing_ok=True)
        result = {
            'success': False,
            'output_dir': output_dir,
            'metadata': {'errors': errors},
            'errors': errors
        }
        try:
            report_attempt(output_dir, blend_file_path, result, validation)
        except OSError as report_error:
            print(f"Could not persist failure report: {report_error}")
        return result
def validate_sample_quality(
    output_dir: str,
    config: Dict,
    start_renders: List[Dict],
    goal_renders: List[Dict],
    start_visibility: Dict,
    goal_visibility: Dict
) -> Tuple[bool, str]:
    """
    Validate the generated sample's quality.
    
    Checks:
    1. Required artifacts exist.
    2. Rendered image counts match.
    3. START and GOAL differ photometrically.
    4. Visibility meets the required threshold.
    
    Returns:
        (is_valid, error_message)
    """
    validation_config = config.get('validation_config', {})
    
    # Check 1: Required files, excluding metadata.json which is saved later.
    required_files = ['start_info.json', 'goal_info.json']
    for filename in required_files:
        filepath = os.path.join(output_dir, filename)
        if not os.path.exists(filepath):
            return False, f"Missing required file: {filename}"
    
    if len(start_renders) != len(goal_renders):
        return False, f"Render count mismatch: {len(start_renders)} START vs {len(goal_renders)} GOAL"
    
    if len(start_renders) == 0:
        return False, "No renders generated"
    
    photometric_threshold = validation_config.get('photometric_threshold', 0.0009)
    
    try:
        total_loss = 1.0
        valid_pairs = 0
        
        for start_render, goal_render in zip(start_renders, goal_renders):
            if 'rgb' in start_render and 'rgb' in goal_render:
                loss = compute_photometric_loss(
                    start_render['rgb'],
                    goal_render['rgb']
                )

                total_loss = min(total_loss, loss)
                valid_pairs += 1
        
        assert valid_pairs > 0, "No valid render pairs for photometric loss"
        if total_loss < photometric_threshold:
            return False, f"Photometric loss too low: {total_loss:.6f} < {photometric_threshold:.6f}"
        
    except Exception as e:
        print(f"   ⚠️  Could not compute photometric loss: {e}")
        raise ValueError(f"Photometric loss computation failed: {e}")
    
    min_visibility = validation_config.get('min_visibility_ratio', 0.2)
    
    start_coverage = start_visibility['summary'].get('coverage_rate', 0)
    goal_coverage = goal_visibility['summary'].get('coverage_rate', 0)
    
    if start_coverage < min_visibility:
        return False, f"START visibility too low: {start_coverage:.2%}"
    
    if goal_coverage < min_visibility:
        return False, f"GOAL visibility too low: {goal_coverage:.2%}"
    
    return True, "All quality checks passed"


def compute_photometric_loss(img1_path: str, img2_path: str) -> float:
    """Compute the L1 loss between two images."""
    try:
        from PIL import Image
        import numpy as np
        
        img1 = np.array(Image.open(img1_path)).astype(np.float32) / 255.0
        img2 = np.array(Image.open(img2_path)).astype(np.float32) / 255.0
        if np.mean(img1) < 0.01 and np.mean(img2) < 0.01:
            raise ValueError("Both images are almost black, invalid for photometric loss")
        return np.mean(np.abs(img1 - img2))
    except ImportError:
        raise ImportError("PIL and numpy are required for photometric loss computation")


def process_asset_directory(
    asset_dir: str,
    output_base_dir: str,
    config: Dict,
    num_samples: Optional[int] = None,
    start_sample_id: int = 0,
    max_retries_per_sample: int = 10,
    randomize_assets: bool = False
) -> List[Dict]:
    """
    Generate the requested number of samples from an asset directory.
    
    Traverse scene directories and assign consecutive sample IDs.
    Automatically switch to another asset when generation fails.
    
    Args:
        asset_dir: Root asset directory.
        output_base_dir: Root output directory.
        config: Configuration.
        num_samples: Number of samples to generate; None processes all assets.
        start_sample_id: First sample ID (default: 0).
        max_retries_per_sample: Maximum retries per sample (default: 10).
        randomize_assets: Shuffle assets instead of using their original order (default: False).
    
    Returns:
        List of generation results.
    """
    import random
    
    results = []
    blend_filename = config.get('asset_config', {}).get('blend_file_name', 'scene_texture_packed.blend')
    
    asset_path = Path(asset_dir)
    blend_files = list(asset_path.glob(f"*/{blend_filename}"))
    
    if not blend_files:
        print(f"❌ No blend files found in {asset_dir}")
        return results
    
    # Shuffle assets with a fixed seed when randomization is enabled.
    if randomize_assets:
        # The same start_sample_id produces the same shuffled order.
        random.seed(start_sample_id)
        blend_files = blend_files.copy()
        random.shuffle(blend_files)
        print(f"Asset selection: Randomized (seed={start_sample_id})")
    else:
        print(f"Asset selection: Deterministic (sample_id % num_assets)")
    
    if num_samples is not None:
        total_samples = num_samples
    else:
        total_samples = len(blend_files)
    
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING")
    print(f"{'='*80}")
    print(f"Available assets: {len(blend_files)}")
    print(f"Samples to generate: {total_samples}")
    print(f"Starting sample ID: {start_sample_id:05d}")
    print(f"Max retries per sample: {max_retries_per_sample}")
    print(f"{'='*80}\n")
    
    sample_count = 0
    
    while sample_count < total_samples:
        current_sample_id = start_sample_id + sample_count
        sample_name = f"sample_{current_sample_id:05d}"
        output_dir = os.path.join(output_base_dir, sample_name)
        
        success = False
        tried_assets = set()
        retry_count = 0
        
        while not success and retry_count < max_retries_per_sample:
            if retry_count == 0:
                # First attempt: index by sample_id so parallel samples start from different assets.
                asset_idx = current_sample_id % len(blend_files)
                blend_file = blend_files[asset_idx]
            else:
                # On retries, randomly choose an asset that has not been attempted.
                available_assets = [f for i, f in enumerate(blend_files) 
                                   if i not in tried_assets]
                
                if not available_assets:
                    # All assets have been attempted; restart the selection.
                    print(f"  ⚠️  All {len(blend_files)} assets tried, restarting from random selection")
                    tried_assets.clear()
                    available_assets = blend_files
                
                blend_file = random.choice(available_assets)
            
            asset_index = blend_files.index(blend_file)
            tried_assets.add(asset_index)
            
            scene_id = blend_file.parent.name
            
            retry_info = f" (retry {retry_count}/{max_retries_per_sample})" if retry_count > 0 else ""
            print(f"\n[{sample_count + 1}/{total_samples}] Generating sample {current_sample_id:05d}{retry_info}")
            print(f"  Asset: {scene_id}")
            print(f"  Output: {output_dir}")
            print("-" * 80)
            
            result = generate_single_sample(
                str(blend_file),
                output_dir,
                config
            )
            
            success = result['success']
            
            if success:
                results.append({
                    'sample_id': current_sample_id,
                    'sample_name': sample_name,
                    'asset': scene_id,
                    'blend_file': str(blend_file),
                    'success': True,
                    'output_dir': output_dir,
                    'errors': result.get('errors', []),
                    'retry_count': retry_count
                })
                
                print(f"✅ SUCCESS: Sample {current_sample_id:05d} from {scene_id}")
                if retry_count > 0:
                    print(f"   (succeeded after {retry_count} retries)")
            else:
                print(f"❌ FAILED: Sample {current_sample_id:05d} from {scene_id}")
                if retry_count < max_retries_per_sample - 1:
                    print(f"   Errors: {result.get('errors', [])}")
                    print(f"   🔄 Will retry with a different asset...")
                    
                    if os.path.exists(output_dir):
                        try:
                            shutil.rmtree(output_dir)
                            print(f"   Cleaned up failed output: {output_dir}")
                        except Exception as e:
                            print(f"   Warning: Could not clean up {output_dir}: {e}")
                
                retry_count += 1
        
        if not success:
            results.append({
                'sample_id': current_sample_id,
                'sample_name': sample_name,
                'asset': 'multiple_assets_tried',
                'blend_file': f"tried_{len(tried_assets)}_assets",
                'success': False,
                'output_dir': output_dir,
                'errors': [f"Failed after {max_retries_per_sample} attempts with different assets"],
                'retry_count': retry_count
            })
            
            print(f"❌ FINAL FAILURE: Sample {current_sample_id:05d}")
            print(f"   Tried {len(tried_assets)} different assets without success")
        
        sample_count += 1
    
    success_count = sum(1 for r in results if r['success'])
    total_retries = sum(r.get('retry_count', 0) for r in results)
    
    print(f"\n{'='*80}")
    print(f"BATCH COMPLETE")
    print(f"{'='*80}")
    print(f"Total samples: {total_samples}")
    print(f"Successful: {success_count}")
    print(f"Failed: {total_samples - success_count}")
    print(f"Total retries: {total_retries}")
    print(f"Average retries per sample: {total_retries/total_samples:.2f}")
    print(f"Sample ID range: [{start_sample_id:05d}, {start_sample_id + total_samples - 1:05d}]")
    print(f"{'='*80}\n")
    
    return results


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description='3D-Front Placement Dataset Generation')
    parser.add_argument('--blend_file', type=str, help='Path to .blend file')
    parser.add_argument('--output_dir', type=str, help='Output directory')
    parser.add_argument('--config', type=str, help='Path to config JSON file or JSON string')
    parser.add_argument('--batch', action='store_true', help='Batch process entire asset directory')
    parser.add_argument('--asset_dir', type=str, help='Asset directory for batch processing')
    parser.add_argument('--num_samples', type=int, help='Number of samples to generate (for batch mode)')
    parser.add_argument('--start_id', type=int, default=0, help='Starting sample ID (default: 0)')
    parser.add_argument('--randomize_assets', action='store_true', 
                        help='Randomize asset selection instead of deterministic order')
    
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    args = parser.parse_args(argv)
    
    if args.config:
        if os.path.isfile(args.config):
            with open(args.config, 'r') as f:
                config = json.load(f)
        else:
            config = json.loads(args.config)
    else:
        raise ValueError("config not set")
    
    # Seed once per invocation, so retries and later batch samples advance the RNG.
    if config.get('random_seed') is not None:
        random.seed(config['random_seed'])
        np.random.seed(config['random_seed'])

    if args.batch:
        if not args.asset_dir:
            print("Error: --asset_dir required for batch processing")
            sys.exit(1)
        
        if not args.output_dir:
            print("Error: --output_dir required for batch processing")
            sys.exit(1)
        
        results = process_asset_directory(
            args.asset_dir,
            args.output_dir,
            config,
            num_samples=args.num_samples,
            start_sample_id=args.start_id,
            randomize_assets=args.randomize_assets
        )
        
        # Worker processes append to one locked report instead of overwriting it.
        report_path = os.path.join(args.output_dir, "generation_report.jsonl")
        print(f"\nBatch report: {report_path}")
        
        success_count = sum(1 for r in results if r['success'])
        sys.exit(0 if results and success_count == len(results) else 1)
        
    else:
        if not args.blend_file or not args.output_dir:
            print("Error: --blend_file and --output_dir required for single sample")
            sys.exit(1)
        
        result = generate_single_sample(
            args.blend_file,
            args.output_dir,
            config
        )
        
        sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
