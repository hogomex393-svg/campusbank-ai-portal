"""SQLite storage for local use and pooled PostgreSQL storage for hosted use."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import sqlite3


class Record(dict):
    """Keep named columns and SQLite's positional access for existing callers."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return Record(row) if row is not None else None

    def fetchall(self):
        return [Record(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (Record(row) for row in self.cursor)


class PostgresConnection:
    def __init__(self, connection, integrity_error):
        self.connection = connection
        self.integrity_error = integrity_error

    def execute(self, statement, parameters=()):
        if statement.strip().upper() == 'BEGIN IMMEDIATE':
            # Database.connection already holds the transaction's advisory lock.
            return PostgresCursor(self.connection.cursor())
        # PortalStore owns these SQL statements. Customer text is always bound.
        statement = statement.replace('?', '%s')
        try:
            return PostgresCursor(self.connection.execute(statement, parameters))
        except self.integrity_error:
            raise sqlite3.IntegrityError('Database constraint violation') from None

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)


class Database:
    def __init__(self, location):
        self.postgres = str(location).startswith(('postgres://', 'postgresql://'))
        self.path = None if self.postgres else Path(location)
        self.current = ContextVar('campusbank_database_connection', default=None)
        self.pool = None
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self.integrity_error = psycopg.IntegrityError
            self.pool = ConnectionPool(
                conninfo=str(location), min_size=0, max_size=4,
                timeout=20, max_idle=60, reconnect_timeout=20,
                check=ConnectionPool.check_connection,
                kwargs={'row_factory': dict_row, 'connect_timeout': 15,
                        'prepare_threshold': None, 'application_name': 'campusbank'},
            )
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        current = self.current.get()
        if current is not None:
            yield current
            return
        if self.postgres:
            with self.pool.connection() as connection:
                # Preserve SQLite's serialized transactions across workers. Nested
                # store reads share this connection, including submit -> chat.
                # Transaction locks work with Neon's transaction-mode pooler.
                connection.execute('SELECT pg_advisory_xact_lock(%s)', (32412026,))
                adapter = PostgresConnection(connection, self.integrity_error)
                token = self.current.set(adapter)
                try:
                    yield adapter
                finally:
                    self.current.reset(token)
        else:
            connection = sqlite3.connect(self.path, timeout=20)
            connection.row_factory = sqlite3.Row
            token = self.current.set(connection)
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                self.current.reset(token)
                connection.close()

    def close(self):
        if self.pool is not None:
            self.pool.close()
