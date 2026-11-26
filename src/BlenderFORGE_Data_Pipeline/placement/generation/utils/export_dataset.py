"""Render the 8a704 placement JSONL interface from v1 samples."""

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.contract import check_sample, read_json, require


# Keep wording and JSON serialization identical to the paper's 8a704 exporter.
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

BLENDER_TOOL_PROMPT = (
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


def conv_float(values):
    return [f"{value:.3f}" if isinstance(value, float) else str(value) for value in values]


def paper_pose(obj, factor):
    transform = obj["transform"]
    require(transform["rotation_mode"] not in ("QUATERNION", "AXIS_ANGLE"), "Paper prompts require Euler rotations")
    # The paper displays native Blender local coordinates, not metric world poses.
    return [value / factor for value in transform["location_local"]], transform["rotation"]


def format_scene_info(start, candidate_names):
    factor = start["scene"]["units"]["meters_per_blender_unit"]
    text = "Scene Information (Objects and Cameras):\n"
    for name in candidate_names:
        position, rotation = paper_pose(start["objects"][name], factor)
        text += f"- Name: {name}, Location: {conv_float(position)}, Rotation: {conv_float(rotation)}\n"
    for view in start["views"]:
        name = view["camera_name"]
        obj = start["objects"][name]
        position, rotation = paper_pose(obj, factor)
        camera = obj["camera"]
        require(camera["type"] == "PERSP", "Paper prompts require perspective cameras")
        # Blender Camera.angle uses sensor_height only for VERTICAL sensor_fit.
        sensor = camera["sensor_height_mm"] if camera["sensor_fit"] == "VERTICAL" else camera["sensor_width_mm"]
        fov = math.degrees(2 * math.atan(sensor / (2 * camera["lens_mm"])))
        text += (
            f"- Camera Name: {name}, Camera Location: {conv_float(position)}, "
            f"Camera Rotation: {conv_float(rotation)}, FOV: {conv_float([float(fov)])[0]}, "
            f"Focal Length: {conv_float([float(camera['lens_mm'])])[0]}, Resolution: {camera['resolution']}\n"
        )
    return text


def record(sample, output_directory):
    sample = Path(sample)
    metadata = check_sample(sample)
    require(metadata["task"] == "placement", "Expected a placement sample")
    start = read_json(sample / "start_info.json")
    goal = read_json(sample / "goal_info.json")

    def ref(name):
        return Path(os.path.relpath(sample / name, output_directory)).as_posix()

    goal_views = {view["camera_name"]: view for view in goal["views"]}
    images, start_images, goal_images = [], [], []
    image_prompt = "From the following image pairs you can identify the major changes between the start scene and the goal scene:\n"
    for view in start["views"]:
        name = view["camera_name"]
        start_image, goal_image = ref(view["image"]), ref(goal_views[name]["image"])
        start_images.append(start_image)
        goal_images.append(goal_image)
        images.extend((start_image, goal_image))
        image_prompt += f"The following is rendered in the START SCENE from camera {name} <image>.\n"
        image_prompt += f"and the following is rendered in the GOAL SCENE from the camera {name} <image>.\n"
    scene_info = format_scene_info(start, metadata["editable"]["object_names"])
    return {
        "image": images,
        "scene": ref("start.blend"),
        "prompt": [
            {
                "role": "system",
                "content": (
                    "You are a 3D experts that is skilled at blender. Your job is to follow the user's instruction to modify (restricted to moving objects) the scene."
                    "**Available Tools**:\n"
                    f"{BLENDER_TOOL_PROMPT}\n"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{image_prompt}\n\n"
                    "# Task"
                    "Modify the current Blender scene to match the provided Goal images."
                    "**Current scene Information**:\n"
                    f"{scene_info}\n\n"
                ),
            },
        ],
        "reward_model": {
            "style": "rule",
            "ground_truth": {
                "goal_script": ref("goal.py"),
                "goal_image_list": goal_images,
                "start_image_list": start_images,
                "scene_info": ref("start_info.json"),
                "goal_scene_info": ref("goal_info.json"),
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    samples = [args.dataset] if (args.dataset / "metadata.json").is_file() else sorted(args.dataset.rglob("sample_*"))
    if not samples:
        parser.error("No samples found")
    rows = [record(sample, args.output.resolve().parent) for sample in samples]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    print(f"Exported {len(rows)} records to {args.output}")


if __name__ == "__main__":
    main()
