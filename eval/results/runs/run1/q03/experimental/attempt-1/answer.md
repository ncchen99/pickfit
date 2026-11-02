I recommend **DuckDB**, used through its command-line tool. It's free and open source (MIT) and comes as one standalone binary with no runtime to install. It reads RFC 4180 CSV correctly, including quoted fields that contain commas and line breaks. It uses all your CPU cores and works through the file in chunks, so a 5 GB file doesn't need 5 GB of RAM. Filtering rows, picking columns and group-by counts all fit in one SQL query.

If you'd rather chain small Unix-style commands than write SQL, use **qsv** instead (details below).

I checked pickfit's tested catalog and none of its tools matched this request. The advice below is from general knowledge, and I haven't installed or run any of these here.

## 1. DuckDB CLI (main recommendation)

**Install (one binary, x86_64):**
```bash
# Option A: download from GitHub Releases
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip duckdb_cli-linux-amd64.zip        # gives you a single file: ./duckdb
install -m 755 duckdb ~/.local/bin/     # or /usr/local/bin with sudo

# Option B: official install script (read it before piping it into sh)
curl https://install.duckdb.org | sh
```
On ARM, use `duckdb_cli-linux-arm64.zip` instead. Check the install with `duckdb --version`.

**First run:**
```bash
# Look at the columns and types DuckDB detects
duckdb -c "DESCRIBE SELECT * FROM read_csv('big.csv');"

# Filter, pick columns, write a new CSV
duckdb -c "COPY (SELECT id, status, amount FROM read_csv('big.csv')
                 WHERE status = 'ERROR' AND amount > 100)
           TO 'filtered.csv' (HEADER);"

# Group-by count
duckdb -c "SELECT status, count(*) AS n FROM read_csv('big.csv')
           GROUP BY status ORDER BY n DESC;"
```
**Tips:**
- If type detection guesses wrong on messy data, use `read_csv('big.csv', all_varchar=true)` or `sample_size=-1`.
- To limit memory, add `SET memory_limit='2GB';` at the start of the command. DuckDB writes the overflow to temporary files on disk instead of crashing.
- If you'll query the same file many times, convert it once: `COPY (FROM 'big.csv') TO 'big.parquet';`. Later queries on the Parquet file run much faster.

## 2. qsv (if you prefer command pipelines)

qsv is a Rust tool that continues the older, unmaintained `xsv` project. It's released under MIT/Unlicense and ships static builds (musl) that run on any Linux distro.

**Install:** On the GitHub Releases page for `dathere/qsv`, download `qsv-<version>-x86_64-unknown-linux-musl.zip`. Unzip it and put `qsv` on your PATH. Check the install with `qsv --version`.

**First run:**
```bash
qsv index big.csv          # optional; builds an index that makes count, slice and frequency much faster
qsv count big.csv
qsv search -s status '^ERROR$' big.csv | qsv select id,status,amount > filtered.csv
qsv frequency -s status --limit 0 big.csv     # group-by counts
```

## 3. Miller (if it must be a distro package)

Miller handles quoted fields correctly, including ones with line breaks inside them. It's in the standard repos:
- Debian/Ubuntu: `sudo apt install miller`
- Fedora: `sudo dnf install miller`
- Arch: `sudo pacman -S miller`

Try it with `mlr --icsv --opprint count -g status big.csv`. Miller is slower than the two tools above at 2–5 GB, and commands like `sort` load all the data into memory. That's why I rank it third.

**My assumptions:** You're on x86_64 Linux and allowed to put a binary in `~/.local/bin`. The column names in the examples (`status`, `amount`, `id`) are placeholders for your own.

**Bottom line:** For one-off filtering and group-by counts, DuckDB is the fastest and easiest of these. Add qsv if you like building up pipelines command by command.