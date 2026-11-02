# CSV tool recommendation for 2–5 GB files on Linux

## Main recommendation: DuckDB CLI

**DuckDB CLI** is free and open source (MIT license). It's a single static binary with no runtime dependencies. It runs SQL directly on CSV files and handles RFC-4180 quoting, so commas and line breaks inside quoted fields are parsed correctly. It reads files in parallel on all your cores, streams the data instead of loading it all into memory, and can spill to disk if a group-by gets large. On 2–5 GB files, filtering and group-by counts usually take seconds rather than minutes.

I'm assuming x86_64 Linux and that downloading an official binary from GitHub or duckdb.org is acceptable. Most distros don't package DuckDB in their main repos; Arch has it in the AUR.

### Install (no root needed)

Option A: official installer script. Read it first if you like; it installs to `~/.duckdb/cli/latest/duckdb`.
```bash
curl https://install.duckdb.org | sh
```

Option B: download the binary yourself.
```bash
mkdir -p ~/bin && cd ~/bin
curl -LO https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip   # use -linux-arm64 on ARM
unzip duckdb_cli-linux-amd64.zip && rm duckdb_cli-linux-amd64.zip
chmod +x duckdb
duckdb --version        # make sure ~/bin is on your PATH
```

### First run

```bash
# Check how DuckDB detected the columns and types
duckdb -c "DESCRIBE SELECT * FROM read_csv('export.csv')"

# Filter rows and pick columns, writing the result to a new CSV
duckdb -c "COPY (
  SELECT id, customer, amount
  FROM read_csv('export.csv')
  WHERE status = 'FAILED' AND amount > 100
) TO 'failed.csv' (HEADER)"

# Group-by count
duckdb -c "SELECT country, status, count(*) AS n
           FROM read_csv('export.csv')
           GROUP BY ALL ORDER BY n DESC"
```

Tips:
- **If type or delimiter detection gets something wrong**, set the options yourself: `read_csv('export.csv', header=true, delim=',', quote='"', escape='"', all_varchar=true)`. `all_varchar=true` is the simplest fix when a column has mixed types.
- **To limit memory use**, start with `SET memory_limit='4GB'; SET temp_directory='/tmp/duck';` and put your query after it in the same `-c` string.
- **If you'll query the same export several times**, convert it to Parquet once: `COPY (FROM read_csv('export.csv')) TO 'export.parquet'`. Later queries on `'export.parquet'` will be much faster.
- **For interactive work**, run `duckdb` with no arguments to get a REPL.

## Alternative: qsv (if you prefer pipe-style commands to SQL)

**qsv** is the actively maintained successor to xsv (MIT/Unlicense). It's a single Rust binary and parses quoted fields correctly.

Install by downloading the `x86_64-unknown-linux-musl` zip from https://github.com/dathere/qsv/releases, unzip it, and put `qsv` in `~/bin`.

```bash
qsv index export.csv                                  # optional; makes later commands faster
qsv headers export.csv
qsv search -s status '^FAILED$' export.csv | qsv select id,customer,amount > failed.csv
qsv frequency -s country --limit 0 export.csv         # value counts for one column
```

qsv is great for quick slicing and single-column counts. For group-bys over several columns with conditions, DuckDB's SQL is easier.

## Also worth knowing

**Miller (`mlr`)** is in the Debian/Ubuntu/Fedora/Arch repos (`apt install miller`) and is a single Go binary. It also handles quoting correctly and has a nice syntax (`mlr --icsv --opprint count -g country export.csv`), but it's noticeably slower than the two tools above on files this size.

I didn't run anything on your machine. All the commands above are for you to run yourself.