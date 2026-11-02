I found no official SQLite counterpart to SSDT, but third-party tools now cover the same workflow. Based on the vendors' documentation (I haven't run them), the closest match is **Atlas** (`atlas` CLI, by Ariga). It's built around the same idea as SSDT: you keep the desired schema in a file, and the tool works out the changes. It does all three things you listed:

| SSDT action | Atlas command |
|---|---|
| Start a project from an existing database | `atlas schema inspect` |
| Compare the real database with the project | `atlas schema diff` |
| Update the database from the project | `atlas schema apply` (preview with `--dry-run`) |

SQLite's `ALTER TABLE` can't change much. When a change needs more, Atlas plans the usual SQLite workaround: build a new table, copy the data across and swap it in.

**The catch:** the free version handles tables, columns, indexes, foreign keys and constraints. **Views and triggers require Atlas Pro, which costs $9 per user per month.** You noticed sqldiff skips views and triggers, so I've assumed you need them. If you want a free tool, see sqlite3def below.

## Install and first run (macOS)

```bash
# 1. Install (either one)
brew install ariga/tap/atlas
# or: curl -sSf https://atlasgo.sh | sh

# 2. Log in. Atlas includes views and triggers only after login, and they need Pro
atlas login

# 3. Back up the database before any apply
sqlite3 app.db ".backup app.backup.db"

# 4. Start a project from the existing database (like SSDT Import).
#    The default output format is HCL; this template writes plain SQL instead.
mkdir myproject && cd myproject && git init
atlas schema inspect -u "sqlite://../app.db" --format '{{ sql . }}' > schema.sql
git add schema.sql && git commit -m "Import schema"
```

Day-to-day use:

```bash
# A scratch in-memory SQLite database that Atlas uses to work out the plan
DEV="sqlite://dev?mode=memory"

# Update the project from the database: re-export, then review with git
atlas schema inspect -u "sqlite://../app.db" --format '{{ sql . }}' > schema.sql
git diff schema.sql

# Show what differs between the project and the database
atlas schema diff --from "sqlite://../app.db" --to "file://schema.sql" --dev-url "$DEV"

# Update the database from the project: preview first, then apply
atlas schema apply -u "sqlite://../app.db" --to "file://schema.sql" --dev-url "$DEV" --dry-run
atlas schema apply -u "sqlite://../app.db" --to "file://schema.sql" --dev-url "$DEV"
```

Read every plan before applying it. Unlike SSDT, there's no refactor log, so a renamed column or table can show up as a drop plus an add, which would lose the data.

## Free alternative: sqldef (`sqlite3def`)

This is an open-source tool for the same workflow:

```bash
brew install sqldef/sqldef/sqlite3def
sqlite3def app.db --export > schema.sql             # import
sqlite3def app.db --dry-run --file schema.sql       # preview changes to the database
sqlite3def app.db --apply --file schema.sql         # apply them
sqlite3def app.db --check --file schema.sql         # exits with code 2 if they differ (useful in CI)
```

- By default it never drops anything. Add `--enable-drop` to allow drops.
- It can compare two schema files without a database: `sqlite3def old.sql < new.sql`.
- You can mark renames in the schema file with an `@renamed` annotation, so they aren't treated as drop plus add.
- Its documentation lists support for tables, columns, indexes, constraints, virtual tables and **views**. **Triggers aren't documented.** If you use triggers, test them with `--dry-run` on a copy of the database before relying on it.

## Why not just sqlite3 and sqldiff?

- **`sqlite3 app.db .schema > schema.sql` plus git** covers importing and seeing what changed in the database. It can't update a database from the project, and that's the hard part with SQLite because of the table rebuilds.
- **sqldiff** is mostly for comparing data. As you found, it doesn't report changes to views or triggers. It's still handy for checking data after a migration.

If you'd rather keep a series of numbered migration scripts than generate changes from a schema file, Atlas also supports that (`atlas migrate diff`), as do Flyway and Liquibase. That's a different style from SSDT, though.

Sources:
- [Atlas – Schema diff](https://www.atlasgo.io/declarative/diff)
- [Atlas – Pricing](https://atlasgo.io/pricing)
- [Atlas – Features (open-source vs Pro)](https://atlasgo.io/features)
- [Atlas v0.9.0 announcement](https://atlasgo.io/blog/2023/01/05/atlas-v090)
- [sqldef README](https://github.com/sqldef/sqldef)
- [sqlite3def documentation](https://github.com/sqldef/sqldef/blob/master/cmd-sqlite3def.md)