"""Private offline review rendering and genuine UI decision approval roundtrip."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from channel_identity import HumanDirectory
from projection_review import approve
from review_page import HERE, csp_hash, payload, render, write_page
from source_adapter import prepare
from test_source_adapter import snapshot
from test_view_permissions import scoped_organization


class ReviewPageTests(unittest.TestCase):
    def setUp(self):
        self.org = scoped_organization()
        self.source = snapshot()
        self.draft = prepare(self.source, HumanDirectory(self.org))

    def test_interface_contains_only_review_metadata_and_existing_nonzero_policy_labels(self):
        data = payload(self.draft, self.org, self.source)
        self.assertNotIn('category-0', [row['id'] for row in data['categories']])
        for value in ('PRIVATE_TOKEN', '/private/', 'private@example.invalid', 'NEVER_COPY'):
            self.assertNotIn(value, json.dumps(data))
        self.assertEqual(len(data['resources']), len(self.draft['resources']))

    def test_changed_sources_or_authority_reject_rendering(self):
        self.source['actors'][0]['tools'].append('drive')
        with self.assertRaises(ValueError):
            render(self.draft, self.org, self.source)

    def test_script_breakout_is_encoded_and_csp_pins_static_assets(self):
        malicious = '</script><img src=https://invalid.example onerror=alert(1)>'
        self.source['organizations'][0]['name'] = malicious
        self.draft = prepare(self.source, HumanDirectory(self.org))
        page = render(self.draft, self.org, self.source)
        self.assertNotIn(malicious, page)
        scripts = re.findall(r'<script(?: [^>]*)?>(.*?)</script>', page, re.S)
        self.assertEqual(len(scripts), 2)
        self.assertEqual(json.loads(scripts[0])['resources'][next(
            index for index, row in enumerate(json.loads(scripts[0])['resources']) if row['kind'] == 'organization')]['data']['name'], malicious)
        self.assertIn(csp_hash((HERE / 'review_ui.js').read_text(encoding='utf-8')), page)
        self.assertIn(csp_hash((HERE / 'review_ui.css').read_text(encoding='utf-8')), page)
        self.assertIn("connect-src &#x27;none&#x27;", page)
        self.assertNotIn('unsafe-inline', page)

    def test_output_is_exclusive_private_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'review.html'
            write_page(path, self.draft, self.org, self.source)
            self.assertIn('LOCAL OPERATOR REVIEW', path.read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):
                write_page(path, self.draft, self.org, self.source)
            self.assertFalse((Path(root) / 'active.json').exists())
        with self.assertRaises(ValueError):
            write_page('relative.html', self.draft, self.org, self.source)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for genuine UI model integration')
    def test_review_model_behavior_with_node_builtin_runner(self):
        subprocess.run([shutil.which('node'), '--test', 'test_review_ui.cjs'],
                       capture_output=True, text=True, timeout=15, check=True, cwd=HERE)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for genuine UI model integration')
    def test_ui_export_is_accepted_by_independent_approval_and_stale_sources_are_rejected(self):
        script = """const {ReviewModel}=require('./review_ui.js');
let input='';process.stdin.on('data',chunk=>input+=chunk);process.stdin.on('end',()=>{
const model=new ReviewModel(JSON.parse(input));for(const id of model.rows.keys())model.select(id,true);
model.apply({category:'category-1',scope:'example',secret:false},true);
process.stdout.write(JSON.stringify(model.export()));});"""
        result = subprocess.run([shutil.which('node'), '-e', script], input=json.dumps(payload(self.draft, self.org, self.source)),
                                capture_output=True, text=True, timeout=15, check=True, cwd=HERE)
        decisions = json.loads(result.stdout)
        reviewer = next(iter(HumanDirectory(self.org).scope.policy['humans']))
        bundle = approve(self.draft, decisions, self.org, lambda: self.source, reviewer=reviewer)
        self.assertEqual(len(bundle['catalog']['resources']), len(self.draft['resources']))
        self.source['actors'] = []
        with self.assertRaises(ValueError):
            approve(self.draft, decisions, self.org, lambda: self.source, reviewer=reviewer)


if __name__ == '__main__':
    unittest.main()
