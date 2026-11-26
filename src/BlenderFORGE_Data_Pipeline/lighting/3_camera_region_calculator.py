#!/usr/bin/env python3
"""
Camera Region Calculator - Module 3
Infinigen Lighting Dataset Generation Pipeline

Purpose:
- Compute valid camera placement regions for observing light objects
- Ensure cameras can directly SEE the light objects themselves
- Apply boundary constraints with safety margins
- Handle different light types (POINT, SUN, SPOT, AREA)

Adapted from: placement/generation/3_camera_region_calculator.py

Key Differences from Placement Pipeline:
- Target: LIGHT objects (not moved meshes)
- Goal: Cameras must see the LIGHT object itself (not just illuminated areas)
- Strategy: Spherical sampling around light position
- Exception: SUN lights (infinite distance) - cameras observe scene instead

Called by 6_generate.py inside Blender.
"""

import math
import random
from typing import List, Tuple, Dict, Optional


class CameraRegionCalculator:
    """
    Camera Region Calculator for Lighting Dataset Generation
    
    Computes valid camera placement regions for observing light objects.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize calculator with configuration
        
        Args:
            config: Configuration dict with:
                - min_distance_ratio: Min camera distance as ratio of scene diagonal
                - max_distance_ratio: Max camera distance as ratio of scene diagonal
                - camera_height_ratio_range: [min, max] height ratios
                - boundary_margin: Safety margin from boundaries
                - fov: Camera field of view
        """
        self.config = config or {}
        self.min_distance_ratio = self.config.get('min_distance_ratio', 0.1)
        self.max_distance_ratio = self.config.get('max_distance_ratio', 0.4)
        self.camera_height_ratio_range = self.config.get('camera_height_ratio_range', [0.2, 0.8])
        self.boundary_margin = self.config.get('boundary_margin', 0.3)
        self.fov = self.config.get('fov', 70.0)
    
    def compute_valid_regions_for_lights(
        self,
        light_objects: List[Dict],
        scene_bounds: Dict
    ) -> List[Dict]:
        """
        Compute valid camera regions for all lights
        
        Args:
            light_objects: List of light objects from LightAnalyzer
            scene_bounds: Scene boundaries from LightAnalyzer
            
        Returns:
            List of valid regions for camera placement
        """
        camera_config = {
            'min_distance_ratio': self.min_distance_ratio,
            'max_distance_ratio': self.max_distance_ratio,
            'camera_height_ratio_range': self.camera_height_ratio_range,
            'fov': self.fov
        }
        
        return compute_valid_regions_for_lights(
            light_objects=light_objects,
            scene_bounds=scene_bounds,
            camera_config=camera_config,
            margin=self.boundary_margin
        )



def compute_distance_range_for_light(
    light_type: str,
    light_energy: float,
    scene_bounds: Dict,
    camera_config: Dict
) -> Tuple[float, float]:
    """
    Calculate valid camera distance range for observing a light object.
    
    **NEW**: Uses ratio-based distances relative to scene diagonal.
    
    Strategy:
    1. Compute scene diagonal length: sqrt(dx^2 + dy^2 + dz^2)
    2. min_dist = diagonal * min_distance_ratio
    3. max_dist = diagonal * max_distance_ratio
    
    This makes camera distances scale automatically with scene size!
    
    Args:
        light_type: 'POINT', 'SUN', 'SPOT', 'AREA'
        light_energy: Current light energy value
        scene_bounds: Scene boundary dict with 'min', 'max', 'size'
        camera_config: Camera configuration dict with:
            - min_distance_ratio: float (default 0.05 = 5% of diagonal)
            - max_distance_ratio: float (default 0.3 = 30% of diagonal)
            - use_absolute_distances: bool (default False)
            - min_distance_from_light: float (fallback if use_absolute_distances=True)
            - max_distance_from_light: float (fallback if use_absolute_distances=True)
    
    Returns:
        (min_dist, max_dist): Distance range in meters
    
    Example:
        Scene diagonal = 20m
        min_ratio = 0.05 → min_dist = 1.0m
        max_ratio = 0.3  → max_dist = 6.0m
    """
    if camera_config.get('use_absolute_distances', False):
        min_dist = camera_config.get('min_distance_from_light', 2.0)
        max_dist = camera_config.get('max_distance_from_light', 10.0)
    else:
        size = scene_bounds.get('size', (10.0, 10.0, 3.0))
        diagonal = math.sqrt(size[0]**2 + size[1]**2 + size[2]**2)
        
        min_ratio = camera_config.get('min_distance_ratio', 0.05)
        max_ratio = camera_config.get('max_distance_ratio', 0.3)
        
        min_dist = diagonal * min_ratio
        max_dist = diagonal * max_ratio
    
    if light_type == 'SUN':
        # SUN lights are directional and infinite
        # Cameras observe the scene, not the light
        return (0.0, float('inf'))
    
    elif light_type == 'AREA':
        # Area lights may need slightly larger min distance to see full shape
        min_dist = max(min_dist, min_dist * 1.5)
    
    min_dist = max(min_dist, 0.3)   # At least 0.3 meter away
    max_dist = min(max_dist, 50.0)  # At most 50 meters away (for large scenes)
    
    if min_dist >= max_dist:
        max_dist = min_dist * 3.0
    
    return (min_dist, max_dist)


def compute_valid_angles_for_light(
    light_position: List[float],
    light_type: str,
    min_dist: float,
    max_dist: float,
    scene_bounds: Dict,
    margin: float = 0.5,
    angular_resolution: int = 72
) -> List[Tuple[float, float]]:
    """
    Compute valid horizontal angles from which the light can be observed.
    
    Strategy (adapted from placement pipeline):
    1. Sample camera positions at different angles around the light
    2. Check if camera position is within scene bounds WITH MARGIN
    3. Merge consecutive valid angles into ranges
    4. If no valid angles found, progressively relax constraints
    
    Args:
        light_position: Light center [x, y, z]
        light_type: 'POINT', 'SUN', 'SPOT', 'AREA'
        min_dist: Minimum observation distance
        max_dist: Maximum observation distance
        scene_bounds: Scene boundary info with margin applied:
            {
                'x_min': float,
                'x_max': float,
                'y_min': float,
                'y_max': float,
                'z_floor': float,
                'z_ceiling': float,
                'margin': float
            }
        margin: Safety margin from boundaries (default 0.5m)
        angular_resolution: Number of angle samples (default 72 = every 5°)
    
    Returns:
        List of (theta_start, theta_end) tuples in radians
        Example: [(0, 1.57), (3.14, 6.28)]  # Two valid angle ranges
    """
    if light_type == 'SUN':
        # SUN lights: cameras can be anywhere in the scene
        return [(0.0, 2.0 * math.pi)]
    
    light_x, light_y, light_z = light_position
    
    # Try with different margin levels (fallback mechanism)
    margin_levels = [margin, margin * 0.5, margin * 0.25, 0.1, 0.0]
    
    for current_margin in margin_levels:
        x_min = scene_bounds['x_min'] + current_margin
        x_max = scene_bounds['x_max'] - current_margin
        y_min = scene_bounds['y_min'] + current_margin
        y_max = scene_bounds['y_max'] - current_margin
        
        valid_angles = []
        
        for i in range(angular_resolution):
            theta = (2.0 * math.pi * i) / angular_resolution
            
            # For this angle, check if ANY distance in [min_dist, max_dist] puts camera in bounds
            # Test at min, mid, and max distances
            is_valid = False
            
            for test_dist in [min_dist, (min_dist + max_dist) / 2.0, max_dist]:
                cam_x = light_x + test_dist * math.cos(theta)
                cam_y = light_y + test_dist * math.sin(theta)
                
                if x_min <= cam_x <= x_max and y_min <= cam_y <= y_max:
                    is_valid = True
                    break
            
            if is_valid:
                valid_angles.append(theta)
        
        if valid_angles:
            angle_ranges = merge_angle_ranges(valid_angles, gap_threshold=math.radians(10))
            if angle_ranges:
                return angle_ranges
    
    return []


def merge_angle_ranges(
    angles: List[float],
    gap_threshold: float = 0.174  # ~10 degrees
) -> List[Tuple[float, float]]:
    """
    Merge consecutive discrete angles into continuous ranges.
    
    (Copied from placement pipeline - no changes needed)
    
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


def compute_valid_region_for_light(
    light_obj: Dict,
    scene_bounds: Dict,
    camera_config: Dict,
    margin: float = 0.5
) -> Dict:
    """
    Compute the valid camera observation region for a single light object.
    
    This is the main function for Module 3, adapted from placement pipeline.
    
    Args:
        light_obj: Light object dict from LightAnalyzer:
            {
                'name': str,
                'type': str,              # 'POINT', 'SUN', 'SPOT', 'AREA'
                'location': tuple,        # (x, y, z)
                'energy': float,
                'color': tuple,
                'is_visible': bool
            }
        scene_bounds: Scene boundary info (from LightAnalyzer):
            {
                'min': tuple,  # (x_min, y_min, z_min)
                'max': tuple,  # (x_max, y_max, z_max)
                'center': tuple,
                'size': tuple
            }
        camera_config: Camera configuration dict:
            {
                'fov': 70.0,
                'min_distance_from_light': 2.0,
                'max_distance_from_light': 10.0,
                'camera_height_range': [1.0, 3.0],
                'min_camera_separation': 0.5
            }
        margin: Safety margin from boundaries (default 0.5m)
    
    Returns:
        {
            'light_name': str,
            'light_position': tuple,      # (x, y, z)
            'light_type': str,
            'is_visible': bool,           # Can camera see the light?
            'min_dist': float,            # Minimum observation distance
            'max_dist': float,            # Maximum observation distance
            'valid_angles': [(theta_start, theta_end), ...],  # Radians
            'min_height': float,          # Minimum camera Z coordinate
            'max_height': float,          # Maximum camera Z coordinate
            'target_position': tuple,     # Where camera should look at
            'valid_region_volume': float  # Approximate volume (cubic meters)
        }
    """
    light_name = light_obj['name']
    light_type = light_obj['type']
    light_position = list(light_obj['location'])
    is_visible = light_obj['is_visible']
    energy = light_obj['energy']
    
    min_dist, max_dist = compute_distance_range_for_light(
        light_type,
        energy,
        scene_bounds,
        camera_config
    )
    
    # Convert scene_bounds format to match placement pipeline
    bounds_formatted = {
        'x_min': scene_bounds['min'][0],
        'x_max': scene_bounds['max'][0],
        'y_min': scene_bounds['min'][1],
        'y_max': scene_bounds['max'][1],
        'z_floor': scene_bounds['min'][2],
        'z_ceiling': scene_bounds['max'][2],
        'margin': margin
    }
    
    valid_angles = compute_valid_angles_for_light(
        light_position,
        light_type,
        min_dist,
        max_dist,
        bounds_formatted,
        margin=margin
    )
    
    if camera_config.get('use_absolute_distances', False):
        camera_height_range = camera_config.get('camera_height_range', [1.0, 3.0])
        min_height_cfg = camera_height_range[0]
        max_height_cfg = camera_height_range[1]
    else:
        z_floor = bounds_formatted['z_floor']
        z_ceiling = bounds_formatted['z_ceiling']
        z_range = z_ceiling - z_floor
        
        height_ratio_range = camera_config.get('camera_height_ratio_range', [0.1, 0.9])
        min_height_cfg = z_floor + z_range * height_ratio_range[0]
        max_height_cfg = z_floor + z_range * height_ratio_range[1]
    
    z_floor_margin = bounds_formatted['z_floor'] + margin
    z_ceiling_margin = bounds_formatted['z_ceiling'] - margin
    
    min_height = max(min_height_cfg, z_floor_margin)
    max_height = min(max_height_cfg, z_ceiling_margin)
    
    # For visible lights, use light position as target
    # For SUN lights, use scene center as target
    if light_type == 'SUN':
        target_position = tuple(scene_bounds['center'])
    else:
        target_position = tuple(light_position)
    
    if not valid_angles or light_type == 'SUN':
        scene_size = scene_bounds['size']
        volume = scene_size[0] * scene_size[1] * scene_size[2]
    else:
        # Approximate volume as sum of cylindrical sectors
        total_angle_span = sum(end - start for start, end in valid_angles)
        avg_radius = (min_dist + max_dist) / 2.0
        height_span = max_height - min_height
        
        # Volume ≈ (angle_fraction) * π * r² * h
        angle_fraction = total_angle_span / (2.0 * math.pi)
        volume = angle_fraction * math.pi * (avg_radius ** 2) * height_span
    
    return {
        'light_name': light_name,
        'light_position': tuple(light_position),
        'light_type': light_type,
        'is_visible': is_visible,
        'min_dist': min_dist,
        'max_dist': max_dist,
        'valid_angles': valid_angles,
        'min_height': min_height,
        'max_height': max_height,
        'target_position': target_position,
        'valid_region_volume': volume
    }


def compute_valid_regions_for_lights(
    light_objects: List[Dict],
    scene_bounds: Dict,
    camera_config: Dict,
    margin: float = 0.5
) -> List[Dict]:
    """
    Compute valid camera regions for all light objects.
    
    This is the main entry point for Module 3.
    
    Args:
        light_objects: List of light objects from LightAnalyzer
        scene_bounds: Scene boundaries from LightAnalyzer
        camera_config: Camera configuration dict
        margin: Safety margin from boundaries (default 0.5m)
    
    Returns:
        List of valid region dicts (one per light)
    
    Example:
        >>> regions = compute_valid_regions_for_lights(
        ...     light_objects=analyzer.light_objects,
        ...     scene_bounds=analyzer.scene_bounds,
        ...     camera_config={'fov': 70.0, 'min_distance_from_light': 2.0, 'max_distance_from_light': 10.0},
        ...     margin=0.5
        ... )
        >>> print(f"Computed {len(regions)} valid regions")
    """
    regions = []
    
    for light_obj in light_objects:
        region = compute_valid_region_for_light(
            light_obj,
            scene_bounds,
            camera_config,
            margin
        )
        regions.append(region)
    
    print(f"✓ Computed valid regions for {len(regions)} light objects")
    
    for i, region in enumerate(regions):
        light_name = region['light_name']
        light_type = region['light_type']
        num_angle_ranges = len(region['valid_angles'])
        volume = region['valid_region_volume']
        
        print(f"  [{i}] {light_name} ({light_type}): {num_angle_ranges} angle ranges, volume={volume:.2f}m³")
    
    return regions


def apply_boundary_constraints_with_margin(
    position: Tuple[float, float, float],
    scene_bounds: Dict,
    margin: float
) -> bool:
    """
    Check if camera position is within scene bounds with safety margin.
    
    (Adapted from placement pipeline)
    
    Constraints:
        x_min + margin <= x <= x_max - margin
        y_min + margin <= y <= y_max - margin
        z_floor + margin <= z <= z_ceiling - margin
    
    Args:
        position: Camera position (x, y, z)
        scene_bounds: Scene boundary dict:
            {
                'min': (x_min, y_min, z_min),
                'max': (x_max, y_max, z_max)
            }
        margin: Safety margin in meters
    
    Returns:
        bool: True if within bounds, False otherwise
    
    Example:
        >>> is_valid = apply_boundary_constraints_with_margin(
        ...     (5.0, 3.0, 1.5),
        ...     {'min': (0, 0, 0), 'max': (10, 10, 3)},
        ...     0.5
        ... )
        >>> print(is_valid)  # True
    """
    x, y, z = position
    
    x_min = scene_bounds['min'][0] + margin
    x_max = scene_bounds['max'][0] - margin
    y_min = scene_bounds['min'][1] + margin
    y_max = scene_bounds['max'][1] - margin
    z_min = scene_bounds['min'][2] + margin
    z_max = scene_bounds['max'][2] - margin
    
    if x < x_min or x > x_max:
        return False
    if y < y_min or y > y_max:
        return False
    if z < z_min or z > z_max:
        return False
    
    return True


def sample_camera_position_from_region(
    region: Dict,
    scene_bounds: Dict,
    margin: float = 0.5,
    max_attempts: int = 50
) -> Optional[Tuple[float, float, float]]:
    """
    Sample a random valid camera position from a light's observation region.
    
    Strategy:
    1. Randomly select angle range
    2. Randomly select angle within range
    3. Randomly select distance in [min_dist, max_dist]
    4. Randomly select height in [min_height, max_height]
    5. Check boundary constraints with margin
    
    Args:
        region: Valid region dict from compute_valid_region_for_light()
        scene_bounds: Scene boundaries
        margin: Safety margin
        max_attempts: Maximum sampling attempts (default 50)
    
    Returns:
        (x, y, z) camera position or None if failed
    
    Example:
        >>> pos = sample_camera_position_from_region(region, scene_bounds, margin=0.5)
        >>> if pos:
        ...     print(f"Sampled position: {pos}")
    """
    if not region['valid_angles']:
        # No valid angles (e.g., light is outside scene or too constrained)
        return None
    
    light_x, light_y, light_z = region['light_position']
    min_dist = region['min_dist']
    max_dist = region['max_dist']
    min_height = region['min_height']
    max_height = region['max_height']
    valid_angles = region['valid_angles']
    
    for _ in range(max_attempts):
        angle_range = random.choice(valid_angles)
        theta_start, theta_end = angle_range
        
        theta = random.uniform(theta_start, theta_end)
        
        dist = random.uniform(min_dist, max_dist)
        
        height = random.uniform(min_height, max_height)
        
        cam_x = light_x + dist * math.cos(theta)
        cam_y = light_y + dist * math.sin(theta)
        cam_z = height
        
        position = (cam_x, cam_y, cam_z)
        
        if apply_boundary_constraints_with_margin(position, scene_bounds, margin):
            return position
    
    return None
