import os,sys,tempfile,unittest,runpy
from pathlib import Path
TEMP=tempfile.TemporaryDirectory(prefix='rename150-')
for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
    path=Path(TEMP.name)/kind;path.mkdir();os.environ['BLENDER_USER_'+kind]=str(path)
import bpy,_bpy_restrict_state
_bpy_restrict_state._bpy=bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import batch_rename as addon
with _bpy_restrict_state.RestrictBlend():addon.register()
from batch_rename import data_catalog as catalog,scan_cache,nested_data,id_handles,name_references

class Tests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scan_cache.ensure_initialized()
        self.scene=bpy.context.scene
    def obj(self,name='Object',mesh=None):
        mesh=mesh or bpy.data.meshes.new(name+'Mesh')
        obj=bpy.data.objects.new(name,mesh);self.scene.collection.objects.link(obj);return obj
    def cat(self,key):
        return next(c for c in self.scene.wkngr_categories if c.key==key)
    def apply(self,key,new='Renamed'):
        catalog.scan_all(self.scene)
        c=self.cat(key)
        for row in c.entries:row.new_name=new
        return name_references.apply(c)
    def gn(self,obj,name='\u6743\u91cd'):
        tree=bpy.data.node_groups.new('Tree','GeometryNodeTree')
        tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        node=tree.nodes.new('GeometryNodeInputNamedAttribute');node.inputs['Name'].default_value=name
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        return tree,node,mod
    def test_unrelated_self_object_reader_does_not_block(self):
        target=self.obj('Target');attr=target.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        other=self.obj('Unrelated');tree,node,mod=self.gn(other,'English')
        selfnode=tree.nodes.new('GeometryNodeSelfObject');info=tree.nodes.new('GeometryNodeObjectInfo')
        tree.links.new(selfnode.outputs[0],info.inputs['Object'])
        self.assertEqual(self.apply('__attributes__','Density')[:2],(1,[]))
        self.assertEqual(attr.name,'Density')
    def input_reader(self, reader, source):
        tree,node,mod=self.gn(reader,'English')
        socket=tree.interface.new_socket(name='Source',in_out='INPUT',socket_type='NodeSocketObject')
        groupinput=tree.nodes.new('NodeGroupInput');info=tree.nodes.new('GeometryNodeObjectInfo')
        tree.links.new(groupinput.outputs[socket.identifier],info.inputs['Object'])
        if hasattr(mod,'properties'):getattr(mod.properties.inputs,socket.identifier).value=source
        else:mod[socket.identifier]=source
        return tree,mod
    def test_unrelated_object_interface_does_not_block(self):
        target=self.obj('Target');target.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        self.input_reader(self.obj('Reader'),self.obj('OtherSource'))
        self.assertEqual(self.apply('__attributes__','Density')[:2],(1,[]))
    def test_resolved_object_interface_allows_unrelated_name(self):
        target=self.obj('Target');attr=target.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        self.input_reader(self.obj('Reader'),target)
        count,errors,_=self.apply('__attributes__','Density');self.assertEqual((count,errors),(1,[]));self.assertEqual(attr.name,'Density')
    def test_own_self_object_name_references_can_update(self):
        obj=self.obj();attr=obj.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        tree,node,mod=self.gn(obj,attr.name)
        selfnode=tree.nodes.new('GeometryNodeSelfObject');info=tree.nodes.new('GeometryNodeObjectInfo')
        tree.links.new(selfnode.outputs[0],info.inputs['Object'])
        self.assertEqual(self.apply('__attributes__','Density')[:2],(1,[]));self.assertEqual(node.inputs['Name'].default_value,'Density')
    def test_unused_dynamic_group_does_not_block_attributes(self):
        obj=self.obj();attr=obj.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        orphan=bpy.data.node_groups.new('UnusedTree','GeometryNodeTree')
        source=orphan.nodes.new('GeometryNodeSelfObject');info=orphan.nodes.new('GeometryNodeObjectInfo')
        orphan.links.new(source.outputs[0],info.inputs['Object'])
        self.assertEqual(orphan.users,0)
        self.assertEqual(self.apply('__attributes__','Density')[:2],(1,[]))
        self.assertEqual(attr.name,'Density')
    def test_blocked_preview_is_retained_after_apply(self):
        obj=self.obj();group=obj.vertex_groups.new(name=chr(0x6743)+chr(0x91cd));tree,node,mod=self.gn(obj)
        text=tree.nodes.new('FunctionNodeInputString');text.string=group.name
        tree.links.new(text.outputs[0],node.inputs['Name'])
        other=tree.nodes.new('GeometryNodeStringJoin');tree.links.new(text.outputs[0],other.inputs[1])
        catalog.scan_all(self.scene);c=self.cat('__vertex_groups__');c.entries[0].new_name='Pending'
        self.scene.wkngr_category_index=list(self.scene.wkngr_categories).index(c)
        result=catalog.apply_category(self.scene)
        self.assertEqual(result[0],0);self.assertTrue(result[1])
        self.assertEqual(self.cat('__vertex_groups__').entries[0].new_name,'Pending')
    def test_scan_zero_users_save_preview_reload(self):
        tree=bpy.data.node_groups.new('\u8282\u70b9\u7ec4','GeometryNodeTree');tree.use_fake_user=True
        tree.nodes.new('NodeFrame').label='\u6743\u91cd'
        before=tree.users
        for i in range(3):catalog.scan_all(self.scene);self.assertEqual(tree.users,before)
        c=self.cat('node_groups');c.entries[0].new_name='Pending'
        path=Path(TEMP.name)/'clean.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
        self.assertEqual(tree.users,before);self.assertEqual(self.cat('node_groups').entries[0].new_name,'Pending')
        # File is clean even when the load cleanup is disabled.
        callbacks=list(bpy.app.handlers.load_post);bpy.app.handlers.load_post.clear()
        try:bpy.ops.wm.open_mainfile(filepath=str(path))
        finally:bpy.app.handlers.load_post.extend(callbacks)
        self.assertFalse(bpy.context.scene.wkngr_categories)
        self.assertEqual(bpy.data.node_groups['\u8282\u70b9\u7ec4'].users,1)
    def test_deleted_id_replacement_not_reused(self):
        mat=bpy.data.materials.new('\u6743\u91cd');catalog.scan_all(self.scene);row=self.cat('materials').entries[0]
        self.assertEqual(mat.users,0);bpy.data.materials.remove(mat)
        replacement=bpy.data.materials.new('\u6743\u91cd');self.assertIsNone(row.target)
        row.new_name='Wrong';self.scene.wkngr_category_index=list(self.scene.wkngr_categories).index(self.cat('materials'))
        catalog.apply_category(self.scene);self.assertEqual(replacement.name,'\u6743\u91cd')
    def test_actual_undo_redo_handles(self):
        name=chr(0x6750)+chr(0x8d28)
        mat=bpy.data.materials.new(name);catalog.scan_all(self.scene)
        self.assertEqual(mat.users,0)
        bpy.ops.ed.undo_push(message='Scanned')
        bpy.data.materials.remove(mat);bpy.ops.ed.undo_push(message='Deleted')
        self.assertIsNone(self.cat('materials').entries[0].target)
        bpy.ops.ed.undo();self.scene=bpy.context.scene
        self.assertEqual(self.cat('materials').entries[0].target,bpy.data.materials[name])
        self.assertEqual(bpy.data.materials[name].users,0)
        bpy.ops.ed.redo();self.scene=bpy.context.scene
        self.assertIsNone(self.cat('materials').entries[0].target)
    def test_legacy_raw_pointers_clear(self):
        tree=bpy.data.node_groups.new('Legacy','GeometryNodeTree')
        for i in range(17):self.scene.wkngr_categories.add().entries.add()['target']=tree
        self.scene.wkngr_sockets.add()['node_group']=tree
        self.assertEqual(tree.users,18)
        scan_cache.clear_all();self.assertEqual(tree.users,0)
    def test_vertex_static_nodes_and_constraint(self):
        obj=self.obj();group=obj.vertex_groups.new(name='\u6743\u91cd');tree,node,mod=self.gn(obj)
        mask=obj.modifiers.new('Mask','MASK');mask.vertex_group=group.name
        follower=self.obj('Follower');constraint=follower.constraints.new('COPY_LOCATION');constraint.target=obj;constraint.subtarget=group.name
        count,errors,_=self.apply('__vertex_groups__')
        self.assertEqual((count,errors),(1,[]));self.assertEqual(group.name,'Renamed')
        self.assertEqual(node.inputs['Name'].default_value,group.name);self.assertEqual(mask.vertex_group,group.name);self.assertEqual(constraint.subtarget,group.name)
    def test_modifier_attribute_input_51_52(self):
        obj=self.obj();group=obj.vertex_groups.new(name='\u6743\u91cd');tree,node,mod=self.gn(obj)
        socket=tree.interface.new_socket(name='Weight',in_out='INPUT',socket_type='NodeSocketFloat')
        if hasattr(mod,'properties'):
            value=getattr(mod.properties.inputs,socket.identifier);value.type='ATTRIBUTE';value.attribute_name=group.name
            get=lambda:value.attribute_name
        else:
            mod[socket.identifier+'_use_attribute']=True;mod[socket.identifier+'_attribute_name']=group.name
            get=lambda:mod[socket.identifier+'_attribute_name']
        count,errors,_=self.apply('__vertex_groups__');self.assertEqual((count,errors),(1,[]));self.assertEqual(get(),'Renamed')
    def test_dedicated_constant_string_reference(self):
        obj=self.obj();group=obj.vertex_groups.new(name=chr(0x6743)+chr(0x91cd));tree,node,mod=self.gn(obj)
        string=tree.nodes.new('FunctionNodeInputString');string.string=group.name
        reroute=tree.nodes.new('NodeReroute');tree.links.new(string.outputs[0],reroute.inputs[0]);tree.links.new(reroute.outputs[0],node.inputs['Name'])
        count,errors,_=self.apply('__vertex_groups__');self.assertEqual((count,errors),(1,[]));self.assertEqual(string.string,'Renamed')
    def test_shared_literal_name_is_updated(self):
        obj=self.obj();group=obj.vertex_groups.new(name='\u6743\u91cd');tree,node,mod=self.gn(obj)
        string=tree.nodes.new('FunctionNodeInputString');string.string=group.name;tree.links.new(string.outputs[0],node.inputs['Name'])
        second=tree.nodes.new('GeometryNodeStoreNamedAttribute');tree.links.new(string.outputs[0],second.inputs['Name'])
        count,errors,_=self.apply('__vertex_groups__');self.assertEqual((count,errors),(1,[]));self.assertEqual(group.name,'Renamed');self.assertEqual(string.string,'Renamed')
    def test_shared_node_partial_preserved_then_consistent(self):
        a=self.obj('A');b=self.obj('B');ga=a.vertex_groups.new(name='\u6743\u91cd');gb=b.vertex_groups.new(name='\u6743\u91cd')
        tree,node,mod=self.gn(a);b.modifiers.new('Geometry','NODES').node_group=tree
        catalog.scan_all(self.scene);c=self.cat('__vertex_groups__');c.entries[0].new_name='Renamed'
        self.assertEqual(name_references.apply(c)[0],0);self.assertEqual(node.inputs['Name'].default_value,'\u6743\u91cd')
        for row in c.entries:row.new_name='Renamed'
        count,errors,_=name_references.apply(c);self.assertEqual((count,errors),(2,[]));self.assertEqual(ga.name,gb.name);self.assertEqual(ga.name,'Renamed')
    def test_attributes_and_vertex_color(self):
        obj=self.obj();attr=obj.data.attributes.new('\u6743\u91cd','FLOAT','POINT');color=obj.data.color_attributes.new('\u989c\u8272','FLOAT_COLOR','POINT')
        mat=bpy.data.materials.new('Mat');mat.use_nodes=True;obj.data.materials.append(mat)
        a=mat.node_tree.nodes.new('ShaderNodeAttribute');a.attribute_name=attr.name
        c=mat.node_tree.nodes.new('ShaderNodeVertexColor');c.layer_name=color.name
        tree,node,mod=self.gn(obj,attr.name)
        self.assertEqual(self.apply('__attributes__','Density')[:2],(1,[]));self.assertEqual(a.attribute_name,'Density');self.assertEqual(node.inputs['Name'].default_value,'Density')
        self.assertEqual(self.apply('__color_attributes__','Color')[:2],(1,[]));self.assertEqual(c.layer_name,'Color')
    def test_external_geometry_string_reference_updated(self):
        a=self.obj('A');group=a.vertex_groups.new(name='\u6743\u91cd');b=self.obj('B');tree,node,mod=self.gn(b)
        info=tree.nodes.new('GeometryNodeObjectInfo');info.inputs['Object'].default_value=a
        self.assertEqual(self.apply('__vertex_groups__')[0],1);self.assertEqual(group.name,'Renamed');self.assertEqual(node.inputs['Name'].default_value,'Renamed')
    def test_shared_shader_world_preserved(self):
        obj=self.obj();uv=obj.data.uv_layers.new(name='\u6743\u91cd')
        tree=bpy.data.node_groups.new('ShaderGroup','ShaderNodeTree');n=tree.nodes.new('ShaderNodeUVMap');n.uv_map=uv.name
        mat=bpy.data.materials.new('Mat');mat.use_nodes=True;obj.data.materials.append(mat);mat.node_tree.nodes.new('ShaderNodeGroup').node_tree=tree
        world=bpy.data.worlds.new('World');world.use_nodes=True;world.node_tree.nodes.new('ShaderNodeGroup').node_tree=tree
        self.assertEqual(self.apply('__uv_layers__')[0],0);self.assertEqual(uv.name,'\u6743\u91cd')


    def test_operator_keeps_rejection_reason_visible(self):
        obj=self.obj();attr=obj.data.attributes.new(chr(0x5bc6)+chr(0x5ea6),'FLOAT','POINT')
        text=bpy.data.texts.new('Contract');text.write('bpy.data.meshes['+repr(obj.data.name)+'].attributes['+repr(attr.name)+']')
        catalog.scan_all(self.scene);c=self.cat('__attributes__');c.entries[0].new_name='Pending'
        self.scene.wkngr_category_index=list(self.scene.wkngr_categories).index(c)
        from batch_rename.ops_rename import WKNGR_OT_Apply
        from types import SimpleNamespace
        reports=[]
        operator=SimpleNamespace(report=lambda level,message:reports.append((level,message)))
        self.assertEqual(WKNGR_OT_Apply.execute(operator,SimpleNamespace(scene=self.scene)),{'FINISHED'})
        self.assertEqual(reports[-1][0],{'WARNING'})
        self.assertIn(attr.name,reports[-1][1])
        self.assertEqual(self.cat('__attributes__').entries[0].new_name,'Pending')
    def test_operator_reports_no_new_name(self):
        self.obj(chr(0x5bf9)+chr(0x8c61));catalog.scan_all(self.scene)
        from batch_rename.ops_rename import WKNGR_OT_Apply
        from types import SimpleNamespace
        reports=[]
        operator=SimpleNamespace(report=lambda level,message:reports.append((level,message)))
        WKNGR_OT_Apply.execute(operator,SimpleNamespace(scene=self.scene))
        self.assertEqual(reports[-1][0],{'WARNING'})

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
addon.unregister()
print('RENAME CONTRACT RUNTIME:',bpy.app.version_string)
sys.exit(0 if result.wasSuccessful() else 1)
