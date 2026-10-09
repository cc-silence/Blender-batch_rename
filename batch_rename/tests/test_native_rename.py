"""Native datablock identity and typed string-reference regressions."""
import unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import blender_functional as support
bpy=support.bpy
catalog=support.catalog
class NativePolicy(support.Functional):
    def test_material_pointer_survives_unrelated_text(self):
        old=chr(0x6750)+chr(0x8d28)
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        mat=self.make('materials',old);mesh.materials.append(mat)
        other=self.make('objects','Other',None);other['note']='Documentation '+old
        text=self.make('texts','Notes');text.write('# '+old)
        fc=other.driver_add('location',0);fc.driver.expression='len('+repr(old)+')'
        before=mat.users;self.scan();c=self.cat('materials');c.entries[0].new_name='RenamedMaterial'
        result=catalog.apply_category(self.scene)
        self.assertEqual(result[:2],(1,[]));self.assertEqual(obj.material_slots[0].material,mat)
        self.assertEqual(mat.name,'RenamedMaterial');self.assertEqual(mat.users,before)
        self.assertIn(old,text.as_string());self.assertIn(old,other['note'])
    def test_shared_node_group_keeps_all_pointer_users(self):
        old=chr(0x8282)+chr(0x70b9)+chr(0x7ec4)
        tree=self.make('node_groups',old,'GeometryNodeTree')
        parent=self.make('node_groups','Parent','GeometryNodeTree')
        groupnode=parent.nodes.new('GeometryNodeGroup');groupnode.node_tree=tree
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        mod=obj.modifiers.new('Geometry','NODES');mod.node_group=tree
        obj['note']=old;before=tree.users
        self.scan();self.cat('node_groups').entries[0].new_name='Group'
        self.assertEqual(catalog.apply_category(self.scene)[:2],(1,[]))
        self.assertEqual(mod.node_group,tree);self.assertEqual(groupnode.node_tree,tree)
        self.assertEqual(tree.users,before)
    def test_collection_instance_keeps_pointer(self):
        old=chr(0x96c6)+chr(0x5408)
        collection=self.make('collections',old);obj=self.make('objects','Instance',None)
        obj.instance_type='COLLECTION';obj.instance_collection=collection;obj['note']=old
        self.scan();self.cat('collections').entries[0].new_name='RenamedCollection'
        self.assertEqual(catalog.apply_category(self.scene)[:2],(1,[]))
        self.assertEqual(obj.instance_collection,collection);self.assertEqual(collection.name,'RenamedCollection')
    def test_attribute_note_does_not_block_typed_node_update(self):
        old=chr(0x5bc6)+chr(0x5ea6)
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        attr=mesh.attributes.new(old,'FLOAT','POINT');obj['note']=old
        tree=self.make('node_groups','Tree','GeometryNodeTree')
        node=tree.nodes.new('GeometryNodeInputNamedAttribute');node.inputs['Name'].default_value=old
        obj.modifiers.new('Geometry','NODES').node_group=tree
        self.scan();self.cat('__attributes__').entries[0].new_name='Density'
        self.assertEqual(catalog.apply_category(self.scene)[:2],(1,[]))
        self.assertEqual(attr.name,'Density');self.assertEqual(node.inputs['Name'].default_value,'Density')
        self.assertEqual(obj['note'],old)
    def test_explicit_script_lookup_still_detected(self):
        old=chr(0x6750)+chr(0x8d28);mat=self.make('materials',old)
        text=self.make('texts','Script');text.write('import bpy\nvalue = bpy.data.materials.get('+repr(old)+')')
        self.scan();self.cat('materials').entries[0].new_name='Material'
        result=catalog.apply_category(self.scene)
        self.assertEqual(result[0],0);self.assertTrue(result[1]);self.assertEqual(mat.name,old)
    def test_unrelated_shared_action_does_not_block_node(self):
        old=chr(0x6570)+chr(0x503c)
        mat=self.make('materials','Material');node=mat.node_tree.nodes.new('ShaderNodeValue');node.name=old
        a=self.make('objects','A',None);b=self.make('objects','B',None)
        a['note']=old;a.keyframe_insert('location',index=0,frame=1)
        action=a.animation_data.action;self.created.append(('actions',action))
        b.animation_data_create();b.animation_data.action=action
        curve=action.layers[0].strips[0].channelbags[0].fcurves[0];curve.data_path='nodes["'+old+'"].outputs[0].default_value'
        self.scan();self.cat('__nodes__').entries[0].new_name='Value'
        self.assertEqual(catalog.apply_category(self.scene)[:2],(1,[]));self.assertEqual(node.name,'Value')
    def test_literal_and_lookup_are_distinguished(self):
        from wkngr_functional import name_safety
        self.assertFalse(name_safety.name_lookups('# bpy.data.materials["Old"]'))
        self.assertEqual(name_safety.name_lookups('bpy.data.materials["Old"]'),{('materials','Old')})
        self.assertEqual(name_safety.name_lookups('bpy.data.materials.get("Old")'),{('materials','Old')})
        self.assertFalse(name_safety.name_lookups('note = "Old"'))
        self.assertFalse(name_safety.name_lookups('len("Old")'))
        self.assertFalse(name_safety.name_lookups('notes["Old"]'))

    def test_related_shared_action_still_protected(self):
        old=chr(0x6570)+chr(0x503c)
        a=self.make('node_groups','A','ShaderNodeTree');b=self.make('node_groups','B','ShaderNodeTree')
        node=a.nodes.new('ShaderNodeValue');node.name=old
        other=b.nodes.new('ShaderNodeValue');other.name=old
        node.outputs[0].keyframe_insert('default_value',frame=1)
        action=a.animation_data.action;self.created.append(('actions',action))
        b.animation_data_create();b.animation_data.action=action
        self.scan();c=self.cat('__nodes__')
        for row in c.entries:
            if row.target==a:row.new_name='Value'
        result=catalog.apply_category(self.scene)
        self.assertEqual(result[0],0);self.assertTrue(result[1]);self.assertEqual(node.name,old)

if __name__=='__main__':
    support.pm._dir=str(support.Path(support.TEMP.name)/'initial_presets')
    support.Path(support.pm._dir).mkdir();support.addon.register()
    try:
        names=[name for name in NativePolicy.__dict__ if name.startswith('test_')]
        result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(NativePolicy(name) for name in names))
    finally:support.addon.unregister();support.TEMP.cleanup()
    print('NATIVE POLICY RUNTIME:',bpy.app.version_string)
    if not result.wasSuccessful():raise SystemExit(1)

