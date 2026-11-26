import argparse
import json
from pathlib import Path


def count_shape_keys(data: dict) -> int:
    total = 0
    for file_result in data.values():
        shape_keys = file_result.get("shape_keys", {})
        for key_list in shape_keys.values():
            total += len(key_list)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count total shape keys in a JSON file (duplicates included)."
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "resources/shape_keys_output.json"),
        help="Path to shape keys JSON (default: shape_keys_output.json)",
    )
    args = parser.parse_args()

    json_path = Path(args.json_path)
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    total_shape_keys = count_shape_keys(data)
    print(total_shape_keys)


if __name__ == "__main__":
    main()
