"""Read-only audit of complete samples in supported v1 profiles."""
import argparse
from pathlib import Path
from common.contract import check_sample


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    samples=[args.directory] if (args.directory/'metadata.json').is_file() else sorted(p for p in args.directory.rglob('sample_*') if p.is_dir())
    failed=0
    for sample in samples:
        try:
            check_sample(sample)
            print(f'PASS {sample}')
        except (OSError,ValueError,KeyError,TypeError) as exc:
            failed+=1
            print(f'FAIL {sample}: {exc}')
    print(f'{len(samples)-failed}/{len(samples)} passed')
    return 1 if failed or not samples else 0


if __name__=='__main__':
    raise SystemExit(main())
