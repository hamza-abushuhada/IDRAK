import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from app.config import settings

MIGRATIONS = Path(__file__).parent / "migrations"


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        await conn.execute("create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())")
        done = {r["name"] for r in await conn.fetch("select name from schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                print("skip ", f.name)
                continue
            print("apply", f.name)
            async with conn.transaction():
                await conn.execute(f.read_text(encoding="utf-8"))
                await conn.execute("insert into schema_migrations(name) values($1)", f.name)
        await conn.execute("alter table schema_migrations enable row level security")
        await conn.execute("revoke all on schema_migrations from anon, authenticated")
        print("migrations up to date")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
