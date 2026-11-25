"""Shared source validation, file preparation and Blender process execution."""
import json
import shutil
import subprocess
from pathlib import Path
from typing import List


REQUIRED_FILES = [
    "metadata.json",
    "start_info.json",
    "goal_info.json",
    "start.py",
    "goal.py",
    "start.blend",
    "start_views",
    "goal_views",
    ".SUCCESS",
]


def list_samples(input_root: Path, sample_id: str | None) -> List[Path]:
    if sample_id:
        target = input_root / sample_id
        return [target] if target.is_dir() else []
    return sorted([p for p in input_root.iterdir() if p.is_dir() and p.name.startswith("sample_")])


def validate_sample(sample_dir: Path) -> List[str]:
    metadata_path = sample_dir / "metadata.json"
    if metadata_path.is_file():
        with metadata_path.open() as stream:
            if json.load(stream).get("schema_version") == "1.0":
                raise ValueError("placement/qa is legacy-only until its v1 migration; use a legacy source sample")
    missing = []
    for name in REQUIRED_FILES:
        path = sample_dir / name
        if not path.exists():
            missing.append(name)
    return missing


def prepare_output_sample(sample_dir: Path, out_dir: Path, force: bool) -> None:
    if out_dir.exists() and not force:
        raise FileExistsError(f"Output exists; use --force to replace it: {out_dir}")
    if out_dir.exists() and force:
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in ("start_views", "goal_views"):
        (out_dir / name).mkdir()
        for source in sorted((sample_dir / name).glob("*.png")):
            shutil.copy2(source, out_dir / name / source.name)

    for file_name in ["metadata.json", "start_info.json", "goal_info.json", "start.py", "goal.py"]:
        shutil.copy2(sample_dir / file_name, out_dir / file_name)


def run_blender(
    blender_path: Path,
    blender_script: Path,
    sample_dir: Path,
    out_dir: Path,
    config_path: Path,
) -> int:
    cmd = [
        str(blender_path),
        "--background",
        "--python-exit-code",
        "1",
        "--python",
        str(blender_script),
        "--",
        "--sample_dir",
        str(sample_dir),
        "--output_dir",
        str(out_dir),
        "--config",
        str(config_path),
    ]
    print("[RUN]", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    return result.returncode


def write_success_marker(out_dir: Path) -> None:
    marker = out_dir / ".SUCCESS"
    tmp = out_dir / ".SUCCESS.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        f.write("OK\n")
    tmp.replace(marker)
