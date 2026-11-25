"""Shape-key rendering and the original photometric acceptance rule."""
from pathlib import Path
import numpy as np
import bpy


def render_views(output_dir, camera_names):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    if scene.render.image_settings.file_format != "PNG":
        raise ValueError("Shape-key sample views require PNG output")
    for name in camera_names:
        if not name or any(c in name for c in '/\\\x00') or name in (".", ".."):
            raise ValueError(f"Unsafe camera filename: {name!r}")
        scene.camera = bpy.data.objects[name]
        scene.render.filepath = str(directory / f"{name}.png")
        bpy.ops.render.render(write_still=True)


def calculate_photometric_loss(img1_path: str, img2_path: str) -> float:
    """
    Calculate photometric loss between two images using L1 distance.

    Args:
        img1_path: Path to first image
        img2_path: Path to second image

    Returns:
        Photometric loss value (normalized to [0, 1])
    """
    try:
        from PIL import Image

        img1 = Image.open(img1_path).convert('RGB')
        img2 = Image.open(img2_path).convert('RGB')

        arr1 = np.array(img1, dtype=np.float32) / 255.0
        arr2 = np.array(img2, dtype=np.float32) / 255.0

        photometric_loss = np.mean(np.abs(arr1 - arr2))

        return float(photometric_loss)
    except Exception as e:
        raise RuntimeError(f"Failed to calculate photometric loss between {img1_path} and {img2_path}: {e}")

def photometric_losses(start_dir, goal_dir, camera_names):
    """Return the original float32 image loss, keyed by camera name."""
    if not camera_names:
        raise ValueError("No cameras to compare")
    return {name: calculate_photometric_loss(str(Path(start_dir)/f'{name}.png'),
                                           str(Path(goal_dir)/f'{name}.png'))
            for name in camera_names}
