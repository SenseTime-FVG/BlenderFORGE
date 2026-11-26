"""Bounded host scheduler for both material backends."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common.contract import check_sample, require, write_json


def run_task(index, config, backend, blender, temporary, threads):
    output = Path(config['paths']['output_base_dir'])
    sample = output/f'sample_{index:05d}'
    expected_backend = 'principled_bsdf' if backend == 'basic' else backend
    if sample.exists():
        metadata = check_sample(sample)
        require(metadata['task'] == 'material' and metadata['backend'] == expected_backend,'Existing sample belongs to another task/backend')
        return True
    logs = output/'logs'
    logs.mkdir(exist_ok=True)
    batch = config['batch_generation']
    for attempt in range(batch['max_attempts']):
        task = dict(config,random_seed=config['random_seed']+index+attempt*batch['num_samples'])
        filename = Path(temporary)/f'{index}.json'
        write_json(filename,task)
        with (logs/f'sample_{index:05d}_attempt_{attempt:03d}.log').open('w') as log:
            result = subprocess.run([blender,'-b','-t',str(threads),'--python-exit-code','1','--python',
                str(HERE/'3_generate.py'),'--','--backend',backend,'--config',str(filename),'--output-dir',str(sample)],
                stdout=log,stderr=subprocess.STDOUT)
        if result.returncode == 0:
            metadata = check_sample(sample)
            require(metadata['task'] == 'material' and metadata['backend'] == expected_backend,'Worker produced another task/backend')
            return True
        if sample.exists():
            check_sample(sample)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('basic','infinigen'),required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--blender',default=os.environ.get('BLENDER_PATH','blender'))
    parser.add_argument('--blend-file',type=Path)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--num-samples',type=int)
    parser.add_argument('--start-id',type=int)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--concurrency',type=int,default=4)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--mode',choices=('parallel','serial'),default='parallel')
    parser.add_argument('--jsonl',type=Path)
    args = parser.parse_args()
    path = (args.config or HERE/args.backend/'config.json').resolve()
    config = json.loads(path.read_text())
    for key,value in config['paths'].items():
        p = Path(value).expanduser()
        config['paths'][key] = str(p if p.is_absolute() else (path.parent/p).resolve())
    if args.blend_file:
        config['paths']['blend_file'] = str(args.blend_file.resolve())
    if args.output_dir:
        config['paths']['output_base_dir'] = str(args.output_dir.resolve())
    if args.seed is not None:
        config['random_seed'] = args.seed
    batch = config['batch_generation']
    for arg,key in (('num_samples','num_samples'),('start_id','start_sample_id')):
        value = getattr(args,arg)
        if value is not None:
            batch[key] = value
    require(args.concurrency > 0 and args.threads > 0 and batch['num_samples'] > 0 and
            batch['max_attempts'] > 0 and batch['start_sample_id'] >= 0,'Invalid worker/sample/attempt count')
    require(Path(config['paths']['blend_file']).is_file(),'Blend asset not found')
    if args.backend == 'infinigen':
        require(Path(config['paths']['material_catalog']).is_file(),'Material catalog not found')
    blender = shutil.which(args.blender)
    require(blender is not None,f'Blender executable not found: {args.blender}')
    if args.jsonl:
        require(not args.jsonl.exists(),'JSONL already exists; choose a new filename')
    output = Path(config['paths']['output_base_dir'])
    output.mkdir(parents=True,exist_ok=True)
    indices = list(range(batch['start_sample_id'],batch['start_sample_id']+batch['num_samples']))
    with tempfile.TemporaryDirectory(prefix='.worker_config_',dir=output) as temporary:
        with ThreadPoolExecutor(max_workers=1 if args.mode == 'serial' else args.concurrency) as pool:
            results = list(pool.map(lambda i:run_task(i,config,args.backend,blender,temporary,args.threads),indices))
    write_json(output/'batch_summary.json',{'backend':args.backend,'samples':[{'sample_index':i,'passed':ok} for i,ok in zip(indices,results)]})
    if not all(results):
        print('Some material samples failed; inspect logs/ and generation_report.jsonl.',file=sys.stderr)
        return 1
    if args.jsonl:
        return subprocess.run([sys.executable,str(HERE/'utils/export_dataset.py'),str(output),str(args.jsonl)]).returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
