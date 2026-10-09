"""Real registration recovery, save/reload and module reload lifecycle."""
import importlib.util,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
TEMP=tempfile.TemporaryDirectory(prefix='wkngr-smoke-',ignore_cleanup_errors=True)
for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
    path=Path(TEMP.name)/kind;path.mkdir();os.environ['BLENDER_USER_'+kind]=str(path)
import bpy
from _bpy_restrict_state import RestrictBlend
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wkngr_smoke',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon._load_modules()
from wkngr_smoke import props,reg,preset_manager as pm,data_catalog as catalog,ui_preset
pm._dir=str(Path(TEMP.name)/'presets');Path(pm._dir).mkdir()
try:
    settings=props.WKNGR_Settings;previous=settings.__annotations__['scan_target']
    settings.__annotations__['scan_target']=bpy.props.EnumProperty(items=lambda self,context:[('BOTH','Both','')],default='BOTH')
    try:
        try:bpy.utils.register_class(settings)
        except (RuntimeError,ValueError,TypeError):pass
        else:raise AssertionError('Expected original failure')
    finally:settings.__annotations__['scan_target']=previous
    assert reg.is_registered(settings)
    with RestrictBlend():addon.register()
    addon.register()
    scene=bpy.context.scene
    mat=bpy.data.materials.new('\u5b9e\u4f8b_001')
    ng=bpy.data.node_groups.new('EnglishGroup','GeometryNodeTree')
    socket=ng.interface.new_socket(name='\u5b9e\u4f8b_002',in_out='INPUT',socket_type='NodeSocketFloat')
    pm.save_preset('usr',{'\u5b9e\u4f8b':'Instance'})
    bpy.ops.wkngr.scan()
    for index,category in enumerate(scene.wkngr_categories):
        if category.key=='materials':scene.wkngr_category_index=index
    bpy.ops.wkngr.auto_fill()
    assert catalog.active_category(scene).entries[0].new_name=='Instance_001'
    blend=Path(TEMP.name)/'roundtrip.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene
    category=catalog.active_category(scene)
    assert category.key=='materials' and category.entries[0].target.name=='\u5b9e\u4f8b_001'
    assert category.entries[0].new_name=='Instance_001'
    bpy.ops.wkngr.apply()
    assert bpy.data.materials.get('Instance_001') is not None
    assert 'materials' not in {c.key for c in scene.wkngr_categories}
    for index,category in enumerate(scene.wkngr_categories):
        if category.key==catalog.SOCKETS:scene.wkngr_category_index=index
    bpy.ops.wkngr.auto_fill();bpy.ops.wkngr.apply()
    assert not scene.wkngr_categories
    ng=bpy.data.node_groups.get('EnglishGroup');frame=ng.nodes.new('NodeFrame');frame.label='\u6807\u7b7e'
    bpy.ops.wkngr.scan()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend));bpy.ops.wm.open_mainfile(filepath=str(blend));scene=bpy.context.scene
    for index,category in enumerate(scene.wkngr_categories):
        if category.key=='__frame_labels__':scene.wkngr_category_index=index
    category=catalog.active_category(scene);category.entries[0].new_name='Label';bpy.ops.wkngr.apply()
    assert bpy.data.node_groups['EnglishGroup'].nodes[-1].label=='Label'
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        assert sum(cb.__name__=='_refresh_nested_history' for cb in handlers)==1
    addon.unregister()
    with patch.object(ui_preset,'register',side_effect=RuntimeError('injected late failure')):
        try:addon.register()
        except RuntimeError:pass
        else:raise AssertionError('Expected failure')
    assert not reg._registered and not hasattr(bpy.types.Scene,'wkngr_categories')
    addon.register()
    spec.loader.exec_module(addon);addon.register()
    assert hasattr(bpy.types.Scene,'wkngr_categories')
    addon.unregister();assert not hasattr(bpy.types.Scene,'wkngr_categories')
    print('WKNGR REAL BLENDER SMOKE PASS:',bpy.app.version_string,flush=True)
finally:
    if addon._registered:addon.unregister()
    TEMP.cleanup()
