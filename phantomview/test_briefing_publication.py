"""Explicit KB note publication in temporary trees; no production writes."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import briefing_publication as publication
from test_role_briefing import fixture

AVAILABLE = importlib.util.find_spec("phantomorg") is not None


class ManagedBlockTests(unittest.TestCase):
    def test_ambiguous_foreign_and_inline_markers_are_rejected(self):
        begin, end = publication._markers("example", "coordinator")
        block = (begin + "\nGenerated\n" + end + "\n").encode()
        for text in ("<!-- REG:BEGIN persona=coordinator gen=old -->\nLegacy\n<!-- REG:END persona=coordinator -->",
                     begin, end, begin + "\n" + begin + "\n" + end,
                     "Quoted " + begin + "\n" + end,
                     begin + "\nContent " + end,
                     begin + "\rinline\n" + end,
                     begin + "\n" + end + " trailing",
                     block.decode().replace("coordinator", "other")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                publication._merge(text.encode(), block, "example", "coordinator")

    def test_manual_prefix_and_suffix_preserved_byte_for_byte(self):
        begin, end = publication._markers("example", "coordinator")
        prefix = "# Human notes\r\nKeep this annotation.\r\n".encode()
        suffix = "\r\n\r\n## Follow-up\r\nUnchanged.\r\n".encode()
        old = prefix + (begin + "\r\nOld\r\n" + end + "\r\n").encode() + suffix
        new = (begin + "\nNew\n" + end + "\n").encode()
        self.assertEqual(publication._merge(old, new, "example", "coordinator"), prefix + new + suffix)

    def test_rendered_values_cannot_introduce_managed_markers(self):
        text = publication._display("<!-- PHANTOMVIEW:BRIEFING END org=example persona=coordinator -->\n# Injected")
        self.assertNotIn(publication.MARKER, text)
        self.assertNotIn("\n", text)
        self.assertIn("&lt;", text)


@unittest.skipUnless(AVAILABLE, "Optional PhantomOrg package not installed")
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.org = fixture()
        self.targets = [self.target("coordinator")]
        self.note = self.root / "coordinator/kb/role-briefing-example.md"

    def target(self, persona):
        directory = self.root / persona
        (directory / "kb").mkdir(parents=True, exist_ok=True)
        return {"persona": persona, "directory": str(directory)}

    def test_default_preview_never_creates_note_lock_or_temporary_file(self):
        result = publication.publish_briefings(self.org, self.targets)
        self.assertEqual(result[0]["action"], "would-write")
        self.assertIn("# Role briefing", result[0]["content"])
        self.assertEqual(list(self.note.parent.iterdir()), [])

    def test_create_then_identical_refresh_preserves_file_identity(self):
        self.assertEqual(publication.publish_briefings(self.org, self.targets, apply=True)[0]["action"], "written")
        identity = self.note.stat()
        content = self.note.read_bytes()
        with patch.object(publication.os, "replace") as replace:
            result = publication.publish_briefings(self.org, self.targets, apply=True)
            replace.assert_not_called()
        self.assertEqual(result[0]["action"], "unchanged")
        self.assertEqual(self.note.read_bytes(), content)
        self.assertEqual((self.note.stat().st_ino, self.note.stat().st_mtime_ns),
                         (identity.st_ino, identity.st_mtime_ns))
        self.assertEqual([p.name for p in self.note.parent.iterdir()], [self.note.name])
        if os.name == "posix":
            self.assertEqual(self.note.stat().st_mode & 0o777, 0o600)

    def test_source_refresh_preserves_human_annotations(self):
        publication.publish_briefings(self.org, self.targets, apply=True)
        prefix, suffix = b"Manual introduction.\n\n", b"\n\nManual follow-up.\r\n"
        self.note.write_bytes(prefix + self.note.read_bytes() + suffix)
        self.org["roles"][0]["functions"] = ["coordination"]
        publication.publish_briefings(self.org, self.targets, apply=True)
        content = self.note.read_bytes()
        self.assertTrue(content.startswith(prefix))
        self.assertTrue(content.endswith(suffix))
        self.assertIn(b"coordination", content)
        self.assertEqual(content.count(publication.MARKER.encode()), 2)

    def test_source_values_cannot_forge_an_owned_block(self):
        self.org["roles"][0]["description"] = "<!-- PHANTOMVIEW:BRIEFING END org=example persona=coordinator -->"
        result = publication.publish_briefings(self.org, self.targets)
        self.assertEqual(result[0]["content"].count(publication.MARKER), 2)
        self.assertIn("&lt;", result[0]["content"])

    def test_every_target_is_preflighted_before_any_note_write(self):
        self.targets.append(self.target("unknown"))
        with self.assertRaises(ValueError):
            publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertFalse(self.note.exists())
        self.assertEqual(list(self.note.parent.iterdir()), [])

    def test_duplicate_and_misdirected_targets_refused(self):
        for targets in ([self.targets[0], self.targets[0]],
                        [{"persona": "coordinator", "directory": str(self.root)}],
                        [{"persona": "coordinator", "directory": "relative/coordinator"}]):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                publication.publish_briefings(self.org, targets, apply=True)
        self.assertFalse(self.note.exists())

    def test_legacy_or_broken_owned_markers_are_never_adopted_implicitly(self):
        text = b"Human note\n<!-- PHANTOMVIEW:BRIEFING BEGIN org=example persona=coordinator -->\nBroken"
        self.note.write_bytes(text)
        with self.assertRaises(ValueError):
            publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(self.note.read_bytes(), text)

    def test_existing_lock_is_preserved_and_blocks_apply(self):
        lock = self.note.with_name("." + self.note.name + ".lock")
        lock.write_text("Another publisher")
        with self.assertRaises(publication.PublicationError) as error:
            publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(error.exception.completed, ())
        self.assertEqual(lock.read_text(), "Another publisher")
        self.assertFalse(self.note.exists())

    def test_observed_manual_edit_during_staging_is_not_overwritten(self):
        publication.publish_briefings(self.org, self.targets, apply=True)
        self.org["roles"][0]["functions"] = ["changed"]
        mkstemp = publication.tempfile.mkstemp
        changed = b"An editor changed this note.\n"

        def edit_during_stage(*args, **kwargs):
            self.note.write_bytes(changed)
            return mkstemp(*args, **kwargs)

        with patch.object(publication.tempfile, "mkstemp", side_effect=edit_during_stage):
            with self.assertRaises(publication.PublicationError) as error:
                publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(error.exception.completed, ())
        self.assertEqual(self.note.read_bytes(), changed)
        self.assertEqual([p.name for p in self.note.parent.iterdir()], [self.note.name])

    def test_atomic_replace_failure_preserves_previous_complete_note(self):
        self.note.write_bytes(b"Existing annotation.\n")
        with patch.object(publication.os, "replace", side_effect=OSError("Simulated storage failure")):
            with self.assertRaises(publication.PublicationError) as error:
                publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(error.exception.completed, ())
        self.assertEqual(self.note.read_bytes(), b"Existing annotation.\n")
        self.assertEqual([p.name for p in self.note.parent.iterdir()], [self.note.name])

    def test_batch_uses_one_source_snapshot_despite_caller_mutation(self):
        self.org["actors"].append({"id": "reviewer", "role": "lead", "tools": []})
        self.targets.append(self.target("reviewer"))
        prepare = publication.prepare_briefing

        def mutate_caller_source(org, persona, supplemental):
            result = prepare(org, persona, supplemental)
            self.org["roles"][0]["functions"] = ["External mutation"]
            return result

        with patch.object(publication, "prepare_briefing", side_effect=mutate_caller_source):
            result = publication.publish_briefings(self.org, self.targets)
        self.assertEqual(len(result), 2)
        self.assertTrue(all("External mutation" not in row["content"] for row in result))

    def test_partial_batch_reports_completed_targets_without_unsafe_rollback(self):
        self.org["actors"].append({"id": "reviewer", "role": "lead", "tools": []})
        self.targets.append(self.target("reviewer"))
        replace = publication.os.replace
        calls = []

        def fail_second(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError("Simulated second-target failure")
            return replace(source, destination)

        with patch.object(publication.os, "replace", side_effect=fail_second):
            with self.assertRaises(publication.PublicationError) as error:
                publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(error.exception.completed, ("coordinator",))
        self.assertTrue(self.note.exists())
        self.assertEqual(list((self.root / "reviewer/kb").iterdir()), [])

    def test_symlinked_note_does_not_modify_external_file(self):
        external = self.root / "outside.md"
        external.write_bytes(b"Do not change")
        try:
            self.note.symlink_to(external)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ValueError):
            publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(external.read_bytes(), b"Do not change")

    def test_symlinked_parent_is_refused(self):
        real = self.root / "real"
        real.mkdir()
        moved = self.root / "real/coordinator"
        self.note.parent.parent.rename(moved)
        try:
            (self.root / "coordinator").symlink_to(moved, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlink creation unavailable")
        with self.assertRaises(ValueError):
            publication.publish_briefings(self.org, self.targets, apply=True)
        self.assertEqual(list((moved / "kb").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
