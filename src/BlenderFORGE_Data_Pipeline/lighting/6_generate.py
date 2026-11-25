"""Generate a lighting sample with the original light and camera sampling rules."""
import argparse
import importlib
import json
from pathlib import Path
import random
import shutil
import sys
import uuid

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
analyzer = importlib.import_module('1_light_analyzer')
modifier = importlib.import_module('2_light_modifier')
regions = importlib.import_module('3_camera_region_calculator')
cameras = importlib.import_module('4_camera_placement')
rendering = importlib.import_module('5_rendering')
sample_io = importlib.import_module('7_sample_io')
from common.blender_state import configure_render
from common.contract import append_report, check_sample, require


def generate_sample(source, output, config):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(source.is_file(), f'Asset does not exist: {source}')
    if output.exists():
        require(check_sample(output)['task'] == 'lighting', 'Existing output belongs to another task')
        return True
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent/('.tmp_'+output.name)
    for attempt in range(config['max_retries']+1):
        if temp.exists():
            shutil.rmtree(temp)
        temp.mkdir()
        losses = {}
        retry_quality = False
        report = {'sample':output.name, 'source':source.parent.name+'/'+source.name, 'attempt':attempt}
        try:
            bpy.ops.wm.open_mainfile(filepath=str(source))
            scene_analysis = analyzer.LightAnalyzer().analyze_scene()
            lights = scene_analysis['light_objects']
            require(len(lights) >= config['scene_config']['min_lights_required'], 'Insufficient lights')
            names = [light['name'] for light in lights]
            sample_io.check_supported_scene(names)
            modifications = modifier.LightModifier(config['light_modification']).modify_lights(lights)
            camera_config = config['camera_config']
            bounds = scene_analysis['scene_bounds']
            valid_regions = regions.CameraRegionCalculator(camera_config).compute_valid_regions_for_lights(lights, bounds)
            result = cameras.place_cameras_for_lights(valid_regions, bounds, num_cameras=camera_config['num_views'],
                placement_strategy='greedy', camera_config=camera_config,
                modified_lights=[m['light_name'] for m in modifications if m.get('modified', True)])
            camera_names = result['camera_names']
            require(len(camera_names) == camera_config['num_views'], 'Incomplete camera set')
            configure_render(config['render_config'])
            require(bpy.context.scene.render.image_settings.file_format == 'PNG', 'The v1 profile requires PNG output')
            sample_id = str(uuid.uuid4())
            rendering.render_views(temp/'start_views', camera_names)
            sample_io.save_state(temp, 'start', sample_id, camera_names, names, config)
            for mod in modifications:
                if mod.get('modified', True):
                    obj = bpy.data.objects[mod['light_name']]
                    obj.data.energy = mod['new_energy']
                    obj.data.color = mod['new_color']
            rendering.render_views(temp/'goal_views', camera_names)
            losses = rendering.photometric_losses(temp, camera_names)
            retry_quality = min(losses.values()) < config['validation_config']['min_photometric_difference']
            require(not retry_quality, 'At least one view has insufficient photometric change')
            sample_io.save_state(temp, 'goal', sample_id, camera_names, names, config)
            checks = sample_io.finalize(temp, config, source, names, sample_id, losses)
            temp.rename(output)
            append_report(output.parent/'generation_report.jsonl', {**report, 'passed':True, 'sample_id':sample_id, 'checks':checks})
            return True
        except Exception as exc:
            (temp/'.SUCCESS').unlink(missing_ok=True)
            append_report(output.parent/'generation_report.jsonl', {**report, 'passed':False, 'reason':str(exc), 'image_l1_by_camera':losses})
            print(f'Failed {output.name}: {exc}', flush=True)
            if not retry_quality:
                break
    if temp.exists():
        shutil.rmtree(temp)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=HERE/'config.json')
    parser.add_argument('--blend-file', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--seed', type=int)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    config = json.loads(args.config.read_text())
    if args.seed is not None:
        config['random_seed'] = args.seed
    require(type(config['max_retries']) is int and config['max_retries'] >= 0, 'max_retries must be nonnegative')
    require(config['light_modification']['max_lights_to_modify'] > 0 and
            any(config['light_modification']['modify_'+k] for k in ('energy','color')), 'No light modification configured')
    require(config['scene_config']['min_lights_required'] > 0 and config['camera_config']['num_views'] > 0, 'Invalid light/view count')
    random.seed(config['random_seed'])
    np.random.seed(config['random_seed'])
    return 0 if generate_sample(args.blend_file, args.output_dir, config) else 1


if __name__ == '__main__':
    raise SystemExit(main())
