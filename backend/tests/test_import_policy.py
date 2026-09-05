"""Startup import policy: when does config.json get imported into the database?"""
import os
import sys
import json
import time
import tempfile
import unittest

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db, engine  # noqa: E402
from models import Base, GroupDB  # noqa: E402
import cleanup  # noqa: E402


class TestImportPolicy(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        init_db()
        self.db = SessionLocal()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self._orig = cleanup.CONFIG_PATH
        cleanup.CONFIG_PATH = self.tmp.name

    def tearDown(self):
        cleanup.CONFIG_PATH = self._orig
        self.db.close()
        os.unlink(self.tmp.name)

    def _write(self, data, mtime=None):
        with open(self.tmp.name, "w") as f:
            json.dump(data, f)
        if mtime is not None:
            os.utime(self.tmp.name, (mtime, mtime))
        return data

    def test_empty_database_bootstraps_from_file(self):
        data = self._write({"groups": [{"id": "g1", "name": "G", "nodes": []}], "exported_at": time.time()})
        self.assertTrue(cleanup.should_import_config(self.db, data))

    def test_fresh_export_is_not_reimported(self):
        self.db.add(GroupDB(id="g1", name="G")); self.db.commit()
        now = time.time()
        data = self._write({"groups": [{"id": "g1", "name": "G", "nodes": []}], "exported_at": now}, mtime=now)
        self.assertFalse(cleanup.should_import_config(self.db, data))

    def test_file_edited_after_export_is_imported(self):
        self.db.add(GroupDB(id="g1", name="G")); self.db.commit()
        exported = time.time() - 3600
        data = self._write({"groups": [{"id": "g1", "name": "G", "nodes": []}], "exported_at": exported}, mtime=exported + 600)
        self.assertTrue(cleanup.should_import_config(self.db, data))

    def test_legacy_file_without_exported_at_is_imported_once(self):
        self.db.add(GroupDB(id="g1", name="G")); self.db.commit()
        data = self._write({"groups": [{"id": "g1", "name": "G", "nodes": []}]})
        self.assertTrue(cleanup.should_import_config(self.db, data))

    def test_explicit_flag_forces_import(self):
        self.db.add(GroupDB(id="g1", name="G")); self.db.commit()
        now = time.time()
        data = self._write({"import": True, "groups": [], "exported_at": now}, mtime=now)
        self.assertTrue(cleanup.should_import_config(self.db, data))

    def test_sync_imports_then_exports(self):
        """End to end: legacy file on disk, empty DB -> imported, file rewritten with exported_at."""
        import utils
        orig_utils = utils.CONFIG_PATH
        utils.CONFIG_PATH = self.tmp.name
        try:
            self._write({"groups": [{"id": "g1", "name": "Lab", "nodes": [{"id": "n1", "name": "r", "ip": "10.0.0.1"}]}]})
            cleanup.sync_with_config(self.db)
            self.assertEqual(self.db.query(GroupDB).count(), 1)
            with open(self.tmp.name) as f:
                written = json.load(f)
            self.assertIn("exported_at", written)
            self.assertNotIn("import", written)
            # Second start: file now mirrors the DB, no import
            self.assertFalse(cleanup.should_import_config(self.db, written))
        finally:
            utils.CONFIG_PATH = orig_utils


if __name__ == "__main__":
    unittest.main()
