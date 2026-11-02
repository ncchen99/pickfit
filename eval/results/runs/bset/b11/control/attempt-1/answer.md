Yes. MCP servers can run over the network using the **Streamable HTTP** transport, and the setup you describe works. The language model stays with the client. When a user asks "how many rows are in `abc`?", the client's model sends a tool call (for example, `execute_sql("SELECT COUNT(*) FROM abc")`) over HTTP to the MCP server on the remote machine. That server runs the query against the database and returns the result.

My assumptions: the database is PostgreSQL or MySQL, the remote host is Linux with Docker, and the client is Claude Code or Claude Desktop. Other MCP-capable clients work the same way.

## Main recommendation: DBHub (by Bytebase)

DBHub is an open-source database MCP server. It supports PostgreSQL, MySQL, MariaDB, SQL Server, SQLite and Oracle, and it runs over HTTP. It gives the model a general SQL tool, so ad-hoc questions like "count the rows in abc" work without any setup per question.

### Install and first run (on the remote server)

1. **Try it with the bundled demo database first:**
   ```bash
   docker run --rm -p 8080:8080 bytebase/dbhub --transport http --port 8080 --demo
   ```
2. **Point it at your database:**
   ```bash
   docker run -d --name dbhub -p 127.0.0.1:8080:8080 bytebase/dbhub \
     --transport http --port 8080 \
     --dsn "postgres://readonly_user:PASSWORD@db-host:5432/mydb?sslmode=require"
   ```
   - If the database runs on the Docker host itself, use `host.docker.internal` instead of `localhost` in the DSN.
   - You can also run it without Docker: `npx @bytebase/dbhub --transport http --port 8080 --dsn "..."`
3. **Secure it before exposing it.** In HTTP mode, DBHub listens on `0.0.0.0` and does **not** authenticate clients. That's why the example above binds to `127.0.0.1`. Then do one of these:
   - Put a reverse proxy (Caddy or nginx) in front with TLS plus authentication, such as a bearer token, basic auth, or OAuth.
   - Or skip public exposure and have clients connect through an SSH tunnel: `ssh -L 8080:localhost:8080 user@server`.
   - Either way, use a **read-only database user**. The model writes SQL on the fly, so the database permissions are your real safety limit. Check the current README for DBHub's own read-only option.

### Connect the client

- **Claude Code:**
  ```bash
  claude mcp add --transport http dbhub https://your-server.example.com/mcp
  ```
  With an SSH tunnel, use `http://localhost:8080/mcp` instead. The `/mcp` path is my assumption, so check it against the DBHub README.
- **Claude Desktop:** add it under Settings → Connectors → custom connector using the public HTTPS URL. Or use an `npx mcp-remote <url>` bridge in the config file.
- Then ask: *"How many rows are in the abc table?"*

## Alternative: Google's MCP Toolbox for Databases

Use this if you want more control. Instead of letting the model write any SQL, you define specific tools and their queries in a `tools.yaml` file. It also has built-in authentication, connection pooling and observability, and it supports many databases.

- Install: Docker image, Homebrew, a binary from the GitHub releases page, or `npx @toolbox-sdk/server --config tools.yaml`
- First run: write a `tools.yaml` with a `sources` entry (your database) and `tools` entries (for example, a `count_rows` SQL tool). Then run `toolbox --tools-file tools.yaml`. It serves Streamable HTTP, reportedly at `http://127.0.0.1:5000/mcp`; confirm that against the official docs.
- The docs pages show different versions, so take the current release from GitHub.

**Rule of thumb:** choose DBHub for quick, open-ended questions, and MCP Toolbox when you want to limit exactly which queries can run, for example in production or with many users.

Sources:
- [bytebase/dbhub (GitHub)](https://github.com/bytebase/dbhub)
- [@bytebase/dbhub (npm)](https://npmjs.com/package/@bytebase/dbhub)
- [googleapis/mcp-toolbox (GitHub)](https://github.com/googleapis/mcp-toolbox)
- [MCP Toolbox docs – introduction](https://googleapis.github.io/genai-toolbox/documentation/introduction)
- [Glama review of MCP Toolbox](https://glama.ai/mcp/servers/@bytebase/dbhub/blob/93289367945f7526374faf76d82628c4e534e9f8/docs/blog/postgres-mcp-server-review-mcp-toolbox.mdx)