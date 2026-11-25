"""
Shape Key Extractor for Blender Files
Load .blend assets and extract shape-key names from mesh objects.
"""

import bpy
import json
import os
import sys
import argparse
from pathlib import Path


def clear_scene():
    """Clear all objects from the current scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def get_shape_keys_from_blend(blend_file):
    """
    Load a .blend file and extract all shape keys from mesh objects.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary with 'shape_keys' dict (object_name -> list of shape keys) and 'error' message if any
    """
    result = {
        'shape_keys': {},
        'error': None
    }
    
    try:
        clear_scene()
        
        print(f"Loading: {blend_file}")
        
        # Try to open the blend file directly first (alternative method)
        try:
            bpy.ops.wm.open_mainfile(filepath=blend_file)
            print(f"  Successfully opened blend file directly")
            
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.data.shape_keys:
                    print(f"  Object: {obj.name}")
                    shape_key_list = []
                    for key_block in obj.data.shape_keys.key_blocks:
                        shape_key_name = key_block.name
                        print(f"    - Shape Key: {shape_key_name}")
                        shape_key_list.append(shape_key_name)
                    result['shape_keys'][obj.name] = shape_key_list
            
        except Exception as e1:
            print(f"  Direct open failed, trying append method...")
            print(f"  Error: {str(e1)}")
            
            # Clear scene again before trying append
            clear_scene()
            
            # Try the append method as fallback
            with bpy.data.libraries.load(blend_file, link=False) as (data_from, data_to):
                data_to.objects = data_from.objects
            
            for obj in data_to.objects:
                if obj is not None:
                    bpy.context.collection.objects.link(obj)
            
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.data.shape_keys:
                    print(f"  Object: {obj.name}")
                    shape_key_list = []
                    for key_block in obj.data.shape_keys.key_blocks:
                        shape_key_name = key_block.name
                        print(f"    - Shape Key: {shape_key_name}")
                        shape_key_list.append(shape_key_name)
                    result['shape_keys'][obj.name] = shape_key_list
        
        if not result['shape_keys']:
            print("  No shape keys found in this file")
            
    except Exception as e:
        error_msg = str(e)
        print(f"  Error processing {blend_file}: {error_msg}")
        result['error'] = error_msg
    
    return result


def process_blend_directory(blend_dir, output_json):
    """
    Process all .blend files in a directory and extract shape keys.
    
    Args:
        blend_dir: Directory containing .blend files
        output_json: Path to output JSON file
    """
    blend_dir = Path(blend_dir)
    
    if not blend_dir.exists():
        print(f"Error: Directory {blend_dir} does not exist")
        sys.exit(1)
    
    blend_files = list(blend_dir.glob("*.blend"))
    
    if not blend_files:
        print(f"Warning: No .blend files found in {blend_dir}")
        return
    
    print(f"Found {len(blend_files)} .blend files")
    print("=" * 60)
    
    results = {}
    
    for blend_file in sorted(blend_files):
        filename = blend_file.name
        print(f"\nProcessing: {filename}")
        print("-" * 60)
        
        result = get_shape_keys_from_blend(str(blend_file))
        results[filename] = result
        
        if result['error']:
            print(f"Status: Failed with error")
        else:
            print(f"Status: Success - {len(result['shape_keys'])} shape keys found")
    
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"Results saved to: {output_json}")
    print("=" * 60)
    
    print("\nSummary:")
    total_files = len(results)
    failed_files = sum(1 for r in results.values() if r.get('error'))
    successful_files = total_files - failed_files
    total_shape_keys = sum(sum(len(sk_list) for sk_list in r.get('shape_keys', {}).values()) for r in results.values())
    files_with_shape_keys = sum(1 for r in results.values() if r.get('shape_keys'))
    
    print(f"  Total files processed: {total_files}")
    print(f"  Successful: {successful_files}")
    print(f"  Failed: {failed_files}")
    print(f"  Files with shape keys: {files_with_shape_keys}")
    print(f"  Total shape keys found: {total_shape_keys}")
    
    if failed_files > 0:
        print("\nFailed files:")
        for filename, result in results.items():
            if result.get('error'):
                print(f"  - {filename}: {result['error']}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract shape keys from .blend files in a directory'
    )
    parser.add_argument(
        '--blend_dir',
        type=str,
        required=True,
        help='Directory containing .blend files'
    )
    parser.add_argument(
        '--output_json',
        type=str,
        default='shape_keys_output.json',
        help='Output JSON file path (default: shape_keys_output.json)'
    )
    
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    
    args = parser.parse_args(argv)
    
    process_blend_directory(args.blend_dir, args.output_json)


if __name__ == "__main__":
    main()
