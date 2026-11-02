I couldn't verify this by running it here. The pickfit catalog had no tested tool that fits, so this comes from what I know rather than an install I checked. I've assumed x86_64 Linux. For arm64, use the `aarch64` / `arm64` downloads instead.

## Main recommendation: DuckDB CLI

DuckDB is a free, open-source (MIT) SQL engine. On Linux it comes as one self-contained `duckdb` binary with no runtime dependencies.

- **Quoted fields:** Its CSV reader follows the standard CSV rules (RFC 4180), so commas and line breaks inside quoted fields are handled correctly, unlike awk.
- **Speed and memory:** It uses all your CPU cores and streams the file instead of loading it all like pandas. If a query needs more memory than you allow, it writes temporary data to disk. A 2–5 GB group-by usually takes seconds.
- **Your three tasks are plain SQL:** `WHERE` filters rows, `SELECT` picks columns, and `GROUP BY` with `count(*)` does the counts. Multi-column group-bys are easy too.

### Install
1. Download the binary from the official GitHub releases:
   ```
   mkdir -p ~/.local/bin && cd /tmp
   curl -LO https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
   unzip duckdb_cli-linux-amd64.zip -d ~/.local/bin
   chmod +x ~/.local/bin/duckdb
   ```
   You can also use the official `curl https://install.duckdb.org | sh`. Read the script first if you go that way. Some distros package it (for example, Arch has `duckdb`). Debian and Ubuntu generally don't, so the binary is the reliable option there.
2. Check it works: `duckdb --version`

### First run
```
# Group-by count, with a filter
duckdb -c "SELECT status, count(*) AS n
           FROM 'export.csv'
           WHERE country = 'DE'
           GROUP BY ALL ORDER BY n DESC"

# Filter rows + pick columns, write a new CSV
duckdb -c "COPY (SELECT id, email, amount FROM 'export.csv' WHERE amount > 100)
           TO 'subset.csv' (HEADER)"

# Check what types/columns it detected
duckdb -c "DESCRIBE SELECT * FROM 'export.csv'"
```
Tips:
- **Limit memory:** Add `SET memory_limit='4GB';` at the start of the query.
- **If it guesses columns or types wrong:** Spell out the format, for example `read_csv('export.csv', header=true, quote='"', escape='"', all_varchar=true)`.
- **If you query the same export many times:** Convert it once with `COPY (FROM 'export.csv') TO 'export.parquet'`. Queries on the Parquet file are much faster than re-reading the CSV.

## Alternatives
- **qsv** (successor to xsv, MIT/Unlicense): a single static binary from its GitHub releases (`qsv-…-x86_64-unknown-linux-musl.zip`). It's better if you like small chained commands over SQL, for example `qsv search -s country '^DE$' export.csv | qsv select id,amount` and `qsv frequency -s status export.csv`. Run `qsv index export.csv` first to speed up repeated work. It also handles quoted fields correctly. Its `frequency` command counts one column at a time, so for multi-column group-bys you'd use its `sqlp` SQL command, at which point DuckDB is simpler.
- **Miller (`mlr`)**: available as a distro package (`apt install miller`, `dnf install miller`). It handles quoted CSV correctly and works well as a general record-processing tool (`mlr --icsv --opprint count -g status then sort -nr count export.csv`). It's noticeably slower than DuckDB or qsv on 5 GB files.
- **Avoid xsv**: it is no longer maintained, so use qsv instead.

My pick for you: start with DuckDB, and add qsv if you want quick one-liners in shell pipelines.