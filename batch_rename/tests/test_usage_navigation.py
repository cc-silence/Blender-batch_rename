"""Scene and view-layer navigation through actual Blender window state."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_tools as support
from batch_rename import ops_tools,id_handles,scan_cache
bpy=support.bpy
class Tests(support.Tests):
    def destination(self,name='Destination'):
        scene=bpy.data.scenes.new(name);layer=scene.view_layers.new('Wanted')
        return scene,layer
    def reader(self):
        target=self.object('Target');reader=self.object('Reader')
        reader.constraints.new('COPY_LOCATION').target=target
        return target,reader
    def choose(self,scene,layer,obj):
        return next(i for i,row in enumerate(self.scene.wkngr_usage_rows) if id_handles.resolve(row.scene_uid)==scene and row.view_layer_name==layer.name and id_handles.resolve(row.object_uid)==obj)
    def test_button_switches_exact_scene_and_view_layer(self):
        target,reader=self.reader();destination,layer=self.destination();destination.collection.objects.link(reader)
        before_users=target.users;ops_tools.lookup(self.scene,target);self.assertEqual(target.users,before_users)
        index=self.choose(destination,layer,reader)
        areas=[a for a in bpy.context.window.screen.areas if a.type=='OUTLINER']
        for area in areas:area.spaces.active.display_mode='LIBRARIES';area.spaces.active.filter_text='OldSearch'
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'FINISHED'})
        self.assertEqual(bpy.context.window.scene,destination);self.assertEqual(bpy.context.window.view_layer,layer)
        self.assertEqual(layer.objects.active,reader);self.assertTrue(reader.select_get(view_layer=layer))
        self.assertTrue(all(a.spaces.active.display_mode=='VIEW_LAYER' and not a.spaces.active.filter_text and not a.spaces.active.use_filter_view_layers for a in areas))
        self.assertTrue(destination.wkngr_usage_rows);self.assertFalse(self.scene.wkngr_usage_rows)
        self.assertEqual(destination.wkngr_settings.tool_mode,'LOOKUP')
    def test_shared_object_has_distinct_contexts_without_duplicate_rows(self):
        target,reader=self.reader();destination,layer=self.destination();destination.collection.objects.link(reader)
        reader.constraints.new('COPY_ROTATION').target=target
        ops_tools.lookup(self.scene,target)
        rows=[row for row in self.scene.wkngr_usage_rows if id_handles.resolve(row.object_uid)==reader]
        contexts=[(row.scene_uid,row.view_layer_name,row.object_uid) for row in rows]
        self.assertEqual(len(contexts),len(set(contexts)));self.assertEqual(len(rows),3)
        self.assertTrue(all('constraints' in row.path for row in rows))
    def test_excluded_layer_offered_with_manual_guidance(self):
        target,reader=self.reader();destination,layer=self.destination()
        collection=bpy.data.collections.new('Excluded');destination.collection.children.link(collection);collection.objects.link(reader)
        layer.layer_collection.children[collection.name].exclude=True
        ops_tools.lookup(self.scene,target)
        index=self.choose(destination,layer,reader)
        self.assertTrue(self.scene.wkngr_usage_rows[index].excluded)
    def test_deleted_view_layer_does_not_switch_scene(self):
        target,reader=self.reader();destination,layer=self.destination();destination.collection.objects.link(reader)
        ops_tools.lookup(self.scene,target);index=self.choose(destination,layer,reader);destination.view_layers.remove(layer)
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'CANCELLED'});self.assertEqual(bpy.context.scene,self.scene)
    def test_non_object_reference_never_filters_outliner(self):
        mesh=bpy.data.meshes.new('UnusedMesh');material=bpy.data.materials.new('Material');mesh.materials.append(material)
        areas=[a for a in bpy.context.window.screen.areas if a.type=='OUTLINER'];before=[(a.spaces.active.display_mode,a.spaces.active.filter_text) for a in areas]
        ops_tools.lookup(self.scene,material)
        rows=[(i,row) for i,row in enumerate(self.scene.wkngr_usage_rows) if id_handles.resolve(row.owner_uid)==mesh]
        self.assertTrue(rows);index,row=rows[0];self.assertFalse(row.object_uid)
        self.assertEqual(bpy.ops.wkngr.locate_usage(index=index),{'CANCELLED'})
        self.assertEqual(before,[(a.spaces.active.display_mode,a.spaces.active.filter_text) for a in areas])
    def test_scene_switch_keeps_source_layer_selection(self):
        target,reader=self.reader();selected=self.object('SourceSelected');source_layer=self.scene.view_layers[0]
        source_layer.update();selected.select_set(True,view_layer=source_layer);source_layer.objects.active=selected
        destination,layer=self.destination();destination.collection.objects.link(reader)
        ops_tools.locate(bpy.context,reader,destination,layer.name)
        self.assertTrue(selected.select_get(view_layer=source_layer));self.assertEqual(source_layer.objects.active,selected)
        self.assertEqual(layer.objects.active,reader)
    def test_requery_after_navigation_releases_old_scene_handles(self):
        target,reader=self.reader();destination,layer=self.destination();destination.collection.objects.link(reader)
        ops_tools.lookup(self.scene,target);index=self.choose(destination,layer,reader);bpy.ops.wkngr.locate_usage(index=index)
        scan_cache.clear_all();self.assertFalse(id_handles._live)
        self.assertFalse(self.scene.wkngr_usage_rows);self.assertFalse(destination.wkngr_usage_rows)
    def test_context_snapshot_restored_after_save_without_persisting(self):
        target,reader=self.reader();destination,layer=self.destination();destination.collection.objects.link(reader)
        ops_tools.lookup(self.scene,target)
        before=[(r.scene_uid,r.view_layer_name,r.object_uid,r.location_label) for r in self.scene.wkngr_usage_rows]
        path=Path(support.support.TEMP.name)/'navigation.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
        self.assertEqual(before,[(r.scene_uid,r.view_layer_name,r.object_uid,r.location_label) for r in self.scene.wkngr_usage_rows])
        bpy.ops.wm.open_mainfile(filepath=str(path));self.assertFalse(any(s.wkngr_usage_rows for s in bpy.data.scenes))

if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.support.batch_rename.unregister()
    print('NAVIGATION RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)
