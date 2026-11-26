"""Native lighting state, packed snapshots and replay acceptance."""
import hashlib
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.blender_state import apply_render_config, capture_render_config, export_state, pack_resources
from common.contract import compare_values, publish_success, read_json, require, write_json


def check_supported_scene(names):
    require(not bpy.data.libraries, 'Linked libraries must be localized before generation')
    for obj in bpy.context.scene.objects:
        require(not obj.animation_data and not obj.constraints, f'Dynamic object: {obj.name}')
        if obj.name in names:
            require(obj.data.users == 1, f'Shared editable light data: {obj.name}')
            require(not obj.data.animation_data, f'Animated/driven light: {obj.name}')
            tree = obj.data.node_tree
            require(not tree or not tree.animation_data, f'Animated light nodes: {obj.name}')
    require(all(name in bpy.context.scene.objects for name in names), 'Lights outside the active scene are unsupported')
    pack_resources(allow_static_geometry_nodes=True)


def export_lighting_state(sample_id, state, cameras, names):
    scope = set(names) | set(cameras)
    for name in tuple(scope):
        parent = bpy.data.objects[name].parent
        while parent:
            scope.add(parent.name)
            parent = parent.parent
    return export_state(sample_id, state, cameras, names, object_names=scope, include_material_nodes=False)


def restore_script(state, names):
    lines = ['import bpy', '', f'bpy.context.scene.frame_set({state["scene"]["frame"]!r})']
    for name in names:
        for key in ('energy', 'color'):
            lines.append(f'bpy.data.objects[{name!r}].data.{key} = {state["objects"][name]["light"][key]!r}')
    lines.append('bpy.context.view_layer.update()')
    return '\n'.join(lines)+'\n'


def render_settings_only(snapshot):
    # Light observations belong to the editable state, not the renderer preset.
    return {key: value for key, value in snapshot.items() if key != 'lights'}


def save_state(root, state, sample_id, cameras, names, config):
    root = Path(root)
    bpy.context.scene.camera = bpy.data.objects[cameras[0]]
    bpy.context.scene.render.filepath = f'//{state}_views/{cameras[0]}.png'
    info = export_lighting_state(sample_id, state, cameras, names)
    version = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(root/f'{state}.blend'), copy=True)
    finally:
        bpy.context.preferences.filepaths.save_version = version
    write_json(root/f'{state}_info.json', info)
    (root/f'{state}.py').write_text(restore_script(info, names))
    requested = config['render_config']
    effective = capture_render_config(requested.get('scene'), requested.get('view_layer'))
    if state == 'start':
        write_json(root/'render_config.json', {'schema_version':'1.0', 'sample_id':sample_id,
                                              'requested':requested, 'effective':effective})
    else:
        compare_values(render_settings_only(effective), render_settings_only(read_json(root/'render_config.json')['effective']))


def replay_checks(root):
    root = Path(root)
    metadata = read_json(root/'metadata.json')
    start, goal = [read_json(root/f'{s}_info.json') for s in ('start', 'goal')]
    names = metadata['editable']['object_names']
    cameras = [v['camera_name'] for v in start['views']]
    render = read_json(root/'render_config.json')
    checks = []
    for route, snapshot, scripts, expected in (
        ('start_replay', 'start', ('start',), start),
        ('goal_replay', 'start', ('start', 'goal'), goal),
        ('goal_snapshot', 'goal', (), goal)):
        bpy.ops.wm.open_mainfile(filepath=str(root/f'{snapshot}.blend'))
        for script in scripts:
            filename = root/f'{script}.py'
            exec(compile(filename.read_text(), str(filename), 'exec'), {'__name__':'__main__'})
        apply_render_config(render)
        error = compare_values(export_lighting_state(metadata['sample_id'], expected['state'], cameras, names), expected)
        effective = render['effective']
        actual_render = capture_render_config(effective.get('configured_scene'), effective.get('configured_view_layer'))
        compare_values(render_settings_only(actual_render), render_settings_only(effective))
        if expected['state'] == 'start':
            compare_values(actual_render['lights'], effective['lights'])
        require(bpy.context.scene.camera.name == cameras[0], 'Snapshot active camera differs from selected first view')
        checks.append({'name':route, 'executed':True, 'passed':True,
                       'metrics':{'max_absolute_numeric_error':error}, 'tolerance':1e-6, 'reason':None})
    return checks


def finalize(root, config, source, names, sample_id, losses):
    root, source = Path(root), Path(source)
    start, goal = [read_json(root/f'{s}_info.json') for s in ('start','goal')]
    changed = [name for name in names if any(start['objects'][name]['light'][k] != goal['objects'][name]['light'][k]
                                           for k in ('energy', 'color'))]
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    modification = config['light_modification']
    metadata = {'schema_version':'1.0', 'sample_id':sample_id, 'task':'lighting', 'backend':None,
                'source':{'asset_id':source.parent.name, 'filename':source.name, 'sha256':digest},
                'generator':{'name':'lighting', 'config':config, 'seed':config['random_seed'],
                             'seed_scope':'invocation', 'blender_version':bpy.app.version_string},
                'dependencies':{'external_files':[], 'resources_packed':True, 'python_modules_for_replay':['bpy']},
                'editable':{'object_names':names, 'properties':['light.'+k for k in ('energy','color') if modification['modify_'+k]],
                            'policy':'asset_lights'},
                'num_views':len(start['views']),
                'edit_summary':{'requested_max':modification['max_lights_to_modify'], 'actual_changed':len(changed), 'object_names':changed}}
    write_json(root/'metadata.json', metadata)
    threshold = config['validation_config']['min_photometric_difference']
    checks = [{'name':'quality', 'executed':True, 'passed':bool(losses) and min(losses.values()) >= threshold,
               'metrics':{'image_l1_by_camera':losses}, 'tolerance':threshold, 'reason':None}]
    checks.extend(replay_checks(root))
    publish_success(root, checks)
    return checks
