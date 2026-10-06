"""Transactional persistence shared by requests and the background worker."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .catalog import CATALOG

TABLES = {"targets", "skills", "sessions", "evidence", "plans", "operations", "settings"}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class GrowthRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def seed(self):
        with self.transaction() as connection:
            for item in CATALOG:
                self.save("skills", item["id"], item, connection=connection)
            connection.execute("INSERT OR IGNORE INTO growth_settings VALUES ('default', ?)", (dump({"dailyMinutes": 120}),))

    def all(self, table, connection=None):
        self._table(table)
        if connection is None:
            with self.transaction() as conn:
                return self.all(table, conn)
        return [json.loads(row["payload_json"]) for row in connection.execute(f"SELECT payload_json FROM growth_{table} ORDER BY rowid")]

    def get(self, table, identifier, connection=None):
        self._table(table)
        if connection is None:
            with self.transaction() as conn:
                return self.get(table, identifier, conn)
        row = connection.execute(f"SELECT payload_json FROM growth_{table} WHERE id=?", (identifier,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def save(self, table, identifier, value, *, connection=None):
        self._table(table)
        if connection is None:
            with self.transaction() as conn:
                return self.save(table, identifier, value, connection=conn)
        fields = {"id": identifier, "payload_json": dump(value)}
        if table not in {"skills", "settings"}:
            fields["updated_at" if table != "evidence" else "created_at"] = value.get("updatedAt", value.get("createdAt", ""))
        if table == "targets":
            fields.update(source=value["source"], source_id=value["sourceId"])
        if table == "evidence":
            fields.update(skill_id=value["skillId"], session_id=value.get("sessionId"), question_id=value.get("questionId"))
        if table == "operations":
            fields["request_key"] = value["requestKey"]
        names = ",".join(fields)
        updates = ",".join(f"{key}=excluded.{key}" for key in fields if key != "id")
        connection.execute(f"INSERT INTO growth_{table} ({names}) VALUES ({','.join('?' for _ in fields)}) ON CONFLICT(id) DO UPDATE SET {updates}", tuple(fields.values()))

    @staticmethod
    def _table(table):
        if table not in TABLES:
            raise ValueError("未知成长记录类型")
