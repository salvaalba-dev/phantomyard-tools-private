"""Explicit logical document editions; format membership never grants access."""
import re


def validated(value, original=None, organization=None):
    if (not isinstance(value, dict) or not {'id', 'title'} <= set(value)
            or set(value) - {'id', 'title', 'version', 'code'}
            or not isinstance(value['id'], str) or len(value['id']) > 512
            or not re.fullmatch(r'urn:[a-z0-9][a-z0-9_-]{0,99}:document:[a-z0-9][a-z0-9_./-]{0,299}', value['id'])):
        raise ValueError('A logical document requires an explicit organization identity and edition')
    if any(part in {'', '.', '..'} for part in value['id'].split(':document:', 1)[1].split('/')):
        raise ValueError('Invalid logical document identity segments')
    for key, limit in [('title', 240), ('version', 40), ('code', 80)]:
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                             or len(value[key]) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value[key])):
            raise ValueError('Invalid logical document label')
    if organization is not None and not value['id'].startswith('urn:' + organization + ':document:'):
        raise ValueError('Logical documents must remain within the selected organization')
    if original is not None and (original.get('version') != value.get('version')
                                 or 'code' in value and original.get('code') != value['code']):
        raise ValueError('Format metadata must match the declared logical document edition')
    return dict(value)


def check_members(documents):
    """Reject inconsistent members instead of selecting a convenient representative."""
    groups = {}
    for document in documents:
        group = document.get('document_group')
        if group is None:
            continue
        original = document['original']
        key = (group['id'], group.get('version'))
        from working_documents import recipients
        signature = (group, document['folder'], tuple(sorted(recipients(document))))
        if key not in groups:
            groups[key] = (signature, set())
        expected, formats = groups[key]
        if signature != expected or original['media_type'] in formats:
            raise ValueError('Logical document members must have consistent identity and distinct formats')
        formats.add(original['media_type'])
