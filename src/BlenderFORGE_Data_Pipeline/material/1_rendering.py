"""Backend-specific material quality metrics and native rendering."""
from pathlib import Path

import bpy
import numpy as np
from PIL import Image, ImageChops, ImageStat


def render_view(path, camera):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    scene = bpy.context.scene
    if scene.render.image_settings.file_format != 'PNG':
        raise ValueError('The material v1 profile requires PNG output')
    scene.camera = scene.objects[camera]
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise ValueError(f'Missing rendered image: {path.name}')


def rgb_l1(start, goal):
    with Image.open(start) as a, Image.open(goal) as b:
        if a.size != b.size:
            raise ValueError('START/GOAL image dimensions differ')
        stat = ImageStat.Stat(ImageChops.difference(a.convert('RGB'),b.convert('RGB')))
    return sum(stat.mean)/(len(stat.mean)*255.0)


def blender_rgb(path):
    image = bpy.data.images.load(str(path))
    try:
        width,height = image.size
        return np.array(image.pixels[:]).reshape((height,width,image.channels))[:,:,:3]
    finally:
        bpy.data.images.remove(image)


def validate_pair(start, goal, backend, config):
    validation = config['validation']
    if backend == 'principled_bsdf':
        value = rgb_l1(start,goal)
        if value < validation['min_photometric_diff']:
            raise ValueError(f'RGB L1 below threshold: {value}')
        return {'png_rgb_l1':value}

    # Preserve Blender's image decoding and the original per-channel threshold.
    a,b = blender_rgb(start),blender_rgb(goal)
    gray = validation['gray_check']
    min_luminance = validation.get('min_mean_luminance')
    if gray['enabled'] or min_luminance is not None:
        means = [float(np.mean(image)) for image in (a,b)]
        if gray['enabled']:
            for image,mean in zip((a,b),means):
                if mean < gray['brightness_threshold'] or np.var(image) < gray['variance_threshold']:
                    raise ValueError('Material render failed the gray-image check')
    ratio = float(np.mean(np.any(np.abs(a-b) > 0.01,axis=2)))
    shift = float(np.mean(np.sqrt(np.sum((a-b)**2,axis=2))))
    if not (ratio >= validation['min_photometric_diff']):
        raise ValueError(f'Changed-pixel fraction below threshold: {ratio}')
    min_shift = validation.get('min_mean_color_shift')
    if min_shift is not None and shift < min_shift:
        raise ValueError(f'Mean color shift below threshold: {shift}')
    if min_luminance is not None and min(means) < min_luminance:
        raise ValueError('Material render is below the minimum luminance')
    return {'blender_rgb_changed_pixel_fraction':ratio,'blender_rgb_mean_euclidean_shift':shift}
