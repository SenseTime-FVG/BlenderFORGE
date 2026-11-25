"""Generate complete v1 shape-key samples using the original sampling rules."""
import argparse
import importlib
import json
import logging
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
sampling = importlib.import_module('1_key_sampling')
rendering = importlib.import_module('2_rendering')
sample_io = importlib.import_module('3_sample_io')
from common.blender_state import configure_render
from common.contract import append_report, check_sample, require


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    for key in ('blender_asset_path','save_data_path','shapekey_modifiable_path','shapekey_rephrase_path'):
        value = Path(config[key]).expanduser()
        config[key] = str(value if value.is_absolute() else (path.parent/value).resolve())
    for key in ('num_of_key_change','Max_num_of_key_displayed','num_samples','max_asset_attempts'):
        require(type(config[key]) is int and config[key] > 0, f'{key} must be a positive integer')
    require(type(config['Max_retry']) is int and config['Max_retry'] >= 0, 'Max_retry must be nonnegative')
    require(0 <= config['rename_probability'] <= 1, 'rename_probability must be in [0,1]')
    require(0 < config['min_change_proportion'] < 1, 'min_change_proportion must be in (0,1)')
    require('camera_selection' not in config, 'camera_selection belongs to the retired single-view experiment; remove it to use all asset cameras')
    return config


def apply_values(key_values, renamed, state):
    # Preserve the old sampler's six-decimal assignment, then export actual RNA values.
    for key, values in key_values.items():
        bpy.data.objects[key[0]].data.shape_keys.key_blocks[renamed[key]].value = float(f"{values[state+'_value']:.6f}")
    bpy.context.view_layer.update()


def generate_sample(config, sample_index):
    output = Path(config['save_data_path'])
    output.mkdir(parents=True, exist_ok=True)
    final = output/f'sample_{sample_index:05d}'
    if final.exists():
        metadata = check_sample(final)
        require(metadata['task']=='shapekey', 'Existing output belongs to a different task')
        return True
    assets = list(Path(config['blender_asset_path']).glob('*.blend'))
    require(assets, 'No blend assets found')
    rephrases = json.loads(Path(config['shapekey_rephrase_path']).read_text())
    temp = output/f'.tmp_sample_{sample_index:05d}'
    for asset_attempt in range(config['max_asset_attempts']):
        source = random.choice(assets)
        report = {'sample_index':sample_index,'source':source.name,'asset_attempt':asset_attempt}
        try:
            bpy.ops.wm.open_mainfile(filepath=str(source))
            available = sampling.get_modifiable_shapekeys(source.name, config['shapekey_modifiable_path'])
            require(available, 'Asset has no listed modifiable keys')
            displayed = sampling.select_keys(available,config['Max_num_of_key_displayed'])
        except Exception as exc:
            append_report(output/'generation_report.jsonl', {**report,'passed':False,'reason':str(exc)})
            continue
        for value_attempt in range(max(1,config['Max_retry'])):
            loss_by_camera = {}
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir()
            try:
                if value_attempt:
                    bpy.ops.wm.open_mainfile(filepath=str(source))
                changed = sampling.select_keys(displayed,config['num_of_key_change'])
                values = sampling.generate_key_values(displayed,changed,config['min_change_proportion'])
                renamed = sampling.rename_keys(displayed,rephrases,config['rename_probability'])
                sampling.apply_key_renames(renamed)
                public_keys = [{'object_name':key[0],'key_name':renamed[key]} for key in displayed]
                editable = {}
                for item in public_keys:
                    editable.setdefault(item['object_name'],[]).append(item['key_name'])
                sample_io.check_supported_scene(editable)
                configure_render(config['render_config'])
                cameras = [obj.name for obj in bpy.data.objects if obj.type=='CAMERA']
                require(cameras, 'No cameras found')
                require(all(name in bpy.context.scene.objects for name in cameras), 'Cameras outside the active scene are unsupported')
                sample_id = str(uuid.uuid4())
                apply_values(values,renamed,'start')
                rendering.render_views(temp/'start_views',cameras)
                sample_io.save_state(temp,'start',sample_id,cameras,editable,public_keys,config)
                apply_values(values,renamed,'goal')
                rendering.render_views(temp/'goal_views',cameras)
                loss_by_camera = rendering.photometric_losses(temp/'start_views',temp/'goal_views',cameras)
                require(max(loss_by_camera.values()) > config['photometric_loss_threshold'], 'Photometric change below threshold')
                sample_io.save_state(temp,'goal',sample_id,cameras,editable,public_keys,config)
                checks = sample_io.finalize(temp,config,source,public_keys,sample_id,loss_by_camera)
                temp.rename(final)
                append_report(output/'generation_report.jsonl',{**report,'value_attempt':value_attempt,'passed':True,
                              'sample_id':sample_id,'checks':checks,'all_camera_losses':loss_by_camera})
                logging.info('Generated %s',final)
                return True
            except Exception as exc:
                (temp/'.SUCCESS').unlink(missing_ok=True)
                append_report(output/'generation_report.jsonl',{**report,'value_attempt':value_attempt,'passed':False,
                              'reason':str(exc),'all_camera_losses':loss_by_camera})
                logging.warning('%s attempt failed: %s',final.name,exc)
        if temp.exists():
            shutil.rmtree(temp)
    return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(HERE/'config.json'))
    parser.add_argument('--asset-dir')
    parser.add_argument('--output-dir')
    parser.add_argument('--num-samples',type=int)
    parser.add_argument('--start-id',type=int)
    parser.add_argument('--seed',type=int)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    args=parser.parse_args(argv)
    config=load_config(args.config)
    for arg,key in (('asset_dir','blender_asset_path'),('output_dir','save_data_path'),
                    ('num_samples','num_samples'),('start_id','start_sample_id'),('seed','random_seed')):
        value=getattr(args,arg)
        if value is not None:
            config[key]=str(Path(value).resolve()) if arg in ('asset_dir','output_dir') else value
    require(config['num_samples']>0 and config['start_sample_id']>=0,'Invalid sample range')
    logging.basicConfig(level=config.get('log_level','INFO'),format='%(levelname)s: %(message)s')
    random.seed(config['random_seed'])
    np.random.seed(config['random_seed'])
    failed=0
    for index in range(config['start_sample_id'],config['start_sample_id']+config['num_samples']):
        if not generate_sample(config,index):
            failed+=1
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
