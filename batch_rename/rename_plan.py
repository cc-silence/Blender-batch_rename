"""One preflight and reversible transaction for every scanned data category."""
import uuid
from . import nested_data, name_safety, name_references as names, utils

DATA_KEYS = {'__uv_layers__','__vertex_groups__','__attributes__','__color_attributes__'}
REF_KEY = '__name_references__'

def _namespace(operation):
    return (operation['key'], 0 if not operation['key'].startswith('__') else operation['owner'].as_pointer())

def _identity(target, field):
    return target.as_pointer(), field

def _general(category, safety, errors, denied):
    from . import data_catalog as catalog
    members = nested_data.live_members(category.key, category.entries) if category.key in nested_data.LABELS else None
    indexes = {}
    for row in category.entries:
        desired = row.new_name.strip()
        if desired == row.old_name or (not desired and row.field not in ('label','description')):
            continue
        owner = row.target
        if row.read_only or not catalog.editable(owner):
            errors.append(row.old_name + ': \u6570\u636e\u5df2\u5220\u9664\u6216\u53ea\u8bfb')
            continue
        target = owner
        if members is not None:
            target = nested_data.resolve(row.cache_key)
            if target is not None and (owner.as_pointer(),target.as_pointer(),row.field) not in members:
                target = None
        elif category.key == catalog.SOCKETS:
            if owner.as_pointer() not in indexes:
                indexes[owner.as_pointer()] = utils.socket_index(owner)
            target = indexes[owner.as_pointer()].get(row.identifier)
        if target is None or names.read(target,row.field) != row.old_name:
            errors.append(row.old_name + ': \u6570\u636e\u5df2\u53d8\u5316\uff0c\u9700\u91cd\u65b0\u67e5\u627e')
            continue
        if utils.contains_chinese(desired):
            denied.add(_identity(target,row.field))
            errors.append(row.old_name + ': 新名仍含中文，已保留原名')
            continue
        reason = '' if category.key == REF_KEY else safety.reason(category.key,owner,row.old_name,desired,row.field)
        if reason:
            errors.append(row.old_name + ': ' + reason)
            continue
        yield {'owner':owner,'target':target,'field':row.field,'old':row.old_name,
               'desired':desired,'key':category.key}

def build(categories):
    safety = name_safety.Preflight()
    errors, operations, refs, namespace_ids = [], {}, {}, {}
    denied = set()
    for category in categories:
        if category.key in DATA_KEYS:
            plans, records, issues = names.prepare(category,safety,validate_refs=False)
            errors.extend(issues)
            for namespace_key,(owner,target,old,desired) in plans.items():
                identity = _identity(target,'name')
                operations[identity] = {'owner':owner,'target':target,'field':'name','old':old,
                                        'desired':desired,'key':category.key}
                namespace_ids[namespace_key] = identity
            for target,field,owner,users,old in records:
                identity = _identity(target,field) if target is not None else (owner.as_pointer(),'@dynamic:'+old)
                record = refs.setdefault(identity, {'target':target,'field':field,'owner':owner,'old':old,'users':set()})
                record['users'].update(users)
        else:
            for operation in _general(category,safety,errors,denied):
                identity = _identity(operation['target'],operation['field'])
                previous = operations.get(identity)
                if previous is not None and previous['desired'] != operation['desired']:
                    errors.append(operation['old'] + ': \u540c\u4e00\u5b57\u6bb5\u5b58\u5728\u51b2\u7a81\u7684\u65b0\u540d')
                    operations.pop(identity,None)
                else:
                    operations[identity] = operation
    # Check the whole dependency graph before changing any RNA value.
    while True:
        blocked = set()
        for identity, record in refs.items():
            keys = {(user,record['old']) for user in record['users']}
            dependencies = {namespace_ids[key] for key in keys if key in namespace_ids}
            active = dependencies & operations.keys()
            explicit = operations.get(identity)
            if not active and explicit is None:
                continue
            complete = len(dependencies) == len(keys) and dependencies <= operations.keys()
            values = {operations[dep]['desired'] for dep in active}
            if explicit is not None:
                values.add(explicit['desired'])
            valid = (identity not in denied and complete and len(values)==1 and record['target'] is not None
                     and utils.is_editable(record['owner']) and not names.readonly(record['target'],record['field']))
            if not valid:
                blocked.update(active)
                if explicit is not None:blocked.add(identity)
        if not blocked:
            break
        for identity in blocked:
            operation = operations.pop(identity,None)
            if operation is not None:
                errors.append(operation['owner'].name + ' / ' + operation['old'] +
                              ': \u5171\u4eab\u5b57\u7b26\u4e32\u5f15\u7528\u65e0\u6cd5\u4e00\u81f4\u66f4\u65b0\uff0c\u5df2\u4fdd\u7559\u539f\u540d')
    updates = {}
    for identity,record in refs.items():
        dependencies = {namespace_ids[key] for key in {(user,record['old']) for user in record['users']}
                        if key in namespace_ids}
        if dependencies and dependencies <= operations.keys():
            updates[identity] = (record,dependencies)
            # A scanned string and an automatic dependency are the same write.
            operations.pop(identity,None)
    return operations, updates, errors

def execute(operations, updates, errors):
    changed, reference_changes, actual, collisions = [], [], {}, []
    try:
        # Only free names involved in a genuine swap/chain. Native setters retain identity.
        moving = {(_namespace(op),op['old']) for op in operations.values() if op['field']=='name'}
        for identity,operation in operations.items():
            changed.append((identity,operation))
            if operation['field']=='name' and (_namespace(operation),operation['desired']) in moving:
                names.write(operation['target'],'name','_wkngr_'+uuid.uuid4().hex)
        for identity,operation in changed:
            names.write(operation['target'],operation['field'],operation['desired'])
            value = names.read(operation['target'],operation['field'])
            if operation['field'] not in ('name','name_display') and value != operation['desired']:
                raise ValueError('Setter did not retain the requested value')
            actual[identity] = value
            if value != operation['desired']:
                collisions.append(operation['desired']+' -> '+value)
        for identity,(record,dependencies) in updates.items():
            values = {actual[dep] for dep in dependencies}
            if len(values)!=1:
                raise ValueError('Shared reference resolves to conflicting actual names')
            desired = next(iter(values))
            reference_changes.append(record)
            names.write(record['target'],record['field'],desired)
            if names.read(record['target'],record['field']) != desired:
                raise ValueError('Reference setter did not retain requested name')
        owners = {op['owner'] for _,op in changed} | {record['owner'] for record in reference_changes}
        for owner in owners:owner.update_tag()
        return len(changed), errors, collisions
    except (RuntimeError,ValueError,TypeError,ReferenceError) as exc:
        failures = []
        def restore(target,field,value):
            try:
                names.write(target,field,value)
                if names.read(target,field)!=value:
                    raise ValueError('Restored value does not match')
            except (RuntimeError,ValueError,TypeError,ReferenceError) as failure:
                failures.append(str(failure))
        for _,operation in changed:
            if operation['field']=='name':
                restore(operation['target'],'name','_wkngr_'+uuid.uuid4().hex)
        for _,operation in changed:
            restore(operation['target'],operation['field'],operation['old'])
        for record in reversed(reference_changes):
            restore(record['target'],record['field'],record['old'])
        if failures:
            errors.append('\u56de\u6eda\u4e0d\u5b8c\u6574\uff0c\u8bf7\u64a4\u9500\u5e76\u6838\u5bf9: '+'; '.join(failures))
        else:
            errors.append('\u5f15\u7528\u66f4\u65b0\u5931\u8d25\uff0c\u5df2\u6062\u590d\u5168\u90e8\u672c\u6b21\u4fee\u6539: '+str(exc))
        return 0, errors, []

def apply(categories):
    with nested_data.validation_session():
        return execute(*build(categories))

