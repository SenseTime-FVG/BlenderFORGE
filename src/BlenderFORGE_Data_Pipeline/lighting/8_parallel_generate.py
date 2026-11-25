"""Launch bounded lighting workers and validate every completed sample."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.contract import check_sample, require, write_json


def run_task(index, config, assets, blender, temporary, threads):
    output = Path(config['save_data_path'])
    sample = output/f'sample_{index:05d}'
    if sample.exists():
        require(check_sample(sample)['task'] == 'lighting', 'Existing sample belongs to another task')
        return True
    log_dir = output/'logs'
    log_dir.mkdir(exist_ok=True)
    for attempt in range(config['max_asset_attempts']):
        source = assets[(index+attempt) % len(assets)]
        task = dict(config, random_seed=config['random_seed']+index+attempt*config['num_samples'])
        filename = Path(temporary)/f'{index}.json'
        write_json(filename, task)
        with (log_dir/f'sample_{index:05d}_asset_{attempt:03d}.log').open('w') as log:
            result = subprocess.run([blender, '-b', '-t', str(threads), '--python-exit-code', '1', '--python',
                str(HERE/'6_generate.py'), '--', '--config', str(filename), '--blend-file', str(source),
                '--output-dir', str(sample)], stdout=log, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            require(check_sample(sample)['task'] == 'lighting', 'Worker produced another task')
            return True
        if sample.exists():
            # Preserve an invalid existing result for diagnosis; never bless or overwrite it.
            check_sample(sample)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=HERE/'config.json')
    parser.add_argument('--blender', default=os.environ.get('BLENDER_PATH', 'blender'))
    parser.add_argument('--asset-dir')
    parser.add_argument('--output-dir')
    parser.add_argument('--num-samples', type=int)
    parser.add_argument('--start-id', type=int)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--concurrency', type=int, default=4)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--mode', choices=('parallel','serial'), default='parallel')
    parser.add_argument('--shuffle-assets', action='store_true')
    parser.add_argument('--jsonl', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    for key in ('blender_asset_path', 'save_data_path'):
        path = Path(config[key]).expanduser()
        config[key] = str(path if path.is_absolute() else (args.config.resolve().parent/path).resolve())
    for arg,key in (('asset_dir','blender_asset_path'), ('output_dir','save_data_path'),
                    ('num_samples','num_samples'), ('start_id','start_sample_id'), ('seed','random_seed')):
        value = getattr(args, arg)
        if value is not None:
            config[key] = str(Path(value).resolve()) if arg in ('asset_dir','output_dir') else value
    require(args.concurrency > 0 and args.threads > 0 and config['num_samples'] > 0 and
            config['start_sample_id'] >= 0 and config['max_asset_attempts'] > 0, 'Invalid worker/sample/attempt count')
    asset_dir = Path(config['blender_asset_path'])
    require(asset_dir.is_dir(), f'Asset directory does not exist: {asset_dir}')
    assets = [p/config['asset_config']['blend_file_name'] for p in sorted(asset_dir.iterdir())
              if p.is_dir() and (p/config['asset_config']['blend_file_name']).is_file()]
    require(assets, 'No asset subdirectories with the configured blend filename')
    if args.shuffle_assets:
        random.Random(config['random_seed']).shuffle(assets)
    blender = shutil.which(args.blender)
    require(blender is not None, f'Blender executable not found: {args.blender}')
    if args.jsonl:
        require(not args.jsonl.exists(), 'JSONL already exists; choose another filename')
    output = Path(config['save_data_path'])
    output.mkdir(parents=True, exist_ok=True)
    indices = list(range(config['start_sample_id'], config['start_sample_id']+config['num_samples']))
    with tempfile.TemporaryDirectory(prefix='.worker_config_', dir=output) as temporary:
        with ThreadPoolExecutor(max_workers=1 if args.mode == 'serial' else args.concurrency) as pool:
            results = list(pool.map(lambda index:run_task(index, config, assets, blender, temporary, args.threads), indices))
    write_json(output/'batch_summary.json', {'samples':[{'sample_index':i, 'passed':ok} for i,ok in zip(indices,results)]})
    if not all(results):
        print('Some lighting samples failed; inspect logs/ and generation_report.jsonl.', file=sys.stderr)
        return 1
    if args.jsonl:
        return subprocess.run([sys.executable, str(HERE/'utils/export_dataset.py'), str(output), str(args.jsonl)]).returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
