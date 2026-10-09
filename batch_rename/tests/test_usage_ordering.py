"""Reference distance, graph completeness and bounded lookup work on native bpy."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_global_rename as support
bpy=support.bpy
from batch_rename import ops_tools,usage_index,id_handles
class Tests(support.Tests):
    def group(self,name,target,child=None):
        tree=bpy.data.node_groups.new(name,'GeometryNodeTree')
        tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        tree.nodes.new('NodeGroupOutput')
        if child:
            node=tree.nodes.new('GeometryNodeGroup');node.node_tree=child
        else:
            node=tree.nodes.new('GeometryNodeCollectionInfo');node.inputs['Collection'].default_value=target
        return tree
    def fixture(self):
        source=self.object('Source');collection=bpy.data.collections.new('ZSourceCollection');collection.objects.link(source)
        parent=bpy.data.collections.new('ZParent');parent.children.link(collection);self.scene.collection.children.link(parent)
        instance=bpy.data.objects.new('ZInstance',None);self.scene.collection.objects.link(instance);instance.instance_type='COLLECTION';instance.instance_collection=collection
        leaf=self.group('ZLeaf',collection)
        reader=self.object('ZDirectReader');reader.modifiers.new('Geometry','NODES').node_group=leaf
        nested=self.group('ANested',collection,leaf)
        deep=self.object('ADeepReader');deep.modifiers.new('Geometry','NODES').node_group=nested
        return source,collection,parent,instance,leaf,reader,nested,deep
    def rows(self,target):
        ops_tools.lookup(self.scene,target);return list(self.scene.wkngr_usage_rows)
    def row(self,rows,owner):
        return next(row for row in rows if id_handles.resolve(row.owner_uid)==owner)
    def test_collection_shortest_distance_overrides_names(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        rows=self.rows(collection)
        depths=[row.reference_depth for row in rows];self.assertEqual(depths,sorted(depths))
        for owner,expected in ((parent,1),(instance,1),(leaf,1),(reader,2),(nested,2),(deep,3)):
            self.assertEqual(self.row(rows,owner).reference_depth,expected)
        self.assertLess(rows.index(self.row(rows,reader)),rows.index(self.row(rows,deep)))
        self.assertLess(rows.index(self.row(rows,parent)),rows.index(self.row(rows,instance)))
    def test_object_membership_instance_and_nested_group_depth(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        rows=self.rows(source);self.assertEqual(id_handles.resolve(rows[0].object_uid),source)
        for owner,expected in ((source,0),(collection,1),(instance,2),(leaf,2),(reader,3),(deep,4)):
            self.assertEqual(self.row(rows,owner).reference_depth,expected)
    def test_multiple_paths_choose_shortest_and_keep_field_locations(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        deep.constraints.new('COPY_LOCATION').target=source
        deep.constraints.new('COPY_ROTATION').target=source
        rows=self.rows(source);found=[r for r in rows if id_handles.resolve(r.object_uid)==deep]
        self.assertEqual(len(found),1);self.assertEqual(found[0].reference_depth,1)
        self.assertIn('constraints[0]',found[0].path);self.assertIn('constraints[1]',found[0].path)
    def test_light_embedded_tree_is_not_extra_reference_hop(self):
        source=self.object('Source');light=bpy.data.lights.new('LampData','POINT');light.use_nodes=True
        obj=bpy.data.objects.new('Lamp',light);self.scene.collection.objects.link(obj)
        node=light.node_tree.nodes.new('ShaderNodeTexCoord');node.object=source
        rows=self.rows(source)
        self.assertEqual(self.row(rows,light).reference_depth,1)
        self.assertEqual(self.row(rows,obj).reference_depth,2)
        self.assertIn(node.name,self.row(rows,obj).path)
    def test_shared_nodes_not_expanded_per_object(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        for i in range(12):self.object('Reader'+str(i)).modifiers.new('Geometry','NODES').node_group=nested
        with patch.object(usage_index.UsageIndex,'query',side_effect=AssertionError('Legacy report expansion')),patch.object(usage_index.UsageIndex,'group_object_users',side_effect=AssertionError('Repeated group binding scan')):
            rows=self.rows(collection)
        found=[r for r in rows if r.object_uid]
        self.assertEqual(len(found),15)
    def test_cycle_terminates_and_unused_group_keeps_reference(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        unused=self.group('Unused',collection);source.constraints.new('COPY_LOCATION').target=instance
        rows=self.rows(source);self.assertEqual(self.row(rows,unused).reference_depth,2)
        self.assertTrue(all(len(r.path)<3000 for r in rows))
        self.assertEqual(self.row(rows,instance).reference_depth,2)
    def test_context_discovery_does_not_evaluate_geometry(self):
        obj=self.object('Reader');destination=bpy.data.scenes.new('Inactive');destination.collection.objects.link(obj)
        layer=destination.view_layers.new('Second')
        from types import SimpleNamespace
        class LayerProxy:
            def __init__(self,layer):self.layer=layer
            def __getattr__(self,name):
                if name=='update':raise AssertionError('Unexpected geometry evaluation')
                return getattr(self.layer,name)
        scenes=[SimpleNamespace(collection=s.collection,view_layers=[LayerProxy(l) for l in s.view_layers]) for s in bpy.data.scenes]
        with patch.object(ops_tools,'bpy',SimpleNamespace(data=SimpleNamespace(scenes=scenes))):
            contexts=ops_tools._scene_contexts([obj])
        self.assertEqual(len(contexts[obj.as_pointer()]),3)
        self.assertTrue(all(not excluded for scene,name,excluded in contexts[obj.as_pointer()]))
    def test_scene_transfer_preserves_sort_metadata(self):
        source,collection,parent,instance,leaf,reader,nested,deep=self.fixture()
        rows=self.rows(collection);before=[(r.reference_depth,r.reference_kind,r.path) for r in rows]
        destination=bpy.data.scenes.new('Destination');ops_tools._transfer_lookup(self.scene,destination)
        self.assertEqual(before,[(r.reference_depth,r.reference_kind,r.path) for r in destination.wkngr_usage_rows])
        self.assertFalse(self.scene.wkngr_usage_rows)
if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.batch_rename.unregister()
    print('ORDERING RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)
