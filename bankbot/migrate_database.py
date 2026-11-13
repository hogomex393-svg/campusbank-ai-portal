"""Atomically import a SQLite portal snapshot into an empty PostgreSQL database."""
import argparse
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3
import tempfile

from .config import Settings
from .portal_store import PortalStore, now


TABLES = (
    'users', 'sessions', 'chats', 'messages', 'sends', 'requests',
    'request_submissions', 'request_events', 'answer_feedback',
    'request_revisions', 'tickets', 'staff_invites',
)
IDENTITY_TABLES = ('messages', 'request_events', 'request_revisions')


def import_sqlite(source, destination_url):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('The source SQLite file does not exist.')
    if not destination_url.startswith(('postgres://', 'postgresql://')):
        raise ValueError('The destination must be PostgreSQL.')
    # SQLite's backup API includes committed WAL content and leaves the source intact.
    with tempfile.TemporaryDirectory(prefix='campusbank-import-') as folder:
        snapshot = Path(folder) / 'portal.sqlite3'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(snapshot)) as backup:
                original.backup(backup)
        upgraded = PortalStore(snapshot)
        records = {}
        columns = {}
        with upgraded.db() as database:
            for table in TABLES:
                columns[table] = [row['name'] for row in database.execute('PRAGMA table_info(' + table + ')')]
                if not all(re.fullmatch(r'[a-z_]+', name) for name in columns[table]):
                    raise ValueError('Unexpected source column name.')
                records[table] = [dict(row) for row in database.execute('SELECT * FROM ' + table)]
                records[table].sort(key=lambda row: json.dumps(row, sort_keys=True))
        fingerprint = sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        counts = {table: len(rows) for table, rows in records.items()}
        destination = PortalStore(destination_url)
        try:
            with destination.db() as database:
                database.execute('CREATE TABLE IF NOT EXISTS portal_imports '
                    '(source_fingerprint TEXT PRIMARY KEY, completed_at TEXT NOT NULL, row_counts TEXT NOT NULL)')
                completed = database.execute('SELECT row_counts FROM portal_imports WHERE source_fingerprint=?',
                    (fingerprint,)).fetchone()
                if completed:
                    return {'status': 'already_imported', 'rows': json.loads(completed['row_counts'])}
                for table in TABLES:
                    if database.execute('SELECT COUNT(*) AS count FROM ' + table).fetchone()['count']:
                        raise ValueError('Destination contains records. Import requires an empty portal database.')
                for table in TABLES:
                    names = ','.join('"' + name + '"' for name in columns[table])
                    placeholders = ','.join('?' for name in columns[table])
                    statement = f'INSERT INTO {table} ({names}) VALUES ({placeholders})'
                    if records[table]:
                        database.executemany(statement,
                            [tuple(row[name] for name in columns[table]) for row in records[table]])
                for table in IDENTITY_TABLES:
                    database.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE(MAX(id), 0) + 1, false) FROM {table}")
                database.execute('INSERT INTO portal_imports VALUES (?,?,?)',
                    (fingerprint, now(), json.dumps(counts)))
        finally:
            destination.close()
        return {'status': 'imported', 'rows': counts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args(argv)
    destination = Settings.load().database_url
    if not destination:
        parser.error('Set DATABASE_URL privately before importing.')
    try:
        result = import_sqlite(args.source, destination)
    except ValueError as error:
        print(str(error))
        return 1
    except Exception:
        print('Database import failed. The transaction was rolled back. Connection details are hidden.')
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
