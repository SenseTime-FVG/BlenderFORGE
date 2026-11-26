#!/usr/bin/env python3
"""
Object Movement - Module 2
Object movement and collision detection.

Features:
- AABB collision detection
- Boundary checks
- Object movement
- Movement under constraints
- Object selection strategies

Usage:
    # Import as a module in Blender Python.
    from importlib import import_module
    ObjectMover = import_module("2_object_movement").ObjectMover
    
    mover = ObjectMover(scene_bounds, other_objects)
    result = mover.move_object_with_constraints(obj_name, config)
"""

import bpy
import math
import random
from mathutils import Vector, Euler
from typing import Dict, List, Tuple, Optional


class ObjectMover:
    """Manage object movement."""
    
    def __init__(self, scene_bounds: Optional[Dict] = None, 
                 structure_objects: Optional[List[str]] = None):
        """
        Initialize the object mover.
        
        Args:
            scene_bounds: Scene boundary information.
            structure_objects: Structural objects that must remain fixed.
        """
        self.scene_bounds = scene_bounds
        self.structure_objects = set(structure_objects or [])
        self.collision_margin = 0.05  # Collision margin of 5 cm.
        self.immovable_objects = set()  # Objects whose movement failed, used as feedback.
    
    def mark_as_immovable(self, obj_name: str) -> None:
        """
        Mark an object as immovable after a failed attempt.
        
        Args:
            obj_name: Object name.
        """
        self.immovable_objects.add(obj_name)
    
    def is_immovable(self, obj_name: str) -> bool:
        """
        Check whether an object is marked immovable.
        
        Args:
            obj_name: Object name.
            
        Returns:
            bool: True if the object is marked immovable.
        """
        return obj_name in self.immovable_objects or obj_name in self.structure_objects
    
    def get_immovable_objects(self) -> List[str]:
        """
        Return all objects marked immovable.
        
        Returns:
            list: Names of objects marked immovable.
        """
        return list(self.immovable_objects.union(self.structure_objects))
    
    def get_world_bbox(self, obj_name: str) -> Tuple[float, float, float, float, float, float]:
        """
        Return the object's world-space axis-aligned bounding box (AABB).
        
        Args:
            obj_name: Object name.
        
        Returns:
            (x_min, x_max, y_min, y_max, z_min, z_max)
        """
        if obj_name not in bpy.data.objects:
            raise ValueError(f"Object '{obj_name}' not found in scene")
        
        obj = bpy.data.objects[obj_name]
        
        if obj.type == 'MESH' and obj.data.vertices:
            bbox_corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
        else:
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        xs = [c.x for c in bbox_corners]
        ys = [c.y for c in bbox_corners]
        zs = [c.z for c in bbox_corners]
        
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    
    def check_collision(self, obj_name: str, other_obj_names: List[str], 
                       allow_minor_overlap: bool = True) -> bool:
        """
        Check for unacceptable collisions with other objects.
        
        Minor overlap is allowed, but reject:
        1. One object completely contained inside another.
        2. Excessive overlap, exceeding 30% of an object's dimension.
        
        Args:
            obj_name: Name of the object to check.
            other_obj_names: Names of the other objects.
            allow_minor_overlap: Whether to allow minor overlap (default: True).
            
        Returns:
            bool: True if an unacceptable collision is detected.
        """
        try:
            bbox1 = self.get_world_bbox(obj_name)
        except ValueError:
            return False
        
        x1_min, x1_max, y1_min, y1_max, z1_min, z1_max = bbox1
        
        width1 = x1_max - x1_min
        depth1 = y1_max - y1_min
        height1 = z1_max - z1_min
        
        for other_name in other_obj_names:
            if other_name == obj_name:
                continue
            
            try:
                bbox2 = self.get_world_bbox(other_name)
            except ValueError:
                continue
            
            x2_min, x2_max, y2_min, y2_max, z2_min, z2_max = bbox2
            
            width2 = x2_max - x2_min
            depth2 = y2_max - y2_min
            height2 = z2_max - z2_min
            
            has_overlap = (x1_max > x2_min and x1_min < x2_max and
                          y1_max > y2_min and y1_min < y2_max and
                          z1_max > z2_min and z1_min < z2_max)
            
            if not has_overlap:
                continue
            
            if not allow_minor_overlap:
                return True
            
            overlap_x = min(x1_max, x2_max) - max(x1_min, x2_min)
            overlap_y = min(y1_max, y2_max) - max(y1_min, y2_min)
            overlap_z = min(z1_max, z2_max) - max(z1_min, z2_min)
            
            # Check whether either object completely contains the other.
            if (x1_min >= x2_min and x1_max <= x2_max and
                y1_min >= y2_min and y1_max <= y2_max and
                z1_min >= z2_min and z1_max <= z2_max):
                return True
            
            if (x2_min >= x1_min and x2_max <= x1_max and
                y2_min >= y1_min and y2_max <= y1_max and
                z2_min >= z1_min and z2_max <= z1_max):
                return True
            
            # Overlap exceeding 30% of either object's dimension is excessive.
            overlap_ratio_1 = max(overlap_x / width1, overlap_y / depth1) if width1 > 0 and depth1 > 0 else 1.0
            overlap_ratio_2 = max(overlap_x / width2, overlap_y / depth2) if width2 > 0 and depth2 > 0 else 1.0
            
            if overlap_ratio_1 > 0.1 or overlap_ratio_2 > 0.1:
                return True
        
        return False
    
    def check_within_bounds(self, obj_name: str, bounds: Optional[Dict] = None) -> bool:
        """
        Check whether the object lies within the scene boundaries.
        
        Args:
            obj_name: Object name.
            bounds: Optional scene boundary information.
            
        Returns:
            bool: True if the object lies within the boundaries.
        """
        if bounds is None:
            bounds = self.scene_bounds
        
        if bounds is None:
            return True  # Accept by default when boundary information is unavailable.
        
        try:
            bbox = self.get_world_bbox(obj_name)
        except ValueError:
            return False
        
        x_min, x_max, y_min, y_max, z_min, z_max = bbox
        
        # Check that the entire object lies within the boundaries.
        return (x_min >= bounds['x_min'] and x_max <= bounds['x_max'] and
                y_min >= bounds['y_min'] and y_max <= bounds['y_max'] and
                z_min >= bounds['z_floor'] and z_max <= bounds['z_ceiling'])
    
    def move_object(self, obj_name: str, 
                    dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
                    dyaw: float = 0.0) -> bool:
        """
        Move an object to a new position.
        
        Args:
            obj_name: Object name.
            dx, dy, dz: Position offsets in meters.
            dyaw: Yaw offset in radians.
            
        Returns:
            bool: Whether the movement was applied successfully.
        """
        if obj_name not in bpy.data.objects:
            print(f"⚠ Object '{obj_name}' not found")
            return False
        
        obj = bpy.data.objects[obj_name]
        
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
        
        # Apply the rotation offset around the Z axis only (yaw).
        if dyaw != 0.0:
            obj.rotation_euler.z += dyaw
        
        bpy.context.view_layer.update()
        
        return True
    
    def restore_object_pose(self, obj_name: str, 
                           position: List[float], 
                           rotation: List[float]) -> bool:
        """
        Restore an object's position and rotation.
        
        Args:
            obj_name: Object name.
            position: [x, y, z]
            rotation: [rx, ry, rz], Euler angles in radians.
            
        Returns:
            bool: Whether restoration succeeded.
        """
        if obj_name not in bpy.data.objects:
            return False
        
        obj = bpy.data.objects[obj_name]
        
        obj.location = Vector(position)
        obj.rotation_euler = Euler(rotation, 'XYZ')
        
        bpy.context.view_layer.update()
        
        return True
    
    def get_random_offset(self, min_val: float, max_val: float) -> float:
        """
        Generate a random offset in either direction.
        
        Args:
            min_val: Minimum absolute offset.
            max_val: Maximum absolute offset.
        
        Returns:
            random value in [-max_val, -min_val] ∪ [min_val, max_val]
        """
        magnitude = random.uniform(min_val, max_val)
        direction = random.choice([-1, 1])
        return magnitude * direction
    
    def compute_valid_position_range(
        self,
        obj_name: str,
        scene_bounds: Dict
    ) -> Optional[Dict]:
        """
        Compute valid object positions from its AABB and the scene boundaries.
        
        Approach:
        To keep the object's AABB inside the boundaries, its center must satisfy:
        - cx ∈ [bounds_x_min + width/2, bounds_x_max - width/2]
        - cy ∈ [bounds_y_min + depth/2, bounds_y_max - depth/2]
        - cz ∈ [bounds_z_floor + height/2, bounds_z_ceiling - height/2]
        
        Args:
            obj_name: Object name.
            scene_bounds: Scene boundaries.
            
        Returns:
            {
                'cx_min': float, 'cx_max': float,
                'cy_min': float, 'cy_max': float,
                'cz_min': float, 'cz_max': float,
                'is_valid': bool  # Whether any valid position exists.
            }
            Or None if the object does not exist.
        """
        if obj_name not in bpy.data.objects:
            return None
        
        try:
            bbox = self.get_world_bbox(obj_name)
        except ValueError:
            return None
        
        x_min, x_max, y_min, y_max, z_min, z_max = bbox
        
        obj_width = x_max - x_min
        obj_depth = y_max - y_min
        obj_height = z_max - z_min
        
        # Compute the valid range for its center.
        cx_min = scene_bounds['x_min'] + obj_width / 2
        cx_max = scene_bounds['x_max'] - obj_width / 2
        cy_min = scene_bounds['y_min'] + obj_depth / 2
        cy_max = scene_bounds['y_max'] - obj_depth / 2
        cz_min = scene_bounds['z_floor'] + obj_height / 2
        cz_max = scene_bounds['z_ceiling'] - obj_height / 2
        
        is_valid = (cx_min < cx_max and cy_min < cy_max and cz_min < cz_max)
        
        return {
            'cx_min': cx_min,
            'cx_max': cx_max,
            'cy_min': cy_min,
            'cy_max': cy_max,
            'cz_min': cz_min,
            'cz_max': cz_max,
            'obj_width': obj_width,
            'obj_depth': obj_depth,
            'obj_height': obj_height,
            'is_valid': is_valid
        }
    
    def sample_valid_offset_smart(
        self,
        obj_name: str,
        config: Dict,
        valid_range: Dict
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Sample an offset within the valid position range.
        
        Unlike unrestricted random sampling, the sampled target lies within the boundaries.
        
        Args:
            obj_name: Object name.
            config: Movement configuration.
            valid_range: Valid range returned by compute_valid_position_range.
            
        Returns:
            (dx, dy, dz, dyaw), or None if no valid offset can be generated.
        """
        if not valid_range['is_valid']:
            return None
        
        if obj_name not in bpy.data.objects:
            return None
        
        obj = bpy.data.objects[obj_name]
        current_cx = obj.location.x
        current_cy = obj.location.y
        current_cz = obj.location.z
        
        new_cx = random.uniform(valid_range['cx_min'], valid_range['cx_max'])
        new_cy = random.uniform(valid_range['cy_min'], valid_range['cy_max'])
        new_cz = random.uniform(valid_range['cz_min'], valid_range['cz_max'])
        
        dx = new_cx - current_cx
        dy = new_cy - current_cy
        dz = new_cz - current_cz
        
        min_x = config.get('target_move_min_x', 0.5)
        max_x = config.get('target_move_max_x', 2.0)
        min_y = config.get('target_move_min_y', 0.5)
        max_y = config.get('target_move_max_y', 2.0)
        min_z = config.get('target_move_min_z', 0.0)
        max_z = config.get('target_move_max_z', 0.0)
        
        abs_dx = abs(dx)
        if abs_dx < min_x or abs_dx > max_x:
            if abs_dx < min_x:
                dx = min_x * (1 if dx >= 0 else -1)
            elif abs_dx > max_x:
                dx = max_x * (1 if dx >= 0 else -1)
        
        abs_dy = abs(dy)
        if abs_dy < min_y or abs_dy > max_y:
            if abs_dy < min_y:
                dy = min_y * (1 if dy >= 0 else -1)
            elif abs_dy > max_y:
                dy = max_y * (1 if dy >= 0 else -1)
        
        abs_dz = abs(dz)
        if abs_dz < min_z or abs_dz > max_z:
            if abs_dz < min_z:
                dz = min_z * (1 if dz >= 0 else -1) if min_z > 0 else 0.0
            elif abs_dz > max_z:
                dz = max_z * (1 if dz >= 0 else -1) if max_z > 0 else 0.0
        
        dyaw_deg = self.get_random_offset(
            config.get('target_move_min_yaw', 30.0),
            config.get('target_move_max_yaw', 180.0)
        )
        dyaw = math.radians(dyaw_deg)
        
        return (dx, dy, dz, dyaw)
    
    def move_object_with_constraints(
        self,
        obj_name: str,
        config: Dict,
        scene_bounds: Optional[Dict] = None,
        other_objects: Optional[List[str]] = None,
        max_retries: int = 50,
        use_smart_sampling: bool = True
    ) -> Dict:
        """
        Move an object under constraints, optionally using geometric sampling.
        
        Constraints:
        1. Stay within the scene boundaries.
        2. Avoid collisions with other objects.
        3. Stay on the floor unless the configuration allows Z movement.
        4. Keep the movement distance within the configured range.
        
        Sampling options:
        - use_smart_sampling=True: Sample only within geometrically valid boundaries (recommended).
        - use_smart_sampling=False: Use the original random retry method for compatibility.
        
        Args:
            obj_name: Object name.
            config: Movement configuration.
                {
                    'target_move_min_x': float,
                    'target_move_max_x': float,
                    'target_move_min_y': float,
                    'target_move_max_y': float,
                    'target_move_min_z': float,
                    'target_move_max_z': float,
                    'target_move_min_yaw': float,  # Degrees.
                    'target_move_max_yaw': float   # Degrees.
                }
            scene_bounds: Scene boundary information.
            other_objects: Names of other objects.
            max_retries: Maximum number of attempts.
            use_smart_sampling: Whether to use geometric sampling (default: True).
            
        Returns:
            {
                'success': bool,
                'original_position': [x, y, z],
                'original_rotation': [rx, ry, rz],
                'new_position': [x, y, z],
                'new_rotation': [rx, ry, rz],
                'offset': [dx, dy, dz, dyaw],
                'attempts': int,
                'reason': str,
                'sampling_method': str  # 'smart' or 'random'
            }
        """
        if obj_name not in bpy.data.objects:
            return {
                'success': False,
                'reason': f"Object '{obj_name}' not found",
                'attempts': 0,
                'sampling_method': 'none'
            }
        
        obj = bpy.data.objects[obj_name]
        
        original_position = list(obj.location)
        original_rotation = list(obj.rotation_euler)
        
        bounds = scene_bounds or self.scene_bounds
        
        if other_objects is None:
            other_objects = [o.name for o in bpy.data.objects 
                           if o.type == 'MESH' and o.name != obj_name]
        
        valid_range = None
        if use_smart_sampling and bounds is not None:
            valid_range = self.compute_valid_position_range(obj_name, bounds)
            if valid_range and not valid_range['is_valid']:
                # The object is too large to fit in the scene.
                return {
                    'success': False,
                    'original_position': original_position,
                    'original_rotation': original_rotation,
                    'new_position': original_position,
                    'new_rotation': original_rotation,
                    'offset': [0, 0, 0, 0],
                    'attempts': 0,
                    'reason': 'Object too large for scene boundaries',
                    'sampling_method': 'smart'
                }
        
        sampling_method = 'smart' if (use_smart_sampling and valid_range) else 'random'
        for attempt in range(max_retries):
            if use_smart_sampling and valid_range:
                offset_result = self.sample_valid_offset_smart(obj_name, config, valid_range)
                if offset_result is None:
                    reason = 'Cannot generate valid offset'
                    continue
                dx, dy, dz, dyaw = offset_result
            else:
                dx = self.get_random_offset(
                    config.get('target_move_min_x', 0.5),
                    config.get('target_move_max_x', 2.0)
                )
                dy = self.get_random_offset(
                    config.get('target_move_min_y', 0.5),
                    config.get('target_move_max_y', 2.0)
                )
                dz = self.get_random_offset(
                    config.get('target_move_min_z', 0.0),
                    config.get('target_move_max_z', 0.0)
                )
                
                # Convert yaw from degrees to radians.
                dyaw_deg = self.get_random_offset(
                    config.get('target_move_min_yaw', 30.0),
                    config.get('target_move_max_yaw', 180.0)
                )
                dyaw = math.radians(dyaw_deg)
            
            self.move_object(obj_name, dx, dy, dz, dyaw)
            
            within_bounds = self.check_within_bounds(obj_name, bounds)
            has_collision = self.check_collision(obj_name, other_objects)
            
            if within_bounds and not has_collision:
                new_position = list(obj.location)
                new_rotation = list(obj.rotation_euler)
                
                return {
                    'success': True,
                    'original_position': original_position,
                    'original_rotation': original_rotation,
                    'new_position': new_position,
                    'new_rotation': new_rotation,
                    'offset': [dx, dy, dz, dyaw],
                    'attempts': attempt + 1,
                    'reason': 'Successfully moved within constraints',
                    'sampling_method': sampling_method
                }
            
            # Restore the original position after a failed attempt.
            self.restore_object_pose(obj_name, original_position, original_rotation)
            
            if not within_bounds:
                reason = 'Out of bounds'
            elif has_collision:
                reason = 'Collision detected'
            else:
                reason = 'Unknown'
        
        return {
            'success': False,
            'original_position': original_position,
            'original_rotation': original_rotation,
            'new_position': original_position,
            'new_rotation': original_rotation,
            'offset': [0, 0, 0, 0],
            'attempts': max_retries,
            'reason': f'Failed after {max_retries} attempts: {reason}',
            'sampling_method': sampling_method
        }
    
    def calculate_movability_score(self, obj_metadata: Dict, scene_bounds: Optional[Dict] = None) -> float:
        """
        Compute an object's movability score.
        
        Factors:
        1. Object size: smaller objects are easier to move.
        2. Object category: chair > table > bed.
        3. Current position: objects near the center are easier to move.
        
        Args:
            obj_metadata: Object metadata from Module 1's extract_object_metadata.
            scene_bounds: Optional scene boundaries.
        
        Returns:
            float: Score from 0 to 1; higher values indicate easier movement.
        """
        # Use the metadata's movability_score if it is already available.
        if 'movability_score' in obj_metadata:
            base_score = obj_metadata['movability_score']
        else:
            base_score = 0.5
        
        if scene_bounds:
            position = obj_metadata.get('position', [0, 0, 0])
            
            center_x = (scene_bounds['x_min'] + scene_bounds['x_max']) / 2
            center_y = (scene_bounds['y_min'] + scene_bounds['y_max']) / 2
            
            room_size_x = scene_bounds['x_max'] - scene_bounds['x_min']
            room_size_y = scene_bounds['y_max'] - scene_bounds['y_min']
            
            dist_from_center_x = abs(position[0] - center_x) / (room_size_x / 2)
            dist_from_center_y = abs(position[1] - center_y) / (room_size_y / 2)
            
            # Reduce scores for objects near the boundaries.
            edge_penalty = (dist_from_center_x + dist_from_center_y) / 2
            base_score *= (1 - edge_penalty * 0.3)  # Reduce by at most 30%.
        
        return max(0.0, min(1.0, base_score))
    
    def select_objects_to_move(
        self,
        movable_objects: List[Dict],
        num_to_select: int,
        scene_bounds: Optional[Dict] = None
    ) -> List[str]:
        """
        Select the objects best suited for movement.
        
        Args:
            movable_objects: Movable objects with metadata.
            num_to_select: Number of objects to select.
            scene_bounds: Scene boundaries.
            
        Returns:
            list: Names of the selected objects.
        """
        if not movable_objects:
            return []
        
        scored_objects = []
        for obj_meta in movable_objects:
            score = self.calculate_movability_score(obj_meta, scene_bounds)
            scored_objects.append((obj_meta['name'], score))
        
        scored_objects.sort(key=lambda x: x[1], reverse=True)
        
        num_to_select = min(num_to_select, len(scored_objects))
        selected = [obj_name for obj_name, score in scored_objects[:num_to_select]]
        
        return selected



def get_world_bbox(obj_name: str) -> Tuple[float, float, float, float, float, float]:
    """Return an object's bounding box."""
    mover = ObjectMover()
    return mover.get_world_bbox(obj_name)


def check_collision(obj_name: str, other_obj_names: List[str]) -> bool:
    """Check for collisions."""
    mover = ObjectMover()
    return mover.check_collision(obj_name, other_obj_names)


def check_within_bounds(obj_name: str, bounds: Dict) -> bool:
    """Check scene boundaries."""
    mover = ObjectMover()
    return mover.check_within_bounds(obj_name, bounds)


def move_object(obj_name: str, dx: float = 0.0, dy: float = 0.0, 
                dz: float = 0.0, dyaw: float = 0.0) -> bool:
    """Move an object."""
    mover = ObjectMover()
    return mover.move_object(obj_name, dx, dy, dz, dyaw)


def restore_object_pose(obj_name: str, position: List[float], 
                       rotation: List[float]) -> bool:
    """Restore an object's position."""
    mover = ObjectMover()
    return mover.restore_object_pose(obj_name, position, rotation)


def move_object_with_constraints(obj_name: str, config: Dict,
                                 scene_bounds: Dict, other_objects: List[str],
                                 max_retries: int = 50) -> Dict:
    """Move an object under constraints."""
    mover = ObjectMover(scene_bounds)
    return mover.move_object_with_constraints(
        obj_name, config, scene_bounds, other_objects, max_retries
    )


def select_objects_to_move(movable_objects: List[Dict], num_to_select: int,
                          scene_bounds: Dict) -> List[str]:
    """Select objects to move."""
    mover = ObjectMover(scene_bounds)
    return mover.select_objects_to_move(movable_objects, num_to_select, scene_bounds)



def batch_move_objects(
    objects_to_move: List[str],
    config: Dict,
    scene_bounds: Dict,
    all_objects: List[str],
    max_retries: int = 50,
    use_feedback_mechanism: bool = True
) -> Dict:
    """
    Move multiple objects, optionally using failure feedback.
    
    Failure feedback:
    - Mark an object as a fixed obstacle when it exhausts its movement attempts.
    - Later objects treat failed objects as fixed obstacles during collision checks.
    - This can improve the success rate for subsequent objects.
    
    Args:
        objects_to_move: Names of objects to move.
        config: Movement configuration.
        scene_bounds: Scene boundaries.
        all_objects: All objects used for collision checks.
        max_retries: Maximum attempts per object.
        use_feedback_mechanism: Whether to enable failure feedback (default: True).
    
    Returns:
        {
            'total': int,
            'successful': int,
            'failed': int,
            'immovable_objects': List[str],  # Objects marked immovable.
            'results': [...]
        }
    """
    mover = ObjectMover(scene_bounds)
    
    results = []
    successful = 0
    failed = 0
    immovable_objects = []
    
    for obj_name in objects_to_move:
        # Failed objects are already present in all_objects.
        other_objs = [o for o in all_objects if o != obj_name]
        
        result = mover.move_object_with_constraints(
            obj_name, config, scene_bounds, other_objs, max_retries
        )
        
        if result['success']:
            successful += 1
        else:
            failed += 1
            
            # Mark failed objects as immovable for subsequent attempts.
            if use_feedback_mechanism:
                mover.mark_as_immovable(obj_name)
                immovable_objects.append(obj_name)
                
                # move_object_with_constraints has already restored the original position.
                print(f"  ⚠ '{obj_name}' marked as immovable obstacle")
        
        results.append({
            'object': obj_name,
            **result
        })
    
    summary = {
        'total': len(objects_to_move),
        'successful': successful,
        'failed': failed,
        'success_rate': successful / len(objects_to_move) if objects_to_move else 0,
        'immovable_objects': immovable_objects,
        'results': results
    }
    
    print(f"\n{'='*60}")
    print(f"Batch Movement Summary")
    print(f"{'='*60}")
    print(f"Total objects: {summary['total']}")
    print(f"Successful: {summary['successful']} ✓")
    print(f"Failed: {summary['failed']} ✗")
    if immovable_objects:
        print(f"Immovable objects: {len(immovable_objects)} (marked as obstacles)")
        for obj in immovable_objects:
            print(f"  - {obj}")
    print(f"Success rate: {summary['success_rate']*100:.1f}%")
    
    return summary


if __name__ == "__main__":
    print("Object Movement Module - Module 2")
    print("This module should be imported and used with Blender.")
    print("\nExample usage:")
    print("  from importlib import import_module")
    print('  ObjectMover = import_module("2_object_movement").ObjectMover')
    print("  mover = ObjectMover(scene_bounds)")
    print("  result = mover.move_object_with_constraints(obj_name, config)")
