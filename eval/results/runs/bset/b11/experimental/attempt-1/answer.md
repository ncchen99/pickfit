Yes. This is a standard MCP setup: the server runs on the remote machine using the **HTTP transport** (not stdio), and your client connects to its URL. My main pick is **DBHub** (by Bytebase). It's free and open source, works with PostgreSQL, MySQL, MariaDB, SQL Server, Oracle and SQLite, and is built to run as a network service.

**How much is verified:** My recommendation service (pickfit) had no tested tool for this case, so I haven't tested DBHub. The commands below come from DBHub's README and its install page at dbhub.ai. I'm assuming the remote machine runs Linux with Docker or Node.js 22.5+, and the database is Postgres. For other databases, only the connection string changes.

## Main pick: DBHub

**How it works:**
```
Your client (Claude Code / Desktop / etc.)  ──HTTP──▶  remote host: DBHub :8080/mcp  ──▶  database
```
The client sends "how many rows are in abc?", the model calls DBHub's `execute_sql` tool with `SELECT COUNT(*) FROM abc`, and the result comes back. DBHub also has a `search_objects` tool for looking up tables and columns. `explain_sql` and `health_check` are optional extras.

### Install and run on the remote server

**Option A: Docker**
```bash
docker run --rm --init --name dbhub \
  --publish 127.0.0.1:8080:8080 \
  bytebase/dbhub \
  --transport http --port 8080 \
  --dsn "postgres://readonly_user:password@DB_HOST:5432/dbname?sslmode=disable"
```
If the database runs on the same machine, outside Docker, use `host.docker.internal` as `DB_HOST`.

**Option B: Node (22.5 or later)**
```bash
npx @bytebase/dbhub@latest --transport http --port 8080 \
  --dsn "postgres://readonly_user:password@localhost:5432/dbname?sslmode=disable"
```

**Trying it out first:** add `--demo` instead of `--dsn` to run against a built-in sample database.

The MCP endpoint is **`http://<server>:8080/mcp`**.

### Connect from the client
- **Claude Code:**
  `claude mcp add --transport http dbhub https://your-server.example.com/mcp`
- **Clients that use a JSON config:** add `{"mcpServers": {"dbhub": {"type": "http", "url": "https://your-server.example.com/mcp"}}}`

Then ask: *"How many rows are in the abc table?"*

### Security (important)
- **Use a database user that can only read** (for example, give it only `SELECT` permission). The `execute_sql` tool runs whatever SQL the model writes.
- **Don't put port 8080 on the open internet.** DBHub has an `--auth-token` option, but its docs don't explain how it works. Instead, do one of these:
  - **SSH tunnel** (easiest): `ssh -L 8080:localhost:8080 user@server`, then point the client at `http://localhost:8080/mcp`.
  - **Reverse proxy** (Caddy or nginx) with TLS and authentication, or a private network like Tailscale or WireGuard.
- For several databases, or to set up read-only custom tools, use a `dbhub.toml` file with `--config`. Check the dbhub.ai docs for the current options.

## Alternatives (also not verified by me)
- **Google's MCP Toolbox for Databases** (`genai-toolbox`): a single Go binary that runs as an HTTP server. You write the allowed queries yourself in a `tools.yaml` file, so the model can't run arbitrary SQL. That makes it a good choice if you want tighter control.
- **Database-specific servers**, such as Postgres MCP Pro (`crystaldba/postgres-mcp`), which supports SSE and has a restricted mode. Choose one of these if you only use one type of database and want features like performance tuning.

Sources:
- https://github.com/bytebase/dbhub
- https://dbhub.ai/installation