#!/usr/bin/env bash
# Raw-HTTP checks against the spike server (start it first: node serve.mjs).
# Covers both protocol eras on ONE endpoint:
#   legacy = 2025-11-25 (initialize handshake, no per-request _meta)
#   modern = 2026-07-28 (no handshake, _meta + MCP headers on every request)
set -u
URL="${MCP_URL:-http://127.0.0.1:8787/mcp}"
ACCEPT='Accept: application/json, text/event-stream'
CT='Content-Type: application/json'
META='"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"curl","version":"0"},"io.modelcontextprotocol/clientCapabilities":{}}'
ARGS='{"need":"run an LLM offline on my laptop","os":"macos","offline_required":true}'

post() { # $1 = label, rest = extra curl args
  local label="$1"; shift
  echo "=== $label"
  curl -sS --noproxy '*' -D /dev/stderr -o - -X POST "$URL" -H "$CT" -H "$ACCEPT" "$@" 2> >(grep -i -E '^(HTTP/|content-type|mcp-session-id)' >&2)
  echo; echo
}

# --- legacy era ---
post "L1 legacy initialize (expect 200, NO Mcp-Session-Id header)" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'

post "L2 legacy tools/list with no session id (expect 200)" \
  -H 'MCP-Protocol-Version: 2025-11-25' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

post "L3 legacy tools/call find_software (expect 200, structuredContent)" \
  -H 'MCP-Protocol-Version: 2025-11-25' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"find_software\",\"arguments\":$ARGS}}"

# --- modern era (2026-07-28) ---
post "M1 modern server/discover (expect 200, supportedVersions)" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: server/discover' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":10,\"method\":\"server/discover\",\"params\":{$META}}"

post "M2 modern tools/list (expect 200, ttlMs/cacheScope)" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/list' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":11,\"method\":\"tools/list\",\"params\":{$META}}"

post "M3 modern tools/call find_software (expect 200, resultType complete)" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' -H 'Mcp-Name: find_software' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":12,\"method\":\"tools/call\",\"params\":{\"name\":\"find_software\",\"arguments\":$ARGS,$META}}"

post "M4 modern tools/call WITHOUT Mcp-Name header (expect 400, -32020 HeaderMismatch)" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":13,\"method\":\"tools/call\",\"params\":{\"name\":\"find_software\",\"arguments\":$ARGS,$META}}"

post "M5 bad input (need too short) (expect isError or -32602)" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' -H 'Mcp-Name: find_software' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":14,\"method\":\"tools/call\",\"params\":{\"name\":\"find_software\",\"arguments\":{\"need\":\"x\"},$META}}"

post "M6 unsupported version 2099-01-01 (expect 400, -32022)" \
  -H 'MCP-Protocol-Version: 2099-01-01' -H 'Mcp-Method: tools/list' \
  -d '{"jsonrpc":"2.0","id":15,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2099-01-01","io.modelcontextprotocol/clientCapabilities":{}}}}'
