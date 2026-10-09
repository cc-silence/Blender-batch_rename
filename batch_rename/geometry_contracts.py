"""Preflight for geometry name contracts whose origin is not statically known."""
import bpy
from . import nested_data, node_names

NAMED = {'GeometryNodeInputNamedAttribute', 'GeometryNodeStoreNamedAttribute', 'GeometryNodeRemoveAttribute'}
EXTERNAL = {'GeometryNodeObjectInfo', 'GeometryNodeCollectionInfo'}


def trees(root):
    seen = set()
    todo = [root] if root else []
    while todo:
        tree = todo.pop()
        if tree.as_pointer() in seen:
            continue
        seen.add(tree.as_pointer())
        yield tree
        todo.extend(node.node_tree for node in tree.nodes if getattr(node, 'node_tree', None))


def _safe_name_consumers(output, seen=None, kind='ATTRIBUTE'):
    """Only share a writable name source among other name inputs."""
    seen = set() if seen is None else seen
    if output.as_pointer() in seen:
        return False
    seen.add(output.as_pointer())
    for link in output.links:
        node = link.to_node
        if node_names.NAME_KINDS.get((node.bl_idname,link.to_socket.name)) == kind:
            continue
        if node.bl_idname == 'NodeReroute' and _safe_name_consumers(node.outputs[0],seen.copy(),kind):
            continue
        if getattr(node,'node_tree',None) is not None and link.to_socket.type == 'STRING':
            inputs = [n for n in node.node_tree.nodes if n.bl_idname=='NodeGroupInput']
            matches = [s for n in inputs for s in n.outputs if s.identifier==link.to_socket.identifier]
            if matches and all(_safe_name_consumers(s,seen.copy(),kind) for s in matches):
                continue
        return False
    return True

def name_source(socket, values=None):
    """Resolve writable literal strings through constants, reroutes and group inputs."""
    values = values or {}
    kind=node_names.NAME_KINDS.get((socket.node.bl_idname,socket.name),'ATTRIBUTE')
    current, seen = socket, set()
    while current.is_linked:
        if len(current.links)!=1:
            return None
        link=current.links[0];node=link.from_node
        if node.as_pointer() in seen or node.mute:
            return None
        seen.add(node.as_pointer())
        if not _safe_name_consumers(link.from_socket,kind=kind):
            return None
        if node.bl_idname=='FunctionNodeInputString':
            return node,'string'
        if node.bl_idname=='NodeGroupInput':
            source=values.get(link.from_socket.identifier)
            return source if isinstance(source,tuple) and len(source)==2 else None
        if node.bl_idname!='NodeReroute':
            return None
        current=node.inputs[0]
    return current,'default_value'

def string_value(source):
    target,field=source
    return target.get(field[4:],'') if field.startswith('@id:') else getattr(target,field)

def child_values(node, values, obj):
    return {socket.identifier: (name_source(socket,values) if socket.type=='STRING'
                                else input_value(socket,values,obj))
            for socket in node.inputs if socket.type in {'OBJECT','COLLECTION','STRING'}}



UNKNOWN = object()


def input_value(socket, values, self_object):
    seen = set()
    while socket.is_linked:
        if len(socket.links) != 1:
            return UNKNOWN
        link = socket.links[0]
        node = link.from_node
        if node.as_pointer() in seen or node.mute:
            return UNKNOWN
        seen.add(node.as_pointer())
        kind = node.bl_idname
        if kind == 'GeometryNodeSelfObject':
            return self_object if self_object is not None else UNKNOWN
        if kind == 'GeometryNodeInputObject':
            return node.object
        if kind == 'GeometryNodeInputCollection':
            return node.collection
        if kind == 'NodeGroupInput':
            return values.get(link.from_socket.identifier, UNKNOWN)
        if kind != 'NodeReroute':
            return UNKNOWN
        socket = node.inputs[0]
    return getattr(socket, 'default_value', UNKNOWN)


def modifier_values(modifier):
    result = {}
    props = getattr(modifier, 'properties', None)
    for socket in modifier.node_group.interface.items_tree:
        if socket.item_type != 'SOCKET' or socket.in_out != 'INPUT':
            continue
        if socket.socket_type not in {'NodeSocketObject', 'NodeSocketCollection','NodeSocketString'}:
            continue
        if props is not None:
            item = getattr(props.inputs, socket.identifier, None)
            result[socket.identifier] = ((item,'value') if socket.socket_type=='NodeSocketString' and item is not None else getattr(item,'value',UNKNOWN))
        else:
            if socket.socket_type=='NodeSocketString':
                result[socket.identifier] = (modifier,'@id:'+socket.identifier) if socket.identifier in modifier else (socket,'default_value')
            else:
                result[socket.identifier] = modifier.get(socket.identifier,getattr(socket,'default_value',UNKNOWN))
    return result


def contexts(tree, values, self_object, path=()):
    if tree is None or tree.as_pointer() in path:
        return
    yield tree, values
    path = (*path, tree.as_pointer())
    for node in tree.nodes:
        child = getattr(node, 'node_tree', None)
        if child is not None:
            inputs = child_values(node,values,self_object)
            yield from contexts(child,inputs,self_object,path)


def external_value(node, values, obj):
    socket = node.inputs.get('Object' if node.bl_idname == 'GeometryNodeObjectInfo' else 'Collection')
    return input_value(socket, values, obj) if socket is not None else UNKNOWN


def reason(objects, old, external=None):
    targets = {obj.as_pointer() for obj in objects}
    for obj in objects:
        for modifier in obj.modifiers:
            if modifier.type in {'DATA_TRANSFER', 'DYNAMIC_PAINT', 'FLUID'}:
                return '\u6570\u636e\u4f20\u9012\u6216\u6a21\u62df\u4fee\u6539\u5668\u7684\u5c5e\u6027\u6620\u5c04\u5c1a\u672a\u786e\u8ba4'
            if modifier.type != 'NODES' or modifier.node_group is None:
                continue
            for tree, values in contexts(modifier.node_group, modifier_values(modifier), obj):
                for node in tree.nodes:
                    where = ' [' + obj.name + ' / ' + modifier.name + ' / ' + tree.name + ' / ' + node.name + ']'
                    if node.bl_idname in NAMED:
                        socket = node.inputs.get('Name')
                        if socket is not None and name_source(socket,values) is None:
                            return '\u5c5e\u6027\u540d\u79f0\u7531\u8282\u70b9\u8fde\u7ebf\u63d0\u4f9b\uff0c\u65e0\u6cd5\u786e\u5b9a\u6240\u6709\u52a8\u6001\u503c' + where
    return ''

