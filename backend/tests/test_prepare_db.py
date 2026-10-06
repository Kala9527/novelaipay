import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class PrepareDatabaseTest(unittest.TestCase):
    def test_initializes_fresh_database_and_can_run_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'fresh.db'
            env = {**os.environ, 'DATABASE_URL': f'sqlite:///{database.as_posix()}'}
            backend = Path(__file__).resolve().parents[1]
            for _ in range(2):
                result = subprocess.run([sys.executable, '-m', 'app.prepare_db'],
                                        cwd=backend, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT version_num FROM alembic_version').fetchone(), ('0013',))
                columns = {row[1] for row in connection.execute('PRAGMA table_info(upstream_groups)')}
                self.assertIn('is_private', columns)
                self.assertIn('deleted_at', columns)
