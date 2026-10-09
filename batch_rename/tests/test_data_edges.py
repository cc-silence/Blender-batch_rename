"""Audit regressions for migration and shared preset selection."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_offline as support
pm,props,ops,bpy=support.pm,support.props,support.ops_preset,support.bpy
class Settings(dict):
    @property
    def active_preset(self):
        return props.PRESET_ITEMS[props._get_active_preset(self)][0]
    @active_preset.setter
    def active_preset(self,name):
        props._set_active_preset(self,next(i for i,item in enumerate(props.PRESET_ITEMS) if item[0]==name))
class DataEdges(unittest.TestCase):
    def setUp(self):
        support.Regressions.setUp(self)
        target=Path(self.directory)/'user';target.mkdir()
        pm._dir=str(target);pm.invalidate_cache();pm.ensure_defaults();props.refresh_preset_enum()
    def test_deleted_migrated_dictionary_stays_deleted(self):
        legacy=Path(self.directory)/'legacy';legacy.mkdir()
        target=Path(self.directory)/'target';target.mkdir()
        (legacy/'obsolete.json').write_text('{"word":"value"}',encoding='utf-8')
        pm._dir=''
        with patch.object(pm,'__package__','bl_ext.user_default.batch_rename_cn'), patch.object(bpy.utils,'user_resource',return_value=str(legacy),create=True), patch.object(bpy.utils,'extension_path_user',return_value=str(target),create=True):
            pm.get_preset_dir()
            self.assertTrue(pm.delete_preset('obsolete'))
            pm.unregister();pm.get_preset_dir()
            self.assertFalse((target/'obsolete.json').exists())
    def test_discover_late_reference_dictionary(self):
        import shutil,json
        source=Path(self.directory)/'addon';source.mkdir()
        sample=next(support.ROOT.parent.glob('CC_*.json'))
        pm.list_presets()
        shutil.copy2(sample,source/sample.name)
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            self.assertEqual(pm.refresh_external_presets(),[])
            self.assertIn(sample.stem,pm.list_presets())
            self.assertEqual(pm.load_preset(sample.stem),json.loads(sample.read_text(encoding='utf-8')))
            self.assertEqual(pm.refresh_external_presets(),[])
            self.assertEqual(pm.list_presets(),['usr',sample.stem])
    def test_discovered_removal_and_rename_do_not_resurrect(self):
        source=Path(self.directory)/'addon';source.mkdir()
        (source/'words.json').write_text('{"word":"Word"}',encoding='utf-8')
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            pm.refresh_external_presets();pm.rename_preset('words','renamed')
            pm.refresh_external_presets();self.assertNotIn('words',pm.list_presets())
            pm.delete_preset('renamed');pm.refresh_external_presets()
            self.assertEqual(pm.list_presets(),['usr'])
    def test_external_conflict_preserves_user_edits(self):
        source=Path(self.directory)/'addon';source.mkdir()
        pm.save_preset('words',{'word':'User'})
        (source/'words.json').write_text('{"word":"External"}',encoding='utf-8')
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            pm.refresh_external_presets();pm.refresh_external_presets()
            self.assertEqual(pm.load_preset('words'),{'word':'User'})
            self.assertEqual(pm.load_preset('words.001'),{'word':'External'})
            self.assertEqual(pm.list_presets(),['usr','words','words.001'])
    def test_bad_external_file_does_not_block_good_file(self):
        source=Path(self.directory)/'addon';source.mkdir()
        (source/'bad.json').write_text('{broken',encoding='utf-8')
        (source/'good.JSON').write_text('{"word":"Good"}',encoding='utf-8')
        (source/'custom_filter.json').write_text('["filter"]',encoding='utf-8')
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            errors=pm.refresh_external_presets()
            self.assertEqual(len(errors),1);self.assertIn('bad.json',errors[0])
            self.assertEqual(pm.load_preset('good'),{'word':'Good'})
            self.assertEqual(pm.list_presets(),['usr','good'])
    def test_source_changes_refresh_copy_without_overwriting_user_edit(self):
        source=Path(self.directory)/'addon';source.mkdir()
        path=source/'words.json';path.write_text('{"word":"First"}',encoding='utf-8')
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            pm.refresh_external_presets()
            path.write_text('{"word":"Second"}',encoding='utf-8');pm.refresh_external_presets()
            self.assertEqual(pm.load_preset('words'),{'word':'Second'})
            self.assertEqual(pm.list_presets(),['usr','words'])
            pm.save_preset('words',{'word':'User'})
            path.write_text('{"word":"Third"}',encoding='utf-8');pm.refresh_external_presets()
            self.assertEqual(pm.load_preset('words'),{'word':'User'})
            self.assertEqual(pm.load_preset('words.001'),{'word':'Third'})
    def test_recursive_default_hidden_but_translated(self):
        source=Path(self.directory)/'addon';source.mkdir()
        (source/'nested'/'deep').mkdir(parents=True)
        (source/'default'/'nested').mkdir(parents=True)
        (source/'nested'/'deep'/'words.json').write_text('{"visible":"Visible","shared":"Custom"}',encoding='utf-8')
        (source/'default'/'nested'/'words.json').write_text('{"hidden":"Hidden","shared":"Default"}',encoding='utf-8')
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            self.assertEqual(pm.refresh_external_presets(),[])
            self.assertEqual(pm.list_presets(),['usr','nested/deep/words'])
            self.assertEqual(pm.load_translation_dictionary('usr'),{'visible':'Visible','shared':'Custom','hidden':'Hidden'})
            self.assertEqual(pm.load_preset('nested/deep/words')['visible'],'Visible')
            pm.refresh_external_presets()
            self.assertEqual(len(pm.list_translation_presets()),3)
    def test_user_directory_recursive_and_uppercase_extension(self):
        root=Path(pm.get_preset_dir());(root/'nested').mkdir()
        (root/'nested'/'words.JSON').write_text('{"visible":"Visible"}',encoding='utf-8')
        (root/'default'/'words.json').write_text('{"hidden":"Hidden"}',encoding='utf-8')
        pm.invalidate_cache()
        self.assertEqual(pm.list_presets(),['usr','nested/words'])
        self.assertEqual(pm.load_preset('nested/words'),{'visible':'Visible'})
        self.assertIn('hidden',pm.load_translation_dictionary('usr'))
    def test_nested_rename_keeps_folder_and_other_scene_selection(self):
        pm.save_preset('nested/original',{'key':'Value'});props.refresh_preset_enum()
        first,second=support.scene(),support.scene();second.session_uid=2
        for scene in (first,second):
            scene.wkngr_settings=Settings();scene.wkngr_settings.active_preset='nested/original'
        bpy.data.scenes=[first,second]
        op=ops.WKNGR_OT_PresetRename();op.preset_name='renamed'
        self.assertEqual(op.execute(support.NS(scene=first)),{'FINISHED'})
        self.assertEqual(second.wkngr_settings.active_preset,'nested/renamed')
        self.assertEqual(pm.load_preset('nested/renamed'),{'key':'Value'})
    def test_export_cannot_overwrite_nested_internal_dictionary(self):
        pm.save_preset('nested/words',{'key':'Value'})
        with self.assertRaises(ValueError):pm.export_preset('usr',str(Path(pm.get_preset_dir())/'nested'/'words.json'))
        self.assertEqual(pm.load_preset('nested/words'),{'key':'Value'})
    def test_initial_migration_is_recursive_and_default_hidden(self):
        source=Path(self.directory)/'source';(source/'nested').mkdir(parents=True);(source/'default').mkdir()
        (source/'nested'/'words.json').write_text('{"visible":"Visible"}',encoding='utf-8')
        (source/'default'/'words.json').write_text('{"hidden":"Hidden"}',encoding='utf-8')
        target=Path(self.directory)/'fresh';target.mkdir()
        pm._dir='';pm.invalidate_cache()
        with patch.object(pm,'__package__','bl_ext.user_default.batch_rename_cn'),patch.object(pm,'_addon_preset_dir',return_value=str(source)),patch.object(bpy.utils,'user_resource',return_value='',create=True),patch.object(bpy.utils,'extension_path_user',return_value=str(target),create=True):
            self.assertEqual(pm.list_presets(),['usr','nested/words'])
            self.assertEqual(pm.load_translation_dictionary('usr'),{'visible':'Visible','hidden':'Hidden'})
    def shared(self):
        pm.create_preset('shared');props.refresh_preset_enum()
        first,second=support.scene(),support.scene();second.session_uid=2
        for s in (first,second):
            s.wkngr_settings=Settings();s.wkngr_settings.active_preset='shared'
        bpy.data.scenes=[first,second]
        return first,second
    def test_shared_rename_preserves_other_scene_selection(self):
        first,second=self.shared()
        op=ops.WKNGR_OT_PresetRename();op.preset_name='renamed'
        self.assertEqual(op.execute(support.NS(scene=first)),{'FINISHED'})
        self.assertEqual(second.wkngr_settings.active_preset,'renamed')
    def test_deleted_selection_does_not_return_on_name_reuse(self):
        first,second=self.shared()
        self.assertEqual(ops.WKNGR_OT_PresetRemove().execute(support.NS(scene=first)),{'FINISHED'})
        self.assertEqual(second.wkngr_settings.active_preset,'usr')
        pm.create_preset('shared');props.refresh_preset_enum()
        self.assertEqual(second.wkngr_settings.active_preset,'usr')
if __name__=='__main__':unittest.main(verbosity=2)
