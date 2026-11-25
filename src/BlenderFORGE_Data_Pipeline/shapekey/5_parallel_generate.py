"""Run shape-key generation with bounded workers and validated completion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common.contract import check_sample, require, write_json


def run_task(index, config, blender, temporary, threads):
    sample=Path(config['save_data_path'])/f'sample_{index:05d}'
    if sample.exists():
        metadata=check_sample(sample)
        require(metadata['task']=='shapekey','Existing sample belongs to a different task')
        return True
    task=dict(config, start_sample_id=index, num_samples=1, random_seed=config['random_seed']+index)
    filename=Path(temporary)/f'{index}.json'
    write_json(filename,task)
    log_dir=Path(config['save_data_path'])/'logs'
    log_dir.mkdir(exist_ok=True)
    with (log_dir/f'sample_{index:05d}.log').open('w') as log:
        result=subprocess.run([blender,'-b','-t',str(threads),'--python-exit-code','1','--python',
                               str(HERE/'4_generate.py'),'--','--config',str(filename)],stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        return False
    metadata=check_sample(sample)
    require(metadata['task']=='shapekey','Worker produced a different task')
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=HERE/'config.json')
    parser.add_argument('--blender',default=os.environ.get('BLENDER_PATH','blender'))
    parser.add_argument('--asset-dir')
    parser.add_argument('--output-dir')
    parser.add_argument('--num-samples',type=int)
    parser.add_argument('--start-id',type=int)
    parser.add_argument('--concurrency',type=int,default=4)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--mode',choices=('parallel','serial'),default='parallel')
    parser.add_argument('--jsonl',type=Path)
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    for key in ('blender_asset_path','save_data_path','shapekey_modifiable_path','shapekey_rephrase_path'):
        path=Path(config[key]).expanduser()
        config[key]=str(path if path.is_absolute() else (args.config.resolve().parent/path).resolve())
    for arg,key in (('asset_dir','blender_asset_path'),('output_dir','save_data_path'),('num_samples','num_samples'),('start_id','start_sample_id')):
        value=getattr(args,arg)
        if value is not None:
            config[key]=str(Path(value).resolve()) if arg in ('asset_dir','output_dir') else value
    blender=shutil.which(args.blender)
    require(blender is not None, f'Blender executable not found: {args.blender}')
    require(args.concurrency>0 and args.threads>0 and config['num_samples']>0 and config['start_sample_id']>=0,'Invalid concurrency, threads or sample range')
    require(any(Path(config['blender_asset_path']).glob('*.blend')),'No blend assets found')
    if args.jsonl:
        require(not args.jsonl.exists(),'JSONL already exists; choose a new filename')
    output=Path(config['save_data_path'])
    output.mkdir(parents=True,exist_ok=True)
    indices=list(range(config['start_sample_id'],config['start_sample_id']+config['num_samples']))
    with tempfile.TemporaryDirectory(prefix='.worker_config_',dir=output) as temporary:
        if args.mode=='serial':
            filename=Path(temporary)/'batch.json'
            write_json(filename,config)
            result=subprocess.run([blender,'-b','-t',str(args.threads),'--python-exit-code','1','--python',str(HERE/'4_generate.py'),'--','--config',str(filename)])
            if result.returncode:
                return result.returncode
            results=[check_sample(output/f'sample_{i:05d}')['task']=='shapekey' for i in indices]
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                results=list(pool.map(lambda index:run_task(index,config,blender,temporary,args.threads),indices))
    write_json(output/'batch_summary.json',{'mode':args.mode,'samples':[{'sample_index':i,'passed':ok} for i,ok in zip(indices,results)]})
    if not all(results):
        return 1
    if args.jsonl:
        return subprocess.run([sys.executable,str(HERE/'utils/export_dataset.py'),str(output),str(args.jsonl)]).returncode
    return 0


if __name__=='__main__':
    raise SystemExit(main())
