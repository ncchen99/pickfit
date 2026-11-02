# Use the DuckDB CLI for this

I checked pickfit, the catalog of tools it has installed and tested. None of its 23 tested tools fits this job. It suggested DuckDB but hasn't tested it. Everything below comes from my own knowledge of these tools. I haven't run any of it on your machine.

**Assumptions:** you're on x86_64 Linux, and the files are mostly standard CSV (RFC 4180, the usual format), with a header row.

## Main recommendation: DuckDB CLI

- **License and packaging:** MIT license, one self-contained binary, no runtime needed.
- **Handles your problem files:** its CSV reader correctly handles quoted fields that contain commas, escaped quotes and line breaks.
- **Speed and memory:** it streams and runs in parallel on all cores. When memory runs short, it spills to disk instead of loading the whole file, so 2–5 GB is easy.
- **All three jobs in one query:** filtering, picking columns and group-by counts are plain SQL.

### Install
DuckDB usually isn't in Debian or Ubuntu repos, so download the release binary:
```bash
mkdir -p ~/.local/bin && cd /tmp
curl -LO https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
# (on ARM: duckdb_cli-linux-arm64.zip)
unzip duckdb_cli-linux-amd64.zip -d ~/.local/bin
chmod +x ~/.local/bin/duckdb
duckdb --version
```
(The site also offers a `curl … | sh` installer. Downloading the zip directly avoids piping a script into your shell.)

### First run
```bash
# Look at the columns and the types DuckDB detected
duckdb -c "DESCRIBE SELECT * FROM read_csv('export.csv')"

# Group-by count
duckdb -c "SELECT status, count(*) AS n FROM read_csv('export.csv')
           GROUP BY status ORDER BY n DESC"

# Filter rows + pick columns -> new CSV
duckdb -c "COPY (SELECT id, customer, amount FROM read_csv('export.csv')
                 WHERE amount > 100 AND country = 'DE')
           TO 'filtered.csv' (HEADER)"
```
Tips:
- **Type errors partway through a file:** DuckDB guesses column types from a sample of rows. If a later row breaks that guess, use `read_csv('f.csv', all_varchar=true)` or `sample_size=-1`.
- **Capping memory:** add `SET memory_limit='2GB';` at the start of the `-c` string.
- **Querying the same file many times:** convert it once with `COPY (FROM read_csv('f.csv')) TO 'f.parquet'`. Queries on the Parquet file are much faster.

## Alternative: qsv (if you want Unix-style subcommands instead of SQL)
qsv is the maintained fork of xsv, written in Rust. It's a single static binary and uses little memory.
- **Install:** on https://github.com/dathere/qsv/releases, download the `x86_64-unknown-linux-musl` zip and put `qsv` on your PATH.
- **First run:**
```bash
qsv index export.csv                      # one-time, speeds up later commands
qsv headers export.csv
qsv search -s country '^DE$' export.csv | qsv select id,customer,amount > filtered.csv
qsv frequency -s status --limit 0 export.csv   # group-by count for one column
```
qsv is great for quick pipelines. Group-bys on several columns are easier in DuckDB, though qsv's `sqlp` command can do them.

## Option from your distro's package manager: Miller (`mlr`)
- **Install:** `sudo apt install miller` or `sudo dnf install miller`. It's a Go binary.
- **First run:** `mlr --icsv --opprint filter '$amount > 100' then cut -f id,amount then count -by status export.csv`
- **Trade-off:** it parses quoted fields correctly and streams, but it's noticeably slower than DuckDB or qsv on multi-GB files.

**Bottom line:** start with DuckDB. Add qsv if you also want quick one-liners in pipes.