## Recommendation: DuckDB CLI

DuckDB is a single static-ish binary with no runtime. Its CSV reader handles quoted fields with commas and embedded newlines, and it streams large files and spills to disk instead of loading everything into RAM. Filtering, column selection, and group-by counts are each one SQL query.

I'm assuming x86_64 Linux with glibc and that you're comfortable with basic SQL. I haven't run or tested these steps here.

### Install

Get the latest CLI from the official GitHub releases:

```sh
curl -LO https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip duckdb_cli-linux-amd64.zip
mkdir -p ~/.local/bin && mv duckdb ~/.local/bin/
```

Make sure `~/.local/bin` is on your `PATH`. If you'd rather use a distro package, check `apt search duckdb` or your distro's equivalent, but versions there may lag. Verify with:

```sh
duckdb --version
```

### First run

Replace `big.csv` with your file. Start with a preview:

```sh
duckdb -c "SELECT * FROM read_csv('big.csv') LIMIT 5"
```

Common tasks:

```sh
# Filter rows and pick columns, printed as CSV
duckdb -csv -c "SELECT id, name, amount
  FROM read_csv('big.csv') WHERE status = 'active'" > out.csv

# Group-by counts, most frequent first
duckdb -c "SELECT country, count(*) AS n
  FROM read_csv('big.csv') GROUP BY country ORDER BY n DESC"

# Write a filtered subset to a new file
duckdb -c "COPY (SELECT * FROM read_csv('big.csv') WHERE amount > 100)
  TO 'subset.csv' (HEADER)"
```

### Tips for multi-GB files

- **Type inference:** if a query fails partway through with a type error, the sampled types were wrong. Use `read_csv('big.csv', sample_size=-1)` to scan the whole file for types, or `all_varchar=true` to read everything as text and cast explicitly.
- **Memory and temp space:** cap memory and point spill files at a disk with room. Run these at the start of a session, or put them in a `.duckdbrc`-style init file:
  ```sql
  SET memory_limit = '4GB';
  SET temp_directory = '/path/with/space';
  ```
- **Interactive use:** run `duckdb` with no arguments to get a REPL, and use `.mode box` or `.mode markdown` for readable output.

### Alternatives

- **qsv** (Rust, single binary from GitHub releases): if you prefer pipeline-style commands, it has `select`, `search`, and `frequency` subcommands, and it is also quote-aware. Use it if you want shell pipelines rather than SQL.
- **Miller (`mlr`)**: a single Go binary with quote-aware CSV and an awk-like DSL. Some verbs, such as `sort`, hold data in memory, so it's less suited to 5 GB files than DuckDB or qsv.

Sources:
- DuckDB CLI installation and releases: https://duckdb.org/docs/installation/
- DuckDB CSV import options (sample_size, all_varchar): https://duckdb.org/docs/data/csv/overview
- qsv: https://github.com/dathere/qsv
- Miller: https://github.com/johnkerl/miller