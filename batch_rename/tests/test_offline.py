"""Offline regressions using a minimal RNA stub, not a Blender runtime test."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NS = types.SimpleNamespace
class RNA:
    is_registered = False
class Operator(RNA):
    def report(self, level, message):
        self.reports = getattr(self, 'reports', []) + [(level, message)]
class Property:
    def __init__(self, kind, **kw):
        self.kind, self.kw = kind, kw

def register_class(cls):
    if 'bl_rna' in cls.__dict__:
        raise ValueError('already registered')
    # Match Blender: the RNA class exists before deferred properties are checked.
    cls.bl_rna = object()
    cls.is_registered = True
    for prop in getattr(cls, '__annotations__', {}).values():
        if isinstance(prop, Property) and prop.kind == 'EnumProperty':
            if callable(prop.kw['items']) and isinstance(prop.kw.get('default'), str):
                raise TypeError('Dynamic enum string default')
    cls.is_registered = True

def unregister_class(cls):
    if 'bl_rna' in cls.__dict__:
        del cls.bl_rna
    cls.is_registered = False

bpy = types.ModuleType('bpy')
bpy.types = NS(**{n:type(n, (RNA,), {}) for n in ('ID','PropertyGroup','Scene','NodeTree','Material','Panel','UIList')})
bpy.types.Operator = Operator
bpy.props = NS(**{n:(lambda kind: lambda **kw: Property(kind, **kw))(n) for n in
    ('EnumProperty','StringProperty','BoolProperty','IntProperty','PointerProperty','CollectionProperty')})
bpy.utils = NS(register_class=register_class, unregister_class=unregister_class)
bpy.data = NS(scenes=[], node_groups=[], materials=[])
handlers = types.ModuleType('bpy.app.handlers')
handlers.persistent = lambda fn: fn
handlers.load_post, handlers.depsgraph_update_post = [], []
handlers.undo_post, handlers.redo_post = [], []
handlers.save_pre, handlers.save_post = [], []
bpy.app = NS(handlers=handlers)
sys.modules['bpy'] = bpy
sys.modules['bpy.app.handlers'] = handlers
spec = importlib.util.spec_from_file_location('wkngr_test', ROOT/'__init__.py', submodule_search_locations=[str(ROOT)])
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon._load_modules()
from wkngr_test import props, reg, preset_manager as pm, ops_preset, ops_scan, ops_rename, utils, ui_preset

class Collection(list):
    def add(self):
        item = NS()
        self.append(item)
        return item

def scene():
    return NS(session_uid=1, library=None, wkngr_words=Collection(), wkngr_tokens=Collection(), wkngr_categories=Collection(),
        wkngr_sockets=Collection(), wkngr_materials=Collection(), wkngr_word_index=0, wkngr_token_index=0,
        wkngr_settings=NS(active_preset='usr', custom_enable=True, custom_quick='', scan_target='BOTH',
            tree_filter='ALL', replace_scope='ALL', replace_from='', replace_to=''))

def socket(name, identifier='s1'):
    return NS(name=name, identifier=identifier, in_out='INPUT', item_type='SOCKET')

def tree(sockets):
    ng=NS(name='Group', library=None, override_library=None, is_editable=True,
        bl_idname='GeometryNodeTree', interface=NS(items_tree=sockets), updates=0)
    ng.as_pointer=lambda:id(ng)
    def update(): ng.updates += 1
    ng.update_tag=update
    return ng

class Regressions(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory=tmp.name
        pm._dir=tmp.name
        pm.invalidate_cache()
        pm.ensure_defaults()
        props.refresh_preset_enum()
        ops_preset._scene_versions.clear()
        bpy.data.scenes=[]
        bpy.data.node_groups=[]
        bpy.data.materials=[]

    def test_fixed_enum_contract(self):
        for name, prop in props.WKNGR_Settings.__annotations__.items():
            if prop.kind=='EnumProperty' and name!='active_preset':
                self.assertFalse(callable(prop.kw['items']))
                self.assertIn(prop.kw['default'], [i[0] for i in prop.kw['items']])

    def test_preset_selection_survives_reorder(self):
        pm.create_preset('zebra')
        props.refresh_preset_enum()
        settings={}
        props._set_active_preset(settings,1)
        pm.create_preset('alpha')
        props.refresh_preset_enum()
        self.assertEqual(props.PRESET_ITEMS[props._get_active_preset(settings)][0],'zebra')
        pm.delete_preset('alpha')
        props.refresh_preset_enum()
        self.assertEqual(props.PRESET_ITEMS[props._get_active_preset(settings)][0],'zebra')

    def test_corrupt_dictionary_not_overwritten(self):
        p=Path(pm._preset_path('usr'))
        p.write_text('{broken',encoding='utf-8')
        s=scene()
        s.wkngr_settings.original_text='new'
        s.wkngr_settings.translate_text='value'
        self.assertEqual(ops_preset.WKNGR_OT_WordAdd().execute(NS(scene=s)),{'CANCELLED'})
        self.assertEqual(p.read_text(encoding='utf-8'),'{broken')

    def test_wrong_filter_type(self):
        (Path(self.directory)/pm.CUSTOM_FILTER_FILENAME).write_text('{}',encoding='utf-8')
        with self.assertRaises(ValueError): pm.load_custom_tokens()

    def test_invalid_names_and_traversal(self):
        for name in ('custom_filter','CUSTOM_FILTER','CON','NUL.txt','..',''):
            self.assertFalse(pm.create_preset(name),name)
        with self.assertRaises(ValueError): pm._preset_path('../escape')
        self.assertEqual(pm.load_custom_tokens(),[])

    def test_dictionary_crud_unicode(self):
        self.assertTrue(pm.create_preset('words'))
        pm.save_preset('words',{'\u989c\u8272':'Color'})
        self.assertTrue(pm.rename_preset('words','translated'))
        self.assertEqual(pm.load_preset('translated'),{'\u989c\u8272':'Color'})
        self.assertTrue(pm.delete_preset('translated'))
        self.assertEqual(pm.list_presets(),['usr'])

    def test_failed_atomic_write_cleanup(self):
        pm.save_preset('usr',{'a':'b'})
        with patch.object(pm.os,'replace',side_effect=OSError('test failure')):
            with self.assertRaises(OSError): pm.save_preset('usr',{'c':'d'})
        self.assertEqual(pm.load_preset('usr'),{'a':'b'})
        self.assertEqual(list(Path(self.directory).glob('*.tmp')),[])

    def test_deleted_socket_never_matches_namesake(self):
        ng=tree([socket('\u989c\u8272','new_id')])
        self.assertIsNone(utils.find_socket_by_identifier(ng,'deleted_id','\u989c\u8272'))







    def test_scene_sync_cache_revision(self):
        s=scene(); pm.save_preset('usr',{'a':'b'})
        with patch.object(pm,'load_preset',wraps=pm.load_preset) as read:
            ops_preset.sync_scene(s); ops_preset.sync_scene(s)
            self.assertEqual(read.call_count,1)
            pm.save_preset('usr',{'c':'d'}); ops_preset.sync_scene(s)
            self.assertEqual(read.call_count,2)
        self.assertEqual(s.wkngr_words[0].cn,'c')

    def test_class_failure_rollback(self):
        good=type('Good',(RNA,),{}); bad=type('Bad',(RNA,),{})
        def fail(cls):
            if cls is bad: raise RuntimeError('injected')
            register_class(cls)
        with patch.object(bpy.utils,'register_class',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'injected'): reg.register_classes([good,bad])
        self.assertFalse(good.is_registered)
        self.assertNotIn('Good',reg._registered)

    def test_late_failure_cleanup_and_retry(self):
        def fail(cls):
            if cls.__name__=='WKNGR_PT_Preset_View3D': raise RuntimeError('injected')
            register_class(cls)
        with patch.object(bpy.utils,'register_class',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'injected'): addon.register()
        self.assertFalse(reg._registered)
        self.assertFalse(handlers.load_post)
        self.assertFalse(handlers.depsgraph_update_post)
        self.assertFalse(hasattr(bpy.types.Scene,'wkngr_settings'))
        pm._dir=self.directory
        addon.register(); addon.register()
        self.assertEqual({cb.__name__ for cb in handlers.load_post},{'_on_load','_refresh_nested_history'})
        self.assertEqual(len(handlers.load_post),2)
        addon.unregister(); addon.unregister()
        self.assertFalse(reg._registered)

    def test_draw_does_not_write_scene(self):
        context=NS(scene=scene())
        for cls in (ui_preset.WKNGR_PT_Preset_Node,ui_preset.WKNGR_PT_Preset_View3D):
            panel=cls(); panel.layout=object()
            with patch.object(ui_preset,'draw_preset') as draw:
                panel.draw(context)
                draw.assert_called_once_with(panel.layout,context)
        self.assertEqual(context.scene.wkngr_words,[])


    def test_deferred_property_failure_unregisters_failing_class(self):
        good=type('Good',(RNA,),{})
        bad=type('Bad',(RNA,),{'__annotations__':{'scan_target':Property('EnumProperty',
            items=lambda self,context:[('BOTH','Both','')],default='BOTH')}})
        with self.assertRaisesRegex(TypeError,'Dynamic enum'):
            reg.register_classes([good,bad])
        self.assertFalse(reg.is_registered(good))
        self.assertFalse(reg.is_registered(bad))
        self.assertFalse(reg._registered)
        bad.__annotations__={}
        reg.register_classes([good,bad])
        reg.unregister_classes([good,bad])

    def test_old_settings_class_absent_from_ledger_is_recovered(self):
        old=type('WKNGR_Settings',(bpy.types.PropertyGroup,),{'__module__':props.__name__})
        register_class(old)
        bpy.types.Scene.wkngr_settings=Property('PointerProperty',type=old)
        self.assertNotIn('WKNGR_Settings',reg._registered)
        addon.register()
        try:
            self.assertFalse(reg.is_registered(old))
            self.assertTrue(reg.is_registered(props.WKNGR_Settings))
            self.assertIs(bpy.types.Scene.wkngr_settings.kw['type'],props.WKNGR_Settings)
        finally:
            addon.unregister()

    def test_same_python_class_left_half_registered_is_recovered(self):
        cls=props.WKNGR_Settings
        original=cls.__annotations__['scan_target']
        cls.__annotations__['scan_target']=Property('EnumProperty',
            items=lambda self,context:[('BOTH','Both','')],default='BOTH')
        try:
            with self.assertRaises(TypeError): register_class(cls)
        finally:
            cls.__annotations__['scan_target']=original
        self.assertTrue(reg.is_registered(cls))
        addon.register()
        try:
            self.assertTrue(reg.is_registered(cls))
        finally:
            addon.unregister()

    def test_stale_callback_removed_without_touching_other_addon(self):
        def old_handler(*args): pass
        old_handler.__name__='_on_load'
        old_handler.__module__=ops_preset.__name__
        def unrelated(*args): pass
        unrelated.__name__='_on_load'
        unrelated.__module__='another_addon.ops_preset'
        handlers.load_post.extend([old_handler,unrelated])
        addon.register()
        try:
            self.assertNotIn(old_handler,handlers.load_post)
            self.assertIn(unrelated,handlers.load_post)
            self.assertIn(ops_preset._on_load,handlers.load_post)
        finally:
            addon.unregister()
            handlers.load_post.remove(unrelated)

    def test_reloaded_package_reloads_cached_submodules(self):
        addon.register()
        old_settings=props.WKNGR_Settings
        old_handler=ops_preset._on_load
        # Re-execute __init__ while its child modules and RNA remain alive.
        spec.loader.exec_module(addon)
        self.assertTrue(addon._needs_reload)
        with patch.object(bpy.utils,'user_resource',return_value=self.directory,create=True):
            addon.register()
        try:
            self.assertIsNot(props.WKNGR_Settings,old_settings)
            self.assertFalse(reg.is_registered(old_settings))
            self.assertTrue(reg.is_registered(props.WKNGR_Settings))
            self.assertNotIn(old_handler,handlers.load_post)
            self.assertEqual(handlers.load_post.count(ops_preset._on_load),1)
        finally:
            addon.unregister()

    def test_foreign_class_collision_is_not_deleted(self):
        foreign=type('WKNGR_Settings',(bpy.types.PropertyGroup,),{'__module__':'unrelated.props'})
        register_class(foreign)
        try:
            with self.assertRaisesRegex(RuntimeError,'another add-on'):
                addon.register()
            self.assertTrue(reg.is_registered(foreign))
        finally:
            unregister_class(foreign)

if __name__=='__main__': unittest.main(verbosity=2)
