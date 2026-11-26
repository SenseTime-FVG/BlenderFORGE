"""Shape-key selection and sampling from the original generator."""
import json
import logging
import random
from typing import Dict, List, Tuple
import bpy


def get_modifiable_shapekeys(blend_filename: str, shapekey_modifiable_path: str) -> List[Tuple[str, str, float, float]]:
    """
    Get all modifiable shape keys from a blend file.

    Args:
        blend_filename: Name of the blend file
        shapekey_modifiable_path: Path to shape keys JSON file

    Returns:
        List of tuples: (object_name, key_name, min_value, max_value)
    """
    with open(shapekey_modifiable_path, 'r', encoding='utf-8') as f:
        shapekey_data = json.load(f)

    if blend_filename not in shapekey_data:
        logging.warning(f"Blend file {blend_filename} not found in shape keys database")
        return []

    file_data = shapekey_data[blend_filename]
    if 'error' in file_data and file_data['error']:
        logging.warning(f"Error in shape keys for {blend_filename}: {file_data['error']}")
        return []

    shape_keys_dict = file_data.get('shape_keys', {})

    modifiable_keys = []
    for obj_name, key_names in shape_keys_dict.items():
        if obj_name not in bpy.data.objects:
            continue

        obj = bpy.data.objects[obj_name]
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue

        for key_name in key_names:
            # Skip Basis key
            if key_name == "Basis":
                continue

            if key_name in obj.data.shape_keys.key_blocks:
                key_block = obj.data.shape_keys.key_blocks[key_name]
                min_val = key_block.slider_min
                max_val = key_block.slider_max

                if min_val == max_val:
                    continue

                modifiable_keys.append((obj_name, key_name, min_val, max_val))

    return modifiable_keys

def select_keys(keys: List[Tuple], count: int) -> List[Tuple]:
    """Select up to count keys; keep the original order when all keys fit."""
    if len(keys) <= count:
        return keys
    return random.sample(keys, count)

def generate_key_values(displayed_keys: List[Tuple], changed_keys: List[Tuple],
                       min_change_prop: float) -> Dict[Tuple, Dict]:
    """
    Generate start and goal values for shape keys.

    Args:
        displayed_keys: All keys to display
        changed_keys: Keys that will change
        min_change_prop: Minimum change proportion

    Returns:
        Dictionary mapping keys to their values
    """
    key_values = {}

    for key in displayed_keys:
        obj_name, key_name, min_val, max_val = key

        if key in changed_keys:
            min_delta = (max_val - min_val) * min_change_prop

            start_value = random.uniform(min_val, max_val)

            range1_min = min_val
            range1_max = start_value - min_delta
            range2_min = start_value + min_delta
            range2_max = max_val

            len1 = max(0, range1_max - range1_min)
            len2 = max(0, range2_max - range2_min)
            total_len = len1 + len2

            if total_len <= 0:
                # Cannot satisfy min_change_proportion, skip this key
                logging.warning(f"Cannot satisfy min_change_proportion for {obj_name}.{key_name}, skipping")
                # Use same value for both (effectively not changing)
                goal_value = start_value
            else:
                # Weighted random selection of range
                if random.random() < len1 / total_len:
                    goal_value = random.uniform(range1_min, range1_max)
                else:
                    goal_value = random.uniform(range2_min, range2_max)
        else:
            value = random.uniform(min_val, max_val)
            start_value = value
            goal_value = value

        key_values[key] = {
            'start_value': start_value,
            'goal_value': goal_value,
        }

    return key_values

def rename_keys(displayed_keys: List[Tuple], rephrase_dict: Dict,
                rename_prob: float) -> Dict[Tuple, str]:
    """Sample optional alternative names without changing the keys' identities."""
    rename_map = {}
    for key in displayed_keys:
        key_name = key[1]
        rename_map[key] = key_name
        if random.random() < rename_prob and rephrase_dict.get(key_name):
            rename_map[key] = random.choice(rephrase_dict[key_name])
    return rename_map

def apply_key_renames(rename_map: Dict[Tuple, str]):
    """
    Apply shape key renames directly in the Blender scene.
    This is done before generating scripts to avoid including rename logic in training data.

    Args:
        rename_map: Dictionary mapping original keys to renamed versions
    """
    blocks = {key: bpy.data.objects[key[0]].data.shape_keys.key_blocks[key[1]] for key in rename_map}
    # Keep references through swaps/collisions, and record Blender's final names.
    for index, (key, block) in enumerate(blocks.items()):
        if rename_map[key] != key[1]:
            block.name = f"__blenderforge_rename_{index}__"
    for key, block in blocks.items():
        block.name = rename_map[key]
        rename_map[key] = block.name
