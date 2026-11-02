# Version-controlling a SQLite schema the way SSDT does

**My main recommendation is sqldef's `sqlite3def`.** It's a free, open-source CLI that works from a desired-state file, which is how SSDT works. It covers your three needs:

| What you want (SSDT) | `sqlite3def` |
|---|---|
| Start a project from an existing database | `sqlite3def app.db --export > schema.sql` |
| Diff the real database against the project and update the project | Re-export, then `git diff schema.sql` |
| Diff the project against the database and update the database | `--dry-run` shows the DDL it would run, `--apply` runs it, and `--check` is for CI |

There's no official SSDT for SQLite. Tools like this are the nearest equivalent.

**Two things I couldn't confirm:**
- **Triggers:** The `sqlite3def` docs say views and virtual tables are supported, but they don't mention triggers. Test this yourself (step 5 below) before relying on it.
- **Table rebuilds:** SQLite's `ALTER TABLE` can do very little. Some changes, like changing a column's type, mean rebuilding the table. Always read the `--dry-run` output before applying, and keep a backup.

You're right about `sqldiff`: it's mainly for comparing data, and it skips triggers and views. It isn't the right tool for this.

## Install and first run (macOS, assuming Homebrew)

```sh
# 1. Install
brew install sqldef/sqldef/sqlite3def

# 2. Import the existing database into a project
mkdir myschema && cd myschema && git init
sqlite3def /path/to/app.db --export > schema.sql
git add schema.sql && git commit -m "Import schema from app.db"

# 3. Project -> database: edit schema.sql, then preview and apply
sqlite3 /path/to/app.db ".backup /path/to/app.backup.db"   # back up first
sqlite3def /path/to/app.db --dry-run --file schema.sql      # shows the DDL it would run
sqlite3def /path/to/app.db --apply   --file schema.sql      # add --enable-drop to allow DROP statements

# 4. Database -> project: pull in changes someone made directly to the database
sqlite3def /path/to/app.db --export > schema.sql
git diff schema.sql            # review, then commit

# 5. Check that triggers are handled (run on a scratch copy)
cp /path/to/app.db /tmp/t.db
sqlite3 /tmp/t.db "CREATE TRIGGER trg_test AFTER INSERT ON <sometable> BEGIN SELECT 1; END;"
sqlite3def /tmp/t.db --export | grep -i trigger      # does the export include it?
```

`sqlite3def /path/to/app.db --check --file schema.sql` exits with code 2 if the database has drifted from the project, so you can use it in CI. To rename a table or column instead of dropping and recreating it, add a `-- @renamed from=old_name` comment.

## A simple safety net that also catches triggers and views

SQLite keeps the original `CREATE` text of every table, index, view and trigger in `sqlite_schema`. That makes a plain dump an exact record of the schema, whatever tool you use. Commit it next to `schema.sql`:

```sh
sqlite3 /path/to/app.db ".schema" > schema.dump.sql
git diff schema.dump.sql
```

This is what you found in your research. It works well for the database → project direction. It doesn't help with project → database, because you'd have to write the `ALTER` and table-rebuild steps by hand. That's the part `sqlite3def` does for you.

## Alternatives

- **Atlas (ariga.io)** has a more polished SSDT-like workflow: `atlas schema inspect`, `schema diff` and `schema apply`, with a plan you review before it runs. It handles SQLite tables, indexes and constraints for free. **Views and triggers need the paid Atlas Pro plan** and an `atlas login`, so if you rely on triggers you'd have to pay.
  ```sh
  brew install ariga/tap/atlas
  atlas schema inspect -u "sqlite:///path/to/app.db" --format '{{ sql . }}' > schema.sql
  atlas schema diff  --from "sqlite:///path/to/app.db" --to file://schema.sql --dev-url "sqlite://dev?mode=memory"
  atlas schema apply -u "sqlite:///path/to/app.db" --to file://schema.sql --dev-url "sqlite://dev?mode=memory"
  ```
- **Liquibase** is free and supports SQLite, but it works by running a list of migration steps rather than comparing against a desired state, so it's less like SSDT. Its SQLite diff support is limited. I haven't checked how it works with SQLite in practice.

I also checked pickfit, a catalogue of developer tools it has installed and tested. None of them fit this need. Its only suggestion was Liquibase, which it hasn't tested.

Sources:
- [sqldef README](https://github.com/sqldef/sqldef)
- [sqlite3def docs](https://github.com/sqldef/sqldef/blob/master/cmd-sqlite3def.md)
- [Atlas feature compatibility](https://atlasgo.io/features)
- [Atlas inspect docs](https://atlasgo.io/inspect)
- [Atlas Community Edition](https://www.atlasgo.io/community-edition)
- [Atlas v0.13 blog](https://atlasgo.io/blog/2023/08/06/atlas-v-0-13)