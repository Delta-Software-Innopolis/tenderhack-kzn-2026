"""Logical characteristic identity and read-time deduplication; no database writes."""

import json

if __package__:
    from .language import name_key
else:
    from language import name_key


def characteristic_key(characteristic):
    # Equal names with different catalogue codes/types are not necessarily duplicates.
    return characteristic['code'], name_key(characteristic['name']), characteristic['ktru_type']


def source_ids(characteristic):
    return characteristic.get('source_ids', [characteristic['id']])


def coalesce_characteristics(characteristics):
    """Merge duplicate definitions within ONE candidate, retaining row/value provenance."""
    groups = {}
    for characteristic in characteristics:
        key = characteristic_key(characteristic)
        if key not in groups:
            groups[key] = dict(characteristic, values=[], issues=[], source_ids=[])
        group = groups[key]
        group['source_ids'].extend(source_ids(characteristic))
        group['values'].extend(characteristic['values'])
        group['issues'].extend(characteristic['issues'])
        for field in ('kind', 'is_required', 'choice_type'):
            if group[field] != characteristic[field]:
                group[field] = None
    for group in groups.values():
        values = {}
        for value in group['values']:
            key = json.dumps({k: value[k] for k in ('type', 'value', 'unit')}, sort_keys=True, ensure_ascii=False)
            if key not in values:
                values[key] = dict(value, name=group['name'])
            else:
                existing = values[key]
                codes = list(dict.fromkeys(existing.get('value_codes', [existing['value_code']]) +
                                           value.get('value_codes', [value['value_code']])))
                if len(codes) > 1:
                    existing['value_codes'] = codes
        group['values'] = list(values.values())
        if len(group['source_ids']) == 1:
            del group['source_ids']
    return list(groups.values())
