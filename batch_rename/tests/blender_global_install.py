import os,sys,tempfile,importlib,json
from pathlib import Path
root=Path.cwd();archive=root/'batch_rename-1.6.0-blender51.zip'
temp=tempfile.TemporaryDirectory()
for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
 p=Path(temp.name)/kind;p.mkdir();os.environ['BLENDER_USER_'+kind]=str(p)
import bpy,addon_utils
from bl_pkg.cli import blender_ext
bpy.ops.wm.read_factory_settings(use_empty=True)
manifest=blender_ext.pkg_manifest_from_archive_and_validate(str(archive),strict=True);assert not isinstance(manifest,str),manifest
repo=bpy.context.preferences.extensions.repos.new(name='Release160',module='release160',custom_directory=str(Path(temp.name)/'repository'),source='USER')
assert bpy.ops.extensions.package_install_files('EXEC_DEFAULT',filepath=str(archive),repo=repo.module,enable_on_install=True)=={'FINISHED'}
name='bl_ext.release160.batch_rename_cn';addon=sys.modules[name];assert addon.__addon_enabled__
catalog=importlib.import_module(name+'.data_catalog')
scene=bpy.context.scene
old=chr(0x65e7)
mesh=bpy.data.meshes.new('SourceMesh');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
source=bpy.data.objects.new('Source',mesh);scene.collection.objects.link(source)
attr=mesh.attributes.new(old,'FLOAT','POINT')
for item,value in zip(attr.data,(0.2,0.4,0.6)):item.value=value
uv=mesh.uv_layers.new(name=old+'UV')
collection=bpy.data.collections.new(old+'Collection');collection.objects.link(source)
reader=bpy.data.objects.new(old+'Reader',bpy.data.meshes.new('ReaderMesh'));scene.collection.objects.link(reader)
tree=bpy.data.node_groups.new('ReaderTree','GeometryNodeTree')
tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
out=tree.nodes.new('NodeGroupOutput')
info=tree.nodes.new('GeometryNodeCollectionInfo');info.inputs['Collection'].default_value=collection
realize=tree.nodes.new('GeometryNodeRealizeInstances')
named=tree.nodes.new('GeometryNodeInputNamedAttribute');named.data_type='FLOAT';named.inputs['Name'].default_value=old
store=tree.nodes.new('GeometryNodeStoreNamedAttribute');store.data_type='FLOAT';store.domain='POINT';store.inputs['Name'].default_value='Proof'
tree.links.new(info.outputs['Instances'],realize.inputs['Geometry'])
tree.links.new(realize.outputs['Geometry'],store.inputs['Geometry'])
tree.links.new(named.outputs['Attribute'],store.inputs['Value'])
tree.links.new(store.outputs['Geometry'],out.inputs['Geometry'])
reader.modifiers.new('Geometry','NODES').node_group=tree
mat=bpy.data.materials.new(old+'Material');mesh.materials.append(mat)
shader=mat.node_tree.nodes.new('ShaderNodeUVMap');shader.uv_map=uv.name
def evaluated():
 bpy.context.view_layer.update()
 obj=reader.evaluated_get(bpy.context.evaluated_depsgraph_get())
 result=obj.to_mesh()
 try:
  proof=result.attributes.get('Proof');assert proof is not None
  return [v.value for v in proof.data]
 finally:obj.to_mesh_clear()
before=evaluated();assert len(before)==3 and all(abs(a-b)<1e-6 for a,b in zip(before,(0.2,0.4,0.6))),before
orphan=bpy.data.collections.new(old+'Unused')
catalog.scan_all(scene);scene.wkngr_settings.replace_from=old;scene.wkngr_settings.replace_to='New'
assert bpy.ops.wkngr.preview_replace()=={'FINISHED'}
assert bpy.ops.wkngr.apply()=={'FINISHED'}
assert attr.name=='New' and named.inputs['Name'].default_value=='New'
assert uv.name=='NewUV' and shader.uv_map=='NewUV'
assert reader.name=='NewReader' and mat.name=='NewMaterial'
assert info.inputs['Collection'].default_value==collection and orphan.users==0
after=evaluated();assert after==before,(before,after)
assert not any(key.startswith('_wkngr_') for key in source.keys())
print('FROZEN ZIP INSTALL, GLOBAL ACTION, UV STRING, COLLECTION GEOMETRY VALUES AND ZERO USERS PASS',bpy.app.version_string)
addon_utils.disable(name,default_set=True);print('DISABLE PASS')
logs=root/'blender_validation_runtime/audit_1.6.0_logs'
(logs/(Path(sys.executable).parent.name+'_install.json')).write_text(json.dumps({'passed':True,'runtime':bpy.app.version_string,'evaluated_before':before,'evaluated_after':after},indent=2),encoding='utf-8')
