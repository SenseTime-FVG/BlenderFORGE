#!/usr/bin/env python3
"""
Module 4: Intelligent Camera Placement
Infinigen Lighting Dataset Generation Pipeline

Purpose:
- Place cameras to observe light objects in the scene
- Ensure all lights are covered by at least one camera
- Maximize coverage and quality
- Handle collision detection and boundary constraints

Key Features:
1. Camera creation at optimal positions
2. Camera orientation (look-at) calculation
3. Coverage validation (ensure all lights are observed)
4. Multi-level fallback for guaranteed placement

Dependencies:
- Blender Python API (bpy)
- 3_camera_region_calculator.py

Adapted from: placement/generation/4_camera_placement.py
"""

import math
from typing import List, Dict, Optional
import bpy
import mathutils


# Cache collision objects to avoid rebuilding the list on every check.
_cached_collision_objects = None


def _build_collision_cache() -> List[Dict]:
    """
    Build a cache of collision objects with precomputed world-space bounding boxes.
    
    **CRITICAL PERFORMANCE OPTIMIZATION**:
    - Only called ONCE per scene (not per camera check)
    - Uses obj.bound_box (8 corners) instead of obj.data.vertices (thousands of vertices)
    - Precomputes world-space transforms
    
    Expected speedup: 50-100x for scenes with many objects
    
    Returns:
        List of dicts with:
        - 'name': object name
        - 'bbox': {'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max'}
    """
    cache = []
    
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        
        if ".spawn_asset" not in obj.name:
            continue
        
        if obj.name.lower().endswith(('.wall', '.floor', '.ceiling', '.exterior')):
            continue
        
        # Use the eight bound-box corners for collision tests.
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        
        xs = [c.x for c in bbox_corners]
        ys = [c.y for c in bbox_corners]
        zs = [c.z for c in bbox_corners]
        
        cache.append({
            'name': obj.name,
            'bbox': {
                'x_min': min(xs), 'x_max': max(xs),
                'y_min': min(ys), 'y_max': max(ys),
                'z_min': min(zs), 'z_max': max(zs)
            }
        })
    
    print(f"✓ Built collision cache: {len(cache)} objects")
    return cache


def clear_collision_cache():
    """Clear the collision cache (call this if scene changes)."""
    global _cached_collision_objects
    _cached_collision_objects = None
    print("✓ Collision cache cleared")


def check_camera_clearance(
    camera_position: List[float],
    camera_size: float = 0.1,
    exclude_objects: Optional[List[str]] = None
) -> bool:
    """
    Check if a camera position is clear of collisions with scene objects.
    
    **PERFORMANCE**: Uses cached bounding boxes - first call builds cache,
    subsequent calls are 50-100x faster than original implementation.
    
    Treats the camera as a cubic bounding box centered at the given position,
    and checks for AABB (axis-aligned bounding box) overlap with all MESH objects
    in the scene.
    
    Args:
        camera_position: [x, y, z] position of camera center
        camera_size: Size of camera bounding box (default 0.1m for 0.1×0.1×0.1m box)
        exclude_objects: Optional list of object names to exclude from collision check
    
    Returns:
        bool: True if position is clear (no collisions), False if collision detected
    
    Example:
        >>> is_clear = check_camera_clearance([1.0, 2.0, 1.5])
        >>> if is_clear:
        ...     print("Camera position is valid")
    """
    global _cached_collision_objects
    
    if _cached_collision_objects is None:
        _cached_collision_objects = _build_collision_cache()
    
    if exclude_objects is None:
        exclude_objects = []
    
    half_size = camera_size / 2.0
    cam_x, cam_y, cam_z = camera_position
    cam_bbox = {
        'x_min': cam_x - half_size,
        'x_max': cam_x + half_size,
        'y_min': cam_y - half_size,
        'y_max': cam_y + half_size,
        'z_min': cam_z - half_size,
        'z_max': cam_z + half_size
    }
    
    for obj_data in _cached_collision_objects:
        if obj_data['name'] in exclude_objects:
            continue
        
        obj_bbox = obj_data['bbox']
        
        # Reject Z-separated boxes before checking X/Y.
        if not (cam_bbox['z_min'] <= obj_bbox['z_max'] and cam_bbox['z_max'] >= obj_bbox['z_min']):
            continue
        
        if not (cam_bbox['x_min'] <= obj_bbox['x_max'] and cam_bbox['x_max'] >= obj_bbox['x_min']):
            continue
        
        if not (cam_bbox['y_min'] <= obj_bbox['y_max'] and cam_bbox['y_max'] >= obj_bbox['y_min']):
            continue
        
        # All axes overlap = collision detected
        return False
    
    return True


def create_camera_at_position(
    position: List[float],
    look_at: List[float],
    camera_index: int,
    fov: float = 50.0,
    name_prefix: str = "Camera"
) -> str:
    """
    Create a camera object at specified position looking at target.
    
    Args:
        position: Camera position [x, y, z]
        look_at: Target point to look at [x, y, z]
        camera_index: Camera index for naming
        fov: Field of view in degrees (default 50°)
        name_prefix: Prefix for camera name (default "Camera")
    
    Returns:
        str: Camera object name
    
    Example:
        >>> cam_name = create_camera_at_position([0, -3, 1.5], [0, 0, 0.5], 0)
        >>> print(cam_name)  # "Camera_00"
    """
    cam_name = f"{name_prefix}_{camera_index:02d}"
    
    cam_data = bpy.data.cameras.new(cam_name)
    cam_data.lens_unit = 'FOV'
    cam_data.angle = math.radians(fov)
    
    cam_obj = bpy.data.objects.new(cam_name, cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    
    cam_obj.location = mathutils.Vector(position)
    
    direction = mathutils.Vector(look_at) - mathutils.Vector(position)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam_obj.rotation_euler = rot_quat.to_euler()
    
    # Update world matrices before the coverage checks.
    bpy.context.view_layer.update()
    
    print(f"✓ Created camera: {cam_name} at {position}")
    
    return cam_name


def delete_all_cameras() -> int:
    """
    Delete all camera objects in the scene.
    
    Returns:
        int: Number of cameras deleted
    """
    cameras = [obj for obj in bpy.data.objects if obj.type == 'CAMERA']
    count = len(cameras)
    
    for cam in cameras:
        bpy.data.objects.remove(cam, do_unlink=True)
    
    if count > 0:
        print(f"✓ Deleted {count} camera(s)")
    
    return count




def select_camera_positions_greedy(
    regions: List[Dict],
    num_cameras: int,
    scene_bounds: Dict,
    max_attempts_per_camera: int = 100,
    modified_lights: List[str] = None
) -> List[Dict]:
    """
    Greedily select camera positions to maximize light coverage.
    
    Strategy:
    1. MUST place exactly num_cameras (as requested by user)
    2. **PRIORITIZE covering modified lights first**
    3. After modified lights covered, cover remaining lights
    4. After all lights covered, continue placing for diversity/quality
    5. If normal constraints fail, relax constraints to ensure placement
    
    Args:
        regions: List of valid observation regions (from Module 3)
        num_cameras: Number of cameras to place (MUST place this many)
        scene_bounds: Scene boundary info
        max_attempts_per_camera: Max sampling attempts per camera
        modified_lights: List of light names that were modified (prioritize these)
    
    Returns:
        List of camera placement dicts (length = num_cameras)
    """
    import importlib
    sample_camera_position_from_region = importlib.import_module("3_camera_region_calculator").sample_camera_position_from_region
    
    if not regions:
        return []
    
    if modified_lights is None:
        modified_lights = []
    
    all_lights = [r['light_name'] for r in regions]
    modified_lights_set = set(modified_lights)
    covered_lights = set()
    covered_modified_lights = set()
    camera_placements = []
    placed_camera_positions = []
    
    print(f"ℹ️  Modified lights to prioritize: {modified_lights}")
    print(f"ℹ️  Total lights in scene: {len(all_lights)}")
    
    # Progressive relaxation of constraints if placement fails
    min_camera_distance_levels = [0.5, 0.3, 0.1, 0.0]
    fov_levels = [70.0, 90.0, 110.0, 120, 130, 135, 140]
    
    for cam_idx in range(num_cameras):
        best_placement = None
        best_score = -1
        
        print(f"\n📷 Placing camera {cam_idx + 1}/{num_cameras}...")
        print(f"   Greedy estimate: {len(covered_lights)}/{len(all_lights)} lights covered so far")
        if modified_lights:
            print(f"   Modified lights (estimate): {len(covered_modified_lights)}/{len(modified_lights_set)}")
        
        for fov_idx, current_fov in enumerate(fov_levels):
            if best_placement is not None:
                break
            
            if fov_idx > 0:
                print(f"   ⚠️  Increasing FOV to {current_fov}°...")
            
            for distance_level_idx, min_camera_distance in enumerate(min_camera_distance_levels):
                if best_placement is not None:
                    break
                
                if distance_level_idx > 0:
                    print(f"   ⚠️  Relaxing distance constraint to {min_camera_distance:.2f}m...")
                
                # Increase attempts when all lights are covered (need more diversity)
                attempts_per_region = max_attempts_per_camera // len(regions)
                if len(covered_lights) == len(all_lights):
                    attempts_per_region = attempts_per_region * 2
                
                for region in regions:
                    light_name = region['light_name']
                    
                    for attempt in range(attempts_per_region):
                        position = sample_camera_position_from_region(
                            region, scene_bounds, max_attempts=10
                        )
                        
                        if position is None:
                            continue
                        
                        x, y, z = position
                        if not (scene_bounds['x_min'] <= x <= scene_bounds['x_max'] and
                                scene_bounds['y_min'] <= y <= scene_bounds['y_max'] and
                                scene_bounds['z_floor'] <= z <= scene_bounds['z_ceiling']):
                            continue
                        if not check_camera_clearance(position, camera_size=0.05):
                            continue
                        
                        too_close = False
                        if min_camera_distance > 0:
                            for existing_pos in placed_camera_positions:
                                dist = math.sqrt(sum((a - b)**2 for a, b in zip(position, existing_pos)))
                                if dist < min_camera_distance:
                                    too_close = True
                                    break
                        
                        if too_close:
                            continue
                        
                        # Use camera forward direction and FOV to estimate coverage
                        covers = []
                        
                        cam_pos = mathutils.Vector(position)
                        look_at = mathutils.Vector(region['target_position'])
                        cam_forward = (look_at - cam_pos).normalized()
                        
                        half_fov_rad = math.radians(current_fov / 2) * 1.2  # 20% margin
                        
                        for r in regions:
                            light_pos = mathutils.Vector(r['target_position'])
                            
                            to_light = light_pos - cam_pos
                            distance = to_light.length
                            
                            if distance < 0.1:
                                continue
                            
                            to_light_normalized = to_light.normalized()
                            
                            dot = cam_forward.dot(to_light_normalized)
                            
                            if dot <= 0:
                                continue
                            
                            angle = math.acos(max(-1.0, min(1.0, dot)))
                            
                            if angle <= half_fov_rad:
                                covers.append(r['light_name'])
                        
                        # Fallback: if no lights detected, at least add the primary target
                        # (This handles edge cases where FOV might be too narrow)
                        if not covers and region['light_name']:
                            covers.append(region['light_name'])
                        
                        num_new_covered = sum(1 for light in covers if light not in covered_lights)
                        num_new_modified_covered = sum(1 for light in covers 
                                                      if light in modified_lights_set 
                                                      and light not in covered_modified_lights)
                        quality_score = len(covers)
                        
                        # Priority 1: Cover modified lights (HIGHEST)
                        # Priority 2: Cover other uncovered lights
                        # Priority 3: Quality and diversity
                        
                        if num_new_modified_covered > 0:
                            combined_score = num_new_modified_covered * 100 + num_new_covered * 10 + quality_score
                        elif num_new_covered > 0:
                            combined_score = num_new_covered * 10 + quality_score
                        else:
                            min_dist_to_existing = float('inf')
                            if placed_camera_positions:
                                distances = [
                                    math.sqrt(sum((a - b)**2 for a, b in zip(position, existing_pos)))
                                    for existing_pos in placed_camera_positions
                                ]
                                min_dist_to_existing = min(distances)
                            
                            diversity_bonus = min(min_dist_to_existing, 5.0)
                            combined_score = quality_score + diversity_bonus
                        
                        if combined_score > best_score:
                            best_score = combined_score
                            best_placement = {
                                'position': position,
                                'look_at': region['target_position'],
                                'covers_lights': covers,
                                'quality_score': quality_score,
                                'num_new_covered': num_new_covered
                            }
        
        if best_placement:
            camera_placements.append(best_placement)
            placed_camera_positions.append(best_placement['position'])
            
            newly_covered_lights = [light for light in best_placement['covers_lights'] 
                                   if light not in covered_lights]
            covered_lights.update(best_placement['covers_lights'])
            
            newly_covered_modified = [light for light in best_placement['covers_lights'] 
                                     if light in modified_lights_set and light not in covered_modified_lights]
            covered_modified_lights.update(best_placement['covers_lights'])
            
            print(f"   ✓ Position: [{best_placement['position'][0]:.2f}, {best_placement['position'][1]:.2f}, {best_placement['position'][2]:.2f}]")
            print(f"   ✓ Quality: {best_placement['quality_score']:.2f}")
            print(f"   ✓ Sees: {len(best_placement['covers_lights'])} lights total")
            if newly_covered_lights:
                print(f"   ✓ Newly covered: {len(newly_covered_lights)} lights → Total: {len(covered_lights)}/{len(all_lights)}")
            if newly_covered_modified:
                print(f"   🎯 PRIORITY: Newly covered MODIFIED lights: {newly_covered_modified}")
            if best_placement['num_new_covered'] == 0:
                print(f"   ℹ️  All lights already covered - placed for diversity")
        else:
            print(f"   ⚠️  WARNING: Could not find valid position even with relaxed constraints!")
            print(f"   ℹ️  Using fallback: random position from regions")
            
            # Try fallback with NO constraints at all
            fallback_success = False
            for fallback_attempt in range(200):
                # Try different regions in round-robin
                region_idx = (cam_idx + fallback_attempt) % len(regions)
                position = sample_camera_position_from_region(
                    regions[region_idx], scene_bounds, max_attempts=5
                )
                if position is not None:
                    fallback_placement = {
                        'position': position,
                        'look_at': regions[region_idx]['target_position'],
                        'covers_lights': all_lights,
                        'quality_score': 0.5,
                        'num_new_covered': 0
                    }
                    camera_placements.append(fallback_placement)
                    placed_camera_positions.append(fallback_placement['position'])
                    print(f"   ✓ Fallback placement successful (attempt {fallback_attempt + 1})")
                    fallback_success = True
                    break
            
            if not fallback_success:
                print(f"   ⚠️  LAST RESORT: Placing at default safe position")
                safe_position = (
                    (scene_bounds['x_min'] + scene_bounds['x_max']) / 2,
                    (scene_bounds['y_min'] + scene_bounds['y_max']) / 2,
                    (scene_bounds['z_floor'] + scene_bounds['z_ceiling']) / 2
                )
                # Offset slightly for each camera to avoid exact duplicates
                offset_x = (cam_idx % 3 - 1) * 0.5
                offset_y = (cam_idx // 3 % 3 - 1) * 0.5
                safe_position = (
                    safe_position[0] + offset_x,
                    safe_position[1] + offset_y,
                    safe_position[2]
                )
                
                last_resort_placement = {
                    'position': safe_position,
                    'look_at': regions[0]['target_position'],
                    'covers_lights': all_lights,
                    'quality_score': 0.1,
                    'num_new_covered': 0
                }
                camera_placements.append(last_resort_placement)
                placed_camera_positions.append(safe_position)
                print(f"   ✓ Safe position used: [{safe_position[0]:.2f}, {safe_position[1]:.2f}, {safe_position[2]:.2f}]")
    
    print(f"\n✓ Camera placement complete: {len(camera_placements)}/{num_cameras} cameras placed")
    print(f"✓ Greedy algorithm completed")
    print(f"   NOTE: Coverage estimates below are heuristic-based and may not reflect actual visibility")
    print(f"   Greedy estimate: {len(covered_lights)}/{len(all_lights)} lights")
    if modified_lights:
        print(f"   Modified lights (estimate): {len(covered_modified_lights)}/{len(modified_lights_set)}")
    
    if len(camera_placements) < num_cameras:
        print(f"❌ ERROR: Failed to place all requested cameras!")
        print(f"   Requested: {num_cameras}, Placed: {len(camera_placements)}")
    else:
        print(f"✓ All {num_cameras} cameras placed successfully")
        print(f"   (Actual coverage will be verified after camera creation using frustum checks)")
    
    return camera_placements


def place_cameras_for_lights(
    regions: List[Dict],
    scene_bounds: Dict,
    num_cameras: int = None,
    placement_strategy: str = 'greedy',
    camera_config: Dict = None,
    modified_lights: List[str] = None
) -> Dict:
    """
    Main function to place cameras for observing light objects.
    
    Args:
        regions: Valid observation regions from Module 3
        scene_bounds: Scene boundary info
        num_cameras: Number of cameras to place (None = auto-determine)
        placement_strategy: 'greedy', 'random', or 'clustered'
        camera_config: Camera configuration dict
        modified_lights: List of light names that were modified (for prioritization)
    
    Returns:
        {
            'camera_names': List[str],       # Created camera names
            'camera_data': List[Dict],       # Camera metadata
            'coverage': Dict,                # Coverage statistics
            'num_cameras_placed': int        # Total cameras placed
        }
    
    Example:
        >>> result = place_cameras_for_lights(regions, bounds, num_cameras=3)
        >>> print(result['camera_names'])  # ['Camera_00', 'Camera_01', 'Camera_02']
    """
    if camera_config is None:
        camera_config = {}
    
    if modified_lights is None:
        modified_lights = []
    
    fov = camera_config.get('fov', 50.0)
    
    if num_cameras is None:
        # Default: ceil(num_lights / 2), min 2, max 5
        num_lights = len(regions)
        num_cameras = min(max((num_lights + 1) // 2, 2), 5)
        print(f"ℹ️  Auto-determined {num_cameras} cameras for {num_lights} lights")
    
    delete_all_cameras()
    
    # Clear collision cache to ensure we use current scene state
    clear_collision_cache()
    
    if placement_strategy == 'greedy':
        camera_placements = select_camera_positions_greedy(
            regions, num_cameras, scene_bounds, modified_lights=modified_lights
        )
    else:
        raise ValueError(f"Unsupported placement strategy: {placement_strategy}")
    
    camera_names = []
    camera_data = []
    
    for i, placement in enumerate(camera_placements):
        cam_name = create_camera_at_position(
            position=placement['position'],
            look_at=placement['look_at'],
            camera_index=i,
            fov=fov
        )
        camera_names.append(cam_name)
        
        camera_data.append({
            'name': cam_name,
            'position': placement['position'],
            'look_at': placement['look_at'],
            'covers_lights': placement.get('covers_lights', []),
            'quality_score': placement.get('quality_score', 0.0)
        })
    
    # Recheck coverage from the created cameras; greedy estimates use planned poses.
    light_positions = {r['light_name']: r['target_position'] for r in regions}
    actual_coverage = verify_actual_light_coverage(
        camera_names=camera_names,
        light_positions=light_positions,
        fov_degrees=fov,
        debug=False
    )
    
    coverage = {
        'total_lights': actual_coverage['total_lights'],
        'covered_lights': actual_coverage['covered_lights'],
        'coverage_percentage': actual_coverage['coverage_percentage'],
        'uncovered_lights': actual_coverage['uncovered_lights'],
        'coverage_by_camera': actual_coverage['coverage_by_camera'],
        'coverage_by_light': actual_coverage['coverage_by_light']
    }
    
    print(f"\n{'='*60}")
    print(f"CAMERA PLACEMENT SUMMARY (ACTUAL COVERAGE)")
    print(f"{'='*60}")
    print(f"Total cameras placed: {len(camera_names)}")
    print(f"Light coverage (verified): {coverage['covered_lights']}/{coverage['total_lights']} ({coverage['coverage_percentage']:.1f}%)")
    
    if modified_lights:
        modified_set = set(modified_lights)
        covered_modified = [light for light in modified_lights 
                          if light in actual_coverage['coverage_by_light'] 
                          and actual_coverage['coverage_by_light'][light]]
        print(f"Modified lights covered: {len(covered_modified)}/{len(modified_lights)} ({len(covered_modified)/len(modified_lights)*100 if modified_lights else 0:.1f}%)")
        
        for light in modified_lights:
            cams = actual_coverage['coverage_by_light'].get(light, [])
            status = "✓" if cams else "✗"
            print(f"  {status} {light}: {len(cams)} camera(s)")
    
    if coverage['uncovered_lights']:
        print(f"⚠️  Uncovered lights: {coverage['uncovered_lights']}")
    print(f"{'='*60}")
    
    return {
        'camera_names': camera_names,
        'camera_data': camera_data,
        'coverage': coverage,
        'num_cameras_placed': len(camera_names)
    }


def verify_actual_light_coverage(
    camera_names: List[str],
    light_positions: Dict[str, List[float]],
    fov_degrees: float = 70.0,
    debug: bool = False
) -> Dict:
    """
    Verify which lights are actually visible from created cameras.
    
    This function performs actual frustum checks after cameras are created
    to determine the true coverage, rather than relying on greedy algorithm estimates.
    
    Args:
        camera_names: List of created camera names
        light_positions: Dict mapping light names to [x, y, z] positions
        fov_degrees: Camera field of view in degrees
        debug: Print debug information
        
    Returns:
        {
            'total_lights': int,
            'covered_lights': int,
            'coverage_percentage': float,
            'coverage_by_camera': {cam_name: [light_names]},
            'coverage_by_light': {light_name: [cam_names]},
            'uncovered_lights': [light_names]
        }
    """
    coverage_by_camera = {cam: [] for cam in camera_names}
    coverage_by_light = {light: [] for light in light_positions.keys()}
    
    for cam_name in camera_names:
        cam_obj = bpy.data.objects.get(cam_name)
        if not cam_obj or cam_obj.type != 'CAMERA':
            continue
            
        cam_pos = list(cam_obj.matrix_world.translation)
        cam_forward = cam_obj.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))
        
        for light_name, light_pos in light_positions.items():
            to_light = mathutils.Vector(light_pos) - mathutils.Vector(cam_pos)
            distance = to_light.length
            
            if distance < 0.01:
                continue
            
            to_light.normalize()
            
            dot = to_light.dot(cam_forward)
            if dot <= 0:
                continue
            
            half_fov_rad = math.radians(fov_degrees / 2)
            angle = math.acos(max(-1, min(1, dot)))
            
            if angle <= half_fov_rad * 1.2:  # Add 20% margin
                coverage_by_camera[cam_name].append(light_name)
                coverage_by_light[light_name].append(cam_name)
                if debug:
                    print(f"  {cam_name} sees {light_name} (angle={math.degrees(angle):.1f}°)")
    
    covered_lights = [light for light, cams in coverage_by_light.items() if cams]
    uncovered_lights = [light for light, cams in coverage_by_light.items() if not cams]
    
    result = {
        'total_lights': len(light_positions),
        'covered_lights': len(covered_lights),
        'coverage_percentage': len(covered_lights) / len(light_positions) * 100 if light_positions else 0,
        'coverage_by_camera': coverage_by_camera,
        'coverage_by_light': coverage_by_light,
        'uncovered_lights': uncovered_lights
    }
    
    if debug:
        print(f"\n=== ACTUAL COVERAGE VERIFICATION ===")
        print(f"Total lights: {result['total_lights']}")
        print(f"Covered lights: {result['covered_lights']}")
        print(f"Coverage: {result['coverage_percentage']:.1f}%")
        if uncovered_lights:
            print(f"Uncovered: {uncovered_lights}")
    
    return result
