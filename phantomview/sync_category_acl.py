"""Generate the dependency-free category reader from its pinned native source."""

import argparse
import ast
import hashlib
import json
from pathlib import Path


def generate(source, metadata):
    raw = Path(source).read_bytes().replace(b'\r\n', b'\n')
    if (hashlib.sha256(raw).hexdigest() != metadata['sha256']
            or hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            != metadata['git_blob_sha']):
        raise ValueError('Category ACL source differs from the reviewed revision')
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    constants = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == '_CATEGORY_ID_RE'
                         for target in node.targets)]
    if len(constants) != 1:
        raise ValueError('Native category identifier rule is missing or ambiguous')
    selected = [constants[0], *(functions[name] for name in metadata['functions'])]
    header = ('"""Generated PhantomOrg category reader; do not edit by hand.\n\n'
              'Canonical source: ' + metadata['repository'] + '/' + metadata['path'] + '\n'
              'Reviewed revision: ' + metadata['revision'] + '\n'
              'Regenerate and verify with sync_category_acl.py. No local access grants.\n'
              '"""\nfrom __future__ import annotations\n\nimport re\nimport warnings\n'
              'from typing import Any\n\n')
    return header + '\n\n'.join(ast.get_source_segment(text, node) for node in selected) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Pinned PhantomDocs access.py source file')
    parser.add_argument('--check', action='store_true', help='Refuse drift without writing files')
    args = parser.parse_args()
    root = Path(__file__).parent
    metadata = json.loads((root / 'category_acl_source.json').read_text(encoding='utf-8'))
    generated = generate(args.source, metadata)
    output = root / 'category_acl.py'
    if args.check:
        if output.read_bytes().replace(b'\r\n', b'\n') != generated.encode('utf-8'):
            raise SystemExit('Generated category ACL reader differs from its canonical source')
        print('Category ACL source and generated reader match the reviewed revision')
    else:
        output.write_bytes(generated.encode('utf-8'))


if __name__ == '__main__':
    main()
