# universal_mocker

A Python CLI tool that connects to a relational database, reflects its schema, and populates every table with realistic [Faker](https://faker.readthedocs.io)-generated mock data — respecting foreign key dependency order.

**Supported databases:** PostgreSQL · MySQL / MariaDB · SQLite

---

## Features

- Auto-discovers all tables via SQLAlchemy schema reflection — no configuration needed beyond a connection URL
- Topological insert order — parent tables are populated before child tables, so FK constraints are never violated
- Semantically aware data — column names like `email`, `phone`, `city`, `status`, `uuid` get appropriate fake values
- Skips tables that already contain data (and still tracks their PKs for FK resolution)
- Handles circular FK references gracefully

---

## Requirements

- Python 3.9+
- A running PostgreSQL, MySQL/MariaDB, or SQLite database

---

## Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

> `requirements.txt` lists all drivers. Install only what you need — e.g. you don't need `psycopg2-binary` for a SQLite project.

---

## Configuration

Copy `.env.example` to `.env` and fill in your connection details:

```bash
cp .env.example .env
```

### `.env` variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Full SQLAlchemy connection URL (**required**) | — |
| `DB_SCHEMA` | Target schema (PostgreSQL) or database (MySQL). Ignored for SQLite. | `public` (PostgreSQL) |
| `ROW_COUNT` | Number of rows to insert per table | `10` |

### `DATABASE_URL` examples

```dotenv
# PostgreSQL
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/mydb

# MySQL / MariaDB
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/mydb

# SQLite (relative path)
DATABASE_URL=sqlite:///./mydb.sqlite

# SQLite (absolute path)
DATABASE_URL=sqlite:////absolute/path/to/mydb.sqlite
```

---

## Usage

```bash
# Use values from .env
python mocker.py

# Override rows and schema on the command line
python mocker.py --rows 50 --schema myschema
```

### CLI options

| Flag | Description |
|---|---|
| `--rows N` | Rows to insert per table (overrides `ROW_COUNT`) |
| `--schema NAME` | Schema / database name to reflect (overrides `DB_SCHEMA`) |

---

## How it works

1. Connects to the database using `DATABASE_URL`
2. Reflects all tables in the target schema with SQLAlchemy
3. Builds a foreign key dependency graph and sorts tables topologically
4. For each empty table, inserts `ROW_COUNT` rows of fake data:
   - FK columns reference previously inserted primary keys
   - Column names are matched to semantic Faker providers (email, phone, city, …)
   - Column types drive the fallback (integer, decimal, boolean, date, …)
5. Tables with existing rows are skipped; their PKs are still tracked so child tables can reference them

---

## Database-specific notes

### PostgreSQL
- Requires `psycopg2-binary` (already in `requirements.txt`)
- `DB_SCHEMA` selects a PostgreSQL schema (default: `public`)

### MySQL / MariaDB
- Requires `PyMySQL` (already in `requirements.txt`)
- `DB_SCHEMA` is optional; if omitted the database in the URL is used
- The `RETURNING` clause is not used — compatible with MySQL 5.7+

### SQLite
- No extra driver needed (`sqlite3` is built into Python)
- `DB_SCHEMA` is ignored; all tables in the file are reflected

---

## Project structure

```
universal_mocker/
├── mocker.py          # Main script
├── requirements.txt   # Python dependencies
├── .env.example       # Configuration template
└── .gitignore
```

---

## License

MIT
