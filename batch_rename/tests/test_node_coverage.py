"""Real RNA regressions for node interface names and attribute name sources."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_tools as support
from batch_rename import nested_data,name_references,node_names,geometry_contracts,scan_cache
bpy=support.bpy;catalog=support.catalog;OLD=support.OLD
class Tests(support.Tests):
    def rows(self,key):
        return list(next(c for c in self.scene.wkngr_categories if c.key==key).entries)
    def target_row(self,target,field):
        return next(row for row in self.rows('__name_references__') if nested_data.resolve(row.cache_key)==target and row.field==field)
    def test_input_output_interface_names_keep_identifiers_and_links(self):
        tree=bpy.data.node_groups.new('Group','GeometryNodeTree')
        inp=tree.interface.new_socket(name=OLD+'Input',in_out='INPUT',socket_type='NodeSocketFloat')
        out=tree.interface.new_socket(name=OLD+'Output',in_out='OUTPUT',socket_type='NodeSocketFloat')
        inputnode=tree.nodes.new('NodeGroupInput');outputnode=tree.nodes.new('NodeGroupOutput')
        tree.links.new(inputnode.outputs[inp.identifier],outputnode.inputs[out.identifier])
        parent=bpy.data.node_groups.new('Parent','GeometryNodeTree');instance=parent.nodes.new('GeometryNodeGroup');instance.node_tree=tree
        identifiers=(inp.identifier,out.identifier);count=len(tree.links)
        catalog.scan_all(self.scene);rows=self.rows(catalog.SOCKETS)
        self.assertEqual(len(rows),2)
        for row in rows:row.new_name='Input' if row.identifier==inp.identifier else 'Output'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(2,[]))
        self.assertEqual((inp.identifier,out.identifier),identifiers);self.assertEqual(len(tree.links),count)
        self.assertEqual(instance.inputs[inp.identifier].name,'Input');self.assertEqual(instance.outputs[out.identifier].name,'Output')
    def test_all_shader_attribute_modes_found(self):
        mat=bpy.data.materials.new('Mat');nodes=[]
        for mode in ('GEOMETRY','OBJECT','INSTANCER','VIEW_LAYER'):
            node=mat.node_tree.nodes.new('ShaderNodeAttribute');node.attribute_type=mode;node.attribute_name=OLD+mode;nodes.append(node)
        catalog.scan_all(self.scene)
        for node in nodes:
            row=self.target_row(node,'attribute_name');self.assertEqual(row.old_name,node.attribute_name)
            self.assertEqual(row.read_only,node.attribute_type!='GEOMETRY')
    def test_group_default_attribute_name_found_and_applied(self):
        tree=bpy.data.node_groups.new('Group','GeometryNodeTree')
        socket=tree.interface.new_socket(name='Input',in_out='INPUT',socket_type='NodeSocketFloat');socket.default_attribute_name=OLD
        catalog.scan_all(self.scene);self.target_row(socket,'default_attribute_name').new_name='Density'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(socket.default_attribute_name,'Density')
    def test_group_input_string_default_name_source_found(self):
        obj=self.object();tree,socket,node,mod=self.string_group(obj)
        catalog.scan_all(self.scene)
        self.assertEqual(self.target_row(socket,'default_value').old_name,OLD)
        self.target_row(socket,'default_value').new_name='Density'
        result=catalog.apply_all(self.scene);self.assertGreaterEqual(result[0],1);self.assertEqual(socket.default_value,'Density')
    def test_modifier_group_input_name_source_found_and_applied(self):
        obj=self.object();tree,socket,node,mod=self.string_group(obj)
        source=geometry_contracts.modifier_values(mod)[socket.identifier]
        name_references.write(*source,OLD+'Value')
        catalog.scan_all(self.scene);row=self.target_row(*source);self.assertEqual(row.target,obj)
        row.new_name='Density'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(geometry_contracts.string_value(source),'Density')
    def test_modifier_input_output_attribute_names_found(self):
        obj=self.object();tree=bpy.data.node_groups.new('Group','GeometryNodeTree')
        inp=tree.interface.new_socket(name='Input',in_out='INPUT',socket_type='NodeSocketFloat')
        out=tree.interface.new_socket(name='Output',in_out='OUTPUT',socket_type='NodeSocketFloat')
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        if hasattr(mod,'properties'):
            getattr(mod.properties.inputs,inp.identifier).attribute_name=OLD+'In'
            getattr(mod.properties.outputs,out.identifier).attribute_name=OLD+'Out'
        else:
            mod[inp.identifier+'_attribute_name']=OLD+'In';mod[out.identifier+'_attribute_name']=OLD+'Out'
        fields=list(name_references.modifier_attributes(mod));self.assertGreaterEqual(len(fields),2)
        catalog.scan_all(self.scene)
        for target,field in fields:
            row=self.target_row(target,field);self.assertEqual(row.target,obj);row.new_name='Attribute'
        result=catalog.apply_all(self.scene);self.assertEqual(result[1],[])
        self.assertTrue(all(name_references.read(target,field)=='Attribute' for target,field in fields))
    def test_uv_tangent_reference_is_synchronized(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD)
        mat=bpy.data.materials.new('Mat');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeTangent');node.direction_type='UV_MAP';node.uv_map=OLD
        catalog.scan_all(self.scene);self.target_row(node,'uv_map');self.draft('__uv_layers__','UVMap')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(uv.name,'UVMap');self.assertEqual(node.uv_map,'UVMap')
    def test_interface_attribute_default_is_synchronized(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        tree=bpy.data.node_groups.new('Group','GeometryNodeTree')
        socket=tree.interface.new_socket(name='Value',in_out='INPUT',socket_type='NodeSocketFloat');socket.default_attribute_name=OLD
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        catalog.scan_all(self.scene);self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[1],[]);self.assertEqual(attr.name,'Density');self.assertEqual(socket.default_attribute_name,'Density')
    def test_registered_item_collections_cover_runtime_schema(self):
        base={p.identifier for p in bpy.types.Node.bl_rna.properties};missing=[]
        for name in dir(bpy.types):
            cls=getattr(bpy.types,name)
            if not isinstance(cls,type) or not issubclass(cls,bpy.types.Node):continue
            for prop in cls.bl_rna.properties:
                if prop.identifier not in base and prop.type=='COLLECTION' and prop.fixed_type.properties.get('name'):
                    if prop.identifier not in node_names.NODE_ITEM_COLLECTIONS and prop.identifier!='entries':missing.append((name,prop.identifier))
        self.assertEqual(missing,[])
    def test_new_node_item_names_found_and_applied(self):
        tree=bpy.data.node_groups.new('Items','GeometryNodeTree')
        node=tree.nodes.new('GeometryNodeFieldToList');items=node.list_items
        params=items.bl_rna.functions['new'].parameters
        print('ITEM NEW PARAMETERS',[(p.identifier,p.type) for p in params])
        item=items.new('FLOAT',OLD)
        catalog.scan_all(self.scene);rows=self.rows('__node_items__')
        row=next(row for row in rows if nested_data.resolve(row.cache_key)==item);row.new_name='Value'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(item.name,'Value')
    def test_coverage_scan_does_not_increase_id_users(self):
        obj=self.object();tree,socket,node,mod=self.string_group(obj)
        orphan=bpy.data.collections.new(OLD);before=tree.users
        for _ in range(3):catalog.scan_all(self.scene);self.assertEqual(orphan.users,0);self.assertEqual(tree.users,before)
        scan_cache.clear_all();self.assertFalse(nested_data._refs)

    def test_volume_attribute_inputs_found_and_synchronized(self):
        obj=self.object();attr=obj.data.attributes.new(OLD,'FLOAT','POINT')
        mat=bpy.data.materials.new('VolumeMaterial');obj.data.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeVolumePrincipled')
        for name in node_names.ATTRIBUTE_INPUTS[node.bl_idname]:node.inputs[name].default_value=OLD
        catalog.scan_all(self.scene)
        for name in node_names.ATTRIBUTE_INPUTS[node.bl_idname]:self.target_row(node.inputs[name],'default_value')
        self.draft('__attributes__','Density')
        result=catalog.apply_all(self.scene);self.assertEqual(result[1],[]);self.assertEqual(attr.name,'Density')
        self.assertTrue(all(node.inputs[name].default_value=='Density' for name in node_names.ATTRIBUTE_INPUTS[node.bl_idname]))
    def test_modifier_uv_reference_found_and_applied(self):
        obj=self.object();uv=obj.data.uv_layers.new(name=OLD);mod=obj.modifiers.new('Warp','UV_WARP');mod.uv_layer=OLD
        catalog.scan_all(self.scene);self.target_row(mod,'uv_layer').new_name='UVMap';self.draft('__uv_layers__','UVMap')
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(mod.uv_layer,'UVMap')
    def test_other_name_contracts_are_visible_and_readonly(self):
        tree=bpy.data.node_groups.new('Names','GeometryNodeTree');nodes=[]
        for kind,fields in node_names.OTHER_NAME_INPUTS.items():
            node=tree.nodes.new(kind);node.inputs[fields[0]].default_value=OLD;nodes.append(node)
        mat=bpy.data.materials.new('Mat');aov=mat.node_tree.nodes.new('ShaderNodeOutputAOV');aov.aov_name=OLD
        catalog.scan_all(self.scene);rows=self.rows('__node_other_names__')
        self.assertEqual(len(rows),len(nodes)+1);self.assertTrue(all(row.read_only for row in rows))
        for row in rows:row.new_name='Unconfirmed'
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0)
        self.assertEqual(aov.aov_name,OLD);self.assertTrue(all(node.inputs[0].node==node for node in nodes))
    def test_mixed_reference_families_do_not_share_mutable_literal(self):
        tree=bpy.data.node_groups.new('Mixed','GeometryNodeTree');string=tree.nodes.new('FunctionNodeInputString');string.string=OLD
        attribute=tree.nodes.new('GeometryNodeInputNamedAttribute');grid=tree.nodes.new('GeometryNodeGetNamedGrid')
        tree.links.new(string.outputs[0],attribute.inputs['Name']);tree.links.new(string.outputs[0],grid.inputs['Name'])
        self.assertIsNone(geometry_contracts.name_source(attribute.inputs['Name']))
        self.assertIsNone(geometry_contracts.name_source(grid.inputs['Name']))

    def test_geometry_output_name_found_and_applied(self):
        tree=bpy.data.node_groups.new('Names','GeometryNodeTree');node=tree.nodes.new('GeometryNodeSetGeometryName');node.inputs['Name'].default_value=OLD
        catalog.scan_all(self.scene);self.target_row(node.inputs['Name'],'default_value').new_name='GeometryName'
        result=catalog.apply_all(self.scene);self.assertEqual(result[:2],(1,[]));self.assertEqual(node.inputs['Name'].default_value,'GeometryName')
    def test_compositor_tracking_and_cryptomatte_names_found(self):
        tree=bpy.data.node_groups.new('Composite','CompositorNodeTree');expected=[]
        for kind in ('CompositorNodeCryptomatteV2','CompositorNodeKeyingScreen','CompositorNodePlaneTrackDeform','CompositorNodeTrackPos'):
            node=tree.nodes.new(kind)
            for field in node_names.INSPECTION_FIELDS[kind]:
                setattr(node,field,OLD);expected.append((node,field))
        catalog.scan_all(self.scene);rows=self.rows('__node_other_names__')
        self.assertEqual(len(rows),len(expected));self.assertTrue(all(row.read_only for row in rows))
    @unittest.skipUnless(hasattr(bpy.types,'ShaderNodeRaycast') and 'sample_attribute_items' in bpy.types.ShaderNodeRaycast.bl_rna.properties,'Raycast sample attribute items are not available in this runtime')
    def test_raycast_attribute_name_is_visible_and_protected(self):
        tree=bpy.data.node_groups.new('Raycast','ShaderNodeTree');node=tree.nodes.new('ShaderNodeRaycast')
        item=node.sample_attribute_items.new('FLOAT',OLD)
        catalog.scan_all(self.scene);rows=self.rows('__node_other_names__')
        row=next(row for row in rows if nested_data.resolve(row.cache_key)==item)
        self.assertTrue(row.read_only)

    def test_deleted_named_attribute_socket_skipped(self):
        tree=bpy.data.node_groups.new('Names','GeometryNodeTree');node=tree.nodes.new('GeometryNodeInputNamedAttribute');node.inputs['Name'].default_value=OLD
        catalog.scan_all(self.scene);self.target_row(node.inputs['Name'],'default_value').new_name='Density'
        tree.nodes.remove(node)
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])
    def test_deleted_modifier_string_source_skipped(self):
        obj=self.object();tree,socket,node,mod=self.string_group(obj)
        source=geometry_contracts.modifier_values(mod)[socket.identifier];name_references.write(*source,OLD+'Value')
        catalog.scan_all(self.scene);self.target_row(*source).new_name='Density'
        obj.modifiers.remove(mod)
        result=catalog.apply_all(self.scene);self.assertEqual(result[0],0);self.assertTrue(result[1])

if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.support.batch_rename.unregister()
    print('NODE COVERAGE RUNTIME:',bpy.app.version_string)
    raise SystemExit(0 if result.wasSuccessful() else 1)
