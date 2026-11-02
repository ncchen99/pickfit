## Recommendation: DuckDB CLI

DuckDB is a free, open-source (MIT) analytical database that ships as a single binary. Its CSV reader handles quoted fields with commas and embedded newlines correctly, it streams large files, and it can spill to disk when a `GROUP BY` gets too big for RAM. Filtering, column selection, and group-by counts are each one SQL statement.

### Install

1. Download the CLI for Linux x86_64 or arm64 from the official install page (https://duckdb.org/docs/installation) or the GitHub releases page. Use the `duckdb_cli-linux-*.zip` asset.
2. Unzip it and move the binary onto your PATH:
   ```
   unzip duckdb_cli-linux-amd64.zip -d ~/.local/bin
   chmod +x ~/.local/bin/duckdb
   ```
   Make sure `~/.local/bin` is on your PATH.
3. Check it: `duckdb --version`.

Some distros package DuckDB (for example, Arch's `extra` repo). Check your package manager first if you prefer that. Verify the version you get, since I can't confirm current release details.

### First run

Do the filter and column pick, then the group-by count:

```
duckdb -c "
  SELECT id, name, status
  FROM read_csv('export.csv', header = true)
  WHERE status = 'active';" > active.csv
```

Add `-csv` before `-c` if you want CSV output. The default output is a table, which is fine for small results.

```
duckdb -c "
  SELECT country, count(*) AS n
  FROM read_csv('export.csv', header = true)
  GROUP BY country
  ORDER BY n DESC;"
```

For a messy file, add these settings:

- `all_varchar = true` keeps every column as text, so type guessing doesn't fail halfway through a 5 GB file.
- `ignore_errors = true` skips malformed rows instead of stopping.
- `SET memory_limit = '4GB';` caps RAM use. Put it in a file and run `duckdb -init setup.sql`, or put it at the start of the SQL before the query.
- `SET temp_directory = '/some/fast/disk';` tells it where to spill large sorts and groups.

### Alternatives

- **qsv** (Rust, single binary, MIT license): a CLI toolkit with `select`, `search`, `filter`, and `frequency` commands. It's the best fit if you want shell-style subcommands and not SQL. It's the maintained successor to `xsv`. Use it if you dislike writing SQL.
- **Miller (`mlr`)** (Go, single binary, BSD-2): streams records with proper CSV quoting. It has `filter`, `cut`, and `count -g`, and uses very little memory. It's in many distro repos as `miller`. Use it for streaming pipelines with low memory.

Avoid csvkit, since it's Python.

### Assumptions

- You're on an x86_64 or arm64 Linux machine with a normal shell.
- Your CSVs use a header row. If they don't, set `header = false` and name the columns yourself.