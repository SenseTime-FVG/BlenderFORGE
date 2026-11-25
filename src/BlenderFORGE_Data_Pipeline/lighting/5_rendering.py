"""Render lighting views and evaluate the original float64 RGB L1 metric."""
from pathlib import Path

import bpy
import numpy as np
from PIL import Image


def render_views(directory, camera_names):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    for name in camera_names:
        if not name or any(c in name for c in '/\\\x00') or name in ('.', '..'):
            raise ValueError(f'Unsafe camera name: {name!r}')
        scene.camera = scene.objects[name]
        scene.render.filepath = str(directory / f'{name}.png')
        bpy.ops.render.render(write_still=True)


def photometric_losses(root, camera_names):
    root = Path(root)
    losses = {}
    for name in camera_names:
        with Image.open(root/'start_views'/f'{name}.png') as start, Image.open(root/'goal_views'/f'{name}.png') as goal:
            pixels1 = np.array(start.convert('RGB')) / 255.0
            pixels2 = np.array(goal.convert('RGB')) / 255.0
        if np.all(pixels1 < 0.001) and np.all(pixels2 < 0.001):
            raise ValueError(f'Invalid view {name}: both images are completely black')
        losses[name] = float(np.mean(np.abs(pixels1 - pixels2)))
    return losses
