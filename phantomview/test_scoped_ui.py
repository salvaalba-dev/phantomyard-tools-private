"""Exercise scoped browser model behavior through Node's built-in test runner."""
from pathlib import Path
import shutil
import subprocess
import unittest


class ScopedUITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for scoped UI behavior checks')
    def test_visible_only_menus_graphs_and_search_models(self):
        subprocess.run([shutil.which('node'), '--test', 'test_scoped_ui.cjs'], capture_output=True,
                       text=True, timeout=15, check=True, cwd=Path(__file__).resolve().parent)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for scoped consultation UI checks')
    def test_scoped_consultation_lifecycle_and_response_binding(self):
        subprocess.run([shutil.which('node'), '--test', 'test_scoped_chat.cjs'], capture_output=True,
                       text=True, timeout=15, check=True, cwd=Path(__file__).resolve().parent)
