"""Check complete v1 samples without loading Blender or modifying the dataset."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.contract import check_sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    samples = [args.directory] if (args.directory / "metadata.json").exists() else sorted(args.directory.rglob("sample_*"))
    failures = 0
    for sample in samples:
        try:
            check_sample(sample)
            print(f"PASS {sample}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures += 1
            print(f"FAIL {sample}: {exc}")
    print(f"{len(samples) - failures}/{len(samples)} passed")
    return 1 if failures or not samples else 0


if __name__ == "__main__":
    raise SystemExit(main())
