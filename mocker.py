"""
universal_mocker — reflects a relational database schema and fills every table
with Faker-generated mock data, respecting FK dependency order.

Supports PostgreSQL, MySQL/MariaDB, and SQLite.

Usage:
    python mocker.py [--rows N] [--schema SCHEMA]

Configuration via .env (or environment variables):
    DATABASE_URL  — full SQLAlchemy URL
    DB_SCHEMA     — target schema (PostgreSQL default: public;
                    optional for MySQL/MariaDB; ignored for SQLite)
    ROW_COUNT     — rows per table (default: 10)
"""

import argparse
import os
import random
import string
from datetime import datetime, date, timezone

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import (
    create_engine, text, func, select,
    String, Integer, BigInteger, SmallInteger,
    Float, Numeric, Boolean,
    Date, DateTime, Time,
    Text, LargeBinary, Uuid,
)
from sqlalchemy import MetaData
try:
    from sqlalchemy.dialects.postgresql import UUID
except ImportError:
    UUID = None

load_dotenv()

fake = Faker()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def get_config(args):
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set. Copy .env.example to .env and fill it in."
        )
    schema = args.schema or os.getenv("DB_SCHEMA")
    rows = args.rows or int(os.getenv("ROW_COUNT", "10"))
    return url, schema, rows


# ---------------------------------------------------------------------------
# Value generation
# ---------------------------------------------------------------------------

def fake_value(col):
    """Return a plausible fake value for a SQLAlchemy column."""
    name = col.name.lower()
    ct = col.type

    # Nullable → occasionally None
    if col.nullable and random.random() < 0.05:
        return None

    # ---- type-based generation (isinstance handles dialect subtypes) ----
    if isinstance(ct, (Uuid,)) or (UUID is not None and isinstance(ct, UUID)):
        return fake.uuid4()

    if isinstance(ct, Boolean):
        return random.choice([True, False])

    if isinstance(ct, (SmallInteger, Integer, BigInteger)):
        return random.randint(1, 100_000)

    if isinstance(ct, (Float, Numeric)):
        return round(random.uniform(0.0, 10_000.0), 2)

    if isinstance(ct, DateTime):
        return fake.date_time_between(start_date="-5y", end_date="now",
                                      tzinfo=timezone.utc)

    if isinstance(ct, Date):
        return fake.date_between(start_date="-5y", end_date="today")

    if isinstance(ct, Time):
        return fake.time_object()

    if isinstance(ct, LargeBinary):
        return os.urandom(16)

    # String / Text — try to pick a semantic value based on column name
    if isinstance(ct, (String, Text)):
        length = getattr(col.type, "length", None) or 255

        if any(k in name for k in ("email",)):
            return fake.email()[:length]
        if any(k in name for k in ("phone", "mobile", "tel")):
            return fake.phone_number()[:length]
        if any(k in name for k in ("url", "website", "link")):
            return fake.url()[:length]
        if any(k in name for k in ("zip", "postal")):
            return fake.postcode()[:length]
        if any(k in name for k in ("country",)):
            return fake.country()[:length]
        if any(k in name for k in ("city",)):
            return fake.city()[:length]
        if any(k in name for k in ("address", "street")):
            return fake.street_address()[:length]
        if any(k in name for k in ("first", "fname", "firstname")):
            return fake.first_name()[:length]
        if any(k in name for k in ("last", "lname", "lastname", "surname")):
            return fake.last_name()[:length]
        if any(k in name for k in ("name",)):
            return fake.name()[:length]
        if any(k in name for k in ("description", "desc", "notes", "comment", "bio")):
            return fake.text(max_nb_chars=min(200, length))
        if any(k in name for k in ("title",)):
            return fake.sentence(nb_words=4)[:length]
        if any(k in name for k in ("uuid", "guid")):
            return fake.uuid4()[:length]
        if any(k in name for k in ("status",)):
            return random.choice(["active", "inactive", "pending"])[:length]
        if any(k in name for k in ("code",)):
            return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))[:length]
        if any(k in name for k in ("color", "colour")):
            return fake.color_name()[:length]
        if any(k in name for k in ("username", "user_name")):
            return fake.user_name()[:length]
        if any(k in name for k in ("password", "passwd", "hash")):
            return fake.sha256()[:length]
        if any(k in name for k in ("ip",)):
            return fake.ipv4()[:length]

        # generic string
        return fake.lexify(text="?" * min(10, length))[:length]

    # fallback
    return None


# ---------------------------------------------------------------------------
# Topological sort (FK-aware insertion order)
# ---------------------------------------------------------------------------

def topological_sort(tables, foreign_keys_map):
    """
    Returns tables in an order where parents are inserted before children.
    foreign_keys_map: {table_name: [referred_table_name, ...]}
    """
    result = []
    visited = set()
    temp = set()

    def visit(name):
        if name in visited:
            return
        if name in temp:
            # Cycle detected — skip to avoid infinite loop
            return
        temp.add(name)
        for dep in foreign_keys_map.get(name, []):
            if dep in {t.name for t in tables}:
                visit(dep)
        temp.discard(name)
        visited.add(name)
        result.append(name)

    for tbl in tables:
        visit(tbl.name)

    table_map = {t.name: t for t in tables}
    return [table_map[n] for n in result if n in table_map]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fill a database schema with Faker mock data (PostgreSQL, MySQL, SQLite)."
    )
    parser.add_argument("--rows", type=int, help="Rows to insert per table (default: 10)")
    parser.add_argument("--schema", help="Schema name (PostgreSQL default: public; ignored for SQLite)")
    args = parser.parse_args()

    url, schema, row_count = get_config(args)

    print(f"🔌 Connecting to database …")
    engine = create_engine(url)

    dialect = engine.dialect.name

    # Normalise schema per dialect
    if dialect == "postgresql" and schema is None:
        schema = "public"
    elif dialect in ("sqlite",):
        schema = None  # SQLite does not support named schemas

    # Reflect schema
    label = f"'{schema}'" if schema else "default"
    print(f"🔍 Reflecting schema {label} …")
    metadata = MetaData(schema=schema)
    metadata.reflect(bind=engine)

    tables = list(metadata.sorted_tables)
    if not tables:
        hint = "Check DB_SCHEMA in your .env." if schema else "Ensure DATABASE_URL points to the correct database."
        raise SystemExit(f"No tables found in schema {label}. {hint}")

    print(f"📋 Found {len(tables)} table(s): {', '.join(t.name for t in tables)}")

    # Build FK dependency map
    fk_map = {}
    for tbl in tables:
        deps = []
        for fk in tbl.foreign_keys:
            referred = fk.column.table.name
            if referred != tbl.name:
                deps.append(referred)
        fk_map[tbl.name] = deps

    ordered_tables = topological_sort(tables, fk_map)

    # Collect inserted PKs so FK columns can reference real values
    # pk_pool[table_name][pk_col_name] = [list of inserted values]
    pk_pool: dict[str, dict[str, list]] = {}

    with engine.begin() as conn:
        for tbl in ordered_tables:
            count = conn.execute(select(func.count()).select_from(tbl)).scalar()
            if count > 0:
                print(f"\n  ⏭️  Skipping '{tbl.name}' — already has {count} row(s).")
                # Still populate pk_pool so child tables can reference these rows
                pk_cols = list(tbl.primary_key.columns)
                if pk_cols:
                    rows = conn.execute(tbl.select().with_only_columns(*pk_cols)).fetchall()
                    pk_pool[tbl.name] = {col.name: [r[i] for r in rows] for i, col in enumerate(pk_cols)}
                continue

            print(f"\n  ⏳ Inserting {row_count} row(s) into '{tbl.name}' …")

            inserted_pks: dict[str, list] = {c.name: [] for c in tbl.primary_key.columns}

            for _ in range(row_count):
                row = {}
                for col in tbl.columns:
                    # Skip server-default / autoincrement PKs
                    if col.primary_key and (col.autoincrement is True or
                                            str(col.autoincrement) == "auto"):
                        continue

                    # FK column — pick a random already-inserted PK value
                    fk_targets = list(col.foreign_keys)
                    if fk_targets:
                        fk = next(iter(fk_targets))
                        ref_table = fk.column.table.name
                        ref_col = fk.column.name
                        pool = pk_pool.get(ref_table, {}).get(ref_col, [])
                        if pool:
                            row[col.name] = random.choice(pool)
                        elif col.nullable:
                            row[col.name] = None
                        else:
                            row[col.name] = fake_value(col)
                    else:
                        row[col.name] = fake_value(col)

                result = conn.execute(tbl.insert(), row)

                # Collect inserted PKs — works for all supported dialects.
                # For explicitly set PK columns (UUIDs, strings) read from `row`;
                # for auto-increment columns use inserted_primary_key (lastrowid).
                for i, pk_col in enumerate(tbl.primary_key.columns):
                    val = row.get(pk_col.name)
                    if val is None:
                        try:
                            ipk = result.inserted_primary_key
                            val = ipk[i] if ipk else None
                        except Exception:
                            val = None
                    if val is not None:
                        inserted_pks[pk_col.name].append(val)

            # Merge into pool
            pk_pool[tbl.name] = inserted_pks
            print(f"  ✅ Done — '{tbl.name}'")

    print(f"\n🎉 All done! Inserted {row_count} row(s) into each of {len(ordered_tables)} table(s).")


if __name__ == "__main__":
    main()
