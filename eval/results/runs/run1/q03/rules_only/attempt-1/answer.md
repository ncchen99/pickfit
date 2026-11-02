I'm recommending **qsv**: one Rust binary, free and open source (MIT/Unlicense), no runtime needed. It handles standard CSV quoting, including commas and line breaks inside quoted fields, and is built for multi-GB files.

I didn't run anything on your machine. I also checked pickfit's catalogue of tested tools, but it had nothing relevant for this job. So the advice below comes from my own knowledge, and **I haven't installed or tested these tools myself**.

**My assumptions:** x86_64 Linux, files that are standard comma-separated CSV with a header row, and the ability to put a binary in `~/.local/bin`.

---

## Main pick: qsv

**Why it fits:**
- It reads CSV properly, so quoted fields with commas or line breaks don't break it the way they break awk.
- It streams the file, so most commands use little memory. With an index file, commands like `frequency` and `stats` run on several CPU cores.
- It has a command for each of your jobs: `search` filters rows, `select` picks columns, `frequency` does single-column counts, and `sqlp` runs SQL (using the Polars engine) for multi-column group-bys.
- It's actively maintained. It started as a fork of the older xsv tool, which is no longer maintained.

### Install (prebuilt binary, no root needed)
1. Open https://github.com/dathere/qsv/releases and download the Linux zip for your machine. Use the `x86_64-unknown-linux-musl` build if you want it to run on any distro. For example:
   ```bash
   mkdir -p ~/tmp/qsv-dl && cd ~/tmp/qsv-dl
   curl -LO https://github.com/dathere/qsv/releases/download/<VERSION>/qsv-<VERSION>-x86_64-unknown-linux-musl.zip
   unzip qsv-*.zip
   install -m 755 qsv ~/.local/bin/qsv
   ```
   Check the releases page for the exact file name. The zip also includes `qsvlite` and `qsvdp`, which are cut-down versions you don't need.
2. Make sure `~/.local/bin` is on your `PATH`, then confirm it works: `qsv --version`

### First run
```bash
# Optional but recommended for big files: build an index (enables multithreading)
qsv index big.csv

# Quick look at the file
qsv headers big.csv
qsv count big.csv

# Filter rows: keep rows where the "status" column matches a regex
qsv search -s status '^active$' big.csv > active.csv

# Pick columns (by name or position)
qsv select id,country,status big.csv > slim.csv

# Chain them
qsv search -s status '^active$' big.csv | qsv select id,country > out.csv

# Group-by count on one column (--limit 0 = show all values)
qsv frequency -s country --limit 0 big.csv

# Multi-column group-by with SQL
qsv sqlp big.csv "SELECT country, status, COUNT(*) AS n
                  FROM big GROUP BY country, status ORDER BY n DESC"
```
Two things to watch:
- `frequency` keeps a count for every distinct value in memory. If a column has millions of distinct values, use `sqlp` instead.
- In `sqlp`, the table name is the file name without `.csv` (so `big` above). `_t_1` also works and always refers to the first file.

---

## Alternatives

**DuckDB CLI** (one binary, MIT license): best if you'd rather write SQL for everything. It's very fast at group-bys on multi-GB files and also reads quoted fields correctly.
```bash
# Download duckdb_cli-linux-amd64.zip from https://github.com/duckdb/duckdb/releases, unzip, then:
install -m 755 duckdb ~/.local/bin/
duckdb -c "SELECT country, count(*) n FROM read_csv('big.csv') WHERE status='active' GROUP BY ALL ORDER BY n DESC"
duckdb -c "COPY (SELECT id, country FROM read_csv('big.csv') WHERE status='active') TO 'out.csv' (HEADER)"
```

**Miller (`mlr`)** (one Go binary, BSD license): the only one of the three that's in the standard distro repos, e.g. `sudo apt install miller` or `sudo dnf install miller`. It's slower than qsv or DuckDB on 5 GB files but still far lighter than pandas. Miller 6 reads quoted line breaks correctly.
```bash
mlr --icsv --ocsv filter '$status == "active"' then cut -f id,country big.csv > out.csv
mlr --icsv --opprint count -g country big.csv
```

**Rule of thumb:** use qsv for fast everyday filtering and column picking, DuckDB when the question is easier to write as SQL, and Miller if you're only allowed packages from your distro's repos.