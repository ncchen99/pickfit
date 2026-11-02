# Use qsv

Install **qsv** ([github.com/dathere/qsv](https://github.com/dathere/qsv)). It is the maintained successor to BurntSushi's `xsv`, written in Rust, and released under MIT/Unlicense. It ships as one static binary with no runtime. Its CSV parser follows RFC 4180, so quoted fields that contain commas and line breaks are handled correctly. It streams the file instead of loading it into memory, and once you build an index it uses all your cores. A 2–5 GB file should be no problem.

My assumptions: x86_64 Linux, and UTF-8 CSV with standard double-quote escaping. I didn't run anything on this machine.

## Install

1. Open the [releases page](https://github.com/dathere/qsv/releases/latest) and download the asset named `qsv-<version>-x86_64-unknown-linux-musl.zip`. The musl build is fully static, so it runs on any distro. Use the `aarch64` build on ARM.
2. Unzip it and install it:
   ```bash
   unzip qsv-*-x86_64-unknown-linux-musl.zip -d qsv-dl
   install -m 755 qsv-dl/qsv ~/.local/bin/    # or sudo install ... /usr/local/bin/
   qsv --version
   ```
   The zip also contains `qsvlite` and `qsvdp`, which are smaller variants. You only need `qsv`.

qsv is in Homebrew, Nix, Arch (AUR) and Scoop, but it generally isn't in the Debian, Ubuntu or Fedora repos. If you need a distro package, see Miller below.

## First run

```bash
qsv index big.csv                 # one-time; writes big.csv.idx, makes count/frequency/stats fast + parallel
qsv headers big.csv               # list column names with their positions
qsv count big.csv                 # row count (instant once indexed)

# Pick columns
qsv select id,status,country big.csv > slim.csv

# Filter rows (regex on one column), then pick columns
qsv search -s status '^shipped$' big.csv | qsv select id,country,amount > shipped.csv

# Group-by count on one column (all values, sorted by count)
qsv frequency -s country --limit 0 big.csv

# Multi-column group-by, or filter+group in one step (SQL via the built-in Polars engine)
qsv sqlp big.csv "SELECT country, status, COUNT(*) AS n
                  FROM _t_1 WHERE amount > 100
                  GROUP BY country, status ORDER BY n DESC"
```

A few other commands that help: `qsv stats big.csv` profiles each column, `qsv slice -l 20 big.csv | qsv table` gives a quick look at the data, and `qsv sort` and `qsv dedup` do what their names say. `qsv --list` shows every command.

## Alternatives

- **DuckDB CLI** (MIT license, single binary, `duckdb_cli-linux-amd64.zip` on its GitHub releases page). Pick this if most of your work is SQL-style grouping, joins or aggregations. It's very fast, multithreaded, and runs out-of-core:
  ```bash
  duckdb -c "SELECT country, status, count(*) n FROM read_csv('big.csv') GROUP BY ALL ORDER BY n DESC"
  ```
- **Miller (`mlr`)** (BSD license, single Go binary). Pick this if you must install from your distro's repos: `apt install miller` or `dnf install miller`. It's slower than qsv or DuckDB on files this big, but it parses CSV correctly and its syntax is friendly:
  ```bash
  mlr --icsv --opprint filter '$amount > 100' then count -g country,status big.csv
  ```
- **Avoid plain `xsv`.** It works, but it's no longer maintained, and qsv covers everything it does.

In short: use qsv for everyday filter, select and count work, and add DuckDB when the queries get complex.