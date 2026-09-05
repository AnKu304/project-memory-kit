import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.project_memory.graph.sqlite_store import SQLiteGraphStore


class SQLiteLifecycleTests(unittest.TestCase):
    def test_transaction_context_commits_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteGraphStore(root, root / 'graph.sqlite')
            with store.connect() as conn:
                conn.execute('CREATE TABLE sample(value TEXT)')
                conn.execute("INSERT INTO sample VALUES ('saved')")
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')
            self.assertEqual(store.query('SELECT value FROM sample')[0]['value'], 'saved')

    def test_exception_rolls_back_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteGraphStore(root, root / 'graph.sqlite')
            with store.connect() as setup:
                setup.execute('CREATE TABLE sample(value TEXT)')
            with self.assertRaisesRegex(ValueError, 'fixture'):
                with store.connect() as conn:
                    conn.execute("INSERT INTO sample VALUES ('not saved')")
                    raise ValueError('fixture')
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')
            self.assertEqual(store.query('SELECT * FROM sample'), [])


if __name__ == '__main__':
    unittest.main()
