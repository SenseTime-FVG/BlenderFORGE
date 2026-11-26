import json
import os

def extract_shapekey_namelist(input_json_path, output_json_path):
    with open(input_json_path, 'r') as infile:
        data = json.load(infile)

    shapekey_namelist = set()
    for item in data.values():
        shape_keys = item["shape_keys"]
        for _, keylist in shape_keys.items():
            for key in keylist:
                shapekey_namelist.add(f"{key}") if key != "Basis" else None

    with open(output_json_path, 'w') as outfile:
        json.dump(list(shapekey_namelist), outfile, indent=2)
    print(f"Extracted {len(shapekey_namelist)} unique shape key names to {output_json_path}")

if __name__ == "__main__":
    input_json = os.path.join(os.path.dirname(__file__), '..', 'resources', 'shape_keys_output.json')
    output_json = os.path.join(os.path.dirname(__file__), '..', 'resources', 'shapekey_namelist.json')
    extract_shapekey_namelist(input_json, output_json)
