#!/usr/bin/env python3
"""Read light candidates and scene bounds for lighting sampling."""

import bpy
from mathutils import Vector
from typing import Dict, List
import numpy as np


class LightAnalyzer:
    """Analyze scene lighting setup for dataset generation"""

    def __init__(self):
        self.light_objects = None


    def analyze_scene(self) -> Dict:
        """Read light candidates and bounds from the already loaded scene."""
        self.light_objects = self.identify_light_objects()
        return {'light_objects': self.light_objects, 'scene_bounds': self.compute_scene_bounds()}

    def identify_light_objects(self) -> List[Dict]:
        """Keep the original data-object ordering and world-space positions."""
        light_objects = []

        for obj in bpy.data.objects:
            if obj.type != 'LIGHT':
                continue

            light_data = obj.data
            light_info = {
                'name': obj.name,
                'type': light_data.type,
                'location': tuple(obj.matrix_world.translation),  # World coordinates!
                'energy': float(light_data.energy),
                'color': tuple(light_data.color),
                'is_visible': light_data.type != 'SUN',  # SUN is not visible
            }

            light_objects.append(light_info)

        print(f"✓ Found {len(light_objects)} light objects in scene")
        return light_objects


    def compute_scene_bounds(self) -> Dict:
        """
        Compute overall scene boundaries

        Returns:
            {
                'min': tuple,  # (x_min, y_min, z_min)
                'max': tuple,  # (x_max, y_max, z_max)
                'center': tuple,  # Scene center
                'size': tuple,  # (width, depth, height)
            }
        """
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']

        if not mesh_objects:
            # Fallback: use light positions if no meshes
            if self.light_objects:
                positions = [Vector(light['location']) for light in self.light_objects]
            else:
                return {
                    'min': (-10.0, -10.0, -10.0),
                    'max': (10.0, 10.0, 10.0),
                    'center': (0.0, 0.0, 0.0),
                    'size': (20.0, 20.0, 20.0),
                    'x_min': -10.0,
                    'x_max': 10.0,
                    'y_min': -10.0,
                    'y_max': 10.0,
                    'z_min': -10.0,
                    'z_max': 10.0,
                    'z_floor': -10.0,
                    'z_ceiling': 10.0
                }
        else:
            positions = []
            for obj in mesh_objects:
                bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                positions.extend(bbox_corners)

        positions_array = np.array([list(p) for p in positions])
        min_coords = positions_array.min(axis=0)
        max_coords = positions_array.max(axis=0)

        center = (min_coords + max_coords) / 2.0
        size = max_coords - min_coords

        return {
            'min': tuple(min_coords),
            'max': tuple(max_coords),
            'center': tuple(center),
            'size': tuple(size),
            'x_min': float(min_coords[0]),
            'x_max': float(max_coords[0]),
            'y_min': float(min_coords[1]),
            'y_max': float(max_coords[1]),
            'z_min': float(min_coords[2]),
            'z_max': float(max_coords[2]),
            'z_floor': float(min_coords[2]),
            'z_ceiling': float(max_coords[2])
        }
