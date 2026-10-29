"""Download-only workbook delivery preserves bytes, reviewed metadata and ACL."""
import hashlib
from io import BytesIO
import json
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from original_documents import EXCEL_MEDIA, EXCEL_TYPES_NS, MAX_EXCEL_TYPES_BYTES, descriptor, serve, validate_descriptor
import test_original_documents as originals
import test_working_documents as working
from working_documents import bindings, validated


def workbook(extra=None):
    """A synthetic package; no real workbook or organizational data is used."""
    output = BytesIO()
    with ZipFile(output, 'w') as package:
        for name, value in {
            '[Content_Types].xml': ('<Types xmlns="' + EXCEL_TYPES_NS + '">'
                '<Override PartName="/xl/workbook.xml" ContentType="' + EXCEL_MEDIA + '.main+xml"/>'
                '</Types>'), '_rels/.rels': '<Relationships/>',
            'xl/workbook.xml': '<workbook/>',
            'xl/worksheets/sheet1.xml': '<worksheet><f>1+2</f><v>3</v></worksheet>',
            **(extra or {}),
        }.items():
            package.writestr(name, value)
    return output.getvalue()


def metadata(raw):
    return {'contentHash': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}


class ExcelMetadataTests(unittest.TestCase):
    def test_reviewed_workbook_keeps_exact_digest_size_and_no_invented_version(self):
        raw = workbook()
        value = descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Project application'})
        self.assertEqual(value['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(value['size_bytes'], len(raw))
        self.assertTrue(value['filename'].endswith('.xlsx'))
        self.assertNotIn('version', value)
        self.assertNotIn('<f>', json.dumps(value))

    def test_arbitrary_zip_truncated_file_and_macro_package_are_rejected(self):
        empty = BytesIO()
        with ZipFile(empty, 'w') as package:
            package.writestr('unrelated.txt', 'unrelated')
        for raw in (empty.getvalue(), workbook()[:-12], b'not a workbook',
                    workbook({'xl/vbaProject.bin': b'macro'})):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})

    def test_package_check_reads_only_content_types_and_never_cells(self):
        raw = workbook()
        original_open = ZipFile.open
        opened = []
        def open_types(package, name, *args, **kwargs):
            self.assertEqual(name, '[Content_Types].xml')
            opened.append(name)
            return original_open(package, name, *args, **kwargs)
        with patch.object(ZipFile, 'open', open_types):
            descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})
        self.assertEqual(opened, ['[Content_Types].xml'])

    def test_excel_four_macro_sheets_are_rejected_even_without_vba(self):
        for name in ('xl/macrosheets/sheet1.xml', 'xl/intlmacrosheets/sheet1.xml',
                     'XL/MACROSHEETS/sheet1.xml', 'xl\\macrosheets\\sheet1.xml'):
            raw = workbook({name: '<worksheet/>'})
            with self.subTest(name=name), self.assertRaises(ValueError):
                descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})

    def test_macro_content_types_are_rejected_without_a_named_macro_part(self):
        for media in ('application/vnd.ms-excel.sheet.macroEnabled.main+xml',
                      'application/vnd.ms-excel.macrosheet+xml',
                      'application/vnd.ms-excel.intlmacrosheet+xml',
                      'application/vnd.ms-office.vbaProject',
                      'application/vnd.ms-excel.sheet.macroEnab&#108;ed.main+xml'):
            types = ('<Types xmlns="' + EXCEL_TYPES_NS + '">'
                     '<Override PartName="/xl/workbook.xml" ContentType="' + EXCEL_MEDIA + '.main+xml"/>'
                     '<Override PartName="/xl/renamed.xml" ContentType="' + media + '"/></Types>')
            raw = workbook({'[Content_Types].xml': types})
            with self.subTest(media=media), self.assertRaises(ValueError):
                descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})

    def test_unreviewable_content_types_fail_closed(self):
        for types in ('<Types/>', '<invalid', '<!DOCTYPE Types [<!ENTITY x "value">]><Types/>',
                      '<Types>' + ' ' * MAX_EXCEL_TYPES_BYTES + '</Types>',
                      b'\xff\xfe<\x00T\x00y\x00p\x00e\x00s\x00/\x00>\x00',
                      '<Types xmlns="' + EXCEL_TYPES_NS + '"/>'):
            raw = workbook({'[Content_Types].xml': types})
            with self.subTest(size=len(types)), self.assertRaises(ValueError):
                descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})

    def test_filename_media_mismatch_and_oversize_are_rejected(self):
        raw = workbook()
        value = descriptor(raw, metadata(raw), EXCEL_MEDIA, {'title': 'Application'})
        for change in ({'filename': 'application.html'}, {'size_bytes': 32 * 1024 * 1024 + 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_descriptor(value | change)


class ExcelDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = originals.OriginalDeliveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.raw = workbook()
        self.excel = descriptor(self.raw, metadata(self.raw), EXCEL_MEDIA, {'title': 'Application'})
        self.path = self.fixture.root / self.excel['sha256']
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)
        self.fixture.replace(self.fixture.ident, {'source': 'reviewed-working-document', 'original': self.excel})

    def test_workbook_is_attachment_with_unchanged_formulas_and_private_headers(self):
        f = self.fixture
        serve(f.handler, f.backend, f.store, f.ident)
        self.assertEqual(f.handler.wfile.getvalue(), self.raw)
        headers = dict(call.args for call in f.handler.send_header.call_args_list)
        self.assertEqual(headers['Content-Type'], EXCEL_MEDIA)
        self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(headers['Cache-Control'], 'no-store, private')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_expired_session_and_denied_workbook_never_open_bytes(self):
        f = self.fixture
        store = Mock()
        serve(f.handler, f.backend, store, f.hidden)
        f.gate.recipients.clear()
        with self.assertRaises(ValueError):
            serve(f.handler, f.backend, store, f.ident)
        store.read.assert_not_called()

    def test_acl_change_during_read_and_tampered_copy_release_no_workbook(self):
        f = self.fixture
        self.path.write_bytes(b'x' * len(self.raw))
        with self.assertRaises(ValueError):
            serve(f.handler, f.backend, f.store, f.ident)
        f.handler.send_response.assert_not_called()
        store = Mock()
        def read(_):
            f.gate.recipients.clear()
            return self.raw
        store.read.side_effect = read
        with self.assertRaises(ValueError):
            serve(f.handler, f.backend, store, f.ident)
        self.assertEqual(f.handler.wfile.getvalue(), b'')
        f.handler.send_response.assert_not_called()


class ExcelCollectionTests(unittest.TestCase):
    def test_collection_publishes_metadata_only_and_requires_explicit_opt_in(self):
        fixture = working.WorkingDocumentTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        raw = workbook()
        fixture.path.write_bytes(raw)
        fixture.node.update(metadata(raw))
        fixture.binding.update(format=EXCEL_MEDIA, sha256=metadata(raw)['contentHash'],
                               original=True, original_only=True,
                               display={'title': 'Project application'})
        value = fixture.collect()[fixture.node['urn']]
        self.assertEqual(value['content'], 'Project application')
        self.assertEqual(value['format'], EXCEL_MEDIA)
        self.assertEqual(value['original']['sha256'], metadata(raw)['contentHash'])
        self.assertNotIn('worksheet', json.dumps(value))
        self.assertEqual(validated(value), value)
        from document_refresh import _matrix
        matrix = {'schema_version': 1, 'organization': 'example', 'documents': [{
            'urn': 'urn:example:doc:projects/application', 'actor': fixture.actor['id'],
            'category': 'category-2', 'format': EXCEL_MEDIA, 'original_only': True,
            'display': {'title': 'Project application'},
        }]}
        self.assertEqual(len(_matrix(matrix, 'example')), 1)
        for key in ('original', 'original_only', 'display'):
            incomplete = {k: v for k, v in fixture.binding.items() if k != key}
            with self.subTest(key=key), self.assertRaises(ValueError):
                bindings([incomplete])
        with self.assertRaises(ValueError):
            validated(value | {'original': value['original'] | {'media_type': 'application/pdf',
                                                               'filename': 'application.pdf'}})
