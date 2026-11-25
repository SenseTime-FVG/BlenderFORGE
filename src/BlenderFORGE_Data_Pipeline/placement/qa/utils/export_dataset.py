import argparse
import os
import json


ASSISTANT_NAME = "assistant"
SYSTEM_NAME = "system"
USER_NAME = "user"
THINK_TAG = ("<think>\n", "\n</think>\n\n")

SYSTEM_PROMPT = (
    "The user is working on a 3D scene placement task. The user has a start scene, a goal scene, and a current scene."
    "The user just performed an action to move an object in the current scene. The user wants to know whether the action is correct, i.e, objects are closer to their positions in the goal scene."
    "The answer should be either 'Yes' or 'No'."
    "The object the user refers to may be confusing, you need to use the scene info the user provides to identify."
)


def get_target_directory_path(base_path: str, black_list=None) -> list:
    target_dirs = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name and dir_name[-1].isdigit() and (black_list is None or dir_name not in black_list):
                target_dirs.append(os.path.join(root, dir_name))
    print(f"Found {len(target_dirs)} target directories in total in {base_path}. Now checking the integrity of each directory...")
    real_target_dirs = []
    for dir_path in target_dirs:
        try:
            assert os.path.exists(os.path.join(dir_path, ".SUCCESS")), f"'.SUCCESS' file not found in {dir_path}"
            assert os.path.exists(os.path.join(dir_path, "goal_views")), f"'goal_views' directory not found in {dir_path}"
            assert os.path.exists(os.path.join(dir_path, "start_views")), f"'start_views' directory not found in {dir_path}"
            assert os.path.exists(os.path.join(dir_path, "current_views")), f"'current_views' directory not found in {dir_path}"
            assert os.path.exists(os.path.join(dir_path, "qa_items.json")), f"'qa_items.json' file not found in {dir_path}"
            assert os.path.exists(os.path.join(dir_path, "start_info.json")), f"'start_info.json' file not found in {dir_path}"
            num_start_imgs = len([f for f in os.listdir(os.path.join(dir_path, "start_views")) if f.endswith('.png')])
            num_current_imgs = len([f for f in os.listdir(os.path.join(dir_path, "current_views")) if f.endswith('.png')])
            num_goal_imgs = len([f for f in os.listdir(os.path.join(dir_path, "goal_views")) if f.endswith('.png')])
            assert num_start_imgs == num_current_imgs == num_goal_imgs, (
                f"Number of images in 'start_views', 'current_views', and 'goal_views' do not match in {dir_path}"
            )
            real_target_dirs.append(dir_path)
        except (AssertionError, OSError) as e:
            print(f"Skipping directory due to missing files: {e}")

    print(f"Found {len(real_target_dirs)} target directories in total in {base_path}.")
    return real_target_dirs


def collect_qa_data_item(target_dir_path: str, base_path: str) -> dict:
    start_img_ls = sorted([f for f in os.listdir(os.path.join(target_dir_path, "start_views")) if f.endswith('.png')])
    current_img_ls = sorted([f for f in os.listdir(os.path.join(target_dir_path, "current_views")) if f.endswith('.png')])
    goal_img_ls = sorted([f for f in os.listdir(os.path.join(target_dir_path, "goal_views")) if f.endswith('.png')])
    qa_item = os.path.join(target_dir_path, "qa_items.json")
    scene_info = os.path.join(target_dir_path, "start_info.json")
    goal_scene_info = os.path.join(target_dir_path, "goal_info.json")
    return {
        "start_views": [os.path.join(target_dir_path, "start_views", img) for img in start_img_ls],
        "current_views": [os.path.join(target_dir_path, "current_views", img) for img in current_img_ls],
        "goal_views": [os.path.join(target_dir_path, "goal_views", img) for img in goal_img_ls],
        "qa_item": qa_item,
        "scene_info": scene_info,
        "goal_scene_info": goal_scene_info,
        "base_path": base_path
    }


def get_immovable_objects_from_goal_info(goal_scene_info_path: str) -> list:
    immovable_objects = []
    if not os.path.exists(goal_scene_info_path):
        return immovable_objects
    try:
        with open(goal_scene_info_path, "r", encoding="utf-8") as f:
            goal_data = json.load(f)
        goal_info = goal_data.get("scene_info", goal_data)
        goal_objects = goal_info.get("objects", [])
        for obj in goal_objects:
            pos = obj.get('location')
            rot = obj.get('rotation_euler')
            if isinstance(pos, str) and isinstance(rot, str):
                pos_vals = pos.split(',')
                rot_vals = rot.split(',')
                concat_pose = pos_vals + rot_vals
                if all(abs(float(c.strip())) < 1e-7 for c in concat_pose):
                    immovable_objects.append(obj.get("name"))
    except Exception as e:
        print(f"Warning: Failed to read immovable objects from goal info: {e}")
    return [name for name in immovable_objects if name]


def interpret_scene_info(scene_info: dict, exclude_names: list = None) -> dict:
    if exclude_names is None:
        exclude_names = []
    info_str = "Scene Information (Objects and Cameras):\n"
    for obj in scene_info.get('objects', []):
        if obj['name'] in exclude_names:
            continue
        info_str += f"- Name: {obj['name']}, Location: {obj['position']}, Rotation: {obj['rotation']}\n"
    for views in scene_info.get('views', []):
        info_str += f"- Camera Name: {views['camera_name']}, Camera Location: {views['camera_pose']['position']}, Camera Rotation: {views['camera_pose']['rotation']}, FOV: {views['camera_pose']['fov']}, Focal Length: {views['camera_pose']['focal_length']}, Resolution: {views['camera_pose']['resolution']}\n"
    return info_str


def construct_qa_context(data_item: dict) -> tuple[str, list]:
    assert len(data_item['start_views']) == len(data_item['current_views']) == len(data_item['goal_views']), (
        "Number of start views, current views, and goal views must be the same."
    )
    camera_names = [os.path.splitext(os.path.basename(i))[0] for i in data_item['start_views']]
    context_lines = []
    image_ls = []
    for start_view, goal_view, camera_name in zip(data_item['start_views'], data_item['goal_views'], camera_names):
        context_lines.append(f"This is the image shot by camera '{camera_name}' from the start scene <image>")
        context_lines.append(f"This is the image shot by camera '{camera_name}' from the goal scene <image>")
        image_ls.append(start_view)
        image_ls.append(goal_view)

    context_lines.append("These are the images shot by")
    for current_view, camera_name in zip(data_item['current_views'], camera_names):
        context_lines.append(f"camera '{camera_name}', ")
        image_ls.append(current_view)
    context_lines.append(f", {'<image>' * len(data_item['current_views'])} respectively, from the current scene.")
    context = "\n".join(context_lines) + "\n"
    image_ls = [os.path.relpath(img_path, data_item['base_path']) for img_path in image_ls]
    return context, image_ls

def construct_qa_item(data_item: dict) -> list:
    QA_list = []
    with open(data_item['qa_item'], 'r', encoding='utf-8') as f:
        qa_items = json.load(f)
    with open(data_item['scene_info'], 'r', encoding='utf-8') as f:
        scene_info = json.load(f)
    immovable_objects = get_immovable_objects_from_goal_info(data_item['goal_scene_info'])
    scene_info_str = interpret_scene_info(scene_info, exclude_names=immovable_objects)
    context, image_ls = construct_qa_context(data_item)

    for qa in qa_items:
        question = qa["question_pos"]
        answer = qa["answer_pos"]
        single_qa_item = {
            "image": image_ls,
            "conversations": [
                {
                    "from": SYSTEM_NAME,
                    "value": SYSTEM_PROMPT
                },
                {
                    "from": USER_NAME,
                    "value": context + f"This is the scene info of the start scene: {scene_info_str}. " + "Now answer the question: " + question
                },
                {
                    "from": ASSISTANT_NAME,
                    "value": THINK_TAG[0] + THINK_TAG[1] + answer
                }
            ]
        }
        QA_list.append(single_qa_item)
    return QA_list

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QA jsonl from 3DFront placement dataset.")
    parser.add_argument(
        "--base_path",
        type=str,
        required=True,
        help="Base dataset path that contains sample directories.",
    )
    parser.add_argument(
        "--output_jsonl_name",
        type=str,
        default="all_QA_items.jsonl",
        help="Output jsonl file name (written under --base_path).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_path = args.base_path
    target_dirs = get_target_directory_path(base_path)
    all_QA_items = []
    for target_dir in target_dirs:
        data_item = collect_qa_data_item(target_dir, base_path)
        QA_items = construct_qa_item(data_item)
        all_QA_items.extend(QA_items)
    with open(os.path.join(base_path, args.output_jsonl_name), 'w', encoding='utf-8') as f:
        for item in all_QA_items:
            f.write(json.dumps(item) + '\n')


if __name__ == "__main__":
    main()
