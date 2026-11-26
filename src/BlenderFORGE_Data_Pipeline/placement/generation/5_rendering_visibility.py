"""
Module 5: Rendering and Visibility Analysis

This module renders RGB images from multiple cameras and analyzes visibility.

Core Features:
1. Render engine configuration (Cycles/EEVEE)
2. Multi-view RGB rendering
3. Object pass-index helpers for diagnostics
4. Object visibility analysis
5. Coverage verification

Dependencies:
- Blender Python API (bpy)
- NumPy
- Pillow (PIL)

Author: 3D-Front Placement Pipeline
Date: 2024
"""

import importlib
import os
import sys
import math
from pathlib import Path
from typing import List, Dict
import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.blender_state import configure_render


def setup_render_engine(config: Dict) -> None:
    """Apply render_config; Blender property names and values come from JSON."""
    configure_render(config)
    scene = bpy.context.scene
    print(f"Render engine configured: {scene.render.engine}")
    print(f"  Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")


def assign_object_indices(obj_names: List[str]) -> Dict[str, int]:
    """
    Assign unique pass_index to objects for segmentation.
    
    Args:
        obj_names: List of object names to assign indices
    
    Returns:
        Dict mapping object name to index
    
    Example:
        >>> index_map = assign_object_indices(['chair', 'table', 'lamp'])
        >>> print(index_map)  # {'chair': 1, 'table': 2, 'lamp': 3}
    """
    obj_index_map = {}
    
    for i, obj_name in enumerate(obj_names, start=1):
        if obj_name in bpy.data.objects:
            obj = bpy.data.objects[obj_name]
            obj.pass_index = i
            obj_index_map[obj_name] = i
            print(f"  Assigned index {i} to '{obj_name}'")
        else:
            print(f"  ⚠️  Object '{obj_name}' not found")
    
    return obj_index_map


def get_object_indices() -> Dict[str, int]:
    """
    Get current object indices in scene.
    
    Returns:
        Dict mapping object name to pass_index
    """
    return {
        obj.name: obj.pass_index 
        for obj in bpy.data.objects 
        if obj.type == 'MESH' and obj.pass_index > 0
    }


def render_camera_view(
    camera_name: str,
    output_path: str,
    render_rgb: bool = True
) -> Dict[str, str]:
    """
    Render a single camera view.
    
    Args:
        camera_name: Name of camera to render from
        output_path: Output file path (without extension)
        render_rgb: Whether to render RGB image
    
    Returns:
        Dict with paths to rendered files
    
    Example:
        >>> paths = render_camera_view('Camera_00', 'output/cam_00')
        >>> print(paths['rgb'])  # 'output/cam_00.png'
    """
    if camera_name not in bpy.data.objects:
        print(f"❌ Camera '{camera_name}' not found")
        return {}
    
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[camera_name]
    
    results = {}
    
    if render_rgb:
        if scene.render.image_settings.file_format != 'PNG':
            raise ValueError("Placement sample views require PNG; set scene.render.image_settings.file_format in config")
        rgb_path = f"{output_path}.png"
        scene.render.filepath = rgb_path
        
        try:
            # Suppress Blender's verbose render output by redirecting at OS level
            import os as os_module
            
            original_stdout_fd = os_module.dup(1)
            original_stderr_fd = os_module.dup(2)
            
            devnull_fd = os_module.open(os_module.devnull, os_module.O_WRONLY)
            os_module.dup2(devnull_fd, 1)
            os_module.dup2(devnull_fd, 2)
            try:
                bpy.ops.render.render(write_still=True)
            finally:
                os_module.dup2(original_stdout_fd, 1)
                os_module.dup2(original_stderr_fd, 2)
                
                os_module.close(devnull_fd)
                os_module.close(original_stdout_fd)
                os_module.close(original_stderr_fd)
            results['rgb'] = rgb_path
            print(f"  ✓ Rendered RGB: {rgb_path}")
        except Exception as e:
            print(f"  ❌ RGB render failed: {e}")
            raise
    
    camera_obj = bpy.data.objects[camera_name]
    
    camera_data = camera_obj.data
    fov_radians = camera_data.angle
    fov_degrees = math.degrees(fov_radians)
    focal_length = camera_data.lens  # in millimeters
    
    scene = bpy.context.scene
    resolution_x = scene.render.resolution_x
    resolution_y = scene.render.resolution_y
    resolution_percentage = scene.render.resolution_percentage
    
    actual_resolution_x = int(resolution_x * resolution_percentage / 100.0)
    actual_resolution_y = int(resolution_y * resolution_percentage / 100.0)
    
    results['camera_pose'] = {
        'position': list(camera_obj.location),
        'rotation': list(camera_obj.rotation_euler),
        'fov': fov_degrees,  # Field of view in degrees
        'fov_radians': fov_radians,  # FOV in radians
        'focal_length': focal_length,  # Focal length in millimeters
        'resolution': [actual_resolution_x, actual_resolution_y],
        'resolution_x': actual_resolution_x,
        'resolution_y': actual_resolution_y
    }
    
    return results


def render_all_cameras(
    camera_names: List[str],
    output_dir: str,
    render_config: Dict
) -> List[Dict]:
    """
    Render all camera views.
    
    Args:
        camera_names: List of camera names
        output_dir: Output directory
        render_config: Render configuration
    
    Returns:
        List of render results
    
    Example:
        >>> config = {'engine': 'CYCLES', 'width': 512, 'height': 512, 'samples': 64}
        >>> results = render_all_cameras(['Camera_00', 'Camera_01'], 'output', config)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    setup_render_engine(render_config)
    
    results = []
    
    print(f"\n{'='*70}")
    print(f"RENDERING {len(camera_names)} CAMERA VIEWS")
    print(f"{'='*70}")
    
    for idx, cam_name in enumerate(camera_names):
        print(f"\n📷 Rendering camera {idx + 1}/{len(camera_names)}: {cam_name}")
        
        output_path = os.path.join(output_dir, cam_name)
        
        render_result = render_camera_view(
            cam_name,
            output_path,
            render_rgb=True
        )
        
        render_result['camera_name'] = cam_name
        render_result['camera_index'] = idx
        results.append(render_result)
    
    print(f"\n{'='*70}")
    print(f"RENDERING COMPLETE")
    print(f"{'='*70}")
    print(f"✓ Rendered {len(results)} views")
    print(f"✓ Output directory: {output_dir}")
    
    return results


def analyze_visibility_simple(
    render_results: List[Dict],
    target_objects: List[str]
) -> Dict:
    """
    Analyze object visibility using simple heuristics.
    
    This is a simplified version that doesn't require segmentation maps.
    It checks if objects are in camera frustums.
    
    Args:
        render_results: List of render results from render_all_cameras()
        target_objects: List of object names to check visibility
    
    Returns:
        Visibility analysis dict
    """
    is_object_in_camera_frustum = importlib.import_module('4_camera_placement').is_object_in_camera_frustum
    
    visibility_per_camera = []
    
    for result in render_results:
        cam_name = result['camera_name']
        visible_objects = []
        
        for obj_name in target_objects:
            # Use larger margin for visibility check
            if is_object_in_camera_frustum(cam_name, obj_name, margin=1.5):
                visible_objects.append(obj_name)
        
        visibility_per_camera.append({
            'camera': cam_name,
            'camera_index': result['camera_index'],
            'visible_objects': visible_objects,
            'visibility_count': len(visible_objects)
        })
    
    all_visible = set()
    for v in visibility_per_camera:
        all_visible.update(v['visible_objects'])
    
    coverage_rate = len(all_visible) / len(target_objects) if target_objects else 0.0
    
    summary = {
        'total_objects': len(target_objects),
        'visible_objects': sorted(list(all_visible)),
        'visibility_count': len(all_visible),
        'coverage_rate': coverage_rate,
        'avg_objects_per_camera': np.mean([v['visibility_count'] for v in visibility_per_camera]) if visibility_per_camera else 0.0
    }
    
    return {
        'per_camera': visibility_per_camera,
        'summary': summary
    }


def verify_visibility_coverage(
    visibility_report: Dict,
    min_coverage: float = 0.8,
    min_cameras_per_object: int = 1
) -> Dict:
    """
    Verify that visibility coverage meets requirements.
    
    Args:
        visibility_report: Report from analyze_visibility_simple()
        min_coverage: Minimum fraction of objects that must be visible
        min_cameras_per_object: Minimum cameras that must see each object
    
    Returns:
        Verification result dict
    """
    summary = visibility_report['summary']
    
    coverage_ok = summary['coverage_rate'] >= min_coverage
    
    object_camera_count = {}
    for cam_vis in visibility_report['per_camera']:
        for obj in cam_vis['visible_objects']:
            object_camera_count[obj] = object_camera_count.get(obj, 0) + 1
    
    insufficient_objects = [
        obj for obj, count in object_camera_count.items()
        if count < min_cameras_per_object
    ]
    
    cameras_ok = len(insufficient_objects) == 0
    
    return {
        'passed': coverage_ok and cameras_ok,
        'coverage_ok': coverage_ok,
        'coverage_rate': summary['coverage_rate'],
        'min_coverage_required': min_coverage,
        'cameras_per_object_ok': cameras_ok,
        'object_camera_count': object_camera_count,
        'insufficient_objects': insufficient_objects,
        'min_cameras_required': min_cameras_per_object
    }


def create_visualization_grid(
    image_paths: List[str],
    output_path: str,
    grid_cols: int = 2
) -> str:
    """
    Create a grid visualization of multiple rendered views.
    
    Args:
        image_paths: List of image file paths
        output_path: Output path for grid image
        grid_cols: Number of columns in grid
    
    Returns:
        Path to created grid image
    """
    try:
        from PIL import Image
        
        if not image_paths:
            print("⚠️  No images to create grid")
            return None
        
        images = []
        for path in image_paths:
            if os.path.exists(path):
                images.append(Image.open(path))
        
        if not images:
            print("⚠️  No valid images found")
            return None
        
        grid_rows = (len(images) + grid_cols - 1) // grid_cols
        
        img_width, img_height = images[0].size
        
        grid_width = img_width * grid_cols
        grid_height = img_height * grid_rows
        grid_image = Image.new('RGB', (grid_width, grid_height), color='black')
        
        for idx, img in enumerate(images):
            row = idx // grid_cols
            col = idx % grid_cols
            x = col * img_width
            y = row * img_height
            grid_image.paste(img, (x, y))
        
        grid_image.save(output_path)
        print(f"✓ Created visualization grid: {output_path}")
        
        return output_path
        
    except ImportError:
        print("⚠️  PIL not available, skipping grid creation")
        return None
    except Exception as e:
        print(f"❌ Grid creation failed: {e}")
        return None


def save_visibility_report(
    visibility_report: Dict,
    output_path: str
) -> None:
    """
    Save visibility analysis report to JSON.
    
    Args:
        visibility_report: Report from analyze_visibility_simple()
        output_path: Output JSON file path
    """
    import json
    
    with open(output_path, 'w') as f:
        json.dump(visibility_report, f, indent=2)
    
    print(f"✓ Saved visibility report: {output_path}")


def render_and_analyze(
    camera_names: List[str],
    target_objects: List[str],
    output_dir: str,
    render_config: Dict,
    scene_state: str = "goal"
) -> Dict:
    """
    Main function: Render all views and analyze visibility.
    
    Args:
        camera_names: List of camera names to render
        target_objects: List of object names to check visibility
        output_dir: Output directory for renders and reports
        render_config: Render configuration
        scene_state: Scene state label ('start' or 'goal')
    
    Returns:
        Complete analysis results
    
    Example:
        >>> config = {'engine': 'CYCLES', 'width': 512, 'height': 512, 'samples': 64}
        >>> result = render_and_analyze(
        ...     ['Camera_00', 'Camera_01'],
        ...     ['chair', 'table'],
        ...     'output',
        ...     config,
        ...     'goal'
        ... )
    """
    print("\n" + "="*70)
    print("RENDERING AND VISIBILITY ANALYSIS")
    print("="*70)
    print(f"Scene state: {scene_state}")
    print(f"Cameras: {len(camera_names)}")
    print(f"Target objects: {len(target_objects)}")
    
    render_dir = os.path.join(output_dir, f"renders_{scene_state}")
    os.makedirs(render_dir, exist_ok=True)
    
    render_results = render_all_cameras(
        camera_names,
        render_dir,
        render_config
    )
    
    print("\n" + "="*70)
    print("VISIBILITY ANALYSIS")
    print("="*70)
    
    visibility_report = analyze_visibility_simple(render_results, target_objects)
    
    print(f"\nVisibility Summary:")
    print(f"  Total objects: {visibility_report['summary']['total_objects']}")
    print(f"  Visible objects: {visibility_report['summary']['visibility_count']}")
    print(f"  Coverage rate: {visibility_report['summary']['coverage_rate']*100:.1f}%")
    print(f"  Avg objects/camera: {visibility_report['summary']['avg_objects_per_camera']:.1f}")
    
    verification = verify_visibility_coverage(visibility_report, min_coverage=0.8)
    
    print(f"\nVerification:")
    print(f"  Overall: {'✓ PASSED' if verification['passed'] else '✗ FAILED'}")
    print(f"  Coverage: {'✓' if verification['coverage_ok'] else '✗'} "
          f"{verification['coverage_rate']*100:.1f}% (>= {verification['min_coverage_required']*100:.1f}%)")
    
    if verification['insufficient_objects']:
        print(f"  ⚠️  Objects with insufficient camera coverage:")
        for obj in verification['insufficient_objects']:
            count = verification['object_camera_count'].get(obj, 0)
            print(f"    - {obj}: {count} camera(s)")
    
    rgb_paths = [r.get('rgb') for r in render_results if 'rgb' in r]
    if rgb_paths:
        grid_path = os.path.join(output_dir, f"grid_{scene_state}.png")
        create_visualization_grid(rgb_paths, grid_path)
    
    report_path = os.path.join(output_dir, f"visibility_{scene_state}.json")
    save_visibility_report(visibility_report, report_path)
    
    verification_path = os.path.join(output_dir, f"verification_{scene_state}.json")
    import json
    with open(verification_path, 'w') as f:
        json.dump(verification, f, indent=2)
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    
    return {
        'render_results': render_results,
        'visibility': visibility_report,
        'verification': verification,
        'output_dir': output_dir
    }


if __name__ == "__main__":
    print("Module 5: Rendering and Visibility Analysis")
    print("This module should be imported and used from test scripts or the main pipeline.")
    print("\nAvailable functions:")
    print("  - setup_render_engine()")
    print("  - assign_object_indices()")
    print("  - render_camera_view()")
    print("  - render_all_cameras()")
    print("  - analyze_visibility_simple()")
    print("  - verify_visibility_coverage()")
    print("  - render_and_analyze()")
