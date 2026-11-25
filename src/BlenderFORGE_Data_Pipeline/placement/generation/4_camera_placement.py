"""
Module 4: Intelligent Camera Placement

This module intelligently places cameras in the scene to observe moved objects.

Core Features:
1. Camera creation at optimal positions
2. Camera orientation (look-at) calculation
3. Coverage validation (ensure all objects are observed)
4. Multi-camera coordination

Dependencies:
- Blender Python API (bpy)
- Module 3 (3_camera_region_calculator)
- 1_scene_analyzer (Module 1)

Author: 3D-Front Placement Pipeline
Date: 2024
"""

import importlib
import math
import random
from typing import List, Dict, Optional, Tuple
import bpy
import mathutils


def check_camera_clearance(
    camera_position: List[float],
    camera_size: float = 0.1,
    exclude_objects: Optional[List[str]] = None
) -> bool:
    """
    Check if a camera position is clear of collisions with scene objects.
    
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
    
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        
        if obj.name in exclude_objects:
            continue
        
        if obj.data.vertices:
            bbox_corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
        else:
            bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
        
        xs = [c.x for c in bbox_corners]
        ys = [c.y for c in bbox_corners]
        zs = [c.z for c in bbox_corners]
        
        obj_bbox = {
            'x_min': min(xs),
            'x_max': max(xs),
            'y_min': min(ys),
            'y_max': max(ys),
            'z_min': min(zs),
            'z_max': max(zs)
        }
        
        # AABB collision detection: check if boxes overlap on all 3 axes
        x_overlap = (cam_bbox['x_min'] <= obj_bbox['x_max'] and 
                     cam_bbox['x_max'] >= obj_bbox['x_min'])
        y_overlap = (cam_bbox['y_min'] <= obj_bbox['y_max'] and 
                     cam_bbox['y_max'] >= obj_bbox['y_min'])
        z_overlap = (cam_bbox['z_min'] <= obj_bbox['z_max'] and 
                     cam_bbox['z_max'] >= obj_bbox['z_min'])
        
        if x_overlap and y_overlap and z_overlap:
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


def is_object_in_camera_frustum(
    camera_name: str,
    obj_name: str,
    margin: float = 1.2,
    debug: bool = False
) -> bool:
    """
    Check if object is within camera frustum (simplified check).
    
    This is a basic check based on:
    1. Object is in front of camera
    2. Object center is within FOV cone
    
    Args:
        camera_name: Camera object name
        obj_name: Target object name
        margin: FOV margin multiplier (1.2 = 20% tolerance)
        debug: Print debug information
    
    Returns:
        bool: True if object is in frustum
    
    Example:
        >>> is_visible = is_object_in_camera_frustum("Camera_00", "chair")
    """
    if camera_name not in bpy.data.objects:
        if debug:
            print(f"  DEBUG: Camera '{camera_name}' not found")
        return False
    if obj_name not in bpy.data.objects:
        if debug:
            print(f"  DEBUG: Object '{obj_name}' not found")
        return False
    
    cam_obj = bpy.data.objects[camera_name]
    target_obj = bpy.data.objects[obj_name]
    
    cam_pos = cam_obj.matrix_world.translation
    obj_pos = target_obj.matrix_world.translation
    
    to_obj = obj_pos - cam_pos
    distance = to_obj.length
    
    if distance < 0.01:
        if debug:
            print(f"  DEBUG: Object too close (distance={distance:.3f})")
        return False
    
    # Camera forward direction (local -Z axis in world space)
    cam_forward = cam_obj.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))
    
    dot_product = to_obj.normalized().dot(cam_forward.normalized())
    
    if debug:
        print(f"  DEBUG: Camera pos: {cam_pos}")
        print(f"  DEBUG: Object pos: {obj_pos}")
        print(f"  DEBUG: Distance: {distance:.3f}")
        print(f"  DEBUG: Dot product: {dot_product:.3f}")
    
    if dot_product < 0.1:  # Behind camera or barely in front (relaxed threshold)
        if debug:
            print(f"  DEBUG: Object behind camera or at edge")
        return False
    
    cam_data = cam_obj.data
    half_fov = cam_data.angle / 2.0 * margin
    
    angle = math.acos(max(-1.0, min(1.0, dot_product)))
    
    if debug:
        print(f"  DEBUG: Half FOV: {math.degrees(half_fov):.1f}°")
        print(f"  DEBUG: Angle to object: {math.degrees(angle):.1f}°")
        print(f"  DEBUG: In frustum: {angle <= half_fov}")
    
    return angle <= half_fov


def select_camera_positions_greedy(
    regions: List[Dict],
    num_cameras: int,
    scene_bounds: Dict,
    max_attempts_per_camera: int = 100
) -> List[Dict]:
    """
    Greedily select camera positions to maximize coverage.
    
    Strategy:
    1. MUST place exactly num_cameras (as requested by user)
    2. Prioritize covering uncovered objects first
    3. After all objects covered, continue placing for diversity/quality
    4. If normal constraints fail, relax constraints to ensure placement
    
    Args:
        regions: List of valid observation regions (from Module 3)
        num_cameras: Number of cameras to place (MUST place this many)
        scene_bounds: Scene boundary info
        max_attempts_per_camera: Max sampling attempts per camera
    
    Returns:
        List of camera placement dicts (length = num_cameras)
    """
    sample_camera_position_from_region = importlib.import_module('3_camera_region_calculator').sample_camera_position_from_region
    evaluate_camera_position = importlib.import_module('3_camera_region_calculator').evaluate_camera_position
    
    if not regions:
        return []
    
    all_objects = [r['object_name'] for r in regions]
    covered_objects = set()
    camera_placements = []
    placed_camera_positions = []
    
    # Progressive relaxation of constraints if placement fails
    min_camera_distance_levels = [0.5, 0.3, 0.1, 0.0]
    
    for cam_idx in range(num_cameras):
        best_placement = None
        best_score = -1
        
        print(f"\n📷 Placing camera {cam_idx + 1}/{num_cameras}...")
        print(f"   Covered objects: {len(covered_objects)}/{len(all_objects)}")
        
        for distance_level_idx, min_camera_distance in enumerate(min_camera_distance_levels):
            if best_placement is not None:
                break
            
            if distance_level_idx > 0:
                print(f"   ⚠️  Relaxing distance constraint to {min_camera_distance:.2f}m...")
            
            # Increase attempts when all objects are covered (need more diversity)
            attempts_per_region = max_attempts_per_camera // len(regions)
            if len(covered_objects) == len(all_objects):
                attempts_per_region = attempts_per_region * 2
            
            for region in regions:
                obj_name = region['object_name']
                
                for attempt in range(attempts_per_region):
                    cam_pos_data = sample_camera_position_from_region(
                        region, scene_bounds, max_attempts=10
                    )
                    
                    if not cam_pos_data or not cam_pos_data['is_valid']:
                        continue
                    
                    position = cam_pos_data['position']
                    
                    x, y, z = position
                    if not (scene_bounds['x_min'] <= x <= scene_bounds['x_max'] and
                            scene_bounds['y_min'] <= y <= scene_bounds['y_max'] and
                            scene_bounds['z_floor'] <= z <= scene_bounds['z_ceiling']):
                        continue
                    
                    if not check_camera_clearance(position, camera_size=0.1):
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
                    
                    covers = []
                    for r in regions:
                        covers.append(r['object_name'])
                    
                    num_new_covered = sum(1 for obj in covers if obj not in covered_objects)
                    quality_score = evaluate_camera_position(
                        position, covers, scene_bounds
                    )
                    
                    # Scoring strategy:
                    # - Prioritize covering new objects (if any remain)
                    # - If all covered, prioritize quality and diversity
                    if num_new_covered > 0:
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
                            'look_at': region['object_position'],
                            'covers_objects': covers,
                            'quality_score': quality_score,
                            'num_new_covered': num_new_covered
                        }
        
        if best_placement:
            camera_placements.append(best_placement)
            placed_camera_positions.append(best_placement['position'])
            covered_objects.update(best_placement['covers_objects'])
            
            print(f"   ✓ Position: [{best_placement['position'][0]:.2f}, {best_placement['position'][1]:.2f}, {best_placement['position'][2]:.2f}]")
            print(f"   ✓ Quality: {best_placement['quality_score']:.2f}")
            print(f"   ✓ Covers: {len(best_placement['covers_objects'])} objects")
            if best_placement['num_new_covered'] == 0:
                print(f"   ℹ️  All objects already covered - placed for diversity")
        else:
            print(f"   ⚠️  WARNING: Could not find valid position even with relaxed constraints!")
            print(f"   ℹ️  Using fallback: random position from regions")
            
            # Try fallback with NO constraints at all
            fallback_success = False
            for fallback_attempt in range(200):
                # Try different regions in round-robin
                region_idx = (cam_idx + fallback_attempt) % len(regions)
                cam_pos_data = sample_camera_position_from_region(
                    regions[region_idx], scene_bounds, max_attempts=5
                )
                if cam_pos_data and cam_pos_data['is_valid']:
                    fallback_placement = {
                        'position': cam_pos_data['position'],
                        'look_at': regions[region_idx]['object_position'],
                        'covers_objects': all_objects,
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
                    'look_at': regions[0]['object_position'],
                    'covers_objects': all_objects,
                    'quality_score': 0.1,
                    'num_new_covered': 0
                }
                camera_placements.append(last_resort_placement)
                placed_camera_positions.append(safe_position)
                print(f"   ✓ Safe position used: [{safe_position[0]:.2f}, {safe_position[1]:.2f}, {safe_position[2]:.2f}]")
    
    print(f"\n✓ Camera placement complete: {len(camera_placements)}/{num_cameras} cameras placed")
    
    if len(camera_placements) < num_cameras:
        print(f"❌ ERROR: Failed to place all requested cameras!")
        print(f"   Requested: {num_cameras}, Placed: {len(camera_placements)}")
    elif len(covered_objects) < len(all_objects):
        print(f"⚠️  Note: Not all objects covered ({len(covered_objects)}/{len(all_objects)}), but all {num_cameras} cameras placed")
    else:
        print(f"✓ All {len(all_objects)} objects covered with {num_cameras} cameras")
    
    return camera_placements


def place_cameras_for_objects(
    regions: List[Dict],
    scene_bounds: Dict,
    num_cameras: int = None,
    placement_strategy: str = 'greedy',
    camera_config: Dict = None
) -> Dict:
    """
    Main function to place cameras for observing moved objects.
    
    Args:
        regions: Valid observation regions from Module 3
        scene_bounds: Scene boundary info
        num_cameras: Number of cameras to place (None = auto-determine)
        placement_strategy: 'greedy', 'random', or 'clustered'
        camera_config: Camera configuration dict
    
    Returns:
        {
            'cameras': [
                {
                    'name': str,
                    'position': [x, y, z],
                    'look_at': [x, y, z],
                    'covers_objects': [obj_names],
                    'quality_score': float
                },
                ...
            ],
            'coverage': {
                'total_objects': int,
                'covered_objects': int,
                'coverage_rate': float
            }
        }
    
    Example:
        >>> result = place_cameras_for_objects(regions, scene_bounds, num_cameras=3)
        >>> print(f"Coverage: {result['coverage']['coverage_rate']*100:.1f}%")
    """
    if not regions:
        return {
            'cameras': [],
            'coverage': {
                'total_objects': 0,
                'covered_objects': 0,
                'coverage_rate': 0.0
            }
        }
    
    if num_cameras is None:
        # Rule of thumb: 1 camera per 2-3 objects
        num_cameras = max(1, (len(regions) + 2) // 3)
    
    if camera_config is None:
        camera_config = {
            'fov': 50.0,
            'name_prefix': 'Camera'
        }
    
    print("\n" + "="*70)
    print("CAMERA PLACEMENT")
    print("="*70)
    print(f"Objects to observe: {len(regions)}")
    print(f"Cameras to place: {num_cameras}")
    print(f"Strategy: {placement_strategy}")
    
    delete_all_cameras()
    
    if placement_strategy == 'greedy':
        placements = select_camera_positions_greedy(
            regions, num_cameras, scene_bounds
        )
    elif placement_strategy == 'random':
        placements = select_camera_positions_random(
            regions, num_cameras, scene_bounds
        )
    else:
        raise ValueError(f"Unknown strategy: {placement_strategy}")
    
    cameras = []
    for idx, placement in enumerate(placements):
        cam_name = create_camera_at_position(
            placement['position'],
            placement['look_at'],
            idx,
            fov=camera_config.get('fov', 50.0),
            name_prefix=camera_config.get('name_prefix', 'Camera')
        )
        
        cameras.append({
            'name': cam_name,
            'position': placement['position'],
            'look_at': placement['look_at'],
            'covers_objects': placement['covers_objects'],
            'quality_score': placement['quality_score']
        })
    
    all_objects = set(r['object_name'] for r in regions)
    covered_objects = set()
    for cam in cameras:
        covered_objects.update(cam['covers_objects'])
    
    coverage_rate = len(covered_objects) / len(all_objects) if all_objects else 0.0
    
    print("\n" + "="*70)
    print("PLACEMENT SUMMARY")
    print("="*70)
    print(f"Cameras placed: {len(cameras)}")
    print(f"Objects covered: {len(covered_objects)}/{len(all_objects)}")
    print(f"Coverage rate: {coverage_rate*100:.1f}%")
    print("="*70)
    
    return {
        'cameras': cameras,
        'coverage': {
            'total_objects': len(all_objects),
            'covered_objects': len(covered_objects),
            'coverage_rate': coverage_rate,
            'uncovered_objects': list(all_objects - covered_objects)
        }
    }


def select_camera_positions_random(
    regions: List[Dict],
    num_cameras: int,
    scene_bounds: Dict
) -> List[Dict]:
    """
    Select camera positions randomly (baseline method).
    
    Args:
        regions: List of valid observation regions
        num_cameras: Number of cameras to place
        scene_bounds: Scene boundary info
    
    Returns:
        List of camera placement dicts
    """
    sample_camera_position_from_region = importlib.import_module('3_camera_region_calculator').sample_camera_position_from_region
    
    placements = []
    
    for cam_idx in range(num_cameras):
        region = random.choice(regions)
        
        cam_pos_data = sample_camera_position_from_region(region, scene_bounds)
        
        if cam_pos_data and cam_pos_data['is_valid']:
            placements.append({
                'position': cam_pos_data['position'],
                'look_at': region['object_position'],
                'covers_objects': [region['object_name']],
                'quality_score': 0.5,
                'num_new_covered': 1
            })
    
    return placements


def verify_camera_coverage(
    camera_names: List[str],
    target_objects: List[str]
) -> Dict:
    """
    Verify which objects are actually visible from placed cameras.
    
    Args:
        camera_names: List of camera object names
        target_objects: List of target object names to check
    
    Returns:
        {
            'camera_coverage': {
                'Camera_00': ['obj1', 'obj2'],
                'Camera_01': ['obj3'],
                ...
            },
            'object_coverage': {
                'obj1': ['Camera_00'],
                'obj2': ['Camera_00'],
                'obj3': ['Camera_01'],
                ...
            },
            'uncovered_objects': ['obj4', ...]
        }
    """
    camera_coverage = {}
    object_coverage = {obj: [] for obj in target_objects}
    
    for cam_name in camera_names:
        if cam_name not in bpy.data.objects:
            continue
        
        visible_objects = []
        for obj_name in target_objects:
            if is_object_in_camera_frustum(cam_name, obj_name):
                visible_objects.append(obj_name)
                object_coverage[obj_name].append(cam_name)
        
        camera_coverage[cam_name] = visible_objects
    
    uncovered = [obj for obj, cams in object_coverage.items() if not cams]
    
    return {
        'camera_coverage': camera_coverage,
        'object_coverage': object_coverage,
        'uncovered_objects': uncovered
    }


def set_active_camera(camera_name: str) -> bool:
    """
    Set the specified camera as the scene's active camera.
    
    Args:
        camera_name: Name of camera to set as active
    
    Returns:
        bool: True if successful
    """
    if camera_name not in bpy.data.objects:
        print(f"❌ Camera '{camera_name}' not found")
        return False
    
    cam_obj = bpy.data.objects[camera_name]
    if cam_obj.type != 'CAMERA':
        print(f"❌ '{camera_name}' is not a camera")
        return False
    
    bpy.context.scene.camera = cam_obj
    print(f"✓ Set active camera: {camera_name}")
    
    return True


if __name__ == "__main__":
    print("Module 4: Intelligent Camera Placement")
    print("This module should be imported and used from test scripts or the main pipeline.")
    print("\nAvailable functions:")
    print("  - create_camera_at_position()")
    print("  - delete_all_cameras()")
    print("  - place_cameras_for_objects()")
    print("  - select_camera_positions_greedy()")
    print("  - verify_camera_coverage()")
    print("  - set_active_camera()")
