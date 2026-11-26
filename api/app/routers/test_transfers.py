"""Large files sent in parts (data.upload_part / finish_transfer) on a fake table.

Run from api/:  python -m unittest app.routers.test_transfers
"""
import gzip
import types
import unittest
import uuid
from unittest import mock

from fastapi import HTTPException

from app.routers import data


def ctx(org):
    return types.SimpleNamespace(org_id=org, role="owner", user=types.SimpleNamespace(id=str(uuid.uuid4())),
                                 can=lambda perm: True)


class Parts:
    """upload_parts as a dict: (transfer_id, seq) -> (org_id, data)."""

    def __init__(self):
        self.rows: dict[tuple, tuple] = {}

    async def execute(self, sql, *args):
        if sql.lstrip().startswith("insert into upload_parts"):
            tid, seq, org, blob = args
            if (tid, seq) not in self.rows or self.rows[(tid, seq)][0] == org:
                self.rows[(tid, seq)] = (org, blob)
        elif "where transfer_id=$1 and org_id=$2" in sql:
            for k in [k for k, v in self.rows.items() if k[0] == args[0] and v[0] == args[1]]:
                del self.rows[k]

    async def fetch(self, sql, tid, org):
        return [{"seq": k[1], "data": v[1]} for k, v in sorted(self.rows.items()) if k[0] == tid and v[0] == org]


class Request:
    def __init__(self, body):
        self._body = body

    async def body(self):
        return self._body


class Transfers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.parts = Parts()
        self.created = []

        async def create(c, name, blob, **kw):
            self.created.append((name, blob, kw))
            return {"id": "u1"}

        self.patches = [mock.patch.object(data.db, "execute", self.parts.execute),
                        mock.patch.object(data.db, "fetch", self.parts.fetch),
                        mock.patch.object(data, "_create_upload", create)]
        for p in self.patches:
            p.start()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def send(self, c, tid, blob, size):
        chunks = [blob[i:i + size] for i in range(0, len(blob), size)]
        for i, ch in enumerate(chunks):
            await data.upload_part(tid, i, Request(ch), c)
        return len(chunks)

    async def test_gzipped_parts_become_the_original_file(self):
        original = ("Invoice,Item,Qty\n" + "1,Zinger,2\n" * 5000).encode()
        c, tid = ctx("org-a"), uuid.uuid4()
        n = await self.send(c, tid, gzip.compress(original), 40)
        self.assertGreater(n, 2)
        res = await data.finish_transfer(tid, data.FinishIn(file_name="sales.csv", parts=n), c)
        self.assertEqual(res, {"id": "u1"})
        self.assertEqual(self.created[0][:2], ("sales.csv", original))
        self.assertEqual(self.parts.rows, {})  # parts are gone once joined

    async def test_a_missing_part_is_reported_not_guessed(self):
        c, tid = ctx("org-a"), uuid.uuid4()
        await data.upload_part(tid, 0, Request(b"abc"), c)
        await data.upload_part(tid, 2, Request(b"ghi"), c)
        with self.assertRaises(HTTPException) as cm:
            await data.finish_transfer(tid, data.FinishIn(file_name="x.csv", parts=3), c)
        self.assertEqual(cm.exception.status_code, 409)
        self.assertEqual(self.created, [])

    async def test_another_company_cannot_use_or_overwrite_the_parts(self):
        a, b, tid = ctx("org-a"), ctx("org-b"), uuid.uuid4()
        await data.upload_part(tid, 0, Request(b"A,B\n1,2\n"), a)
        await data.upload_part(tid, 0, Request(b"evil"), b)
        with self.assertRaises(HTTPException):
            await data.finish_transfer(tid, data.FinishIn(file_name="x.csv", parts=1), b)
        await data.finish_transfer(tid, data.FinishIn(file_name="x.csv", parts=1), a)
        self.assertEqual(self.created[0][1], b"A,B\n1,2\n")

    async def test_part_limits(self):
        c, tid = ctx("org-a"), uuid.uuid4()
        for seq, body in ((0, b""), (0, b"x" * (data.PART_BYTES + 1)), (data.MAX_PARTS, b"x")):
            with self.assertRaises(HTTPException) as cm:
                await data.upload_part(tid, seq, Request(body), c)
            self.assertEqual(cm.exception.status_code, 413)

    async def test_batch_files_go_to_their_batch(self):
        c, tid = ctx("org-a"), uuid.uuid4()
        seen = []

        async def add(c_, batch_id, name, blob):
            seen.append((batch_id, name, blob))
            return {"id": "u2"}

        with mock.patch.object(data, "_add_batch_file", add):
            await data.upload_part(tid, 0, Request(b"A,B\n1,2\n"), c)
            await data.finish_transfer(tid, data.FinishIn(file_name="menu.xlsx", parts=1, batch_id="b1"), c)
        self.assertEqual(seen, [("b1", "menu.xlsx", b"A,B\n1,2\n")])


if __name__ == "__main__":
    unittest.main()
