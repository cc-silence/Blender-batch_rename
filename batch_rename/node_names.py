"""Explicit node name fields; identifiers, paths and arbitrary text are excluded."""
UV_FIELDS = {'ShaderNodeUVMap':'uv_map','ShaderNodeNormalMap':'uv_map','ShaderNodeTangent':'uv_map'}
ATTRIBUTE_FIELDS = {'ShaderNodeAttribute':'attribute_name','ShaderNodeVertexColor':'layer_name'}
NODE_ITEM_COLLECTIONS = (
    'capture_items','repeat_items','state_items','bake_items','enum_items',
    'input_items','output_items','main_items','generation_items','format_items',
    'grid_items','list_items','viewer_items','bundle_items','file_output_items','sample_attribute_items',
)

ATTRIBUTE_INPUTS = {
    'GeometryNodeInputNamedAttribute':('Name',),
    'GeometryNodeStoreNamedAttribute':('Name',),
    'GeometryNodeRemoveAttribute':('Name',),
    'ShaderNodeVolumePrincipled':('Color Attribute','Density Attribute','Temperature Attribute'),
}
EDITABLE_NAME_INPUTS = {**ATTRIBUTE_INPUTS,'GeometryNodeSetGeometryName':('Name',)}
OTHER_NAME_INPUTS = {
    'GeometryNodeBoneInfo':('Bone Name',),
    'GeometryNodeInputNamedLayerSelection':('Name',),
    'GeometryNodeGetNamedGrid':('Name',),
    'GeometryNodeStoreNamedGrid':('Name',),
}
INSPECTION_FIELDS = {
    'ShaderNodeOutputAOV':('aov_name',),
    'CompositorNodeCryptomatte':('matte_id',),
    'CompositorNodeCryptomatteV2':('matte_id',),
    'CompositorNodeKeyingScreen':('tracking_object',),
    'CompositorNodePlaneTrackDeform':('tracking_object','plane_track_name'),
    'CompositorNodeTrackPos':('tracking_object','track_name'),
}
NAME_KINDS = {**{(node,field):'ATTRIBUTE' for node,fields in ATTRIBUTE_INPUTS.items() for field in fields},
              **{(node,field):node for node,fields in OTHER_NAME_INPUTS.items() for field in fields},
              ('GeometryNodeSetGeometryName','Name'):'GEOMETRY_NAME'}
NAME_KINDS[('GeometryNodeGetNamedGrid','Name')]='GRID'
NAME_KINDS[('GeometryNodeStoreNamedGrid','Name')]='GRID'


def name_sockets(node, fields=ATTRIBUTE_INPUTS):
    for field in fields.get(node.bl_idname,()):
        socket=node.inputs.get(field)
        if socket is not None:yield socket


def inspection_candidates():
    from . import nested_data,geometry_contracts
    seen=set()
    for owner,tree,label in nested_data.node_trees():
        defaults={socket.identifier:(socket,'default_value')
                  for socket,direction in nested_data.utils.iter_interface_sockets(tree)
                  if direction=='INPUT' and socket.socket_type=='NodeSocketString'}
        for context,values in geometry_contracts.contexts(tree,defaults,None):
            for node in context.nodes:
                fields=[]
                fields.extend((node,field) for field in INSPECTION_FIELDS.get(node.bl_idname,()))
                if node.bl_idname=='ShaderNodeRaycast':
                    fields.extend((item,'name') for item in node.sample_attribute_items)
                for socket in name_sockets(node,OTHER_NAME_INPUTS):
                    source=geometry_contracts.name_source(socket,values)
                    if source:fields.append(source)
                for target,field in fields:
                    identity=(target.as_pointer(),field)
                    if identity in seen:continue
                    seen.add(identity)
                    source_owner=target.id_data
                    if source_owner.is_embedded_data:source_owner=owner
                    yield source_owner,target,field,label+' / '+node.name


def reference_fields(node, uv=False, attribute=False, scanning=False):
    if scanning or uv:
        field=UV_FIELDS.get(node.bl_idname)
        if field:yield node,field
    field=ATTRIBUTE_FIELDS.get(node.bl_idname)
    if field and (scanning or node.bl_idname!='ShaderNodeAttribute' or node.attribute_type=='GEOMETRY'):
        if scanning or node.bl_idname!='ShaderNodeVertexColor' or attribute:
            yield node,field


def reference_candidates():
    from . import nested_data,geometry_contracts,name_references
    seen=set()
    def emit(owner,target,field,label):
        identity=(target.as_pointer(),field)
        value=name_references.read(target,field)
        if identity not in seen and isinstance(value,str) and value:
            seen.add(identity)
            yield owner,target,field,label
    def sources(owner,tree,values,label):
        for node in tree.nodes:
            for socket in name_sockets(node,EDITABLE_NAME_INPUTS):
                source=geometry_contracts.name_source(socket,values)
                if source:
                    target,field=source
                    source_owner=target.id_data
                    if source_owner.is_embedded_data:source_owner=owner
                    yield from emit(source_owner,target,field,label+' / '+node.name)
    for owner,tree,label in nested_data.node_trees():
        defaults={}
        for socket,direction in nested_data.utils.iter_interface_sockets(tree):
            yield from emit(owner,socket,'default_attribute_name',label+' / '+socket.name)
            if direction=='INPUT' and socket.socket_type=='NodeSocketString':
                defaults[socket.identifier]=(socket,'default_value')
        for node in tree.nodes:
            for target,field in reference_fields(node,scanning=True):
                yield from emit(owner,target,field,label+' / '+node.name)
        for context,values in geometry_contracts.contexts(tree,defaults,None):
            context_owner=owner if context.is_embedded_data else context
            yield from sources(context_owner,context,values,label+' / '+context.name)
    for obj in nested_data.bpy.data.objects:
        for modifier in obj.modifiers:
            label=obj.name+' / '+modifier.name
            for uv in (True,False):
                for target,field in name_references._settings_strings(modifier,uv):
                    yield from emit(obj,target,field,label)
            if modifier.type!='NODES' or modifier.node_group is None:continue
            for target,field in name_references.modifier_attributes(modifier):
                yield from emit(obj,target,field,label)
            for tree,values in geometry_contracts.contexts(modifier.node_group,geometry_contracts.modifier_values(modifier),obj):
                yield from sources(tree,tree,values,label+' / '+tree.name)
