"""Viewport-only reveal and manual exclusion workflow in real Blender RNA."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_usage_navigation as support
from batch_rename import ops_tools,usage_visibility,id_handles
bpy=support.bpy
class Tests(support.Tests):
    def in_collection(self,obj,name='Hidden'):
        collection=bpy.data.collections.new(name);self.scene.collection.children.link(collection);collection.objects.link(obj)
        self.scene.collection.objects.unlink(obj);bpy.context.view_layer.update()
        return collection,bpy.context.view_layer.layer_collection.children[collection.name]
    def test_object_hide_and_select_lock_cleared_render_stays_off(self):
        obj=self.object();layer=bpy.context.view_layer;layer.update();obj.hide_set(True);obj.hide_viewport=True;obj.hide_select=True;obj.hide_render=True
        ops_tools.locate(bpy.context,obj)
        self.assertFalse(obj.hide_get());self.assertFalse(obj.hide_viewport);self.assertFalse(obj.hide_select)
        self.assertTrue(obj.hide_render);self.assertTrue(obj.select_get());self.assertEqual(layer.objects.active,obj)
    def test_collection_viewport_flags_cleared_render_unchanged(self):
        obj=self.object();collection,branch=self.in_collection(obj)
        collection.hide_select=True;collection.hide_viewport=True;collection.hide_render=True;branch.hide_viewport=True
        obj.hide_render=False;branch.holdout=True;branch.indirect_only=True
        ops_tools.locate(bpy.context,obj)
        self.assertFalse(collection.hide_select);self.assertFalse(collection.hide_viewport);self.assertFalse(branch.hide_viewport)
        self.assertTrue(collection.hide_render);self.assertFalse(obj.hide_render);self.assertTrue(branch.holdout);self.assertTrue(branch.indirect_only)
    def test_alternative_membership_does_not_touch_excluded_path(self):
        obj=self.object();excluded,branch=self.in_collection(obj,'Excluded');branch.exclude=True;excluded.hide_render=True
        visible=bpy.data.collections.new('Visible');self.scene.collection.children.link(visible);visible.objects.link(obj)
        ops_tools.locate(bpy.context,obj)
        self.assertTrue(branch.exclude);self.assertTrue(excluded.hide_render);self.assertTrue(obj.select_get())
    def test_only_one_hidden_membership_path_is_revealed(self):
        obj=self.object();a,branch=self.in_collection(obj,'A');b=bpy.data.collections.new('B');self.scene.collection.children.link(b);b.objects.link(obj)
        a.hide_viewport=True;b.hide_viewport=True;b.hide_render=True
        ops_tools.locate(bpy.context,obj)
        self.assertFalse(a.hide_viewport);self.assertTrue(b.hide_viewport);self.assertTrue(b.hide_render)
    def excluded_reader(self):
        target,reader=self.reader();destination,layer=self.destination()
        collection=bpy.data.collections.new('Excluded');destination.collection.children.link(collection);collection.objects.link(reader)
        branch=layer.layer_collection.children[collection.name];branch.exclude=True
        reader.hide_select=True;reader.hide_viewport=True;reader.hide_render=True;collection.hide_render=True
        ops_tools.lookup(self.scene,target);index=self.choose(destination,layer,reader)
        return reader,destination,layer,collection,branch,index
    def test_excluded_button_switches_context_and_opens_manual_guide(self):
        reader,destination,layer,collection,branch,index=self.excluded_reader()
        with patch.object(ops_tools,'_open_excluded_guidance') as guide:
            self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'FINISHED'})
            guide.assert_called_once()
        self.assertEqual(bpy.context.scene,destination);self.assertEqual(bpy.context.view_layer,layer)
        self.assertTrue(branch.exclude);self.assertTrue(reader.hide_viewport);self.assertTrue(reader.hide_select)
        self.assertTrue(reader.hide_render);self.assertTrue(collection.hide_render)
    def test_manual_unexclude_then_confirm_reveals_and_selects(self):
        reader,destination,layer,collection,branch,index=self.excluded_reader()
        with patch.object(ops_tools,'_open_excluded_guidance'):bpy.ops.wkngr.locate_usage(index=index)
        branch.exclude=False
        self.assertEqual(bpy.ops.wkngr.excluded_guidance('EXEC_DEFAULT',scene_uid=str(destination.session_uid),object_uid=str(reader.session_uid),view_layer_name=layer.name),{'FINISHED'})
        self.assertEqual(layer.objects.active,reader);self.assertTrue(reader.select_get(view_layer=layer));self.assertFalse(reader.hide_select)
        self.assertTrue(reader.hide_render);self.assertTrue(collection.hide_render)
    def test_guide_confirm_does_not_unexclude_automatically(self):
        reader,destination,layer,collection,branch,index=self.excluded_reader()
        result=bpy.ops.wkngr.excluded_guidance('EXEC_DEFAULT',scene_uid=str(destination.session_uid),object_uid=str(reader.session_uid),view_layer_name=layer.name)
        self.assertEqual(result,{'CANCELLED'});self.assertTrue(branch.exclude);self.assertTrue(reader.hide_viewport)
        self.assertTrue(reader.hide_render);self.assertTrue(collection.hide_render)
    def test_lookup_only_does_not_reveal_or_unlock(self):
        target,reader=self.reader();layer=bpy.context.view_layer;layer.update();reader.hide_set(True);reader.hide_select=True;reader.hide_render=True
        before=target.users;ops_tools.lookup(self.scene,target)
        self.assertEqual(target.users,before);self.assertTrue(reader.hide_get());self.assertTrue(reader.hide_select);self.assertTrue(reader.hide_render)
    def test_missing_object_does_not_change_visibility(self):
        obj=self.object();obj.hide_select=True;obj.hide_render=True
        other,layer=self.destination()
        with self.assertRaises(ValueError):ops_tools.locate(bpy.context,obj,other,layer.name)
        self.assertTrue(obj.hide_select);self.assertTrue(obj.hide_render);self.assertEqual(bpy.context.scene,self.scene)

    def test_view_layer_render_switch_remains_disabled(self):
        obj=self.object();layer=bpy.context.view_layer;layer.use=False;obj.hide_render=True
        ops_tools.locate(bpy.context,obj)
        self.assertFalse(layer.use);self.assertTrue(obj.hide_render);self.assertEqual(layer.objects.active,obj)
    def test_guidance_draw_exposes_only_manual_exclude_controls(self):
        from types import SimpleNamespace
        reader,destination,layer,collection,branch,index=self.excluded_reader()
        calls=[]
        class Layout:
            def label(self,**kw):pass
            def prop(self,value,field,**kw):calls.append((value,field));getattr(value,field)
        fake=SimpleNamespace(layout=Layout(),targets=lambda:(destination,layer,reader,usage_visibility.choose_path(layer,reader)))
        ops_tools.WKNGR_OT_ExcludedGuidance.draw(fake,bpy.context)
        self.assertTrue(calls);self.assertTrue(all(field=='exclude' and value.exclude for value,field in calls))
        self.assertTrue(branch.exclude);self.assertTrue(reader.hide_render);self.assertTrue(collection.hide_render)

if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.support.support.batch_rename.unregister()
    print('VISIBILITY RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)
