"""Tools menu, locked naming, linked-name provenance and non-owning lookup."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_global_rename as support
bpy=support.bpy;catalog=support.catalog;OLD=support.OLD
from batch_rename import data_tools,ops_tools,id_handles,scan_cache,geometry_contracts,ui_main
class Tests(support.Tests):
    def string_group(self,obj):
        tree=bpy.data.node_groups.new('StringGroup','GeometryNodeTree')
        socket=tree.interface.new_socket(name='Name',in_out='INPUT',socket_type='NodeSocketString')
        socket.default_value=OLD
        node=tree.nodes.new('GeometryNodeInputNamedAttribute');inputnode=tree.nodes.new('NodeGroupInput')
        tree.links.new(inputnode.outputs[socket.identifier],node.inputs['Name'])
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        return tree,socket,node,mod
    def test_modifier_string_input_updated(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        tree,socket,node,mod=self.string_group(obj)
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]))
        source=geometry_contracts.modifier_values(mod)[socket.identifier]
        self.assertEqual(geometry_contracts.string_value(source),'Density');self.assertEqual(attr.name,'Density')
    def test_nested_group_string_input_updated(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        child,socket,node,mod=self.string_group(obj)
        parent=bpy.data.node_groups.new('Parent','GeometryNodeTree')
        group=parent.nodes.new('GeometryNodeGroup');group.node_tree=child
        group.inputs[socket.identifier].default_value=OLD;mod.node_group=parent
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]))
        self.assertEqual(group.inputs[socket.identifier].default_value,'Density')
    def test_shared_string_constant_updates_all_names(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        tree,socket,node,mod=self.string_group(obj)
        string=tree.nodes.new('FunctionNodeInputString');string.string=OLD
        other=tree.nodes.new('GeometryNodeRemoveAttribute')
        tree.links.new(string.outputs[0],node.inputs['Name']);tree.links.new(string.outputs[0],other.inputs['Name'])
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(string.string,'Density')
    def test_runtime_string_join_stays_protected(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        tree,socket,node,mod=self.string_group(obj)
        join=tree.nodes.new('GeometryNodeStringJoin');tree.links.new(join.outputs[0],node.inputs['Name'])
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1]);self.assertEqual(attr.name,OLD)
    def test_data_names_sync_keeps_mesh_identity(self):
        obj=self.object('Desired');before=obj.data
        stats=data_tools.synchronize();self.assertEqual(obj.data,before);self.assertEqual(obj.data.name,obj.name)
        self.assertEqual(stats['renamed'],1)
    def test_shared_mesh_skipped(self):
        a=self.object('A');b=bpy.data.objects.new('B',a.data)
        before=a.data.name;stats=data_tools.synchronize();self.assertEqual(a.data.name,before);self.assertEqual(stats['shared'],1)
    def test_capitalization_preserves_rest(self):
        obj=self.object('treeABC');mat=bpy.data.materials.new('woodXYZ');coll=bpy.data.collections.new('plantsABC')
        count,skipped,errors,collisions=ops_tools.capitalize_all()
        self.assertEqual(errors,[]);self.assertEqual(obj.name,'TreeABC');self.assertEqual(mat.name,'WoodXYZ');self.assertEqual(coll.name,'PlantsABC')
    def test_linked_data_automatically_skipped(self):
        libpath=Path(support.TEMP.name)/'linked-naming.blend'
        mesh=bpy.data.meshes.new('linkedMesh');obj=bpy.data.objects.new('linkedObject',mesh)
        mat=bpy.data.materials.new('linkedMaterial');mesh.materials.append(mat)
        bpy.data.libraries.write(str(libpath),{obj,mat})
        bpy.data.objects.remove(obj);bpy.data.meshes.remove(mesh);bpy.data.materials.remove(mat)
        with bpy.data.libraries.load(str(libpath),link=True) as (src,dst):
            dst.objects=['linkedObject'];dst.materials=['linkedMaterial']
        obj=dst.objects[0];mat=dst.materials[0];before=obj.data.name
        stats=data_tools.synchronize();self.assertGreaterEqual(stats['readonly'],1);self.assertEqual(obj.data.name,before)
        count,skipped,errors,collisions=ops_tools.capitalize_all()
        self.assertGreaterEqual(skipped,2);self.assertEqual(obj.name,'linkedObject');self.assertEqual(mat.name,'linkedMaterial')
    def test_material_lookup_preserves_users_and_exact_owner(self):
        obj=self.object();mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        before=mat.users;count=ops_tools.lookup(self.scene,mat)
        self.assertGreater(count,0);self.assertEqual(mat.users,before)
        self.assertTrue(any(id_handles.resolve(row.owner_uid)==obj for row in self.scene.wkngr_usage_rows))
    def test_object_constraint_lookup_exact_owner(self):
        target=self.object('Target');owner=self.object('Owner')
        constraint=owner.constraints.new('COPY_LOCATION');constraint.target=target
        before=target.users;ops_tools.lookup(self.scene,target)
        self.assertEqual(target.users,before)
        self.assertTrue(any(id_handles.resolve(row.owner_uid)==owner and 'constraints' in row.path for row in self.scene.wkngr_usage_rows))
    def test_collection_node_lookup_exact_reader(self):
        source=self.object('Source');reader,tree,node,collection=self.reader(source)
        before=collection.users;ops_tools.lookup(self.scene,collection)
        self.assertEqual(collection.users,before)
        self.assertTrue(any(id_handles.resolve(row.owner_uid)==reader for row in self.scene.wkngr_usage_rows))
    def test_lookup_clear_releases_handles(self):
        obj=self.object();mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        ops_tools.lookup(self.scene,mat);self.assertTrue(self.scene.wkngr_usage_rows)
        scan_cache.clear_all();self.assertFalse(self.scene.wkngr_usage_rows);self.assertFalse(id_handles._live)
    def test_lookup_rows_not_saved(self):
        obj=self.object();mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        ops_tools.lookup(self.scene,mat)
        path=Path(support.TEMP.name)/'lookup-roundtrip.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
        self.assertFalse(bpy.context.scene.wkngr_usage_rows)
    def test_tools_menu_rna_layout(self):
        from types import SimpleNamespace
        class Probe:
            def label(self,**kw):pass
            def prop(self,data,name,**kw):self_test.assertIn(name,data.bl_rna.properties)
            def prop_search(self,data,name,search,collection,**kw):getattr(search,collection)
            def row(self,**kw):return self
            def operator(self,name,**kw):
                a,b=name.split('.');getattr(getattr(bpy.ops,a),b).get_rna_type();return SimpleNamespace()
            def template_list(self,kind,ident,data,name,active,index,**kw):
                getattr(data,name);getattr(active,index)
        self_test=self
        for mode in ('SYNC','CAPITAL','LOOKUP'):
            self.scene.wkngr_settings.tool_mode=mode;ui_main.draw_main(Probe(),self.scene)
    def test_shared_group_per_object_string_values_independent(self):
        a=self.object('A');b=self.object('B')
        aa=a.data.attributes.new(OLD+'A','FLOAT','POINT');bb=b.data.attributes.new(OLD+'B','FLOAT','POINT')
        tree,socket,node,ma=self.string_group(a);mb=b.modifiers.new('Geometry','NODES');mb.node_group=tree
        def value(mod,text):
            source=geometry_contracts.modifier_values(mod)[socket.identifier]
            support.name_references.write(source[0],source[1],text)
        value(ma,OLD+'A');value(mb,OLD+'B')
        catalog.scan_all(self.scene);category=next(c for c in self.scene.wkngr_categories if c.key=='__attributes__')
        for row in category.entries:row.new_name='DensityA' if row.target==a.data else 'DensityB'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(2,[]))
        self.assertEqual(geometry_contracts.string_value(geometry_contracts.modifier_values(ma)[socket.identifier]),'DensityA')
        self.assertEqual(geometry_contracts.string_value(geometry_contracts.modifier_values(mb)[socket.identifier]),'DensityB')
    def test_actual_object_selection_and_outliner_location(self):
        obj=self.object('LocateMe')
        areas=[area for area in bpy.context.window.screen.areas if area.type=='OUTLINER']
        self.assertTrue(areas)
        ops_tools.locate(bpy.context,obj)
        self.assertEqual(bpy.context.view_layer.objects.active,obj);self.assertTrue(obj.select_get())
        mat=bpy.data.materials.new('LocateMaterial')
        with self.assertRaises(ValueError):ops_tools.locate(bpy.context,mat)
        self.assertTrue(all(area.spaces.active.display_mode=='VIEW_LAYER' and not area.spaces.active.filter_text for area in areas))
    def test_hidden_locate_reveals_and_selects_requested_object(self):
        a=self.object('Selected');b=self.object('Hidden')
        a.select_set(True);self.scene.view_layers[0].objects.active=a;b.hide_set(True)
        ops_tools.locate(bpy.context,b)
        self.assertFalse(b.hide_get());self.assertTrue(b.select_get());self.assertEqual(bpy.context.view_layer.objects.active,b)


    def test_initial_lookup_survives_first_scene_update(self):
        obj=self.object();mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        scan_cache._needs_initial_cleanup=True
        ops_tools.lookup(self.scene,mat)
        self.assertFalse(scan_cache._needs_initial_cleanup)
        bpy.context.view_layer.update();self.assertTrue(self.scene.wkngr_usage_rows)

    def test_lookup_never_descends_unknown_rna_collection(self):
        from types import SimpleNamespace
        from batch_rename import usage_index
        target=self.object('Target')
        class UnsafeOwner:
            bl_rna=SimpleNamespace(properties=[SimpleNamespace(type='COLLECTION',identifier='unsafe_geometry')])
            def as_pointer(self):return 123
            def items(self):return ()
            @property
            def unsafe_geometry(self):raise AssertionError('Unsafe native getter accessed')
        self.assertEqual(usage_index.nested_reference_locations(UnsafeOwner(),target),([],[]))
    def test_native_owner_is_inspected_only_once(self):
        from batch_rename import usage_index
        target=self.object('Target');owner=self.object('Owner')
        owner.constraints.new('COPY_LOCATION').target=target
        native=bpy.data.user_map(subset=[target]).get(target,set())
        with patch.object(usage_index,'nested_reference_locations',wraps=usage_index.nested_reference_locations) as inspect:
            ops_tools.lookup(self.scene,target)
        self.assertEqual(inspect.call_count,len(native))
    def test_repeated_lookup_does_not_add_native_users(self):
        obj=self.object('Target');mat=bpy.data.materials.new('Material');obj.data.materials.append(mat)
        collection=bpy.data.collections.new('Collection');collection.objects.link(obj)
        targets=(obj,mat,collection);before=[target.users for target in targets]
        for _ in range(3):
            for target in targets:ops_tools.lookup(self.scene,target)
        self.assertEqual([target.users for target in targets],before)

if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.batch_rename.unregister()
    print('TOOLS RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)

