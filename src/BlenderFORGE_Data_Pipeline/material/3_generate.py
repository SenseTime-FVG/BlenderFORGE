"""Generate basic or Infinigen material samples using the shared v1 contract."""
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
sys.path.insert(0,str(HERE.parent))
rendering = importlib.import_module('material.1_rendering')
sample_io = importlib.import_module('material.2_sample_io')
from common.blender_state import configure_render
from common.contract import append_report, check_sample, require


def generate_sample(config, backend, output):
    output = Path(output).resolve()
    if output.exists():
        metadata = check_sample(output)
        require(metadata['task'] == 'material' and metadata['backend'] == backend,'Existing output belongs to another task/backend')
        return True
    output.parent.mkdir(parents=True,exist_ok=True)
    temp = output.parent/('.tmp_'+output.name)
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()
    source = Path(config['paths']['blend_file'])
    report = {'sample':output.name,'backend':backend,'seed':config['random_seed']}
    try:
        random.seed(config['random_seed'])
        np.random.seed(config['random_seed'])
        if backend == 'principled_bsdf':
            modifier = importlib.import_module('material.basic.1_sampling').BSDFModifier(config)
            start_params = modifier.sample_parameters()
            shader = None
        else:
            modifier = importlib.import_module('material.infinigen.1_sampling').MaterialModifier(config['paths']['material_catalog'],config)
            mode = config['material_modification']
            selection = mode['shader_selection']
            plan = modifier.plan_modification(shader_category=selection['category_filter'],shader_name=selection['specific_shader'],
                modification_type=mode['modification_type'],param_strategy=mode['param_strategy'])
            shader = plan['shader']
            start_params,goal_params = plan['start_params'],plan['goal_params']
        sample_id = str(uuid.uuid4())
        camera = config['scene']['target_camera']
        for state in ('start','goal'):
            attempts = config.get('max_goal_attempts',1) if state == 'goal' else 1
            for attempt in range(attempts):
                if state == 'goal' and backend == 'principled_bsdf':
                    goal_params,_ = modifier.mutate_parameters(start_params)
                params = start_params if state == 'start' else goal_params
                script = sample_io.make_script(backend,config,params,shader)
                (temp/f'{state}.py').write_text(script)
                bpy.ops.wm.open_mainfile(filepath=str(source))
                sample_io.check_supported_scene(config)
                configure_render(config['render_config'])
                existing_images = {image.as_pointer() for image in bpy.data.images}
                exec(compile(script,str(temp/f'{state}.py'),'exec'),{'__name__':'__main__'})
                require(not any(image.source == 'FILE' and image.as_pointer() not in existing_images for image in bpy.data.images),
                        'Shader construction loads external image files; this profile requires self-contained procedural shaders')
                rendering.render_view(temp/f'{state}_views'/f'{camera}.png',camera)
                if state == 'goal':
                    try:
                        quality = rendering.validate_pair(temp/'start_views'/f'{camera}.png',temp/'goal_views'/f'{camera}.png',backend,config)
                    except ValueError as exc:
                        append_report(output.parent/'generation_report.jsonl',{**report,'passed':False,'goal_attempt':attempt,'reason':str(exc)})
                        if attempt+1 < attempts:
                            continue
                        raise
                sample_io.save_state(temp,state,sample_id,config,backend)
                break
        checks = sample_io.finalize(temp,config,source,backend,sample_id,quality,rendering)
        temp.rename(output)
        append_report(output.parent/'generation_report.jsonl',{**report,'passed':True,'sample_id':sample_id,'checks':checks})
        return True
    except Exception as exc:
        append_report(output.parent/'generation_report.jsonl',{**report,'passed':False,'reason':str(exc)})
        if temp.exists():
            shutil.rmtree(temp)
        print(f'Material sample failed: {exc}',flush=True)
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('basic','infinigen'),required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--blend-file',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seed',type=int)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    path = (args.config or HERE/args.backend/'config.json').resolve()
    config = json.loads(path.read_text())
    for key in ('blend_file','material_catalog'):
        if key in config['paths']:
            p = Path(config['paths'][key]).expanduser()
            config['paths'][key] = str(p if p.is_absolute() else (path.parent/p).resolve())
    if args.blend_file:
        config['paths']['blend_file'] = str(args.blend_file.resolve())
    if args.seed is not None:
        config['random_seed'] = args.seed
    require(type(config['random_seed']) is int and 0 <= config['random_seed'] < 2**32,'Seed must be a uint32 integer')
    require(config.get('max_goal_attempts',1) > 0 and config['replay_image_tolerance'] >= 0,'Invalid attempts/tolerance')
    require(config['material_modification']['modification_type'] in ('single_param','multi_param'),'Unsupported modification type')
    require(args.backend != 'infinigen' or config.get('max_goal_attempts',1) == 1,'Infinigen replans in the batch retry; max_goal_attempts must be 1')
    backend = 'principled_bsdf' if args.backend == 'basic' else 'infinigen'
    return 0 if generate_sample(config,backend,args.output_dir) else 1


if __name__ == '__main__':
    raise SystemExit(main())
