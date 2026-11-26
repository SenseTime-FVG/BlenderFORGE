"""Shape-key snapshots, public state and native replay acceptance."""
import hashlib
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.blender_state import apply_render_config, capture_render_config, export_state, pack_resources
from common.contract import compare_values, publish_success, read_json, require, write_json


def check_supported_scene(editable):
    require(not bpy.data.libraries, "Linked libraries must be localized before generation")
    for obj in bpy.context.scene.objects:
        require(not obj.animation_data and not obj.constraints, f"Dynamic object: {obj.name}")
        data = getattr(obj.data, 'shape_keys', None)
        if data:
            require(data.use_relative and not data.animation_data, f"Absolute/animated/driven shape keys: {obj.name}")
        if obj.name in editable:
            require(obj.data.users == 1, f"Shared editable mesh: {obj.name}")
            require(not obj.show_only_shape_key, f"Solo shape-key display: {obj.name}")
            for name in editable[obj.name]:
                require(not data.key_blocks[name].mute and data.key_blocks[name] != data.reference_key,
                        f"Muted/basis editable shape key: {obj.name}:{name}")
    pack_resources(allow_static_geometry_nodes=True)


def export_shapekey_state(sample_id, state, cameras, editable):
    names = set(editable) | set(cameras)
    for name in tuple(names):
        obj = bpy.data.objects[name].parent
        while obj:
            names.add(obj.name)
            obj = obj.parent
    return export_state(sample_id, state, cameras, list(editable), object_names=names,
                        include_material_nodes=False, shape_keys=editable)


def restore_shape_script(state, public_keys):
    lines = ['import bpy', '', f'bpy.context.scene.frame_set({state["scene"]["frame"]!r})']
    for item in public_keys:
        name, key = item['object_name'], item['key_name']
        value = state['objects'][name]['shapekeys'][key]['value']
        lines.append(f'bpy.data.objects[{name!r}].data.shape_keys.key_blocks[{key!r}].value = {value!r}')
    lines.append('bpy.context.view_layer.update()')
    return '\n'.join(lines) + '\n'


def save_state(root, state, sample_id, cameras, editable, public_keys, config):
    root = Path(root)
    bpy.context.scene.camera = bpy.data.objects[cameras[0]]
    bpy.context.scene.render.filepath = f'//{state}_views/{cameras[0]}.png'
    info = export_shapekey_state(sample_id, state, cameras, editable)
    version = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(root / f'{state}.blend'), copy=True)
    finally:
        bpy.context.preferences.filepaths.save_version = version
    write_json(root / f'{state}_info.json', info)
    (root / f'{state}.py').write_text(restore_shape_script(info, public_keys))
    requested = config['render_config']
    effective = capture_render_config(requested.get('scene'), requested.get('view_layer'))
    if state == 'start':
        write_json(root / 'render_config.json', {'schema_version':'1.0', 'sample_id':sample_id,
                                                'requested':requested, 'effective':effective})
    else:
        require(effective == read_json(root/'render_config.json')['effective'], 'START/GOAL render configuration changed')

def replay_checks(root):
    root = Path(root)
    metadata = read_json(root/'metadata.json')
    start, goal = [read_json(root/f'{s}_info.json') for s in ('start','goal')]
    editable = {}
    for item in metadata['editable']['shape_keys']:
        editable.setdefault(item['object_name'], []).append(item['key_name'])
    cameras = [v['camera_name'] for v in start['views']]
    render = read_json(root/'render_config.json')
    checks = []
    for route, snapshot, scripts, expected in (
        ('start_replay','start',('start',),start),
        ('goal_replay','start',('start','goal'),goal),
        ('goal_snapshot','goal',(),goal)):
        bpy.ops.wm.open_mainfile(filepath=str(root/f'{snapshot}.blend'))
        for script in scripts:
            filename=root/f'{script}.py'
            exec(compile(filename.read_text(),str(filename),'exec'), {'__name__':'__main__'})
        apply_render_config(render)
        actual = export_shapekey_state(metadata['sample_id'], expected['state'], cameras, editable)
        error = compare_values(actual, expected)
        effective=render['effective']
        compare_values(capture_render_config(effective.get('configured_scene'),effective.get('configured_view_layer')), effective)
        require(bpy.context.scene.camera.name == cameras[0], 'Snapshot active camera differs from selected first view')
        checks.append({'name':route,'executed':True,'passed':True,'metrics':{'max_absolute_numeric_error':error},'tolerance':1e-6,'reason':None})
    return checks


def finalize(root, config, source, public_keys, sample_id, losses):
    root, source = Path(root), Path(source)
    start,goal=[read_json(root/f'{s}_info.json') for s in ('start','goal')]
    changed = [item for item in public_keys
               if start['objects'][item['object_name']]['shapekeys'][item['key_name']]['value'] !=
                  goal['objects'][item['object_name']]['shapekeys'][item['key_name']]['value']]
    with source.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    metadata={'schema_version':'1.0','sample_id':sample_id,'task':'shapekey','backend':None,
              'source':{'asset_id':source.stem,'filename':source.name,'sha256':digest},
              'generator':{'name':'shapekey','config':config,'seed':config['random_seed'],
                           'seed_scope':'invocation','blender_version':bpy.app.version_string},
              'dependencies':{'external_files':[],'resources_packed':True,'python_modules_for_replay':['bpy']},
              'editable':{'object_names':sorted({x['object_name'] for x in public_keys}),
                          'properties':['shapekeys.value'],'shape_keys':public_keys,'policy':'displayed_shape_keys'},
              'num_views':len(start['views']),
              'edit_summary':{'requested_max':config['num_of_key_change'],'actual_changed':len(changed),
                              'shape_keys':changed,'object_names':sorted({x['object_name'] for x in changed})}}
    write_json(root/'metadata.json',metadata)
    checks=[{'name':'quality','executed':True,'passed':max(losses.values())>config['photometric_loss_threshold'],
             'metrics':{'image_l1_by_camera':losses},'tolerance':config['photometric_loss_threshold'],'reason':None}]
    checks.extend(replay_checks(root))
    publish_success(root, checks)
    return checks
