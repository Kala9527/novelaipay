import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class GroupMigrationTest(unittest.TestCase):
    def test_upgrade_existing_sqlite_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'legacy.db'
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript('''
                    CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
                    INSERT INTO alembic_version VALUES ('0007');
                    CREATE TABLE upstream_accounts (id INTEGER PRIMARY KEY, name VARCHAR(80));
                    CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320));
                    INSERT INTO upstream_accounts VALUES (7, 'legacy');
                    CREATE TABLE model_mappings (
                        id INTEGER PRIMARY KEY, public_name VARCHAR(100) UNIQUE,
                        upstream_model VARCHAR(150), upstream_account_id INTEGER,
                        enabled BOOLEAN, max_concurrency INTEGER, revision INTEGER);
                    INSERT INTO model_mappings VALUES (5, 'art', 'image', 7, 1, 2, 1);
                    CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER);
                    INSERT INTO api_keys VALUES (3, 1);
                    CREATE TABLE generation_jobs (id VARCHAR(36) PRIMARY KEY, user_id INTEGER);
                    CREATE TABLE wallet_ledger (id INTEGER PRIMARY KEY);
                    CREATE TABLE usage_records (id INTEGER PRIMARY KEY);
                ''')
            env = {**os.environ,
                   'DATABASE_URL': f'sqlite:///{database.as_posix()}',
                   'APP_SECRET_KEY': 'test-session-secret-with-enough-length',
                   'UPSTREAM_KEY_ENCRYPTION_KEY': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
                   'PAYMENT_WEBHOOK_SECRET': 'test-payment-secret'}
            backend = Path(__file__).resolve().parents[1]
            result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                                    cwd=backend, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('SELECT group_id FROM api_keys WHERE id = 3').fetchone(), (1,))
                self.assertEqual(connection.execute('SELECT group_id FROM model_mappings WHERE id = 5').fetchone(), (1,))
                self.assertEqual(connection.execute('SELECT account_id FROM model_routes WHERE model_mapping_id = 5').fetchone(), (7,))
                self.assertEqual(connection.execute('SELECT version_num FROM alembic_version').fetchone(), ('0017',))
                self.assertIn('proxy_id', {row[1] for row in connection.execute('PRAGMA table_info(upstream_accounts)')})
                self.assertIn('encrypted_code', {row[1] for row in connection.execute('PRAGMA table_info(redemption_codes)')})
                self.assertEqual(connection.execute('SELECT is_private FROM upstream_groups WHERE id = 1').fetchone(), (0,))
                self.assertEqual(connection.execute('SELECT deleted_at FROM upstream_groups WHERE id = 1').fetchone(), (None,))
                connection.execute("INSERT INTO upstream_groups (id, name, max_concurrency, enabled) VALUES (2, 'second', 10, 1)")
                connection.execute("INSERT INTO model_mappings (id, public_name, upstream_model, upstream_account_id, enabled, max_concurrency, revision, group_id) VALUES (6, 'art', 'image', 7, 1, 2, 1, 2)")
