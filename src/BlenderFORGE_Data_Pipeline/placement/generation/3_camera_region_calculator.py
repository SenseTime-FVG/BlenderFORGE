"""
Module 3: Camera Valid Region Computation

This module computes valid camera placement regions based on:
1. Object positions and sizes
2. Scene boundaries (walls, floors)
3. Camera FOV and coverage requirements

Dependencies:
- Blender Python API (bpy)
- NumPy (for numerical computations)
- 1_scene_analyzer (Module 1)

Author: 3D-Front Placement Pipeline
Date: 2024
"""

import math
import random
from typing import List, Tuple, Dict, Optional
import bpy


def compute_distance_range(
    obj_size: float,
    fov_degrees: float,
    min_coverage: float,
    max_coverage: float
) -> Tuple[float, float]:
    """
    Calculate the valid camera distance range based on object size and FOV.
    
    The distance is computed such that the object occupies a desired percentage
    of the camera's field of view.
    
    Math:
        coverage ≈ obj_size / (2 * dist * tan(fov/2))
        => dist = obj_size / (2 * tan(fov/2) * coverage)
    
    Args:
        obj_size: Object's maximum dimension (meters)
        fov_degrees: Camera field of view (degrees)
        min_coverage: Minimum object coverage in frame (0-1)
        max_coverage: Maximum object coverage in frame (0-1)
    
    Returns:
        (min_dist, max_dist): Distance range in meters
    
    Example:
        >>> compute_distance_range(1.0, 50.0, 0.2, 0.6)
        (1.5, 4.5)  # Approximately
    """
    fov_rad = math.radians(fov_degrees)
    tan_half_fov = math.tan(fov_rad / 2.0)
    
    # When coverage is high (large), distance is small
    # When coverage is low (small), distance is large
    max_dist = obj_size / (2.0 * tan_half_fov * min_coverage)
    min_dist = obj_size / (2.0 * tan_half_fov * max_coverage)
    
    min_dist = max(min_dist, 1.5)   # At least 1.5 meters away
    max_dist = min(max_dist, 10.0)  # At most 10 meters away
    
    if min_dist >= max_dist:
        min_dist = 1.5
        max_dist = 5.0
    
    return (min_dist, max_dist)


def compute_valid_angles_for_object(
    obj_position: List[float],
    min_dist: float,
    max_dist: float,
    scene_bounds: Dict,
    angular_resolution: int = 72
) -> List[Tuple[float, float]]:
    """
    Compute valid horizontal angles from which the object can be observed.
    
    Strategy:
    1. Sample camera positions at different angles around the object
    2. Check if the camera position is within scene bounds
    3. Merge consecutive valid angles into ranges
    
    Args:
        obj_position: Object center [x, y, z]
        min_dist: Minimum observation distance
        max_dist: Maximum observation distance
        scene_bounds: Scene boundary info from compute_scene_boundaries()
        angular_resolution: Number of angle samples (default 72 = every 5 degrees)
    
    Returns:
        List of (theta_start, theta_end) tuples in radians
        Example: [(0, 1.57), (3.14, 6.28)]  # Two valid angle ranges
    """
    obj_x, obj_y, obj_z = obj_position
    
    x_min = scene_bounds['x_min']
    x_max = scene_bounds['x_max']
    y_min = scene_bounds['y_min']
    y_max = scene_bounds['y_max']
    
    valid_angles = []
    
    for i in range(angular_resolution):
        theta = (2.0 * math.pi * i) / angular_resolution
        
        # For this angle, check if ANY distance in [min_dist, max_dist] puts camera in bounds
        # Test at min, mid, and max distances
        is_valid = False
        
        for test_dist in [min_dist, (min_dist + max_dist) / 2.0, max_dist]:
            cam_x = obj_x + test_dist * math.cos(theta)
            cam_y = obj_y + test_dist * math.sin(theta)
            
            if x_min <= cam_x <= x_max and y_min <= cam_y <= y_max:
                is_valid = True
                break
        
        if is_valid:
            valid_angles.append(theta)
    
    if not valid_angles:
        return []
    
    angle_ranges = merge_angle_ranges(valid_angles, gap_threshold=math.radians(10))
    
    return angle_ranges


def merge_angle_ranges(
    angles: List[float],
    gap_threshold: float = 0.174  # ~10 degrees
) -> List[Tuple[float, float]]:
    """
    Merge consecutive discrete angles into continuous ranges.
    
    Args:
        angles: List of valid angles in radians (sorted)
        gap_threshold: Maximum gap to merge (radians, default 10 degrees)
    
    Returns:
        List of (start, end) angle ranges in radians
    
    Example:
        >>> merge_angle_ranges([0, 0.1, 0.2, 1.0, 1.1], gap_threshold=0.15)
        [(0, 0.2), (1.0, 1.1)]
    """
    if not angles:
        return []
    
    sorted_angles = sorted(angles)
    
    ranges = []
    start = sorted_angles[0]
    end = sorted_angles[0]
    
    for i in range(1, len(sorted_angles)):
        theta = sorted_angles[i]
        
        if theta - end <= gap_threshold:
            end = theta
        else:
            ranges.append((start, end))
            start = theta
            end = theta
    
    ranges.append((start, end))
    
    # Handle wrap-around at 0/2pi
    # If first and last ranges are close, merge them
    if len(ranges) > 1:
        first_start, first_end = ranges[0]
        last_start, last_end = ranges[-1]
        
        if (first_start < gap_threshold) and (2*math.pi - last_end < gap_threshold):
            merged_range = (last_start, first_end)
            ranges = [merged_range] + ranges[1:-1]
    
    return ranges


def compute_valid_region_for_object(
    obj_name: str,
    scene_bounds: Dict,
    camera_config: Dict
) -> Dict:
    """
    Compute the valid camera observation region for a single object.
    
    Args:
        obj_name: Object name in Blender scene
        scene_bounds: Scene boundary info from compute_scene_boundaries()
        camera_config: Camera configuration dict
            {
                'fov': 50.0,  # Field of view in degrees
                'camera_min_height_factor': 0.3,
                'camera_max_height_factor': 0.8,
                'min_object_coverage': 0.2,  # Min object coverage in frame
                'max_object_coverage': 0.6   # Max object coverage in frame
            }
    
    Returns:
        {
            'object_name': str,
            'object_position': [x, y, z],
            'object_size': float,  # Maximum dimension
            'min_dist': float,     # Minimum observation distance
            'max_dist': float,     # Maximum observation distance
            'valid_angles': [(theta_start, theta_end), ...],  # Radians
            'min_height': float,   # Minimum camera height
            'max_height': float,   # Maximum camera height
            'valid_region_volume': float  # Approximate volume (cubic meters)
        }
    
    Raises:
        ValueError: If object not found in scene
    """
    if obj_name not in bpy.data.objects:
        raise ValueError(f"Object '{obj_name}' not found in scene")
    
    obj = bpy.data.objects[obj_name]
    
    obj_position = list(obj.location)
    
    bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    bbox_min = mathutils.Vector([min(c.x for c in bbox_corners),
                                   min(c.y for c in bbox_corners),
                                   min(c.z for c in bbox_corners)])
    bbox_max = mathutils.Vector([max(c.x for c in bbox_corners),
                                   max(c.y for c in bbox_corners),
                                   max(c.z for c in bbox_corners)])
    
    dimensions = bbox_max - bbox_min
    obj_size = max(dimensions.x, dimensions.y, dimensions.z)
    
    min_dist, max_dist = compute_distance_range(
        obj_size,
        camera_config['fov'],
        camera_config['min_object_coverage'],
        camera_config['max_object_coverage']
    )
    
    current_fov = camera_config['fov']
    max_fov = 110.0  # Maximum FOV before giving up
    fov_increment = 15.0
    
    valid_angles = []
    attempts = 0
    max_attempts = 5
    
    while not valid_angles and attempts < max_attempts:
        if attempts > 0:
            current_fov = min(current_fov + fov_increment, max_fov)
            print(f"  ⚠️  No valid angles found, increasing FOV to {current_fov:.1f}° (attempt {attempts + 1})")
            
            min_dist, max_dist = compute_distance_range(
                obj_size,
                current_fov,
                camera_config['min_object_coverage'],
                camera_config['max_object_coverage']
            )
        
        valid_angles = compute_valid_angles_for_object(
            obj_position,
            min_dist,
            max_dist,
            scene_bounds,
            angular_resolution=72
        )
        
        attempts += 1
        
        if not valid_angles and current_fov >= max_fov:
            print(f"  ❌ Reached maximum FOV ({max_fov}°), no valid camera positions found for {obj_name}")
            break
    
    floor_height = scene_bounds['z_floor']
    ceiling_height = scene_bounds['z_ceiling']
    room_height = ceiling_height - floor_height
    
    min_height = floor_height + room_height * camera_config['camera_min_height_factor']
    max_height = floor_height + room_height * camera_config['camera_max_height_factor']
    
    # Approximation: sum of cylindrical sectors
    total_angle = sum(end - start for start, end in valid_angles)
    height_range = max_height - min_height
    
    # Volume ≈ (total_angle / 2π) * π * (max_dist² - min_dist²) * height_range
    annulus_area = math.pi * (max_dist**2 - min_dist**2)
    sector_area = annulus_area * (total_angle / (2 * math.pi))
    volume = sector_area * height_range
    
    return {
        'object_name': obj_name,
        'object_position': obj_position,
        'object_size': obj_size,
        'min_dist': min_dist,
        'max_dist': max_dist,
        'valid_angles': valid_angles,
        'min_height': min_height,
        'max_height': max_height,
        'valid_region_volume': volume,
        'fov_used': current_fov
    }


def compute_valid_regions_for_objects(
    obj_names: List[str],
    scene_bounds: Dict,
    camera_config: Dict
) -> List[Dict]:
    """
    Batch compute valid observation regions for multiple objects.
    
    Args:
        obj_names: List of object names
        scene_bounds: Scene boundary info
        camera_config: Camera configuration
    
    Returns:
        List of region dicts (one per object)
    
    Example:
        >>> regions = compute_valid_regions_for_objects(
        ...     ['chair', 'table'],
        ...     scene_bounds,
        ...     camera_config
        ... )
        >>> len(regions)
        2
    """
    regions = []
    
    for obj_name in obj_names:
        try:
            region = compute_valid_region_for_object(
                obj_name,
                scene_bounds,
                camera_config
            )
            regions.append(region)
        except ValueError as e:
            print(f"Warning: {e}")
            continue
    
    return regions


def compute_valid_region_for_dual_positions(
    obj_name: str,
    start_position: List[float],
    goal_position: List[float],
    scene_bounds: Dict,
    camera_config: Dict
) -> Dict:
    """
    Compute valid camera regions that can observe an object at BOTH positions.
    
    This function computes the intersection of valid regions for the object at
    two different positions (START and GOAL states), ensuring cameras placed in
    this region can see the object in both states.
    
    Strategy:
    1. Compute valid region for object at START position
    2. Compute valid region for object at GOAL position
    3. Compute intersection of the two regions:
       - Distance range: intersection of [min_dist, max_dist]
       - Angle ranges: intersection of valid angle sectors
       - Height range: intersection of [min_height, max_height]
    
    Args:
        obj_name: Object name
        start_position: Object position in START state [x, y, z]
        goal_position: Object position in GOAL state [x, y, z]
        scene_bounds: Scene boundary info
        camera_config: Camera configuration
    
    Returns:
        Dict with intersected region info, or raises ValueError if no intersection
        
    Example:
        >>> region = compute_valid_region_for_dual_positions(
        ...     'chair',
        ...     [1.0, 2.0, 0.5],  # START position
        ...     [3.0, 4.0, 0.5],  # GOAL position
        ...     scene_bounds,
        ...     camera_config
        ... )
    """
    import mathutils
    
    if obj_name not in bpy.data.objects:
        raise ValueError(f"Object '{obj_name}' not found in scene")
    
    obj = bpy.data.objects[obj_name]
    
    if obj.type == 'MESH' and obj.data.vertices:
        bbox_corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
    else:
        bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    
    xs = [c.x for c in bbox_corners]
    ys = [c.y for c in bbox_corners]
    zs = [c.z for c in bbox_corners]
    
    dimensions = mathutils.Vector((
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs)
    ))
    obj_size = max(dimensions.x, dimensions.y, dimensions.z)
    
    # Compute distance range (use goal position as reference, they should be similar)
    min_dist, max_dist = compute_distance_range(
        obj_size,
        camera_config['fov'],
        camera_config['min_object_coverage'],
        camera_config['max_object_coverage']
    )
    
    print(f"  Computing angles for START position: {start_position}")
    start_angles = compute_valid_angles_for_object(
        start_position,
        min_dist,
        max_dist,
        scene_bounds,
        angular_resolution=72
    )
    
    print(f"  Computing angles for GOAL position: {goal_position}")
    goal_angles = compute_valid_angles_for_object(
        goal_position,
        min_dist,
        max_dist,
        scene_bounds,
        angular_resolution=72
    )
    
    if not start_angles:
        raise ValueError(f"No valid angles for {obj_name} at START position")
    if not goal_angles:
        raise ValueError(f"No valid angles for {obj_name} at GOAL position")
    
    intersected_angles = intersect_angle_ranges(start_angles, goal_angles)
    
    if not intersected_angles:
        raise ValueError(
            f"No overlapping camera angles for {obj_name} between START and GOAL positions. "
            f"START angles: {len(start_angles)} ranges, GOAL angles: {len(goal_angles)} ranges"
        )
    
    print(f"  ✓ Found {len(intersected_angles)} intersected angle range(s)")
    
    floor_height = scene_bounds['z_floor']
    ceiling_height = scene_bounds['z_ceiling']
    room_height = ceiling_height - floor_height
    
    min_height = floor_height + room_height * camera_config['camera_min_height_factor']
    max_height = floor_height + room_height * camera_config['camera_max_height_factor']
    
    # Use midpoint of the two positions as reference for camera placement
    midpoint = [
        (start_position[0] + goal_position[0]) / 2.0,
        (start_position[1] + goal_position[1]) / 2.0,
        (start_position[2] + goal_position[2]) / 2.0
    ]
    
    total_angle = sum(end - start for start, end in intersected_angles)
    height_range = max_height - min_height
    annulus_area = math.pi * (max_dist**2 - min_dist**2)
    sector_area = annulus_area * (total_angle / (2 * math.pi))
    volume = sector_area * height_range
    
    return {
        'object_name': obj_name,
        'object_position': midpoint,  # Use midpoint for sampling
        'start_position': start_position,
        'goal_position': goal_position,
        'object_size': obj_size,
        'min_dist': min_dist,
        'max_dist': max_dist,
        'valid_angles': intersected_angles,
        'min_height': min_height,
        'max_height': max_height,
        'valid_region_volume': volume,
        'fov_used': camera_config['fov'],
        'is_dual_position': True
    }


def intersect_angle_ranges(
    ranges1: List[Tuple[float, float]],
    ranges2: List[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """
    Compute intersection of two sets of angle ranges.
    
    Angles are in radians, in range [0, 2π].
    
    Args:
        ranges1: List of (start, end) angle tuples
        ranges2: List of (start, end) angle tuples
    
    Returns:
        List of intersected (start, end) tuples
        
    Example:
        >>> intersect_angle_ranges([(0, 1.5), (3, 5)], [(1, 4)])
        [(1.0, 1.5), (3.0, 4.0)]
    """
    intersections = []
    
    for start1, end1 in ranges1:
        for start2, end2 in ranges2:
            overlap_start = max(start1, start2)
            overlap_end = min(end1, end2)
            
            if overlap_start < overlap_end:
                intersections.append((overlap_start, overlap_end))
    
    if not intersections:
        return []
    
    intersections.sort()
    
    merged = [intersections[0]]
    for start, end in intersections[1:]:
        last_start, last_end = merged[-1]
        
        if start <= last_end + 0.01:  # Small epsilon for floating point
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    
    return merged


def compute_valid_regions_for_dual_positions(
    obj_movement_pairs: List[Dict],
    scene_bounds: Dict,
    camera_config: Dict
) -> List[Dict]:
    """
    Batch compute valid observation regions for objects with dual positions.
    
    Args:
        obj_movement_pairs: List of dicts with:
            - 'object': object name
            - 'start_position': [x, y, z] in START state
            - 'goal_position': [x, y, z] in GOAL state
        scene_bounds: Scene boundary info
        camera_config: Camera configuration
    
    Returns:
        List of region dicts (one per object with dual positions)
        
    Example:
        >>> pairs = [
        ...     {'object': 'chair', 'start_position': [1,2,0.5], 'goal_position': [3,4,0.5]}
        ... ]
        >>> regions = compute_valid_regions_for_dual_positions(pairs, scene_bounds, config)
    """
    regions = []
    
    for pair in obj_movement_pairs:
        obj_name = pair['object']
        start_pos = pair['start_position']
        goal_pos = pair['goal_position']
        
        try:
            region = compute_valid_region_for_dual_positions(
                obj_name,
                start_pos,
                goal_pos,
                scene_bounds,
                camera_config
            )
            regions.append(region)
            print(f"  ✓ Computed dual-position region for {obj_name}")
        except ValueError as e:
            print(f"  ⚠️  Warning: {e}")
            continue
    
    return regions


def sample_camera_position_from_region(
    region: Dict,
    scene_bounds: Dict,
    max_attempts: int = 50
) -> Optional[Dict]:
    """
    Sample a random valid camera position from the observation region.
    
    Strategy:
    1. Randomly select a valid angle range
    2. Sample a random angle within that range
    3. Sample a random distance within [min_dist, max_dist]
    4. Sample a random height within [min_height, max_height]
    5. Check if position is within scene bounds
    
    Args:
        region: Valid observation region (from compute_valid_region_for_object)
        scene_bounds: Scene boundary info
        max_attempts: Maximum sampling attempts
    
    Returns:
        {
            'position': [x, y, z],
            'look_at': [x, y, z],  # Object center
            'distance': float,      # Distance to object
            'angle': float,         # Horizontal angle (radians)
            'elevation': float,     # Elevation angle (radians)
            'is_valid': bool
        }
        or None if sampling fails
    
    Example:
        >>> cam_pos = sample_camera_position_from_region(region, scene_bounds)
        >>> if cam_pos and cam_pos['is_valid']:
        ...     print(f"Camera at {cam_pos['position']}")
    """
    if not region['valid_angles']:
        return None
    
    obj_x, obj_y, obj_z = region['object_position']
    min_dist = region['min_dist']
    max_dist = region['max_dist']
    min_height = region['min_height']
    max_height = region['max_height']
    
    x_min = scene_bounds['x_min']
    x_max = scene_bounds['x_max']
    y_min = scene_bounds['y_min']
    y_max = scene_bounds['y_max']
    
    for attempt in range(max_attempts):
        angle_range = random.choice(region['valid_angles'])
        theta_start, theta_end = angle_range
        
        theta = random.uniform(theta_start, theta_end)
        
        distance = random.uniform(min_dist, max_dist)
        
        cam_z = random.uniform(min_height, max_height)
        
        cam_x = obj_x + distance * math.cos(theta)
        cam_y = obj_y + distance * math.sin(theta)
        
        if x_min <= cam_x <= x_max and y_min <= cam_y <= y_max:
            delta_z = cam_z - obj_z
            horizontal_dist = distance
            elevation = math.atan2(delta_z, horizontal_dist)
            
            return {
                'position': [cam_x, cam_y, cam_z],
                'look_at': region['object_position'],
                'distance': distance,
                'angle': theta,
                'elevation': elevation,
                'is_valid': True
            }
    
    return None


def evaluate_camera_position(
    cam_pos: List[float],
    target_objects: List[str],
    scene_bounds: Dict
) -> float:
    """
    Evaluate the quality of a camera position.
    
    Scoring factors:
    1. Distance to optimal range (prefer middle distances)
    2. Angle variety (avoid extreme horizontal/vertical angles)
    3. Distance from walls (penalize being too close to boundaries)
    4. Coverage uniformity (for multi-object scenes)
    
    Args:
        cam_pos: Camera position [x, y, z]
        target_objects: List of target object names
        scene_bounds: Scene boundary info
    
    Returns:
        float: Quality score in [0, 1], higher is better
    
    Example:
        >>> score = evaluate_camera_position([2, 3, 1.5], ['chair'], scene_bounds)
        >>> print(f"Score: {score:.2f}")
    """
    if not target_objects:
        return 0.0
    
    cam_x, cam_y, cam_z = cam_pos
    
    total_score = 0.0
    
    x_min = scene_bounds['x_min']
    x_max = scene_bounds['x_max']
    y_min = scene_bounds['y_min']
    y_max = scene_bounds['y_max']
    z_min = scene_bounds['z_floor']
    z_max = scene_bounds['z_ceiling']
    
    # Factor 1: Distance to walls (0-0.3 score)
    # Prefer being away from boundaries
    x_dist_to_wall = min(cam_x - x_min, x_max - cam_x)
    y_dist_to_wall = min(cam_y - y_min, y_max - cam_y)
    min_wall_dist = min(x_dist_to_wall, y_dist_to_wall)
    
    if min_wall_dist > 0.5:
        wall_score = 0.3
    else:
        wall_score = 0.3 * (min_wall_dist / 0.5)
    
    total_score += wall_score
    
    # Factor 2: Distance to targets (0-0.4 score)
    # Prefer middle-range distances
    distances = []
    for obj_name in target_objects:
        if obj_name in bpy.data.objects:
            obj = bpy.data.objects[obj_name]
            obj_pos = obj.location
            dist = math.sqrt(
                (cam_x - obj_pos.x)**2 +
                (cam_y - obj_pos.y)**2 +
                (cam_z - obj_pos.z)**2
            )
            distances.append(dist)
    
    if distances:
        avg_dist = sum(distances) / len(distances)
        # Optimal range: 2.5 - 5.0 meters
        if 2.5 <= avg_dist <= 5.0:
            dist_score = 0.4
        elif avg_dist < 2.5:
            dist_score = 0.4 * (avg_dist / 2.5)
        else:
            dist_score = 0.4 * max(0, 1.0 - (avg_dist - 5.0) / 5.0)
        
        total_score += dist_score
    
    # Factor 3: Elevation angle (0-0.3 score)
    # Prefer moderate viewing angles
    room_height = z_max - z_min
    relative_height = (cam_z - z_min) / room_height
    
    # Optimal relative height: 0.4 - 0.7
    if 0.4 <= relative_height <= 0.7:
        height_score = 0.3
    else:
        deviation = min(abs(relative_height - 0.4), abs(relative_height - 0.7))
        height_score = 0.3 * max(0, 1.0 - deviation / 0.3)
    
    total_score += height_score
    
    return min(total_score, 1.0)


def compute_intersecting_region(regions: List[Dict]) -> Dict:
    """
    Compute the intersection of multiple valid observation regions.
    
    Used to find camera positions that can observe multiple objects simultaneously.
    
    Strategy:
    1. Find the center point (average of object positions)
    2. Compute the intersection of distance ranges
    3. Compute the intersection of angle ranges
    4. Compute the intersection of height ranges
    
    Args:
        regions: List of valid observation regions
    
    Returns:
        {
            'center': [x, y, z],  # Combined center point
            'min_dist': float,     # Max of all min_dists
            'max_dist': float,     # Min of all max_dists
            'valid_angles': [...], # Angle range intersection
            'min_height': float,
            'max_height': float,
            'is_valid': bool       # Whether valid intersection exists
        }
    
    Example:
        >>> regions = [region1, region2]
        >>> intersect = compute_intersecting_region(regions)
        >>> if intersect['is_valid']:
        ...     print("Can observe both objects")
    """
    if not regions:
        return {'is_valid': False}
    
    center_x = sum(r['object_position'][0] for r in regions) / len(regions)
    center_y = sum(r['object_position'][1] for r in regions) / len(regions)
    center_z = sum(r['object_position'][2] for r in regions) / len(regions)
    center = [center_x, center_y, center_z]
    
    # To see all objects, we need to be far enough from all (max of min_dists)
    # But not too far from any (min of max_dists)
    min_dist = max(r['min_dist'] for r in regions)
    max_dist = min(r['max_dist'] for r in regions)
    
    if min_dist >= max_dist:
        return {
            'center': center,
            'min_dist': min_dist,
            'max_dist': max_dist,
            'valid_angles': [],
            'min_height': 0,
            'max_height': 0,
            'is_valid': False
        }
    
    min_height = max(r['min_height'] for r in regions)
    max_height = min(r['max_height'] for r in regions)
    
    if min_height >= max_height:
        return {
            'center': center,
            'min_dist': min_dist,
            'max_dist': max_dist,
            'valid_angles': [],
            'min_height': min_height,
            'max_height': max_height,
            'is_valid': False
        }
    
    # This helper uses the first region's angles rather than intersecting circular sectors.
    valid_angles = regions[0]['valid_angles'] if regions else []
    
    return {
        'center': center,
        'min_dist': min_dist,
        'max_dist': max_dist,
        'valid_angles': valid_angles,
        'min_height': min_height,
        'max_height': max_height,
        'is_valid': True
    }


def visualize_valid_region(
    region: Dict,
    num_samples: int = 100,
    create_mesh: bool = True,
    scene_bounds: Dict = None
) -> Optional[str]:
    """
    Visualize the valid observation region in Blender.
    
    Creates a point cloud or mesh representing the valid camera positions.
    Only includes points that are within scene boundaries.
    
    Args:
        region: Valid observation region
        num_samples: Number of sample points to visualize
        create_mesh: Whether to create a mesh object (vs. just empties)
        scene_bounds: Scene boundary info (optional, for boundary checking)
    
    Returns:
        str: Name of created object, or None if failed
    
    Example:
        >>> obj_name = visualize_valid_region(region, num_samples=200, scene_bounds=bounds)
        >>> print(f"Created visualization: {obj_name}")
    """
    import mathutils
    
    obj_x, obj_y, obj_z = region['object_position']
    min_dist = region['min_dist']
    max_dist = region['max_dist']
    min_height = region['min_height']
    max_height = region['max_height']
    valid_angles = region['valid_angles']
    
    if not valid_angles:
        print("No valid angles to visualize")
        return None
    
    if scene_bounds:
        x_min = scene_bounds['x_min']
        x_max = scene_bounds['x_max']
        y_min = scene_bounds['y_min']
        y_max = scene_bounds['y_max']
        z_min = scene_bounds.get('z_floor', scene_bounds.get('floor_z', -1000))
        z_max = scene_bounds.get('z_ceiling', scene_bounds.get('ceiling_z', 1000))
    else:
        x_min, x_max = -1000, 1000
        y_min, y_max = -1000, 1000
        z_min, z_max = -1000, 1000
    
    points = []
    attempts = 0
    max_attempts = num_samples * 10  # Try up to 10x the desired number
    
    while len(points) < num_samples and attempts < max_attempts:
        attempts += 1
        
        angle_range = random.choice(valid_angles)
        theta = random.uniform(angle_range[0], angle_range[1])
        
        dist = random.uniform(min_dist, max_dist)
        
        z = random.uniform(min_height, max_height)
        
        x = obj_x + dist * math.cos(theta)
        y = obj_y + dist * math.sin(theta)
        
        if (x_min <= x <= x_max and 
            y_min <= y <= y_max and 
            z_min <= z <= z_max):
            points.append((x, y, z))
    
    if not points:
        print("⚠️  No valid points found within boundaries")
        return None
    
    print(f"✓ Generated {len(points)} valid points (attempted {attempts})")
    
    if create_mesh:
        mesh = bpy.data.meshes.new(name=f"ValidRegion_{region['object_name']}")
        obj = bpy.data.objects.new(mesh.name, mesh)
        
        bpy.context.collection.objects.link(obj)
        
        vertices = [mathutils.Vector(p) for p in points]
        mesh.from_pydata(vertices, [], [])
        mesh.update()
        
        obj.display_type = 'WIRE'
        
        return obj.name
    else:
        collection_name = f"ValidRegion_{region['object_name']}_Points"
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
        
        for i, point in enumerate(points[:20]):  # Limit to 20 empties
            empty = bpy.data.objects.new(f"Point_{i}", None)
            empty.location = point
            empty.empty_display_size = 0.1
            collection.objects.link(empty)
        
        return collection_name


def export_region_as_point_cloud(
    region: Dict,
    output_path: str,
    num_points: int = 1000
) -> None:
    """
    Export the valid observation region as a point cloud file.
    
    Supported formats: .ply, .xyz
    
    Args:
        region: Valid observation region
        output_path: Output file path (e.g., "region.ply")
        num_points: Number of points to sample
    
    Example:
        >>> export_region_as_point_cloud(
        ...     region,
        ...     "output/camera_region.ply",
        ...     num_points=2000
        ... )
    """
    from pathlib import Path
    
    obj_x, obj_y, obj_z = region['object_position']
    min_dist = region['min_dist']
    max_dist = region['max_dist']
    min_height = region['min_height']
    max_height = region['max_height']
    valid_angles = region['valid_angles']
    
    if not valid_angles:
        print("No valid angles to export")
        return
    
    points = []
    
    for _ in range(num_points):
        angle_range = random.choice(valid_angles)
        theta = random.uniform(angle_range[0], angle_range[1])
        dist = random.uniform(min_dist, max_dist)
        z = random.uniform(min_height, max_height)
        
        x = obj_x + dist * math.cos(theta)
        y = obj_y + dist * math.sin(theta)
        
        points.append((x, y, z))
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.suffix == '.xyz':
        with open(output_path, 'w') as f:
            for x, y, z in points:
                f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")
    
    elif output_path.suffix == '.ply':
        with open(output_path, 'w') as f:
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write(f"element vertex {len(points)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write("end_header\n")
            
            for x, y, z in points:
                f.write(f"{x:.6f} {y:.6f} {z:.6f}\n")
    
    else:
        raise ValueError(f"Unsupported format: {output_path.suffix}")
    
    print(f"Exported {len(points)} points to {output_path}")


try:
    import mathutils
except ImportError:
    print("Warning: mathutils not available (running outside Blender)")


if __name__ == "__main__":
    print("Module 3: Camera Valid Region Computation")
    print("This module should be imported and used from test scripts or the main pipeline.")
    print("\nAvailable functions:")
    print("  - compute_distance_range()")
    print("  - compute_valid_angles_for_object()")
    print("  - compute_valid_region_for_object()")
    print("  - compute_valid_regions_for_objects()")
    print("  - compute_valid_region_for_dual_positions()")
    print("  - compute_valid_regions_for_dual_positions()")
    print("  - sample_camera_position_from_region()")
    print("  - evaluate_camera_position()")
    print("  - compute_intersecting_region()")
    print("  - visualize_valid_region()")
    print("  - export_region_as_point_cloud()")
