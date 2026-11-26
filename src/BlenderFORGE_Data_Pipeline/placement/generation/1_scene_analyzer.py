#!/usr/bin/env python3
"""
Scene Analyzer - Module 1
3D-Front scene analysis utilities.

Features:
- Load .blend scenes.
- Identify structural elements such as walls, floors and ceilings.
- Identify movable objects.
- Compute scene boundaries.
- Extract object metadata.

Usage:
    # Run as a Blender script.
    blender --background scene.blend --python 1_scene_analyzer.py -- --output output.json
    
    # Import as a module in Blender Python.
    from importlib import import_module
    scene_analyzer = import_module("1_scene_analyzer")
    result = scene_analyzer.analyze_scene("path/to/scene.blend")
"""

import bpy
import json
import sys
import os
from mathutils import Vector
from typing import Dict, List, Tuple, Optional
import math


class SceneAnalyzer:
    """Analyze scene structure and movable objects."""
    
    def __init__(self, blend_file_path: Optional[str] = None):
        """
        Initialize the scene analyzer.
        
        Args:
            blend_file_path: Optional .blend path when no scene is already open in Blender.
        """
        self.blend_file_path = blend_file_path
        self.scene_structure = None
        self.movable_objects = None
        self.scene_bounds = None
        
    def load_scene(self, blend_file_path: Optional[str] = None) -> bool:
        """
        Load a .blend file.
        
        Args:
            blend_file_path: Absolute path to the .blend file.
            
        Returns:
            bool: Whether loading succeeded.
            
        Raises:
            FileNotFoundError: The file does not exist.
            RuntimeError: Blender could not load the scene.
        """
        file_path = blend_file_path or self.blend_file_path
        
        if file_path is None:
            if not bpy.data.filepath:
                raise RuntimeError("No blend file is currently open and no path provided")
            file_path = bpy.data.filepath
            
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Blend file not found: {file_path}")
        
        try:
            bpy.ops.wm.open_mainfile(filepath=file_path)
            self.blend_file_path = file_path
            print(f"✓ Successfully loaded scene: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to load blend file: {str(e)}")
    
    def identify_scene_structure(self) -> Dict[str, List[str]]:
        """
        Identify structural elements such as walls, floors and ceilings.
        
        Identification strategies:
        1. Match name keywords: wall, floor, ceiling, window and door.
        2. Identify geometric features such as large planes.
        
        Returns:
            {
                'walls': [obj_names],
                'floors': [obj_names],
                'ceilings': [obj_names],
                'windows': [obj_names],
                'doors': [obj_names],
                'lights': [obj_names]
            }
        """
        structure = {
            'walls': [],
            'floors': [],
            'ceilings': [],
            'windows': [],
            'doors': [],
            'lights': []
        }
        
        keywords_map = {
            'walls': ['wall', 'Wall', 'WALL'],
            'floors': ['floor', 'Floor', 'FLOOR', 'ground', 'Ground'],
            'ceilings': ['ceiling', 'Ceiling', 'CEILING', 'roof', 'Roof'],
            'windows': ['window', 'Window', 'WINDOW'],
            'doors': ['door', 'Door', 'DOOR']
        }
        
        for obj in bpy.data.objects:
            obj_name_lower = obj.name.lower()
            
            if obj.type in ['LIGHT', 'LIGHT_PROBE']:
                structure['lights'].append(obj.name)
                continue
            
            if obj.type != 'MESH':
                continue
            
            categorized = False
            for category, keywords in keywords_map.items():
                if any(kw.lower() in obj_name_lower for kw in keywords):
                    structure[category].append(obj.name)
                    categorized = True
                    break
            
            # Fall back to geometric classification when keywords do not match.
            if not categorized:
                self._classify_by_geometry(obj, structure)
        
        self.scene_structure = structure
        
        print(f"✓ Scene structure identified:")
        for category, objects in structure.items():
            if objects:
                print(f"  - {category}: {len(objects)} objects")
        
        return structure
    
    def _classify_by_geometry(self, obj: bpy.types.Object, structure: Dict[str, List[str]]):
        """
        Classify an object by its geometry.
        
        Args:
            obj: Blender object.
            structure: Structural category dictionary.
        """
        if obj.type != 'MESH' or len(obj.data.vertices) == 0:
            return
        
        bbox = self._get_world_bbox(obj)
        dimensions = [
            bbox['max'][0] - bbox['min'][0],
            bbox['max'][1] - bbox['min'][1],
            bbox['max'][2] - bbox['min'][2]
        ]
        
        # A large, thin plane may be a wall or floor.
        if min(dimensions) < 0.2:  # Thickness below 20 cm.
            area = max(dimensions) * sorted(dimensions)[1]
            
            if area > 5.0:  # Area above 5 square meters.
                z_pos = bbox['min'][2]
                z_height = dimensions[2]
                
                if z_pos < 0.1 and z_height < 0.3:
                    # A thin object near ground level may be a floor.
                    structure['floors'].append(obj.name)
                elif z_pos > 2.5:
                    # A high object may be a ceiling.
                    structure['ceilings'].append(obj.name)
                else:
                    # Other large planes may be walls.
                    structure['walls'].append(obj.name)
    
    def identify_movable_objects(self, scene_structure: Optional[Dict] = None) -> List[Dict]:
        """
        Identify movable furniture and decorations.
        
        Exclusions:
        - Structural scene elements.
        - Cameras and lights.
        - Non-mesh objects.
        - Empty objects.
        
        Args:
            scene_structure: Optional scene structure information.
        
        Returns:
            [
                {
                    'name': str,
                    'type': str,
                    'location': [x, y, z],
                    'rotation': [rx, ry, rz],
                    'scale': [sx, sy, sz],
                    'bounding_box': {
                        'min': [x, y, z],
                        'max': [x, y, z],
                        'size': [width, depth, height]
                    }
                },
                ...
            ]
        """
        if scene_structure is None:
            scene_structure = self.scene_structure or self.identify_scene_structure()
        
        structure_obj_names = set()
        for obj_list in scene_structure.values():
            structure_obj_names.update(obj_list)
        
        excluded_types = {'CAMERA', 'LIGHT', 'EMPTY', 'LIGHT_PROBE', 'ARMATURE'}
        
        movable = []
        for obj in bpy.data.objects:
            if obj.type in excluded_types:
                continue
            
            if obj.name in structure_obj_names:
                continue
            
            # Exclude source objects at the origin with zero rotation.
            is_at_origin = all(abs(c) < 1e-7 for c in obj.location)
            is_zero_rotation = all(abs(r) < 1e-7 for r in obj.rotation_euler)
            if is_at_origin and is_zero_rotation:
                print(f"⚠ Skipping object '{obj.name}' at origin (0,0,0) with zero rotation")
                continue
            
            if obj.type == 'MESH':
                bbox = self._get_world_bbox(obj)
                
                obj_info = {
                    'name': obj.name,
                    'type': obj.type,
                    'location': list(obj.location),
                    'rotation': list(obj.rotation_euler),
                    'scale': list(obj.scale),
                    'bounding_box': bbox
                }
                
                movable.append(obj_info)
        
        self.movable_objects = movable
        
        print(f"✓ Found {len(movable)} movable objects")
        
        return movable
    
    def _get_world_bbox(self, obj: bpy.types.Object) -> Dict:
        """
        Return the object's world-space bounding box.
        
        Args:
            obj: Blender object.
            
        Returns:
            {
                'min': [x, y, z],
                'max': [x, y, z],
                'size': [width, depth, height]
            }
        """
        if obj.type != 'MESH' or not obj.data.vertices:
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        else:
            # Use actual vertices for a more precise bounding box.
            bbox_corners = [obj.matrix_world @ v.co for v in obj.data.vertices]
        
        xs = [c.x for c in bbox_corners]
        ys = [c.y for c in bbox_corners]
        zs = [c.z for c in bbox_corners]
        
        bbox_min = [min(xs), min(ys), min(zs)]
        bbox_max = [max(xs), max(ys), max(zs)]
        size = [
            bbox_max[0] - bbox_min[0],
            bbox_max[1] - bbox_min[1],
            bbox_max[2] - bbox_min[2]
        ]
        
        return {
            'min': bbox_min,
            'max': bbox_max,
            'size': size
        }
    
    def compute_scene_boundaries(self, scene_structure: Optional[Dict] = None, margin: float = 0.0) -> Dict:
        """
        Compute usable scene boundaries from the inner wall faces.
        
        Walls, floors and ceilings define the boundaries; account for wall thickness.
        
        Args:
            scene_structure: Optional scene structure information.
            margin: Safety margin in meters (default: 0.0).
                   - 0.0: Allow objects to touch the walls.
                   - > 0: Leave clearance from the walls, for example 0.1-0.3 meters.
        
        Returns:
            {
                'x_min': float,  # Minimum inner X boundary.
                'x_max': float,  # Maximum inner X boundary.
                'y_min': float,  # Minimum inner Y boundary.
                'y_max': float,  # Maximum inner Y boundary.
                'z_floor': float,  # Floor height.
                'z_ceiling': float,  # Ceiling height.
                'margin': float  # Applied margin.
            }
        """
        if scene_structure is None:
            scene_structure = self.scene_structure or self.identify_scene_structure()
        
        walls = scene_structure.get('walls', [])
        floors = scene_structure.get('floors', [])
        ceilings = scene_structure.get('ceilings', [])
        
        if not (walls or floors or ceilings):
            # Fall back to all mesh objects when no structure is identified.
            print("⚠ No structure objects found, using all MESH objects for boundaries")
            all_objs = [obj.name for obj in bpy.data.objects if obj.type == 'MESH']
            walls, floors, ceilings = all_objs, all_objs, all_objs
        
        wall_info = []
        for wall_name in walls:
            if wall_name not in bpy.data.objects:
                continue
            
            obj = bpy.data.objects[wall_name]
            bbox = self._get_world_bbox(obj)
            
            x_size = bbox['size'][0]
            y_size = bbox['size'][1]
            z_size = bbox['size'][2]
            
            # The thin dimension indicates the wall thickness.
            if x_size < y_size and x_size < z_size:
                # A thin X dimension indicates a north-south wall, perpendicular to X.
                orientation = 'north_south'
                thickness = x_size
                position = (bbox['min'][0] + bbox['max'][0]) / 2
            elif y_size < x_size and y_size < z_size:
                # A thin Y dimension indicates an east-west wall, perpendicular to Y.
                orientation = 'east_west'
                thickness = y_size
                position = (bbox['min'][1] + bbox['max'][1]) / 2
            else:
                # Use AABB limits when the wall orientation is unclear.
                orientation = 'unknown'
                thickness = min(x_size, y_size, z_size)
                position = None
            
            wall_info.append({
                'name': wall_name,
                'bbox': bbox,
                'orientation': orientation,
                'thickness': thickness,
                'position': position
            })
        
        floor_z_coords = []
        ceiling_z_coords = []
        
        for floor_name in floors:
            if floor_name in bpy.data.objects:
                bbox = self._get_world_bbox(bpy.data.objects[floor_name])
                floor_z_coords.extend([bbox['min'][2], bbox['max'][2]])
        
        for ceiling_name in ceilings:
            if ceiling_name in bpy.data.objects:
                bbox = self._get_world_bbox(bpy.data.objects[ceiling_name])
                ceiling_z_coords.extend([bbox['min'][2], bbox['max'][2]])
        
        # Fall back to wall Z coordinates when floors or ceilings are missing.
        if not floor_z_coords and not ceiling_z_coords:
            all_z_coords = []
            for wall in wall_info:
                all_z_coords.extend([wall['bbox']['min'][2], wall['bbox']['max'][2]])
            if all_z_coords:
                floor_z_coords = [min(all_z_coords)]
                ceiling_z_coords = [max(all_z_coords)]
        
        outer_x_min = min(wall['bbox']['min'][0] for wall in wall_info) if wall_info else 0
        outer_x_max = max(wall['bbox']['max'][0] for wall in wall_info) if wall_info else 0
        outer_y_min = min(wall['bbox']['min'][1] for wall in wall_info) if wall_info else 0
        outer_y_max = max(wall['bbox']['max'][1] for wall in wall_info) if wall_info else 0
        
        # 2. Find the wall face closest to the room center in each direction.
        # X axis: west wall (x_min) and east wall (x_max).
        west_walls = [w for w in wall_info if w['orientation'] == 'north_south' and w['position'] is not None and w['position'] < (outer_x_min + outer_x_max) / 2]
        east_walls = [w for w in wall_info if w['orientation'] == 'north_south' and w['position'] is not None and w['position'] > (outer_x_min + outer_x_max) / 2]
        
        if west_walls:
            # West wall: use the easternmost inner face.
            x_min = max(wall['bbox']['max'][0] for wall in west_walls)
        else:
            x_min = outer_x_min
        
        if east_walls:
            # East wall: use the westernmost inner face.
            x_max = min(wall['bbox']['min'][0] for wall in east_walls)
        else:
            x_max = outer_x_max
        
        # Y axis: south wall (y_min) and north wall (y_max).
        south_walls = [w for w in wall_info if w['orientation'] == 'east_west' and w['position'] is not None and w['position'] < (outer_y_min + outer_y_max) / 2]
        north_walls = [w for w in wall_info if w['orientation'] == 'east_west' and w['position'] is not None and w['position'] > (outer_y_min + outer_y_max) / 2]
        
        if south_walls:
            # South wall: use the northernmost inner face.
            y_min = max(wall['bbox']['max'][1] for wall in south_walls)
        else:
            y_min = outer_y_min
        
        if north_walls:
            # North wall: use the southernmost inner face.
            y_max = min(wall['bbox']['min'][1] for wall in north_walls)
        else:
            y_max = outer_y_max
        
        if floor_z_coords:
            z_floor = min(floor_z_coords)
        else:
            z_floor = 0.0
        
        if ceiling_z_coords:
            z_ceiling = max(ceiling_z_coords)
        else:
            # Use a default ceiling height when none is found, typically 2.7-3.0 meters.
            # Infer ceiling height from walls or use a standard indoor height.
            if wall_info:
                wall_heights = [wall['bbox']['max'][2] for wall in wall_info]
                z_ceiling = max(wall_heights) if wall_heights else z_floor + 2.7
            else:
                z_ceiling = z_floor + 2.7
        
        bounds = {
            'x_min': x_min + margin,
            'x_max': x_max - margin,
            'y_min': y_min + margin,
            'y_max': y_max - margin,
            'z_floor': z_floor,
            'z_ceiling': z_ceiling,
            'margin': margin
        }
        
        self.scene_bounds = bounds
        
        room_width = bounds['x_max'] - bounds['x_min']
        room_depth = bounds['y_max'] - bounds['y_min']
        room_height = bounds['z_ceiling'] - bounds['z_floor']
        
        print(f"✓ Scene boundaries computed (inner walls):")
        print(f"  - Room dimensions: {room_width:.2f}m × {room_depth:.2f}m × {room_height:.2f}m")
        print(f"  - X range: [{bounds['x_min']:.2f}, {bounds['x_max']:.2f}]")
        print(f"  - Y range: [{bounds['y_min']:.2f}, {bounds['y_max']:.2f}]")
        print(f"  - Z range: [{bounds['z_floor']:.2f}, {bounds['z_ceiling']:.2f}]")
        if wall_info:
            avg_thickness = sum(w['thickness'] for w in wall_info) / len(wall_info)
            print(f"  - Average wall thickness: {avg_thickness:.3f}m")
        
        return bounds
    
    def extract_object_metadata(self, obj_name: str) -> Dict:
        """
        Extract detailed metadata for one object.
        
        Args:
            obj_name: Object name.
        
        Returns:
            {
                'name': str,
                'category': str,
                'size_class': str,
                'position': [x, y, z],
                'rotation': [rx, ry, rz],
                'scale': [sx, sy, sz],
                'dimensions': {
                    'width': float,
                    'depth': float,
                    'height': float,
                    'volume': float
                },
                'movability_score': float
            }
        """
        if obj_name not in bpy.data.objects:
            raise ValueError(f"Object '{obj_name}' not found in scene")
        
        obj = bpy.data.objects[obj_name]
        bbox = self._get_world_bbox(obj)
        
        width, depth, height = bbox['size']
        volume = width * depth * height
        max_dim = max(bbox['size'])
        
        if max_dim < 0.5:
            size_class = 'small'
        elif max_dim < 1.5:
            size_class = 'medium'
        else:
            size_class = 'large'
        
        category = self._infer_object_category(obj_name)
        
        movability_score = self._calculate_movability_score(size_class, category, volume)
        
        metadata = {
            'name': obj_name,
            'category': category,
            'size_class': size_class,
            'position': list(obj.location),
            'rotation': list(obj.rotation_euler),
            'scale': list(obj.scale),
            'dimensions': {
                'width': width,
                'depth': depth,
                'height': height,
                'volume': volume
            },
            'bounding_box': bbox,
            'movability_score': movability_score
        }
        
        return metadata
    
    def _infer_object_category(self, obj_name: str) -> str:
        """
        Infer an object's category from its name.
        
        Args:
            obj_name: Object name.
        
        Returns:
            str: Inferred category.
        """
        obj_name_lower = obj_name.lower()
        
        category_keywords = {
            'chair': ['chair', 'stool', 'seat', '椅'],
            'table': ['table', 'desk', '桌'],
            'sofa': ['sofa', 'couch', '沙发'],
            'bed': ['bed', '床'],
            'lamp': ['lamp', 'light', '灯'],
            'cabinet': ['cabinet', 'wardrobe', 'closet', '柜'],
            'shelf': ['shelf', 'bookshelf', 'bookcase', '架'],
            'decoration': ['vase', 'plant', 'picture', 'frame', 'decoration', '装饰'],
            'tv': ['tv', 'television', 'monitor', '电视'],
            'appliance': ['refrigerator', 'fridge', 'oven', 'microwave', '冰箱']
        }
        
        for category, keywords in category_keywords.items():
            if any(kw in obj_name_lower for kw in keywords):
                return category
        
        return 'unknown'
    
    def _calculate_movability_score(self, size_class: str, category: str, volume: float) -> float:
        """
        Compute an object's movability score.
        
        Args:
            size_class: Size category.
            category: Object category.
            volume: Object volume.
        
        Returns:
            float: Score from 0 to 1.
        """
        score = 1.0
        
        if size_class == 'small':
            score *= 1.0
        elif size_class == 'medium':
            score *= 0.8
        else:
            score *= 0.5
        
        easy_move_categories = ['decoration', 'lamp', 'chair']
        hard_move_categories = ['bed', 'sofa', 'cabinet']
        
        if category in easy_move_categories:
            score *= 1.0
        elif category in hard_move_categories:
            score *= 0.7
        
        # Adjust by volume; very large objects are harder to move.
        if volume > 2.0:  # Larger than 2 cubic meters.
            score *= 0.6
        
        return max(0.0, min(1.0, score))
    
    def analyze_scene(self, blend_file_path: Optional[str] = None) -> Dict:
        """
        Run the complete scene analysis workflow.
        
        Args:
            blend_file_path: Optional .blend path.
        
        Returns:
            {
                'scene_structure': {...},
                'movable_objects': [...],
                'scene_bounds': {...},
                'object_metadata': [...],
                'summary': {...}
            }
        """
        if blend_file_path:
            self.load_scene(blend_file_path)
        
        scene_structure = self.identify_scene_structure()
        
        movable_objects = self.identify_movable_objects(scene_structure)
        
        scene_bounds = self.compute_scene_boundaries(scene_structure)
        
        object_metadata = []
        for obj_info in movable_objects:
            try:
                metadata = self.extract_object_metadata(obj_info['name'])
                object_metadata.append(metadata)
            except Exception as e:
                print(f"⚠ Warning: Could not extract metadata for {obj_info['name']}: {e}")
        
        summary = self._generate_summary(scene_structure, movable_objects, scene_bounds, object_metadata)
        
        result = {
            'scene_structure': scene_structure,
            'movable_objects': movable_objects,
            'scene_bounds': scene_bounds,
            'object_metadata': object_metadata,
            'summary': summary
        }
        
        print("\n" + "="*60)
        print("Scene Analysis Complete!")
        print("="*60)
        print(f"Total movable objects: {summary['total_movable_objects']}")
        print(f"High movability objects: {summary['high_movability_count']}")
        print(f"Room volume: {summary['room_volume']:.2f} m³")
        
        return result
    
    def _generate_summary(self, scene_structure: Dict, movable_objects: List[Dict], 
                         scene_bounds: Dict, object_metadata: List[Dict]) -> Dict:
        """
        Summarize the analysis results.
        """
        category_counts = {}
        size_counts = {'small': 0, 'medium': 0, 'large': 0}
        high_movability_count = 0
        
        for metadata in object_metadata:
            category = metadata['category']
            category_counts[category] = category_counts.get(category, 0) + 1
            
            size_class = metadata['size_class']
            size_counts[size_class] += 1
            
            if metadata['movability_score'] > 0.7:
                high_movability_count += 1
        
        room_volume = (
            (scene_bounds['x_max'] - scene_bounds['x_min']) *
            (scene_bounds['y_max'] - scene_bounds['y_min']) *
            (scene_bounds['z_ceiling'] - scene_bounds['z_floor'])
        )
        
        return {
            'total_movable_objects': len(movable_objects),
            'category_distribution': category_counts,
            'size_distribution': size_counts,
            'high_movability_count': high_movability_count,
            'room_volume': room_volume,
            'room_dimensions': {
                'width': scene_bounds['x_max'] - scene_bounds['x_min'],
                'depth': scene_bounds['y_max'] - scene_bounds['y_min'],
                'height': scene_bounds['z_ceiling'] - scene_bounds['z_floor']
            }
        }
    
    def save_results(self, output_path: str, result: Optional[Dict] = None):
        """
        Save analysis results as JSON.
        
        Args:
            output_path: Output file path.
            result: Analysis results, or None to use the latest results.
        """
        if result is None:
            if self.scene_structure is None:
                raise RuntimeError("No analysis results available. Run analyze_scene() first.")
            
            result = {
                'scene_structure': self.scene_structure,
                'movable_objects': self.movable_objects,
                'scene_bounds': self.scene_bounds
            }
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Results saved to: {output_path}")



def load_scene(blend_file_path: str) -> bool:
    """Load a scene."""
    analyzer = SceneAnalyzer()
    return analyzer.load_scene(blend_file_path)


def identify_scene_structure() -> Dict[str, List[str]]:
    """Identify scene structure."""
    analyzer = SceneAnalyzer()
    return analyzer.identify_scene_structure()


def identify_movable_objects(scene_structure: Optional[Dict] = None) -> List[Dict]:
    """Identify movable objects."""
    analyzer = SceneAnalyzer()
    return analyzer.identify_movable_objects(scene_structure)


def compute_scene_boundaries(scene_structure: Optional[Dict] = None, margin: float = 0.0) -> Dict:
    """Compute scene boundaries."""
    analyzer = SceneAnalyzer()
    return analyzer.compute_scene_boundaries(scene_structure, margin=margin)


def extract_object_metadata(obj_name: str) -> Dict:
    """Extract object metadata."""
    analyzer = SceneAnalyzer()
    return analyzer.extract_object_metadata(obj_name)


def analyze_scene(blend_file_path: Optional[str] = None) -> Dict:
    """Run the complete scene analysis."""
    analyzer = SceneAnalyzer(blend_file_path)
    return analyzer.analyze_scene()



def main():
    """Command-line entry point."""
    import argparse
    
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    parser = argparse.ArgumentParser(description='3D-Front Scene Analyzer')
    parser.add_argument('--blend_file', type=str, help='Path to .blend file')
    parser.add_argument('--output', type=str, default='scene_analysis.json', 
                       help='Output JSON file path')
    parser.add_argument('--margin', type=float, default=0.3,
                       help='Safety margin for scene boundaries (meters)')
    args = parser.parse_args(argv)
    
    if args.blend_file:
        blend_file_path = args.blend_file
    else:
        blend_file_path = bpy.data.filepath
    
    if not blend_file_path:
        print("Error: No blend file specified. Use --blend_file argument or open a file in Blender.")
        sys.exit(1)
    
    try:
        analyzer = SceneAnalyzer(blend_file_path)
        result = analyzer.analyze_scene()
        
        analyzer.save_results(args.output, result)
        
        print(f"\n✓ Analysis complete! Results saved to: {args.output}")
        
    except Exception as e:
        print(f"\n✗ Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
