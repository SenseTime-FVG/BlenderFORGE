"""Export validated lighting samples with the original paper prompt."""
import argparse
import os
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.contract import check_sample,read_json,require

BLENDER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "blender_code_executor",
            "description": "Execute Blender Python (bpy) scripts to modify, manipulate in the Blender scene. Returns execution status and any output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The complete Blender Python code to execute using the bpy module. Must be valid Python code that uses Blender's bpy API."
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "blender_preview_renderer",
            "description": "Render and return a preview image of the current Blender scene from the specified camera viewpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "camera": {
                        "type": "string",
                        "description": "The name of the camera object in the Blender scene to render from (e.g., 'Camera_01'). Must exactly match an existing camera name in the scene."
                    }
                },
                "required": ["camera"]
            }
        }
    }
]

BLENDER_TOOL_PROMPT=(
        "# Tools\n"
        "\nThese are tools that can be used to interact with blender sandbox.\n"
        "\nYou are provided with function signatures within <tools></tools> XML tags:\n"
        f"<tools>\n{json.dumps(BLENDER_TOOLS)}\n</tools>\n\n"
        "## Tool Usage Instructions\n\n"
        "For each function call, return a JSON object with the function name and arguments within `<tool_call></tool_call>` XML tags:\n\n"
        "```xml\n"
        "<tool_call>\n"
        "{\n"
        '  "name": "<function-name>",\n'
        '  "arguments": <args-json-object>\n'
        "}\n"
        "</tool_call>\n"
        "```\n\n"
    )

def conv_float(input_list):
    output_list = []
    for item in input_list:
        if isinstance(item, float):
            output_list.append(f"{item:.3f}")
        else:
            output_list.append(str(item))
    return output_list

def get_scene_image_prompt(start_image_list: list, goal_image_list: list) -> str:
    prompt = "From the following image pairs you can identify the major changes between the start scene and the goal scene:\n"
    list_of_images = []
    for start_image, goal_image in zip(start_image_list, goal_image_list):
        camera_name = Path(start_image).stem
        require(camera_name == Path(goal_image).stem, 'START/GOAL camera name mismatch')
        prompt += f"The following is rendered in the START SCENE from camera {camera_name} <image>.\n"
        prompt += f"and the following is rendered in the GOAL SCENE from the camera {camera_name} <image>.\n"
        list_of_images.append(start_image)
        list_of_images.append(goal_image)
    return prompt, list_of_images

def formulate_single_data_item(data_dict: dict, root: str):
    assert all (key in data_dict for key in ("start_image_list", "goal_image_list", "scene_info", "start_script", "goal_script")), "Data dictionary missing required keys."

    start_image_path = os.path.relpath(data_dict["start_image_list"][0], root)
    current_sample_dir = os.path.dirname(os.path.dirname(start_image_path))
    blender_scene_blend = str(current_sample_dir)+("/start.blend")
    assert os.path.exists(os.path.join(root, blender_scene_blend)), f"Blender scene file does not exist: {blender_scene_blend}"

    scene_info_str = data_dict['scene_info_text']
    init_prompt, list_of_images = get_scene_image_prompt(data_dict["start_image_list"], data_dict["goal_image_list"])
    rel_image_paths = [os.path.relpath(image_path, root) for image_path in list_of_images]
    single_json_data_item = {
        "image": rel_image_paths,
        "scene": blender_scene_blend,
        "prompt": [
            {
                "role": "system",
                "content": (
                    "You are a 3D experts that is skilled at blender. Your job is to follow the user's instruction to modify the light (energy or color) of the scene."
                    "**Available Tools**:\n"
                    f"{BLENDER_TOOL_PROMPT}\n"
                )
            },
            {
                "role": "user",
                "content": (
                    f"{init_prompt}\n\n"
                    "# Task\n"
                    "Modify the current Blender scene to match the provided Goal images."
                    "**Current scene Information**:\n"
                    f"{scene_info_str}\n\n"
                )
            }
        ],
        "reward_model":{
            "style": "rule",
            "ground_truth": {
                "goal_script": os.path.relpath(data_dict["goal_script"], root),
                "goal_image_list": [os.path.relpath(img, root) for img in data_dict["goal_image_list"]],
                "start_image_list": [os.path.relpath(img, root) for img in data_dict["start_image_list"]],
                "scene_info": os.path.relpath(data_dict["scene_info"], root),
                "goal_scene_info": os.path.relpath(data_dict["goal_scene_info"], root),
            }
        }
    }
    return single_json_data_item


def format_scene_info(start, light_names):
    factor = start['scene']['units']['meters_per_blender_unit']
    info = 'Scene Information (Lights and Cameras):\n'
    for name in light_names:
        obj = start['objects'][name]
        location = [row[3]/factor for row in obj['transform']['matrix_world_evaluated'][:3]]
        light = obj['light']
        info += f"- Light Name: {name}, Location: {conv_float(location)},Energy: {conv_float([float(light['energy'])])[0]}, Color: {conv_float(light['color'])}\n"
    for view in start['views']:
        name = view['camera_name']
        transform = start['objects'][name]['transform']
        require(transform['rotation_mode'] == 'XYZ', 'Paper camera prompt requires XYZ Euler rotation')
        position = [v/factor for v in transform['location_local']]
        info += f"- Camera Name: {name}, Camera Location: {conv_float(position)}, Camera Rotation: {conv_float(transform['rotation'])}\n"
    return info


def record(sample, output_directory):
    sample = Path(sample).resolve()
    metadata = check_sample(sample)
    require(metadata['task'] == 'lighting', 'Expected a lighting sample')
    start = read_json(sample/'start_info.json')
    goal = read_json(sample/'goal_info.json')
    goals = {v['camera_name']:v for v in goal['views']}
    data = {'scene_info_text':format_scene_info(start, metadata['editable']['object_names']),
            'start_image_list':[str(sample/v['image']) for v in start['views']],
            'goal_image_list':[str(sample/goals[v['camera_name']]['image']) for v in start['views']],
            **{key:str(sample/filename) for key,filename in (
                ('scene_info','start_info.json'), ('goal_scene_info','goal_info.json'),
                ('start_script','start.py'), ('goal_script','goal.py'))}}
    return formulate_single_data_item(data, str(Path(output_directory).resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    samples = [args.dataset] if (args.dataset/'metadata.json').is_file() else sorted(p for p in args.dataset.rglob('sample_*') if p.is_dir())
    require(samples, 'No samples found')
    rows = [record(sample, args.output.resolve().parent) for sample in samples]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row)+'\n')
    print(f'Exported {len(rows)} lighting records to {args.output}')


if __name__ == '__main__':
    main()
