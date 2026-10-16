"""Generate a private offline classification interface; never publishes access."""
import argparse
import base64
import hashlib
import html
import os
from pathlib import Path

from channel_identity import HumanDirectory
from projection_review import read_json, root_path
from resource_review import revision
from scoped_backend import MAX_SCAN_BYTES
from source_adapter import encode, prepare

HERE = Path(__file__).resolve().parent


def payload(draft, org, snapshot):
    directory = HumanDirectory(org)
    if prepare(snapshot, directory) != draft:
        raise ValueError('Review page requires an exact current draft and authoritative organization')
    records = {row['id']: row['data'] for row in draft['records']}
    definitions = directory.scope.policy['view_access']['scope_definitions']
    categories = org['policies']['security_categories']
    return {'organization': org['organization'].get('display_name') or org['organization'].get('name') or draft['organization'],
            'draft_revision': revision(draft), 'organization_revision': revision(org),
            'categories': [{'id': key, 'label': key} for key in sorted(categories) if key != 'category-0'],
            'scopes': [{'id': key, 'kind': value['kind'], 'label': value.get('label') or key}
                       for key, value in sorted(definitions.items())],
            'resources': [row | {'data': records[row['id']]} for row in draft['resources']],
            'unsupported': draft['unsupported'], 'omitted_count': len(draft['omitted'])}


def csp_hash(text):
    return 'sha256-' + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


def render(draft, org, snapshot):
    data = encode(payload(draft, org, snapshot)).decode().replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    script = (HERE / 'review_ui.js').read_text(encoding='utf-8')
    style = (HERE / 'review_ui.css').read_text(encoding='utf-8')
    policy = (f"default-src 'none'; script-src '{csp_hash(script)}'; style-src '{csp_hash(style)}'; "
              "connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">
<meta name="referrer" content="no-referrer"><title>PhantomView · Resource review</title><style>{style}</style></head>
<body><header><div><strong>PHANTOMVIEW</strong><p id="organization"></p></div><span class="badge">LOCAL OPERATOR REVIEW</span></header>
<main><h1>Review access to current sources</h1><p class="intro">Select records, inspect their contents and dependencies, then assign an existing category and scope. Exporting decisions does not approve or publish access.</p>
<p id="revision" class="subtle"></p><div class="layout"><section class="panel" aria-label="Draft records">
<div class="tools"><input id="search" type="search" aria-label="Search draft records" placeholder="Search all draft metadata"><select id="kind" aria-label="Resource type"></select></div>
<div class="tools"><button id="select-visible">Select visible</button><button id="clear">Clear selection</button><button id="dependencies">Include source dependencies</button></div>
<p id="visible-count" class="subtle"></p><div class="table-wrap"><table><thead><tr><th>Select</th><th>Record / source</th><th>Type</th><th>Classification</th></tr></thead><tbody id="records"></tbody></table></div>
<div class="detail"><h2 id="detail-title">Inspect a record</h2><pre id="detail">Choose a record title to read its adapted data and source dependencies.</pre></div></section>
<aside class="panel" aria-label="Classification decisions"><h2>Classify selection</h2><p class="subtle">Categories are exact labels. Category zero is a human privilege and cannot classify information.</p>
<label>Information category<select id="category"></select></label><label>Access scope<select id="scope"></select></label>
<label>Secret review<select id="secret"><option value="">Choose explicitly</option><option value="no">Not secret</option><option value="yes">Secret</option></select></label>
<label class="confirm"><input id="reviewed" type="checkbox">I reviewed the current contents of every selected record.</label><button id="apply" class="primary">Apply to selection</button>
<p id="summary" role="status"></p><p id="message" role="alert"></p><button id="download" disabled>Download review decisions</button>
<p class="subtle">Changes stay in this page until downloaded. Approval rechecks sources, authority and dependencies independently.</p></aside></div>
<footer id="coverage"></footer></main><script id="review-data" type="application/json">{data}</script><script>{script}</script></body></html>'''
    if len(document.encode()) > MAX_SCAN_BYTES:
        raise ValueError('Review interface exceeds bounded output size')
    return document


def write_page(path, draft, org, snapshot):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('An absolute private output path is required')
    root_path(path.parent)
    raw = render(draft, org, snapshot).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description='Create a private offline PhantomView classification review')
    parser.add_argument('--draft', required=True)
    parser.add_argument('--organization', required=True, help='Trusted PhantomOrg JSON source')
    parser.add_argument('--snapshot', required=True, help='Current trusted collector JSON export')
    parser.add_argument('--output', required=True, help='Absolute new private HTML path')
    args = parser.parse_args()
    snapshot = read_json(Path(args.snapshot))
    write_page(args.output, read_json(Path(args.draft)), read_json(Path(args.organization)), snapshot.get('snapshot', snapshot))


if __name__ == '__main__':
    main()
