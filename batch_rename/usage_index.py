"""Read-only reference index adapted from blender_usage_lookup_v2.py."""
import bpy
import heapq

def modifier_data_inputs(modifier):
    group = getattr(modifier, 'node_group', None)
    names = {getattr(item, 'identifier', ''): item.name for item in group.interface.items_tree} if group else {}
    inputs = getattr(getattr(modifier, 'properties', None), 'inputs', None)
    if inputs is not None:
        for prop in inputs.bl_rna.properties:
            if prop.type == 'POINTER' and prop.identifier != 'rna_type':
                socket = getattr(inputs, prop.identifier, None)
                value = getattr(socket, 'value', None)
                if isinstance(value, (bpy.types.Material, bpy.types.Collection, bpy.types.Object, bpy.types.NodeTree)):
                    yield names.get(prop.identifier, prop.identifier), value
    else:
        try:
            for name, value in modifier.items():
                if isinstance(value, (bpy.types.Material, bpy.types.Collection, bpy.types.Object, bpy.types.NodeTree)):
                    yield names.get(name, str(name)), value
        except TypeError:
            pass

from collections import defaultdict, deque


def data_label(data):
    library=getattr(data,'library',None)
    return data.name + (' ['+library.filepath+']' if library else '')


def reference_fields(value):
    for prop in value.bl_rna.properties:
        if prop.type!='POINTER' or prop.identifier in {'rna_type','id_data','original'}:
            continue
        cls=getattr(bpy.types,prop.fixed_type.identifier,None)
        if cls is not None and issubclass(cls,(bpy.types.Material,bpy.types.Collection,bpy.types.Object,bpy.types.NodeTree)):
            material=getattr(value,prop.identifier,None)
            if material is not None:
                yield prop.identifier,material


def all_ids():
    """Enumerate concrete ID collections; exclude the 5.2 all_ids aggregate."""
    seen=set()
    for prop in bpy.data.bl_rna.properties:
        if prop.type!='COLLECTION':continue
        cls=getattr(bpy.types,prop.fixed_type.identifier,None)
        if cls is None or cls is bpy.types.ID or not issubclass(cls,bpy.types.ID):continue
        for owner in getattr(bpy.data,prop.identifier):
            pointer=owner.as_pointer()
            if pointer not in seen:
                seen.add(pointer)
                yield owner


def custom_references(value,prefix=''):
    try:items=value.items()
    except (AttributeError,TypeError):return
    for name,child in items:
        prop=value.bl_rna.properties.get(name) if hasattr(value,'bl_rna') else None
        if prop is not None and prop.is_runtime and prop.type in {'POINTER','COLLECTION'}:
            continue  # The same registered field is enumerated through RNA, not twice.
        path=prefix+'['+repr(name)+']'
        if isinstance(child,bpy.types.ID):
            yield path,child
        elif hasattr(child,'items'):
            yield from custom_references(child,path)


def rna_bases(schema):
    while schema is not None:
        yield schema.identifier
        schema=schema.base


def nested_reference_locations(owner,target):
    """Read known reference structures only; never recursively evaluate arbitrary RNA getters.

    The native user map remains authoritative for owners whose field is unsupported.
    """
    locations=[]
    visited=set()
    def inspect(value,path):
        identity=value.as_pointer()
        if identity in visited:return
        visited.add(identity)
        for field,child in reference_fields(value):
            if child==target:locations.append(path+field)
        for suffix,child in custom_references(value):
            if child==target:locations.append(path+suffix)
    def items(values,path):
        for i,value in enumerate(values):inspect(value,path+'['+str(i)+'].')
    inspect(owner,'')
    if isinstance(owner,bpy.types.Object):
        items(owner.constraints,'constraints')
        items(owner.modifiers,'modifiers')
        items(owner.material_slots,'material_slots')
        for i,modifier in enumerate(owner.modifiers):
            for field,child in modifier_data_inputs(modifier):
                if child==target:locations.append('modifiers['+str(i)+'].'+field)
        if owner.pose:
            for i,bone in enumerate(owner.pose.bones):
                items(bone.constraints,'pose.bones['+str(i)+'].constraints')
    if isinstance(owner,bpy.types.Collection):
        for field in ('objects','children'):
            for i,child in enumerate(getattr(owner,field)):
                if child==target:locations.append(field+'['+str(i)+']')
    if isinstance(owner,(bpy.types.Mesh,bpy.types.Curve,bpy.types.MetaBall)):
        for i,material in enumerate(owner.materials):
            if material==target:locations.append('materials['+str(i)+']')
    if isinstance(owner,bpy.types.Scene):
        items(owner.view_layers,'view_layers')
        for i,child in enumerate(owner.collection.children):
            if child==target:locations.append('collection.children['+str(i)+']')
        for i,child in enumerate(owner.collection.objects):
            if child==target:locations.append('collection.objects['+str(i)+']')
    trees=[]
    if isinstance(owner,bpy.types.NodeTree):trees.append(('',owner))
    elif isinstance(owner,(bpy.types.Material,bpy.types.World,bpy.types.Light,bpy.types.Texture)):
        tree=owner.node_tree
        if tree is not None:trees.append(('node_tree.',tree))
    for prefix,tree in trees:
        for i,node in enumerate(tree.nodes):
            base=prefix+'nodes['+str(i)+'].'
            inspect(node,base)
            for j,socket in enumerate(node.inputs):
                if socket.type in {'OBJECT','COLLECTION','MATERIAL'}:
                    if socket.default_value==target:locations.append(base+'inputs['+str(j)+'].default_value')
        for i,socket in enumerate(tree.interface.items_tree):
            if socket.item_type=='SOCKET' and socket.socket_type in {'NodeSocketObject','NodeSocketCollection','NodeSocketMaterial'}:
                if socket.default_value==target:locations.append(prefix+'interface.items_tree['+str(i)+'].default_value')
    return sorted(set(locations)),[]


class UsageIndex:
    def __init__(self):
        self.data={}
        self.edge_keys=set()
        self.pairs=set()
        self.costs={}
        self.tree_owners=defaultdict(list)
        self.owners=tuple(all_ids())
        self.edges=defaultdict(list)
        self.reverse=defaultdict(list)
        self.groups=tuple(bpy.data.node_groups)
        self.materials=tuple(bpy.data.materials)
        self.collections=tuple(bpy.data.collections)
        for collection in self.collections:
            for obj in collection.objects:self._edge(collection,obj,'objects')
            for child in collection.children:
                self._edge(collection,child,'\u5b50\u96c6\u5408')
        for scene in bpy.data.scenes:
            self._edge(scene,scene.collection,'collection')
            for obj in scene.collection.objects:self._edge(scene.collection,obj,'objects')
            for field,child in reference_fields(scene):self._edge(scene,child,field)
            for child in scene.collection.children:
                self._edge(scene.collection,child,'\u5b50\u96c6\u5408')
        for obj in bpy.data.objects:
            if obj.instance_collection:
                self._edge(obj,obj.instance_collection,'\u96c6\u5408\u5b9e\u4f8b\u914d\u7f6e')
        trees={tree.as_pointer():tree for tree in self.groups}
        tree_fields={}
        for owner in self.owners:
            self.data[owner.as_pointer()]=owner
            schema=owner.bl_rna.identifier
            if schema not in tree_fields:
                fields=[]
                for prop in owner.bl_rna.properties:
                    if prop.type!='POINTER' or prop.identifier in {'rna_type','id_data','original'}:continue
                    cls=getattr(bpy.types,prop.fixed_type.identifier,None)
                    if cls is not None and issubclass(cls,bpy.types.NodeTree):fields.append(prop.identifier)
                tree_fields[schema]=fields
            for field in tree_fields[schema]:
                tree=getattr(owner,field,None)
                if tree is not None:
                    trees[tree.as_pointer()]=tree
                    self.tree_owners[tree.as_pointer()].append((owner,field))
                    self._edge(owner,tree,field)
            for path,child in custom_references(owner):
                self._edge(owner,child,'\u81ea\u5b9a\u4e49\u5c5e\u6027 '+path)
        for obj in bpy.data.objects:
            for field,child in reference_fields(obj):self._edge(obj,child,field)
            for i,constraint in enumerate(obj.constraints):
                for field,child in reference_fields(constraint):self._edge(obj,child,'constraints['+str(i)+'].'+field)
            for modifier in obj.modifiers:
                base='\u4fee\u6539\u5668 '+modifier.name+' / '
                for field,child in reference_fields(modifier):self._edge(obj,child,base+field)
                for field,child in modifier_data_inputs(modifier):self._edge(obj,child,base+field)
                # Geometry Nodes input values are already indexed above.
                if modifier.type!='NODES':
                    for path,child in custom_references(modifier):self._edge(obj,child,base+path)
        for tree in trees.values():
            self.data[tree.as_pointer()]=tree
            for node in tree.nodes:
                label='\u8282\u70b9 '+node.name
                child=getattr(node,'node_tree',None)
                if isinstance(child,bpy.types.NodeTree):
                    self._edge(tree,child,label)
                for field,material in reference_fields(node):
                    if field!='node_tree':self._edge(tree,material,label+' / '+field)
                for path,child in custom_references(node):self._edge(tree,child,label+' / '+path)
                for socket in node.inputs:
                    material=getattr(socket,'default_value',None)
                    if isinstance(material,(bpy.types.Material,bpy.types.Collection,bpy.types.Object,bpy.types.NodeTree)):
                        suffix=' (\u5df2\u8fde\u7ebf\u63d2\u53e3\u7684\u9ed8\u8ba4\u503c)' if socket.is_linked else ''
                        self._edge(tree,material,label+' / '+socket.name+suffix)
            interface=getattr(tree,'interface',None)
            if interface:
                for socket in interface.items_tree:
                    material=getattr(socket,'default_value',None)
                    if isinstance(material,(bpy.types.Material,bpy.types.Collection,bpy.types.Object,bpy.types.NodeTree)):
                        self._edge(tree,material,'\u7ec4\u63a5\u53e3\u9ed8\u8ba4\u503c / '+socket.name)

    def _edge(self,parent,child,label):
        a,b=parent.as_pointer(),child.as_pointer()
        self.data[a],self.data[b]=parent,child
        edge=(a,b,label)
        if edge in self.edge_keys:return
        self.edge_keys.add(edge)
        self.pairs.add((a,b))
        self.costs[edge]=0 if child.is_embedded_data else 1
        self.edges[a].append(edge)
        self.reverse[b].append(edge)


    def add_native_edges(self,native):
        scene_members={scene.as_pointer():{obj.as_pointer() for obj in scene.collection.all_objects} for scene in bpy.data.scenes}
        embedded={}
        for tree,owners in self.tree_owners.items():
            if self.data.get(tree) is not None and self.data[tree].is_embedded_data:
                for owner,field in owners:embedded.setdefault(owner.as_pointer(),[]).append(tree)
        pending=[]
        for child,owners in native.items():
            b=child.as_pointer();candidates=[]
            for owner in owners:
                a=owner.as_pointer()
                if (a,b) in self.pairs or b in scene_members.get(a,()):continue
                candidates.append((a,owner))
            tree_ancestors=set()
            if any(isinstance(owner,bpy.types.NodeTree) or a in embedded for a,owner in candidates):
                # Blender node_foreach_id also enumerates eval_dependencies, which
                # summarize nested groups. Follow the real typed tree edges once
                # per child so these cached summaries cannot shorten the chain.
                queue=deque([b])
                while queue:
                    for parent,_,label in self.reverse.get(queue.popleft(),()):
                        if parent not in tree_ancestors and isinstance(self.data[parent],bpy.types.NodeTree):
                            tree_ancestors.add(parent);queue.append(parent)
            for a,owner in candidates:
                if a in tree_ancestors or any(tree in tree_ancestors for tree in embedded.get(a,())):continue
                label='data' if isinstance(owner,bpy.types.Object) and owner.data==child else '\u6570\u636e\u5757\u5f15\u7528'
                pending.append((owner,child,label))
        # Defer fallback edges so cache classification uses only real typed edges.
        for owner,child,label in pending:self._edge(owner,child,label)

    def shortest_routes(self,target):
        key=target.as_pointer();distances={key:0};routes={key:None};queue=[(0,key)]
        while queue:
            distance,child=heapq.heappop(queue)
            if distances.get(child)!=distance:continue
            for edge in self.reverse.get(child,()):
                parent=edge[0];candidate=distance+self.costs[edge]
                if candidate<distances.get(parent,float('inf')):
                    distances[parent]=candidate;routes[parent]=edge;heapq.heappush(queue,(candidate,parent))
        return distances,routes

    def fast_query(self,target,native):
        """One shortest-path pass; no per-object group expansion or unused reports."""
        self.add_native_edges(native);distances,routes=self.shortest_routes(target)
        rows=[];native_users=native.get(target,set())
        locations={owner.as_pointer():nested_reference_locations(owner,target)[0] for owner in native_users}
        for pointer,distance in distances.items():
            owner=self.data.get(pointer)
            if owner is None:continue
            if owner==target and not isinstance(target,bpy.types.Object):continue
            parts=[owner.bl_rna.name+' / '+data_label(owner)];cursor=pointer
            while routes[cursor] is not None:
                edge=routes[cursor];cursor=edge[1];parts.extend([edge[2],data_label(self.data[cursor])])
            ownership=isinstance(owner,(bpy.types.Scene,bpy.types.Collection)) or owner==target
            if isinstance(owner,bpy.types.Object) and routes[pointer] is not None:
                first=routes[pointer]
                kind=2 if isinstance(self.data[first[1]],bpy.types.NodeTree) else 1
            else:kind=0 if ownership else 2
            paths=[' -> '.join(parts)]
            if pointer in locations:
                paths.extend(owner.bl_rna.name+' / '+data_label(owner)+' / '+field+' -> '+data_label(target) for field in locations[pointer])
            rows.append({'_owner':owner,'depth':distance,'kind':kind,
                         'path':'\n'.join(dict.fromkeys(paths)),'direct':distance<=1})
        return {'other_uses':rows}

    def group_object_users(self,group_keys):
        """Index real modifier/material-slot bindings, keeping one path per root and group."""
        bindings=defaultdict(list)
        for obj in sorted(bpy.data.objects,key=data_label):
            for modifier in obj.modifiers:
                group=getattr(modifier,'node_group',None)
                if isinstance(group,bpy.types.NodeTree):
                    bindings[group.as_pointer()].append((obj,'\u7269\u4f53 '+data_label(obj)+' / \u4fee\u6539\u5668 '+modifier.name))
            for index,slot in enumerate(obj.material_slots,1):
                if slot.material:
                    bindings[slot.material.as_pointer()].append((obj,'\u7269\u4f53 '+data_label(obj)+' / \u6750\u8d28\u69fd '+str(index)))
        found=defaultdict(list)
        for root,users in bindings.items():
            parents={root:None}
            queue=deque([root])
            while queue:
                parent=queue.popleft()
                for edge in self.edges.get(parent,()):
                    child=edge[1]
                    if child in parents or not isinstance(self.data[child],(bpy.types.NodeTree,bpy.types.Material)):continue
                    parents[child]=edge
                    queue.append(child)
            for group_key in group_keys.intersection(parents):
                chain=[]
                cursor=group_key
                while parents[cursor] is not None:
                    edge=parents[cursor]
                    chain.append((edge[2],data_label(self.data[cursor])))
                    cursor=edge[0]
                for obj,prefix in users:
                    parts=[prefix,data_label(self.data[root])]
                    for label,name in reversed(chain):parts.extend([label,name])
                    found[group_key].append({'object':data_label(obj),'path':' -> '.join(parts)})
        return found

    def query(self,target,native_map=None):
        key=target.as_pointer()
        routes={key:None}
        queue=deque([key])
        while queue:
            for edge in self.reverse.get(queue.popleft(),()):
                if edge[0] not in routes:
                    routes[edge[0]]=edge
                    queue.append(edge[0])

        def hit(value,prefix,obj=None,owner=None):
            current=value.as_pointer()
            if current not in routes:
                return None
            direct=current==key
            path=[prefix,data_label(value)]
            while routes[current] is not None:
                _,child,label=routes[current]
                path.extend([label,data_label(self.data[child])])
                current=child
            return {'object':data_label(obj) if obj else None,'direct':direct,'path':' -> '.join(path),'_owner':owner or obj or value}

        def collection_node_paths(root,prefix,obj):
            # Enumerate reference locations, not all combinatorial paths through nested groups.
            first=root.as_pointer()
            parents={first:None}
            pending=deque([first])
            rows=[]
            while pending:
                parent=pending.popleft()
                for edge in self.edges.get(parent,()):
                    child=edge[1]
                    if child not in parents:
                        parents[child]=edge
                        pending.append(child)
                    if not isinstance(self.data[child],bpy.types.Collection) or child not in routes:
                        continue
                    if isinstance(self.data[parent],bpy.types.Collection):
                        continue
                    chain=[]
                    cursor=parent
                    while parents[cursor] is not None:
                        previous=parents[cursor]
                        chain.append((previous[2],data_label(self.data[cursor])))
                        cursor=previous[0]
                    parts=[prefix,data_label(root)]
                    for label,name in reversed(chain):parts.extend([label,name])
                    parts.append(edge[2])
                    row=hit(self.data[child],' -> '.join(parts),obj)
                    row['direct']=False
                    rows.append(row)
            return rows

        result={'collection_query':isinstance(target,bpy.types.Collection),'target':data_label(target),'modifiers':[],'slots':[],'groups':[],'materials':[],'instances':[],'collections':[],'scenes':[],'direct_users':[],'direct_locations':[],'other_uses':[],'editors':[],'group_end_users':[],'inspection_warnings':[]}
        for obj in sorted(bpy.data.objects,key=data_label):
            prefix='\u7269\u4f53 '+data_label(obj)
            for modifier in obj.modifiers:
                base=prefix+' / \u4fee\u6539\u5668 '+modifier.name
                references=list(reference_fields(modifier))+list(modifier_data_inputs(modifier))
                group=getattr(modifier,'node_group',None)
                if isinstance(group,bpy.types.NodeTree):
                    references=[(field,value) for field,value in references if field!='node_group']
                    references.insert(0,('\u8282\u70b9\u7ec4',group))
                seen=set()
                for field,value in references:
                    identity=(field,value.as_pointer())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if isinstance(target,bpy.types.Collection) and isinstance(value,bpy.types.NodeTree):
                        result['modifiers'].extend(collection_node_paths(value,base+' / '+field,obj))
                    else:
                        row=hit(value,base+' / '+field,obj)
                        if row:
                            result['modifiers'].append(row)
            if isinstance(target,bpy.types.Collection) and obj.instance_collection:
                row=hit(obj.instance_collection,prefix+' / \u96c6\u5408\u5b9e\u4f8b',obj)
                if row:
                    if obj.instance_type!='COLLECTION':row['path']+=' (\u672a\u542f\u7528\u96c6\u5408\u5b9e\u4f8b)'
                    result['instances'].append(row)
            for number,slot in enumerate(obj.material_slots,1):
                if slot.material:
                    row=hit(slot.material,prefix+' / \u6750\u8d28\u69fd '+str(number),obj)
                    if row:
                        result['slots'].append(row)
        group_users=self.group_object_users({group.as_pointer() for group in self.groups if group.as_pointer() in routes}) if isinstance(target,bpy.types.Collection) else {}
        for group in sorted(self.groups,key=data_label):
            if group==target:
                continue
            for _,child,label in self.edges[group.as_pointer()]:
                row=hit(self.data[child],'\u8282\u70b9\u7ec4 '+data_label(group)+' / '+label,owner=group)
                if row:
                    result['groups'].append(row)
                    if isinstance(target,bpy.types.Collection):
                        endpoints=[]
                        for user in group_users.get(group.as_pointer(),()):
                            full=hit(self.data[child],user['path']+' / '+label)
                            full['object']=user['object']
                            full['direct']=False
                            endpoints.append(full)
                        result['group_end_users'].append({'group':data_label(group),'reference':row['path'],'users':endpoints})
        for material in sorted(self.materials,key=data_label):
            if material!=target:
                row=hit(material,'\u6750\u8d28')
                if row:
                    result['materials'].append(row)
        if isinstance(target,bpy.types.Collection):
            for collection in sorted(self.collections,key=data_label):
                if collection!=target:
                    row=hit(collection,'\u7236\u7ea7\u96c6\u5408')
                    if row:result['collections'].append(row)
            for scene in sorted(bpy.data.scenes,key=data_label):
                row=hit(scene.collection,'\u573a\u666f '+data_label(scene))
                if row:result['scenes'].append(row)
        covered=set()
        for parent,child,label in self.reverse.get(key,()):
            source=self.data[parent]
            if isinstance(source,bpy.types.NodeTree) and source.is_embedded_data:
                covered.update(owner.as_pointer() for owner,field in self.tree_owners.get(parent,()))
            else:covered.add(parent)
        native_users=(native_map if native_map is not None else bpy.data.user_map(subset=[target])).get(target,set())
        expanded=set()
        for user in native_users:
            locations,warnings=nested_reference_locations(user,target)
            result['inspection_warnings'].extend(data_label(user)+' / '+warning for warning in warnings)
            if locations:
                expanded.add(user.as_pointer())
                covered.add(user.as_pointer())
            for path in locations:
                suffix=' [batch_rename \u626b\u63cf/\u8bbe\u7f6e\u8bb0\u5f55\uff0c\u4e0d\u4ee3\u8868\u6a21\u578b\u4f7f\u7528]' if path.startswith('wkngr_') else ''
                result['direct_locations'].append({'object':data_label(user) if isinstance(user,bpy.types.Object) else None,
                    '_owner':user,'direct':True,'path':user.bl_rna.name+' / '+data_label(user)+' / '+path+' -> '+data_label(target)+suffix})
        result['unresolved_owner_count']=sum(user.as_pointer() not in covered for user in native_users)
        result['users_count']=target.users
        result['fake_user']=bool(target.use_fake_user)
        result['extra_user']=bool(target.use_extra_user)
        result['native_owner_count']=len(native_users)
        for user in sorted(native_users,key=lambda x:(x.bl_rna.identifier,data_label(x))):
            result['direct_users'].append({'object':None,'direct':True,
                'path':user.bl_rna.name+' / '+data_label(user)+' -> '+data_label(target)+(' [\u5177\u4f53\u5b57\u6bb5\u5c1a\u672a\u89e3\u6790]' if user.as_pointer() not in covered else '')})
        for parent,child,label in self.reverse.get(key,()):
            source=self.data[parent]
            owners={owner.as_pointer() for owner,field in self.tree_owners.get(parent,())} if isinstance(source,bpy.types.NodeTree) and source.is_embedded_data else {parent}
            if owners and owners.issubset(expanded):continue
            contexts=self.tree_owners.get(parent,()) if isinstance(source,bpy.types.NodeTree) and source.is_embedded_data else ()
            if contexts:
                prefixes=[owner.bl_rna.name+' / '+data_label(owner)+' / '+field for owner,field in contexts]
            else:
                prefixes=[source.bl_rna.name+' / '+data_label(source)]
            for prefix in prefixes:
                result['direct_locations'].append({'object':data_label(source) if isinstance(source,bpy.types.Object) else None,
                    'direct':True,'path':prefix+' / '+label+' -> '+data_label(target)})
        for owner in self.owners:
            if isinstance(owner,(bpy.types.Material,bpy.types.NodeTree,bpy.types.Object,bpy.types.Collection)) or owner==target:continue
            row=hit(owner,owner.bl_rna.name)
            if row:result['other_uses'].append(row)
        for obj in bpy.data.objects:
            if isinstance(obj.data,bpy.types.Light):
                row=hit(obj.data,'\u7269\u4f53 '+data_label(obj)+' / \u706f\u5149\u6570\u636e',obj)
                if row:result['other_uses'].append(row)
        for scene in bpy.data.scenes:
            if scene.world:
                row=hit(scene.world,'\u573a\u666f '+data_label(scene)+' / \u4e16\u754c')
                if row:result['other_uses'].append(row)
        for screen in bpy.data.screens:
            for index,area in enumerate(screen.areas):
                seen=set()
                for space in area.spaces:
                    if space.type!='NODE_EDITOR':continue
                    for field in ('node_tree','edit_tree'):
                        tree=getattr(space,field,None)
                        if tree is None or tree.as_pointer() in seen:continue
                        seen.add(tree.as_pointer())
                        row=hit(tree,'\u5c4f\u5e55 '+data_label(screen)+' / \u533a\u57df '+str(index+1)+' / '+field)
                        if row:result['editors'].append(row)
        return result

