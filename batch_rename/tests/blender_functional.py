"""Real Blender regressions for all data categories and dictionary workflows."""
import importlib.util, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
TEMP=tempfile.TemporaryDirectory(prefix='wkngr-functional-',ignore_cleanup_errors=True)
for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
    target=Path(TEMP.name)/kind.lower();target.mkdir()
    os.environ['BLENDER_USER_'+kind]=str(target)
import bpy
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wkngr_functional',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon._load_modules()
from wkngr_functional import props,preset_manager as pm,ops_preset,utils,ui_main,ui_preset,data_catalog as catalog,nested_data as nested

class LayoutProbe:
    def __init__(self,records=None):self.records=[] if records is None else records
    def row(self,**kw):return LayoutProbe(self.records)
    def box(self,**kw):return LayoutProbe(self.records)
    def column(self,**kw):return LayoutProbe(self.records)
    def split(self,**kw):return LayoutProbe(self.records)
    def label(self,**kw):
        if 'icon' in kw:assert kw['icon'] in utils.valid_icons(),kw
    def prop(self,data,name,**kw):
        assert name in data.bl_rna.properties,name
        getattr(data,name)
    def operator(self,name,**kw):
        category,op=name.split('.');getattr(getattr(bpy.ops,category),op).get_rna_type()
        self.records.append((self,name,kw))
        if 'icon' in kw:assert kw['icon'] in utils.valid_icons()
    def template_list(self,kind,list_id,data,prop,active,active_prop,**kw):
        assert bpy.types.UIList.bl_rna_get_subclass_py(kind) is not None,kind
        getattr(data,prop);getattr(active,active_prop)

class Functional(unittest.TestCase):
    def setUp(self):
        self.created=[];self.scene=bpy.context.scene;self.st=self.scene.wkngr_settings
        self.scene.wkngr_categories.clear();self.scene.wkngr_category_index=0
        self.st.custom_enable=True;self.st.custom_quick=''
        directory=Path(TEMP.name)/self._testMethodName;directory.mkdir()
        pm._dir=str(directory/'presets');Path(pm._dir).mkdir();pm.invalidate_cache();pm.ensure_defaults()
        props.refresh_preset_enum();self.st.active_preset='usr';ops_preset.sync_scene(self.scene,force=True)
    def tearDown(self):
        for category in self.scene.wkngr_categories:nested.release(category.entries)
        self.scene.wkngr_categories.clear()
        for key,item in reversed(self.created):
            try:getattr(bpy.data,key).remove(item)
            except (ReferenceError,RuntimeError):pass
    def make(self,key,name='\u5b9e\u4f8b',*args,**kwargs):
        item=getattr(bpy.data,key).new(name,*args,**kwargs);self.created.append((key,item));return item
    def group(self):
        ng=self.make('node_groups','EnglishGroup','GeometryNodeTree')
        socket=ng.interface.new_socket(name='\u5b9e\u4f8b_001',in_out='INPUT',socket_type='NodeSocketFloat')
        return ng,socket
    def scan(self):self.assertEqual(bpy.ops.wkngr.scan(),{'FINISHED'})
    def cat(self,key):
        for index,category in enumerate(self.scene.wkngr_categories):
            if category.key==key:self.scene.wkngr_category_index=index;return category
        self.fail('Missing category: '+key)
    def keys(self):return {c.key for c in self.scene.wkngr_categories}
    def test_runtime_enumerates_every_id_collection(self):
        expected={p.identifier for p in bpy.data.bl_rna.properties if p.type=='COLLECTION' and p.fixed_type.identifier!='ID' and issubclass(getattr(bpy.types,p.fixed_type.identifier),bpy.types.ID)}
        self.assertEqual(set(catalog.data_types())-{catalog.SOCKETS}-set(nested.LABELS),expected)
        self.assertTrue(expected <= set(catalog.LABELS))
        self.assertNotIn('all_ids',catalog.data_types())
        print('ENUMERATED ID TYPES:',len(expected),flush=True)
    def test_many_actual_datatypes_and_exact_counts(self):
        kinds=('actions','armatures','cameras','collections','lattices','materials','meshes','palettes','pointclouds','speakers','texts','volumes','worlds','scenes')
        for kind in kinds:self.make(kind)
        self.make('objects','\u5b9e\u4f8b',None);self.make('images',width=1,height=1)
        self.make('lights',type='POINT');self.make('curves',type='CURVE');self.make('textures',type='CLOUDS')
        self.make('materials','English');self.scan()
        self.assertEqual(self.keys(),set(kinds)|{'objects','images','lights','curves','textures'})
        self.assertTrue(all(len(c.entries)==1 for c in self.scene.wkngr_categories))
    def test_partial_dictionary_translation_only_current_category(self):
        material=self.make('materials','\u5b9e\u4f8b_001');obj=self.make('objects','\u5b9e\u4f8b_002',None);ng,socket=self.group()
        pm.save_preset('usr',{'\u5b9e\u4f8b':'Instance'});self.scan();category=self.cat('materials')
        bpy.ops.wkngr.auto_fill();self.assertEqual(category.entries[0].new_name,'Instance_001')
        self.assertEqual(self.cat('objects').entries[0].new_name,obj.name)
        self.assertEqual(self.cat(catalog.SOCKETS).entries[0].new_name,socket.name)
        self.assertEqual(material.name,'\u5b9e\u4f8b_001')
    def test_apply_updates_all_previewed_categories(self):
        mat=self.make('materials');obj=self.make('objects','\u7269\u4f53',None);self.scan()
        self.cat('objects').entries[0].new_name='ObjectPreview'
        self.cat('materials').entries[0].new_name='MaterialDone';bpy.ops.wkngr.apply()
        self.assertEqual(mat.name,'MaterialDone');self.assertNotIn('materials',self.keys())
        self.assertEqual(obj.name,'ObjectPreview');self.assertNotIn('objects',self.keys())
    def test_apply_refreshes_remaining_count_until_empty(self):
        a=self.make('materials','\u5b9e\u4f8b_A');b=self.make('materials','\u5b9e\u4f8b_B');self.scan()
        category=self.cat('materials');category.entries[0].new_name='Done';bpy.ops.wkngr.apply()
        self.assertEqual(len(self.cat('materials').entries),1)
        self.cat('materials').entries[0].new_name='Still_\u4e2d\u6587';bpy.ops.wkngr.apply()
        self.assertEqual(len(self.cat('materials').entries),1)
        self.cat('materials').entries[0].new_name='DoneAgain';bpy.ops.wkngr.apply()
        self.assertEqual(len(self.scene.wkngr_categories),0);self.assertEqual(self.scene.wkngr_category_index,0)
    def test_replace_and_reset_are_scoped_and_preview_only(self):
        mat=self.make('materials');obj=self.make('objects','\u5b9e\u4f8b',None);self.scan();self.cat('materials')
        self.st.replace_from='\u5b9e';self.st.replace_to='A';bpy.ops.wkngr.preview_replace()
        self.assertEqual(self.cat('materials').entries[0].new_name,'A\u4f8b')
        self.assertEqual(self.cat('objects').entries[0].new_name,obj.name)
        self.cat('materials');bpy.ops.wkngr.reset();self.assertEqual(self.cat('materials').entries[0].new_name,mat.name)
        self.st.replace_from='';self.assertEqual(bpy.ops.wkngr.preview_replace(),{'CANCELLED'})
    def test_literal_longest_match_and_no_translation_cascade(self):
        translate=utils.make_partial_translator({'\u5b9e':'Short','\u5b9e\u4f8b':'Instance','Instance':'Again','a.b':'Dot','':'Bad'})
        self.assertEqual(translate('\u5b9e\u4f8b_001_a.b'),('Instance_001_Dot',2))
        self.assertEqual(translate('axb'),('axb',0));self.assertEqual(utils.make_partial_translator({})('Same'),('Same',0))
    def test_socket_identity_deleted_and_namesake_protected(self):
        ng,socket=self.group();identifier=socket.identifier;self.scan();self.cat(catalog.SOCKETS).entries[0].new_name='Changed'
        ng.interface.remove(socket);replacement=ng.interface.new_socket(name='\u5b9e\u4f8b_001',in_out='INPUT',socket_type='NodeSocketFloat')
        bpy.ops.wkngr.apply();self.assertEqual(replacement.name,'\u5b9e\u4f8b_001')
        self.assertNotEqual(replacement.identifier,identifier);self.assertEqual(len(self.cat(catalog.SOCKETS).entries),1)
    def test_deleted_datablock_not_redirected_to_namesake(self):
        mat=self.make('materials');name=mat.name;self.scan();self.cat('materials').entries[0].new_name='Changed'
        bpy.data.materials.remove(mat);replacement=self.make('materials',name);bpy.ops.wkngr.apply()
        self.assertEqual(replacement.name,name);self.assertEqual(len(self.cat('materials').entries),1)
    def test_external_rename_is_not_clobbered(self):
        mat=self.make('materials');self.scan();self.cat('materials').entries[0].new_name='Pending'
        mat.name='\u5916\u90e8';bpy.ops.wkngr.apply();self.assertEqual(mat.name,'\u5916\u90e8')
        self.assertEqual(self.cat('materials').entries[0].old_name,'\u5916\u90e8')
    def test_name_collision_and_references_preserved(self):
        self.make('materials','Taken');target=self.make('materials');self.scan();self.cat('materials').entries[0].new_name='Taken'
        bpy.ops.wkngr.apply();self.assertEqual(target.name,'Taken.001');self.assertNotIn('materials',self.keys())
    def test_semicolon_custom_filter_and_disabled_filter(self):
        for name in ('Loose edge','left,right','edge','left'):self.make('materials',name)
        self.st.custom_quick='Loose edge;left,right';self.scan()
        self.assertEqual({r.old_name for r in self.cat('materials').entries},{'Loose edge','left,right'})
        self.st.custom_enable=False
        with patch.object(pm,'load_custom_tokens',side_effect=AssertionError('disabled filter read')):self.scan()
        self.assertFalse(self.keys())
    def test_all_dictionaries_and_hidden_defaults(self):
        pm.save_preset('usr',{'shared':'User'})
        pm.save_preset('nested/other',{'other':'Other','shared':'Other'})
        pm.save_preset('default/deep/builtin',{'hidden':'Hidden','shared':'Default'})
        self.assertNotIn('default/deep/builtin',pm.list_presets())
        self.assertEqual(pm.load_translation_dictionary('nested/other'),{'other':'Other','shared':'Other','hidden':'Hidden'})
    def test_load_recursive_reference_and_current_words(self):
        source=Path(TEMP.name)/'source';(source/'nested').mkdir(parents=True,exist_ok=True);(source/'default').mkdir(exist_ok=True)
        sample=next(ROOT.parent.glob('CC_*.json'));shutil.copy2(sample,source/'nested'/sample.name)
        (source/'default'/'builtin.json').write_text('{"hidden":"Hidden"}',encoding='utf-8')
        pm.save_preset('selected',{'shown':'Selected'});props.refresh_preset_enum();self.st.active_preset='selected'
        with patch.object(pm,'_addon_preset_dir',return_value=str(source)):
            self.assertEqual(bpy.ops.wkngr.preset_reload('INVOKE_DEFAULT'),{'FINISHED'})
            self.assertEqual(self.st.active_preset,'selected');self.assertEqual({x.cn:x.en for x in self.scene.wkngr_words},{'shown':'Selected'})
            self.assertIn('nested/'+sample.stem,[x[0] for x in props.PRESET_ITEMS])
            self.assertNotIn('default/builtin',[x[0] for x in props.PRESET_ITEMS])
            self.st.active_preset='nested/'+sample.stem;bpy.ops.wkngr.preset_reload('INVOKE_DEFAULT')
            self.assertEqual(len(self.scene.wkngr_words),17)
            self.assertEqual(pm.load_translation_dictionary('usr')['hidden'],'Hidden')
    def test_dictionary_import_export_roundtrip(self):
        sample=next(ROOT.parent.glob('CC_*.json'));before=sample.read_bytes()
        self.assertEqual(bpy.ops.wkngr.preset_import(filepath=str(sample)),{'FINISHED'})
        destination=Path(TEMP.name)/'export.json';bpy.ops.wkngr.preset_export(filepath=str(destination))
        self.assertEqual(json.loads(destination.read_text(encoding='utf-8')),json.loads(before.decode('utf-8')))
        self.assertEqual(sample.read_bytes(),before)
    def test_corrupt_dictionary_does_not_partially_fill(self):
        self.make('materials');self.scan();row=self.cat('materials').entries[0];row.new_name='Manual'
        pm.save_preset('usr',{'\u5b9e\u4f8b':'Instance'})
        Path(pm.get_preset_dir(),'broken.json').write_text('{broken',encoding='utf-8')
        with self.assertRaises(RuntimeError):bpy.ops.wkngr.auto_fill()
        self.assertEqual(row.new_name,'Manual')
    def test_dictionary_crud_word_and_token_actions(self):
        bpy.ops.wkngr.preset_new(preset_name='Words');self.st.original_text='\u5b9e\u4f8b';self.st.translate_text='Instance'
        bpy.ops.wkngr.word_add();bpy.ops.wkngr.word_save();self.assertEqual(pm.load_preset('Words'),{'\u5b9e\u4f8b':'Instance'})
        bpy.ops.wkngr.preset_rename(preset_name='Renamed');self.assertEqual(self.st.active_preset,'Renamed')
        bpy.ops.wkngr.word_remove();self.assertEqual(pm.load_preset('Renamed'),{})
        bpy.ops.wkngr.preset_remove();self.assertEqual(self.st.active_preset,'usr')
        self.st.new_token_text='_tmp';bpy.ops.wkngr.token_add();self.assertEqual(pm.load_custom_tokens(),['_tmp'])
        bpy.ops.wkngr.token_remove();self.assertEqual(pm.load_custom_tokens(),[])
    def test_history_refreshes_dictionary_view(self):
        pm.save_preset('usr',{'current':'Disk'});self.scene.wkngr_words.clear();ops_preset._on_history(None)
        self.assertEqual({x.cn:x.en for x in self.scene.wkngr_words},{'current':'Disk'})
    def test_layout_rna_and_same_row_actions(self):
        self.make('materials');self.scan();layout=LayoutProbe();before=len(self.scene.wkngr_words)
        ui_main.draw_main(layout,self.scene);ui_preset.draw_preset(layout,bpy.context)
        category=self.cat('materials')
        ui_main.WKNGR_UL_Categories.draw_item(None,bpy.context,layout,None,category,0,None,'',0)
        ui_main.WKNGR_UL_Data.draw_item(None,bpy.context,layout,None,category.entries[0],0,None,'',0)
        for names in [('wkngr.preview_replace','wkngr.auto_fill','wkngr.apply'),('wkngr.preset_new','wkngr.preset_remove','wkngr.preset_rename','wkngr.preset_reload')]:
            rows=[r for r in layout.records if r[1] in names];self.assertEqual(tuple(r[1] for r in rows),names);self.assertEqual(len({id(r[0]) for r in rows}),1)
        self.assertEqual(len(self.scene.wkngr_words),before)
        self.assertNotIn('wkngr.reset',[r[1] for r in layout.records])
    def test_linked_data_displayed_readonly(self):
        source=self.make('materials','\u94fe\u63a5');path=Path(TEMP.name)/'library.blend'
        bpy.data.libraries.write(str(path),{source});bpy.data.materials.remove(source)
        with bpy.data.libraries.load(str(path),link=True) as (available,requested):requested.materials=available.materials
        linked=requested.materials[0];self.created.append(('materials',linked));self.scan();row=self.cat('materials').entries[0]
        self.assertTrue(row.read_only);row.new_name='Changed';bpy.ops.wkngr.apply();self.assertEqual(linked.name,'\u94fe\u63a5')
        self.assertIn('materials',self.keys())
    def test_refresh_does_not_reset_other_category_selection_previews(self):
        self.make('materials');self.make('meshes');self.scan();mesh=self.cat('meshes');mesh.entries[0].new_name='MeshPreview'
        self.cat('materials').entries[0].new_name='Still_\u4e2d';bpy.ops.wkngr.apply()
        self.assertEqual(catalog.active_category(self.scene).key,'materials');self.assertEqual(self.cat('meshes').entries[0].new_name,'MeshPreview')
    def test_frame_and_node_names_labels_are_separate(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree')
        frame=tree.nodes.new('NodeFrame');frame.name='\u6846\u67b6';frame.label='\u6807\u9898'
        node=tree.nodes.new('NodeReroute');node.name='\u8282\u70b9';node.label='\u6807\u7b7e';node.parent=frame
        self.scan()
        for key in ('__frames__','__frame_labels__','__nodes__','__node_labels__'):self.assertEqual(len(self.cat(key).entries),1)
        old_location=tuple(node.location);old_parent=node.parent
        self.cat('__frame_labels__').entries[0].new_name='Title';bpy.ops.wkngr.apply()
        self.assertEqual(frame.label,'Title');self.assertEqual(frame.name,'\u6846\u67b6')
        self.assertEqual(node.label,'\u6807\u7b7e');self.assertEqual(tuple(node.location),old_location);self.assertEqual(node.parent,old_parent)
        self.assertNotIn('__frame_labels__',self.keys())
    def test_embedded_material_world_light_and_texture_trees(self):
        owners=[self.make('materials','EnglishMat'),self.make('worlds','EnglishWorld'),self.make('lights','EnglishLight',type='POINT'),self.make('textures','EnglishTexture',type='NONE')]
        for owner in owners:
            owner.use_nodes=True
            frame=owner.node_tree.nodes.new('NodeFrame');frame.label='\u6807\u9898'
        self.scan();category=self.cat('__frame_labels__')
        self.assertEqual(len(category.entries),len(owners))
        self.assertEqual({row.target.as_pointer() for row in category.entries},{owner.as_pointer() for owner in owners})
        for row in category.entries:row.new_name='Title'
        bpy.ops.wkngr.apply();self.assertNotIn('__frame_labels__',self.keys())
        self.assertTrue(all(next(n for n in owner.node_tree.nodes if n.bl_idname=='NodeFrame').label=='Title' for owner in owners))
    def test_deleted_node_namesake_never_receives_pending_label(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u9898';name=node.name
        self.scan();self.cat('__frame_labels__').entries[0].new_name='Pending'
        tree.nodes.remove(node);replacement=tree.nodes.new('NodeFrame');replacement.name=name;replacement.label='\u6807\u9898'
        bpy.ops.wkngr.apply();self.assertEqual(replacement.label,'\u6807\u9898')
    def test_node_rename_then_label_retains_live_identity(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree');node=tree.nodes.new('NodeReroute');node.name='\u8282\u70b9';node.label='\u6807\u7b7e'
        self.scan();self.cat('__node_labels__').entries[0].new_name='Label'
        self.cat('__nodes__').entries[0].new_name='Node';bpy.ops.wkngr.apply()
        self.assertEqual(node.name,'Node');self.cat('__node_labels__');bpy.ops.wkngr.apply();self.assertEqual(node.label,'Label')
    def test_label_can_be_cleared_without_renaming_node(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u9898'
        self.scan();self.cat('__frame_labels__').entries[0].new_name='';bpy.ops.wkngr.apply()
        self.assertEqual(node.label,'');self.assertEqual(node.name,'Frame')
    def test_nested_modifiers_constraints_vertexgroups_keys_uvs(self):
        mesh=self.make('meshes','EnglishMesh');mesh.from_pydata([(0,0,0)],[],[])
        obj=self.make('objects','EnglishObject',mesh)
        modifier=obj.modifiers.new('\u4fee\u6539\u5668','MIRROR')
        constraint=obj.constraints.new('COPY_LOCATION');constraint.name='\u7ea6\u675f'
        group=obj.vertex_groups.new(name='\u9876\u70b9\u7ec4')
        block=obj.shape_key_add(name='\u5f62\u6001\u952e')
        uv=mesh.uv_layers.new(name='\u5750\u6807\u5c42')
        self.scan()
        targets={'__modifiers__':modifier,'__constraints__':constraint,'__vertex_groups__':group,'__shape_blocks__':block,'__uv_layers__':uv}
        for index,(key,target) in enumerate(targets.items()):
            self.assertEqual(len(self.cat(key).entries),1)
            self.cat(key).entries[0].new_name='Renamed_'+str(index);bpy.ops.wkngr.apply()
            self.assertEqual(target.name,'Renamed_'+str(index));self.assertNotIn(key,self.keys())
    def test_bones_collections_and_pose_constraints(self):
        arm=self.make('armatures','EnglishArmature');obj=self.make('objects','EnglishRig',arm)
        self.scene.collection.objects.link(obj);bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bone=arm.edit_bones.new('\u9aa8\u9abc');bone.head=(0,0,0);bone.tail=(0,0,1)
        finally:bpy.ops.object.mode_set(mode='OBJECT')
        collection=arm.collections.new('\u96c6\u5408');collection.assign(arm.bones[0])
        constraint=obj.pose.bones[0].constraints.new('COPY_LOCATION');constraint.name='\u7ea6\u675f'
        self.scan()
        self.cat('__bones__').entries[0].new_name='Bone';bpy.ops.wkngr.apply();self.assertEqual(arm.bones[0].name,'Bone')
        self.cat('__pose_constraints__').entries[0].new_name='Constraint';bpy.ops.wkngr.apply();self.assertEqual(constraint.name,'Constraint')
        self.cat('__bone_collections__').entries[0].new_name='Collection';bpy.ops.wkngr.apply();self.assertEqual(collection.name,'Collection')
    def test_interface_panels_and_descriptions(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree')
        panel=tree.interface.new_panel('\u5206\u7ec4');socket=tree.interface.new_socket(name='English',in_out='INPUT',socket_type='NodeSocketFloat',parent=panel);socket.description='\u8bf4\u660e'
        self.scan();self.cat('__interface_panels__').entries[0].new_name='Panel';bpy.ops.wkngr.apply();self.assertEqual(panel.name,'Panel')
        self.cat('__interface_descriptions__').entries[0].new_name='Description';bpy.ops.wkngr.apply();self.assertEqual(socket.description,'Description')
    def test_nested_history_rebuilds_and_scan_cache_is_bounded(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u9898'
        self.scan();baseline=len(nested._refs)
        for _ in range(10):self.scan()
        self.assertEqual(len(nested._refs),baseline)
        self.cat('__frame_labels__').entries[0].new_name='Pending';nested._refresh_nested_history(None)
        self.assertEqual(self.cat('__frame_labels__').entries[0].new_name,'\u6807\u9898')
        self.cat('__frame_labels__').entries[0].new_name='Title';bpy.ops.wkngr.apply();self.assertEqual(node.label,'Title')
    def test_deleted_scene_references_are_pruned(self):
        tree=self.make('node_groups','EnglishTree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u9898'
        other=self.make('scenes','OtherScene');catalog.scan_all(other);self.scan();self.assertEqual(len(nested._refs),2)
        bpy.data.scenes.remove(other);self.scan();self.assertEqual(len(nested._refs),1)
    def test_scene_layers_markers_and_grease_layers(self):
        scene=self.make('scenes','OtherScene');layer=scene.view_layers.new('\u89c6\u56fe\u5c42');marker=scene.timeline_markers.new('\u6807\u8bb0')
        grease=self.make('grease_pencils','EnglishGrease');grease_layer=grease.layers.new('\u56fe\u5c42')
        self.scan()
        for key,target in [('__view_layers__',layer),('__timeline_markers__',marker),('__grease_layers__',grease_layer)]:
            self.cat(key).entries[0].new_name='Renamed';bpy.ops.wkngr.apply();self.assertEqual(target.name,'Renamed')
    def test_object_data_and_uv_are_independent_categories(self):
        mesh=self.make('meshes','\u7f51\u683c');obj=self.make('objects','\u7269\u4f53',mesh);uv=mesh.uv_layers.new(name='\u5750\u6807')
        self.scan();self.cat('objects').entries[0].new_name='Object';bpy.ops.wkngr.apply()
        self.assertEqual(obj.name,'Object');self.assertEqual(mesh.name,'\u7f51\u683c');self.assertEqual(uv.name,'\u5750\u6807')
        self.cat('meshes').entries[0].new_name='Mesh';bpy.ops.wkngr.apply();self.assertEqual(obj.data,mesh)
        self.assertEqual(mesh.name,'Mesh');self.assertEqual(uv.name,'\u5750\u6807')
        self.cat('__uv_layers__').entries[0].new_name='UVMap';bpy.ops.wkngr.apply();self.assertEqual(uv.name,'UVMap')
    def test_uv_rename_updates_shader_and_modifier_references(self):
        mesh=self.make('meshes','Mesh');uv=mesh.uv_layers.new(name='\u5750\u6807');obj=self.make('objects','Object',mesh)
        mat=self.make('materials','Material');mat.use_nodes=True;mesh.materials.append(mat)
        node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=uv.name
        modifier=obj.modifiers.new('UVWarp','UV_WARP');modifier.uv_layer=uv.name
        self.scan();self.cat('__uv_layers__').entries[0].new_name='UVMap';bpy.ops.wkngr.apply()
        self.assertEqual(uv.name,'UVMap');self.assertEqual(node.uv_map,'UVMap');self.assertEqual(modifier.uv_layer,'UVMap')
    def test_vertex_group_rename_updates_modifier_and_named_attribute(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh);group=obj.vertex_groups.new(name='\u9876\u70b9\u7ec4')
        modifier=obj.modifiers.new('Mask','MASK');modifier.vertex_group=group.name
        tree=self.make('node_groups','GeometryTree','GeometryNodeTree');node=tree.nodes.new('GeometryNodeInputNamedAttribute');node.inputs['Name'].default_value=group.name
        geometry=obj.modifiers.new('Geometry','NODES');geometry.node_group=tree
        self.scan();self.cat('__vertex_groups__').entries[0].new_name='Group';bpy.ops.wkngr.apply()
        self.assertEqual(group.name,'Group');self.assertEqual(modifier.vertex_group,group.name);self.assertEqual(node.inputs['Name'].default_value,group.name)
    def test_shared_uv_reference_requires_consistent_rename(self):
        meshes=[self.make('meshes','MeshA'),self.make('meshes','MeshB')]
        uvs=[mesh.uv_layers.new(name='\u5750\u6807') for mesh in meshes]
        mat=self.make('materials','Material');mat.use_nodes=True;node=mat.node_tree.nodes.new('ShaderNodeUVMap');node.uv_map=uvs[0].name
        for index,mesh in enumerate(meshes):self.make('objects','Object'+str(index),mesh);mesh.materials.append(mat)
        self.scan();self.cat('__uv_layers__').entries[0].new_name='UVMap';bpy.ops.wkngr.apply()
        self.assertTrue(all(uv.name=='\u5750\u6807' for uv in uvs));self.assertEqual(node.uv_map,'\u5750\u6807')
        for row in self.cat('__uv_layers__').entries:row.new_name='UVMap'
        bpy.ops.wkngr.apply();self.assertTrue(all(uv.name=='UVMap' for uv in uvs));self.assertEqual(node.uv_map,'UVMap')
    def test_reference_failure_rolls_back_names(self):
        from wkngr_functional import name_references
        mesh=self.make('meshes','Mesh');uv=mesh.uv_layers.new(name='\u5750\u6807');self.scan();self.cat('__uv_layers__').entries[0].new_name='UVMap'
        class Broken:
            def as_pointer(self):return id(self)
            def is_property_readonly(self,field):return False
            @property
            def value(self):return '\u5750\u6807'
            @value.setter
            def value(self,value):
                if value!='\u5750\u6807':raise RuntimeError('injected reference failure')
        with patch.object(name_references,'references',return_value=[[Broken(),'value',mesh,{mesh.as_pointer()},'\u5750\u6807']]):bpy.ops.wkngr.apply()
        self.assertEqual(uv.name,'\u5750\u6807')
    def test_geometry_node_custom_items(self):
        tree=self.make('node_groups','GeometryTree','GeometryNodeTree')
        capture=tree.nodes.new('GeometryNodeCaptureAttribute');first=capture.capture_items.new('FLOAT','\u6355\u83b7')
        repeat=tree.nodes.new('GeometryNodeRepeatOutput');second=repeat.repeat_items.new('FLOAT','\u91cd\u590d')
        menu=tree.nodes.new('GeometryNodeMenuSwitch');third=menu.enum_items.new('\u9009\u9879')
        self.scan();self.assertEqual(len(self.cat('__node_items__').entries),3)
        for index,row in enumerate(self.cat('__node_items__').entries):row.new_name='Item'+str(index)
        bpy.ops.wkngr.apply();self.assertTrue(all(item.name.startswith('Item') for item in (first,second,third)))
    def test_action_layers_slots_groups_and_nla(self):
        obj=self.make('objects','Object',None);obj.keyframe_insert(data_path='location',frame=1)
        action=obj.animation_data.action;self.created.append(('actions',action))
        layer=action.layers[0];layer.name='\u52a8\u4f5c\u5c42';slot=action.slots[0];slot.name_display='\u69fd\u4f4d';handle=slot.handle
        bag=layer.strips[0].channelbags[0];group=bag.groups.new('\u901a\u9053\u7ec4')
        obj.animation_data.action=None;track=obj.animation_data.nla_tracks.new();track.name='\u8f68\u9053'
        strip=track.strips.new('\u7247\u6bb5',1,action)
        self.scan()
        for key,target,field in [('__action_layers__',layer,'name'),('__action_slots__',slot,'name_display'),('__action_groups__',group,'name'),('__nla_tracks__',track,'name'),('__nla_strips__',strip,'name')]:
            self.cat(key).entries[0].new_name='Renamed';bpy.ops.wkngr.apply();self.assertEqual(getattr(target,field),'Renamed')
        self.assertEqual(slot.handle,handle);self.assertEqual(strip.action,action)
    def test_sequence_and_annotation_names(self):
        scene=self.make('scenes','OtherScene');editor=scene.sequence_editor_create()
        strip=editor.strips.new_effect(name='\u7247\u6bb5',type='COLOR',channel=1,frame_start=1,length=10)
        channel=editor.channels[0]
        channel.name='\u901a\u9053'
        with bpy.context.temp_override(scene=scene, sequencer_scene=scene):
            modifier=strip.modifiers.new('\u4fee\u6539\u5668','COLOR_BALANCE')
        annotation=self.make('annotations','Annotation');layer=annotation.layers.new('\u6ce8\u91ca\u5c42')
        self.scan()
        for key,target,field in [('__sequence_strips__',strip,'name'),('__sequence_channels__',channel,'name'),('__strip_modifiers__',modifier,'name'),('__annotation_layers__',layer,'info')]:
            self.cat(key).entries[0].new_name='Renamed';bpy.ops.wkngr.apply();self.assertEqual(getattr(target,field),'Renamed')

    def test_readonly_custom_properties_colors_and_attributes(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        color=mesh.color_attributes.new('\u989c\u8272','FLOAT_COLOR','POINT')
        attribute=mesh.attributes.new('\u5c5e\u6027','FLOAT','POINT')
        obj['\u63a7\u5236']=0.5
        fc=obj.driver_add('location',0);variable=fc.driver.variables.new();variable.name='control';variable.targets[0].id=obj;variable.targets[0].data_path='["\u63a7\u5236"]'
        self.scan()
        for key in ('__custom_properties__',):
            category=self.cat(key);self.assertTrue(all(row.read_only for row in category.entries))
            category.entries[0].new_name='Changed';bpy.ops.wkngr.apply()
        for key in ('__color_attributes__','__attributes__'):
            category=self.cat(key);self.assertFalse(category.entries[0].read_only)
            category.entries[0].new_name='Changed';bpy.ops.wkngr.apply()
        self.assertEqual(color.name,'Changed');self.assertTrue(attribute.name.startswith('Changed'))
        self.assertEqual(obj['\u63a7\u5236'],0.5);self.assertEqual(variable.targets[0].data_path,'["\u63a7\u5236"]')
    def test_vertex_group_shape_key_mask_reference(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        group=obj.vertex_groups.new(name='\u6743\u91cd');mask=obj.modifiers.new('Mask','MASK');mask.vertex_group=group.name
        obj.shape_key_add(name='Basis');shape=obj.shape_key_add(name='Smile');shape.vertex_group=group.name
        self.scan();self.cat('__vertex_groups__').entries[0].new_name='Weight';bpy.ops.wkngr.apply()
        self.assertEqual(group.name,'Weight');self.assertEqual(mask.vertex_group,'Weight');self.assertEqual(shape.vertex_group,'Weight')
    def test_vertex_group_shared_mesh_is_preserved(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh);other=self.make('objects','Other',mesh)
        group=obj.vertex_groups.new(name='\u6743\u91cd');self.scan()
        for row in self.cat('__vertex_groups__').entries:row.new_name='Weight'
        bpy.ops.wkngr.apply();self.assertEqual(group.name,'Weight');self.assertEqual(other.vertex_groups[0].name,group.name)
    def test_scripts_and_driver_expressions_block_name_changes(self):
        obj=self.make('objects','\u7269\u4f53',None);text=self.make('texts','Script');text.write('bpy.data.objects["\u7269\u4f53"]')
        self.scan();self.cat('objects').entries[0].new_name='Object';bpy.ops.wkngr.apply();self.assertEqual(obj.name,'\u7269\u4f53')
        text.clear();driver=obj.driver_add('location',0);driver.driver.expression='len("\u7269\u4f53")'
        self.scan();self.cat('objects').entries[0].new_name='Object';bpy.ops.wkngr.apply();self.assertEqual(obj.name,'Object')
        obj.name='\u7269\u4f53';driver.driver.expression='len(bpy.data.objects.get("\u7269\u4f53").name)'
        self.scan();self.cat('objects').entries[0].new_name='Object';bpy.ops.wkngr.apply();self.assertEqual(obj.name,'\u7269\u4f53')
    def test_shape_key_animation_driver_and_relative_key_references(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        basis=obj.shape_key_add(name='Basis');shape=obj.shape_key_add(name='\u8868\u60c5');shape.value=0.4;shape.keyframe_insert('value',frame=1)
        keys=mesh.shape_keys;action=keys.animation_data.action;self.created.append(('actions',action))
        curve=action.layers[0].strips[0].channelbags[0].fcurves[0]
        driven=self.make('objects','Driven',None);fc=driven.driver_add('location',0);variable=fc.driver.variables.new();target=variable.targets[0];target.id_type='KEY';target.id=keys;target.data_path=shape.path_from_id('value')
        self.scan();self.cat('__shape_blocks__').entries[0].new_name='Smile';bpy.ops.wkngr.apply()
        self.assertEqual(shape.name,'Smile');self.assertEqual(curve.data_path,'key_blocks["Smile"].value');self.assertEqual(target.data_path,curve.data_path)
        self.assertAlmostEqual(keys.path_resolve(target.data_path),0.4);self.assertEqual(shape.relative_key,basis)
    def test_armature_vertex_group_contract_is_preserved(self):
        armature=self.make('armatures','Armature');rig=self.make('objects','Rig',armature);self.scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        bone=armature.edit_bones.new('\u9aa8\u9abc');bone.head=(0,0,0);bone.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh);group=obj.vertex_groups.new(name='\u9aa8\u9abc')
        modifier=obj.modifiers.new('Armature','ARMATURE');modifier.object=rig
        self.scan()
        for key in ('__vertex_groups__','__bones__'):
            self.cat(key).entries[0].new_name='Bone';bpy.ops.wkngr.apply()
        self.assertEqual(group.name,'\u9aa8\u9abc');self.assertIsNotNone(armature.bones.get(group.name))


    def test_node_and_modifier_animation_paths(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh)
        modifier=obj.modifiers.new('\u5012\u89d2','BEVEL');modifier.keyframe_insert('width',frame=1)
        action=obj.animation_data.action;self.created.append(('actions',action));curve=action.layers[0].strips[0].channelbags[0].fcurves[0]
        material=self.make('materials','Material');tree=material.node_tree;node=tree.nodes.new('ShaderNodeValue');node.name='\u6570\u503c'
        node.outputs[0].keyframe_insert('default_value',frame=1);action2=tree.animation_data.action;self.created.append(('actions',action2));curve2=action2.layers[0].strips[0].channelbags[0].fcurves[0]
        self.scan();self.cat('__modifiers__').entries[0].new_name='Bevel';bpy.ops.wkngr.apply()
        self.assertEqual(curve.data_path,modifier.path_from_id('width'));obj.path_resolve(curve.data_path)
        self.cat('__nodes__').entries[0].new_name='Value';bpy.ops.wkngr.apply()
        self.assertEqual(curve2.data_path,node.outputs[0].path_from_id('default_value'));tree.path_resolve(curve2.data_path)
    def test_reenable_rebuilds_nested_cache(self):
        tree=self.make('node_groups','Tree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u7b7e'
        self.scan();self.cat('__frame_labels__').entries[0].new_name='Pending'
        nested.unregister();nested.register();nested.ensure_scene(self.scene)
        row=self.cat('__frame_labels__').entries[0];self.assertEqual(nested.resolve(row.cache_key),node)
        self.assertNotEqual(row.new_name,'Pending');row.new_name='Label';bpy.ops.wkngr.apply();self.assertEqual(node.label,'Label')


    def test_identity_metadata_removed_before_save_and_on_release(self):
        tree=self.make('node_groups','Tree','GeometryNodeTree');node=tree.nodes.new('NodeFrame');node.label='\u6807\u7b7e'
        self.scan();self.assertTrue(any(k.startswith('_wkngr_identity_') for k in node.keys()))
        nested._before_save(None);self.assertFalse(any(k.startswith('_wkngr_identity_') for k in node.keys()))
        nested._after_save(None);row=self.cat('__frame_labels__').entries[0];self.assertEqual(nested.resolve(row.cache_key),node)
        nested.release(self.cat('__frame_labels__').entries);self.assertFalse(any(k.startswith('_wkngr_identity_') for k in node.keys()))
    def test_instancer_uv_reference_preserves_name(self):
        mesh=self.make('meshes','Mesh');obj=self.make('objects','Object',mesh);uv=mesh.uv_layers.new(name='\u5750\u6807')
        material=self.make('materials','Material');mesh.materials.append(material);node=material.node_tree.nodes.new('ShaderNodeUVMap');node.from_instancer=True;node.uv_map=uv.name
        self.scan();self.cat('__uv_layers__').entries[0].new_name='UV';bpy.ops.wkngr.apply()
        self.assertEqual(uv.name,'\u5750\u6807');self.assertEqual(node.uv_map,uv.name)

    def test_empty_categories_are_never_listed(self):
        self.make('materials','English');self.scan();self.assertFalse(self.keys())
        self.assertEqual(bpy.ops.wkngr.auto_fill(),{'CANCELLED'});self.assertEqual(bpy.ops.wkngr.apply(),{'CANCELLED'})

if __name__=='__main__':
    pm._dir=str(Path(TEMP.name)/'initial_presets');Path(pm._dir).mkdir()
    addon.register()
    try:result=unittest.TextTestRunner(verbosity=2).run((unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:],sys.modules[__name__]) if len(sys.argv)>1 else unittest.defaultTestLoader.loadTestsFromTestCase(Functional)))
    finally:addon.unregister();TEMP.cleanup()
    print('FUNCTIONAL RUNTIME:',bpy.app.version_string,flush=True)
    if not result.wasSuccessful():sys.exit(1)
