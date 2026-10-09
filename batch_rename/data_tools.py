"""Native naming tools; skip linked, overridden and shared conflicts."""
import bpy, uuid
from collections import Counter

def protected(item):
    return (item.library is not None or item.override_library is not None
            or not item.is_editable or item.is_property_readonly('name'))


def synchronize():
    stats = Counter()
    owners = {}
    for obj in bpy.data.objects:
        data = obj.data
        if data is None:
            stats['no_data'] += 1
            continue
        owners.setdefault(data, []).append(obj)
    plan = []
    for data, objects in owners.items():
        if protected(data) or any(protected(obj) for obj in objects):
            stats['readonly'] += 1
        elif len({obj.name for obj in objects}) != 1:
            stats['shared'] += 1
        elif data.name == objects[0].name:
            stats['unchanged'] += 1
        else:
            plan.append((data, data.name, objects[0].name))
    # Stage all candidates to resolve cycles (A -> B and B -> A) correctly.
    prefix = '__data_name_sync_' + uuid.uuid4().hex + '_'
    touched = []
    try:
        for index, (data, old, wanted) in enumerate(plan):
            touched.append((data, old))
            data.rename(prefix + str(index), mode='NEVER')
        for data, old, wanted in plan:
            data.rename(wanted, mode='NEVER')
            stats['renamed'] += 1
            if data.name != wanted:
                stats['suffix'] += 1
    except Exception:
        # Restore original names without stealing any unrelated data-block name.
        for index, (data, old) in enumerate(touched):
            data.rename(prefix + 'rollback_' + str(index), mode='NEVER')
        for data, old in touched:
            data.rename(old, mode='NEVER')
        raise
    return stats
