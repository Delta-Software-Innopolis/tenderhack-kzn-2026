"""Serialize requested characteristics in the catalogue's characteristic/value shape."""

if __package__:
    from .language import canonical
    from .values import UNITS, convert_value
    from .catalog import characteristic_key, source_ids
else:
    from language import canonical
    from values import UNITS, convert_value
    from catalog import characteristic_key, source_ids


def normalize_characteristic(query_char, options, candidates):
    # Different rows of the same characteristic are one definition, not ambiguity.
    definitions = {characteristic_key(c) for c in options}
    mapped = len(definitions) == 1
    alternatives = len(definitions) > 1 and query_char.get('match_mode') == 'any'
    status = 'mapped' if mapped else 'alternatives' if alternatives else 'ambiguous' if options else 'not_found'
    name = options[0]['name'] if mapped else query_char['name']
    value = {key: query_char[key] for key in ('type', 'value', 'unit')}
    value.update(name=name, value_code=None)
    reason = None
    inferred = False
    if mapped and value['type'] in {'number', 'interval'}:
        units = {v['unit'] for c in options for v in c['values'] if v['type'] in {'number', 'interval'}}
        source_unit = value['unit']
        if source_unit is None and len(units) > 1:
            status, reason = 'ambiguous', 'Укажите единицу измерения: в КТРУ используются разные единицы'
        elif units:
            dimension = UNITS.get(source_unit, (source_unit,))[0]
            compatible = sorted((u for u in units if source_unit is None or
                                 UNITS.get(u, (u,))[0] == dimension), key=lambda u: u or '')
            if compatible:
                # Deterministic output unit even if candidates use different compatible units.
                value = convert_value(value, compatible[0])
                inferred = source_unit is None and compatible[0] is not None
            else:
                status, reason = 'unit_mismatch', 'Единица запроса несовместима с единицами характеристики КТРУ'
    elif (mapped or alternatives) and value['type'] == 'string':
        spellings = sorted({v['value'] for c in options for v in c['values']
                            if v['type'] == 'string' and canonical(v['value']) == canonical(value['value'])})
        if spellings:
            value['value'] = spellings[0]

    def common(key):
        values = {c[key] for c in options}
        return next(iter(values)) if mapped and len(values) == 1 else None

    option_ids = {c['id'] for c in options}
    return {
        # There is no DB row for the user's requirement. References identify actual rows.
        'id': None, 'code': common('code'), 'name': name,
        'ktru_type': common('ktru_type'), 'kind': common('kind'),
        'is_required': common('is_required'), 'choice_type': common('choice_type'),
        'values': [value], 'issues': [],
        'mapping_status': status, 'in_ktru': bool(options),
        'match_mode': 'any' if alternatives else 'single',
        'reason': reason or ({'not_found': 'Характеристика отсутствует в КТРУ переданных кандидатов',
                              'alternatives': 'Роль свойства не указана; достаточно совпадения с одной из характеристик ktru_refs',
                              'ambiguous': 'Название соответствует нескольким характеристикам КТРУ'}.get(status)),
        'source': query_char['source'], 'start': query_char['start'], 'end': query_char['end'],
        'negated': query_char.get('negated', False), 'unit_inferred': inferred,
        'ktru_refs': [{'candidate_code': candidate['code'], 'characteristic_id': row_id,
                       'code': c['code'], 'name': c['name']}
                      for candidate in candidates for c in candidate['characteristics'] if c['id'] in option_ids
                      for row_id in source_ids(c)],
    }
