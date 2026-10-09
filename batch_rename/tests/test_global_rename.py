"""All-category actions and collection-reader name contracts."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
TEMP=tempfile.TemporaryDirectory(prefix='rename-global-')
for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
    p=Path(TEMP.name)/kind;p.mkdir();os.environ['BLENDER_USER_'+kind]=str(p)
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import bpy,batch_rename
batch_rename.register()
from batch_rename import data_catalog as catalog,scan_cache,preset_manager as pm,props,name_references
OLD=chr(0x65e7)
class Tests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True);scan_cache.ensure_initialized()
        self.scene=bpy.context.scene
        pm._dir=str(Path(TEMP.name)/self._testMethodName);Path(pm._dir).mkdir()
        pm.invalidate_cache();pm.ensure_defaults();props.refresh_preset_enum()
    def object(self,name='Object'):
        mesh=bpy.data.meshes.new(name+'Mesh');obj=bpy.data.objects.new(name,mesh)
        self.scene.collection.objects.link(obj);return obj
    def draft(self,key,value):
        c=next(c for c in self.scene.wkngr_categories if c.key==key)
        for row in c.entries:row.new_name=value
    def reader(self,source,old=OLD):
        collection=bpy.data.collections.new('SourceCollection');collection.objects.link(source)
        obj=self.object('Reader');tree=bpy.data.node_groups.new('ReaderTree','GeometryNodeTree')
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        info=tree.nodes.new('GeometryNodeCollectionInfo');info.inputs['Collection'].default_value=collection
        node=tree.nodes.new('GeometryNodeInputNamedAttribute');node.inputs['Name'].default_value=old
        return obj,tree,node,collection
    def test_actions_cover_all_categories(self):
        obj=self.object(OLD+'Object');mat=bpy.data.materials.new(OLD+'Material');obj.data.materials.append(mat)
        catalog.scan_all(self.scene);self.scene.wkngr_settings.replace_from=OLD;self.scene.wkngr_settings.replace_to='New'
        bpy.ops.wkngr.preview_replace()
        rows=[r for c in self.scene.wkngr_categories for r in c.entries if OLD in r.old_name and not r.read_only]
        self.assertGreaterEqual(len(rows),3);self.assertTrue(all(OLD not in r.new_name for r in rows))
        bpy.ops.wkngr.apply();self.assertEqual(obj.name,'NewObject');self.assertEqual(mat.name,'NewMaterial')
        self.assertEqual(obj.data.name,'NewObjectMesh')
    def test_dictionary_fill_covers_all_categories(self):
        obj=self.object(OLD+'Object');mat=bpy.data.materials.new(OLD+'Material')
        pm.save_preset('usr',{OLD:'New'});catalog.scan_all(self.scene);bpy.ops.wkngr.auto_fill()
        self.assertTrue(all(OLD not in r.new_name for c in self.scene.wkngr_categories for r in c.entries if OLD in r.old_name and not r.read_only))
    def test_collection_reader_attribute_updates(self):
        source=self.object('Source');attr=source.data.attributes.new(OLD,'FLOAT','POINT')
        reader,tree,node,collection=self.reader(source)
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene)
        self.assertEqual(result[:2],(1,[]));self.assertEqual(attr.name,'Density')
        self.assertEqual(node.inputs['Name'].default_value,'Density')
        self.assertEqual(tree.nodes.get('Collection Info').inputs['Collection'].default_value,collection)
    def test_uv_and_material_string_update(self):
        source=self.object('Source');uv=source.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');source.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        self.reader(source,'Unrelated')
        catalog.scan_all(self.scene);self.draft('__uv_layers__','UVMap')
        self.assertIn('__name_references__',{c.key for c in self.scene.wkngr_categories})
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]))
        self.assertEqual(uv.name,'UVMap');self.assertEqual(node.uv_map,'UVMap')
    def test_global_uv_attribute_same_reference_agreement(self):
        source=self.object('Source');uv=source.data.uv_layers.new(name=OLD)
        reader,tree,node,_=self.reader(source)
        mat=bpy.data.materials.new('Material');source.data.materials.append(mat)
        shader=mat.node_tree.nodes.new('ShaderNodeUVMap');shader.uv_map=OLD
        catalog.scan_all(self.scene);self.scene.wkngr_settings.replace_from=OLD;self.scene.wkngr_settings.replace_to='UVMap'
        bpy.ops.wkngr.preview_replace();bpy.ops.wkngr.apply()
        self.assertEqual(uv.name,'UVMap');self.assertEqual(shader.uv_map,'UVMap');self.assertEqual(node.inputs['Name'].default_value,'UVMap')
    def test_shared_collection_conflict_is_retained(self):
        a=self.object('A');b=self.object('B')
        aa=a.data.attributes.new(OLD,'FLOAT','POINT');bb=b.data.attributes.new(OLD,'FLOAT','POINT')
        reader,tree,node,collection=self.reader(a);collection.objects.link(b)
        catalog.scan_all(self.scene);c=next(c for c in self.scene.wkngr_categories if c.key=='__attributes__')
        for row in c.entries:row.new_name='AValue' if row.target==a.data else 'BValue'
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])
        self.assertEqual(aa.name,OLD);self.assertEqual(bb.name,OLD);self.assertEqual(node.inputs['Name'].default_value,OLD)
        self.assertTrue(all(r.new_name!=r.old_name for r in c.entries))
    def test_unrelated_same_name_is_not_modified(self):
        a=self.object('A');b=self.object('B')
        aa=a.data.attributes.new(OLD,'FLOAT','POINT');bb=b.data.attributes.new(OLD,'FLOAT','POINT')
        _,_,node,_=self.reader(a)
        catalog.scan_all(self.scene);c=next(c for c in self.scene.wkngr_categories if c.key=='__attributes__')
        next(r for r in c.entries if r.target==a.data).new_name='Density'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]))
        self.assertEqual(bb.name,OLD);self.assertEqual(node.inputs['Name'].default_value,'Density')
    def test_failure_rolls_back_other_categories(self):
        obj=self.object(OLD+'Object');uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.draft('objects','RenamedObject');self.draft('__uv_layers__','UVMap')
        original=name_references.write
        def fail(target,field,value):
            if target==node and field=='uv_map' and value=='UVMap':raise ValueError('injected reference failure')
            original(target,field,value)
        with patch.object(name_references,'write',side_effect=fail):result=catalog.apply_all(self.scene)
        self.assertEqual(result[0],0);self.assertTrue(result[1]);self.assertEqual(obj.name,OLD+'Object')
        self.assertEqual(uv.name,OLD);self.assertEqual(node.uv_map,OLD)
    def test_zero_users_after_global_scan_and_apply(self):
        collection=bpy.data.collections.new(OLD+'Collection')
        for i in range(3):catalog.scan_all(self.scene);self.assertEqual(collection.users,0)
        self.draft('collections','RenamedCollection');catalog.apply_all(self.scene);self.assertEqual(collection.users,0)
    def test_collection_all_sources_agree(self):
        a=self.object('A');b=self.object('B')
        aa=a.data.attributes.new(OLD,'FLOAT','POINT');bb=b.data.attributes.new(OLD,'FLOAT','POINT')
        _,_,node,collection=self.reader(a);collection.objects.link(b)
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(2,[]))
        self.assertEqual(aa.name,'Density');self.assertEqual(bb.name,'Density')
        self.assertEqual(node.inputs['Name'].default_value,'Density')
    def test_cross_type_uv_attribute_reader_agreement(self):
        a=self.object('A');b=self.object('B')
        uv=a.data.uv_layers.new(name=OLD);attr=b.data.attributes.new(OLD,'FLOAT','POINT')
        _,_,node,collection=self.reader(a);collection.objects.link(b)
        catalog.scan_all(self.scene)
        self.scene.wkngr_settings.replace_from=OLD;self.scene.wkngr_settings.replace_to='Unified'
        bpy.ops.wkngr.preview_replace()
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(2,[]))
        self.assertEqual(uv.name,'Unified');self.assertEqual(attr.name,'Unified')
        self.assertEqual(node.inputs['Name'].default_value,'Unified')
    def test_datablock_name_swap_keeps_identity(self):
        a=self.object('SwapA');b=self.object('SwapB')
        self.scene.wkngr_settings.custom_enable=True
        self.scene.wkngr_settings.custom_quick='Swap'
        catalog.scan_all(self.scene);c=next(c for c in self.scene.wkngr_categories if c.key=='objects')
        for row in c.entries:row.new_name='SwapB' if row.target==a else 'SwapA'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(2,[]))
        self.assertEqual(a.name,'SwapB');self.assertEqual(b.name,'SwapA')
    def test_partial_chinese_draft_skipped_while_complete_applies(self):
        a=self.object(OLD+'A');b=self.object(OLD+'B')
        catalog.scan_all(self.scene)
        c=next(c for c in self.scene.wkngr_categories if c.key=='objects')
        for row in c.entries:row.new_name='Partial'+OLD if row.target==a else 'Complete'
        count,errors,_=catalog.apply_all(self.scene)
        self.assertEqual(count,1);self.assertTrue(errors)
        self.assertEqual(a.name,OLD+'A');self.assertEqual(b.name,'Complete')
        self.assertEqual(next(r for r in c.entries if r.target==a).new_name,'Partial'+OLD)
    def test_partial_uv_and_reference_keep_original(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.draft('__uv_layers__','Partial'+OLD)
        self.draft('__name_references__','Partial'+OLD)
        count,errors,_=catalog.apply_all(self.scene)
        self.assertEqual(count,0);self.assertTrue(errors)
        self.assertEqual(uv.name,OLD);self.assertEqual(node.uv_map,OLD)
    def test_partial_explicit_reference_blocks_complete_uv(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.draft('__uv_layers__','Complete')
        self.draft('__name_references__','Partial'+OLD)
        count,errors,_=catalog.apply_all(self.scene)
        self.assertEqual(count,0);self.assertTrue(errors)
        self.assertEqual(uv.name,OLD);self.assertEqual(node.uv_map,OLD)
    def test_conflicting_reference_draft_blocks_primary(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.draft('__uv_layers__','UVMap');self.draft('__name_references__','Other')
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])
        self.assertEqual(uv.name,OLD);self.assertEqual(node.uv_map,OLD)

    def test_blocked_primary_cannot_leak_through_string_preview(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        text=bpy.data.texts.new('ExplicitLookup')
        text.write('bpy.data.meshes['+repr(obj.data.name)+'].uv_layers['+repr(OLD)+']')
        catalog.scan_all(self.scene);self.draft('__uv_layers__','UVMap');self.draft('__name_references__','UVMap')
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])
        self.assertEqual(uv.name,OLD);self.assertEqual(node.uv_map,OLD)
    def test_unknown_external_source_remains_guarded(self):
        source=self.object('Source');attr=source.data.attributes.new(OLD,'FLOAT','POINT')
        _,tree,node,_=self.reader(source)
        inputnode=tree.nodes.new('NodeGroupInput')
        interface=tree.interface.new_socket(name='Unknown',in_out='INPUT',socket_type='NodeSocketCollection')
        info=tree.nodes.get('Collection Info')
        switch=tree.nodes.new('GeometryNodeSwitch');switch.input_type='COLLECTION'
        tree.links.new(inputnode.outputs[interface.identifier],switch.inputs['True'])
        tree.links.new(switch.outputs[0],info.inputs['Collection'])
        catalog.scan_all(self.scene);self.draft('__attributes__','Density');self.draft('__name_references__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])
        self.assertEqual(attr.name,OLD);self.assertEqual(node.inputs['Name'].default_value,OLD)
    def test_global_save_reload_clears_scan_caches(self):
        source=self.object(OLD+'Source');uv=source.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new(OLD+'Material');source.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.scene.wkngr_settings.replace_from=OLD;self.scene.wkngr_settings.replace_to='New'
        bpy.ops.wkngr.preview_replace();bpy.ops.wkngr.apply()
        path=Path(TEMP.name)/'global-roundtrip.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
        self.assertFalse(bpy.context.scene.wkngr_categories)
        self.assertEqual(bpy.data.materials['NewMaterial'].node_tree.nodes.get('UV Map').uv_map,'New')
        self.assertEqual(bpy.data.meshes['NewSourceMesh'].uv_layers[0].name,'New')
    def test_reference_preview_also_works_when_data_is_unchanged(self):
        mat=bpy.data.materials.new('Material');node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=OLD
        catalog.scan_all(self.scene);self.draft('__name_references__','UVMap')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(node.uv_map,'UVMap')

if __name__=='__main__':
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    finally:batch_rename.unregister()
    print('GLOBAL RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)

