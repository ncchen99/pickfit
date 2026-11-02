# Use the DuckDB CLI

I recommend the **DuckDB CLI**. It's MIT-licensed and ships as one statically linked binary with no runtime dependencies. It reads CSV files with quoted fields containing commas and line breaks correctly, uses all CPU cores, and processes the file as a stream instead of loading it into memory. Large group-bys can spill to disk. You write the filter, column selection and group-by counts as plain SQL, and you don't need an import step. A 2–5 GB file usually takes seconds to tens of seconds, depending on disk and CPU.

**Assumptions:** you're on x86_64 or arm64 Linux, the CSV has a header row, and "free" means open-source with no paid tier.

## Install

Option A: the official install script, which puts the binary in `~/.duckdb/cli/latest/`:
```bash
curl https://install.duckdb.org | sh
```
Option B: download the binary yourself, which avoids piping a script to `sh`:
```bash
mkdir -p ~/dl/duckdb && cd ~/dl/duckdb
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip   # or -linux-arm64
unzip duckdb_cli-linux-amd64.zip
sudo install -m 755 duckdb /usr/local/bin/duckdb
duckdb --version
```
Most distros don't ship DuckDB in their main repos. It's in the Arch AUR, Nix and Homebrew-on-Linux, but the GitHub release binary is the usual route.

## First run

```bash
# 1. Check the column names and types DuckDB detected
duckdb -c "DESCRIBE SELECT * FROM 'export.csv';"

# 2. Preview a few rows
duckdb -c "SELECT * FROM 'export.csv' LIMIT 5;"

# 3. Filter rows and pick columns, writing a new CSV
duckdb -c "COPY (
  SELECT id, email, country
  FROM 'export.csv'
  WHERE status = 'active' AND amount > 100
) TO 'filtered.csv' (HEADER);"

# 4. Group-by counts
duckdb -c "SELECT country, count(*) AS n
           FROM 'export.csv'
           GROUP BY country ORDER BY n DESC;"
```

**Tips:**
- **If type or format detection guesses wrong:** use `read_csv('export.csv', all_varchar=true)` or pass options yourself, e.g. `read_csv('f.csv', delim=';', quote='"', header=true)`.
- **To cap memory:** start the query with `SET memory_limit='4GB'; SET temp_directory='/tmp/duck';`.
- **If you query the same export many times:** convert it to Parquet once. Later queries will be much faster:
  `duckdb -c "COPY (FROM 'export.csv') TO 'export.parquet';"`
- **For output to other tools:** `duckdb -csv -c "..."` or `-json` prints results in that format, so you can pipe them.

## Alternatives

- **qsv** (Rust, single binary from its GitHub releases; Unlicense/MIT): best if you'd rather chain small commands than write SQL. It's the maintained successor to xsv, which is no longer maintained. Examples:
  `qsv index f.csv`, `qsv select id,email f.csv`, `qsv search -s status '^active$' f.csv`, `qsv frequency -s country --limit 0 f.csv`.
  For filtering on numbers you'd use `qsv sqlp`.
- **Miller (`mlr`)** (Go, BSD): use this if you need a regular distro package (`apt install miller` / `dnf install miller`). It handles quoted CSV correctly but is noticeably slower than the two above on multi-GB files. Examples:
  `mlr --icsv --ocsv filter '$status=="active"' then cut -f id,email f.csv`, `mlr --icsv --opprint count -g country f.csv`.

I'd go with DuckDB first. Add qsv if you also want quick one-liners like `frequency`, `stats` or `headers`.