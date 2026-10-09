"""Scene and collection reference actions through native Blender window state."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_global_rename as support
bpy=support.bpy
from batch_rename import ops_tools,id_handles,ui_main
class Tests(support.Tests):
    def fixture(self):
        destination=bpy.data.scenes.new('Destination');layer=destination.view_layers.new('Wanted')
        target=bpy.data.collections.new('Target');parent=bpy.data.collections.new('Parent')
        parent.children.link(target);destination.collection.children.link(parent)
        unused=layer.active_layer_collection
        return destination,layer,target,parent
    def find(self,owner,scene,layer):
        return next((i,row) for i,row in enumerate(self.scene.wkngr_usage_rows) if id_handles.resolve(row.owner_uid)==owner and id_handles.resolve(row.scene_uid)==scene and row.view_layer_name==layer.name)
    def test_scene_result_switches_requested_layer(self):
        destination,layer,target,parent=self.fixture();ops_tools.lookup(self.scene,target)
        index,row=self.find(destination,destination,layer)
        self.assertFalse(row.object_uid);self.assertFalse(row.collection_uid)
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'FINISHED'})
        self.assertEqual(bpy.context.window.scene,destination);self.assertEqual(bpy.context.window.view_layer,layer)
        self.assertTrue(destination.wkngr_usage_rows);self.assertFalse(self.scene.wkngr_usage_rows)
    def test_collection_result_activates_exact_collection(self):
        destination,layer,target,parent=self.fixture();ops_tools.lookup(self.scene,target)
        index,row=self.find(parent,destination,layer);self.assertEqual(id_handles.resolve(row.collection_uid),parent);self.assertIn('Scene Collection / Parent',row.path)
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'FINISHED'})
        self.assertEqual(bpy.context.window.scene,destination);self.assertEqual(bpy.context.window.view_layer,layer)
        self.assertEqual(layer.active_layer_collection.collection,parent)
        self.assertTrue(all(a.spaces.active.display_mode=='VIEW_LAYER' and not a.spaces.active.filter_text for a in bpy.context.window.screen.areas if a.type=='OUTLINER'))
    def test_collection_shared_between_scenes_has_distinct_entries(self):
        destination,layer,target,parent=self.fixture();self.scene.collection.children.link(parent)
        ops_tools.lookup(self.scene,target)
        rows=[r for r in self.scene.wkngr_usage_rows if id_handles.resolve(r.collection_uid)==parent]
        self.assertEqual(len(rows),3);self.assertEqual(len({(r.scene_uid,r.view_layer_name,r.collection_uid) for r in rows}),3)
    def test_scene_navigation_preserves_object_selection(self):
        destination,layer,target,parent=self.fixture();obj=bpy.data.objects.new('Selected',None);destination.collection.objects.link(obj)
        layer.update();obj.select_set(True,view_layer=layer);layer.objects.active=obj
        ops_tools.lookup(self.scene,target);index,row=self.find(destination,destination,layer)
        bpy.ops.wkngr.locate_usage(index=index)
        self.assertEqual(layer.objects.active,obj);self.assertTrue(obj.select_get(view_layer=layer))
    def test_collection_navigation_preserves_all_visibility_flags(self):
        destination,layer,target,parent=self.fixture();branch=layer.layer_collection.children[parent.name]
        parent.hide_render=True;parent.hide_viewport=True;parent.hide_select=True;branch.hide_viewport=True;branch.holdout=True;branch.indirect_only=True
        ops_tools.lookup(self.scene,target);index,row=self.find(parent,destination,layer)
        bpy.ops.wkngr.locate_usage(index=index)
        self.assertTrue(parent.hide_render and parent.hide_viewport and parent.hide_select and branch.hide_viewport and branch.holdout and branch.indirect_only)
        self.assertEqual(layer.active_layer_collection.collection,parent)
    def test_excluded_collection_opens_manual_guidance_without_unexcluding(self):
        destination,layer,target,parent=self.fixture();branch=layer.layer_collection.children[parent.name];branch.exclude=True
        ops_tools.lookup(self.scene,target);index,row=self.find(parent,destination,layer);self.assertTrue(row.excluded)
        with patch.object(ops_tools,'_open_excluded_guidance',return_value={'FINISHED'}) as guide:
            self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'FINISHED'})
        guide.assert_called_once();self.assertEqual(guide.call_args.args[1],parent)
        self.assertTrue(branch.exclude);self.assertEqual(bpy.context.window.view_layer,layer)
    def test_collection_guide_confirm_after_manual_unexclude(self):
        destination,layer,target,parent=self.fixture();branch=layer.layer_collection.children[parent.name];branch.exclude=True
        scene_uid=id_handles.remember(destination);collection_uid=id_handles.remember(parent)
        branch.exclude=False
        self.assertEqual(bpy.ops.wkngr.excluded_guidance('EXEC_DEFAULT',scene_uid=scene_uid,collection_uid=collection_uid,view_layer_name=layer.name),{'FINISHED'});self.assertEqual(layer.active_layer_collection.collection,parent)
    def test_deleted_collection_does_not_switch_scene(self):
        destination,layer,target,parent=self.fixture();ops_tools.lookup(self.scene,target);index,row=self.find(parent,destination,layer)
        bpy.data.collections.remove(parent)
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'CANCELLED'});self.assertEqual(bpy.context.window.scene,self.scene)
    def test_orphan_collection_has_no_scene_navigation(self):
        destination,layer,target,parent=self.fixture();orphan=bpy.data.collections.new('Orphan');orphan.children.link(target)
        ops_tools.lookup(self.scene,target);row=next(r for r in self.scene.wkngr_usage_rows if id_handles.resolve(r.owner_uid)==orphan)
        self.assertFalse(row.scene_uid);self.assertFalse(row.collection_uid)
    def test_scene_and_collection_buttons_are_enabled(self):
        destination,layer,target,parent=self.fixture();ops_tools.lookup(self.scene,target)
        class Probe:
            def __init__(self):self.enabled=True;self.children=[]
            def row(self,**kw):child=Probe();self.children.append(child);return child
            def label(self,**kw):pass
            def operator(self,*args,**kw):return type('Button',(),{})()
        for owner in (destination,parent):
            index,item=self.find(owner,destination,layer);probe=Probe()
            ui_main.WKNGR_UL_Usage.draw_item(None,bpy.context,probe,self.scene,item,0,None,'',index)
            self.assertTrue(probe.children[0].children[0].enabled)
if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.batch_rename.unregister()
    print('COLLECTION NAVIGATION RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)
