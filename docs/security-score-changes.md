# 安全檢查上線前的分數變化（2026-11-03）

跑完 `pickfit security --all --write` 之後，和加入安全檢查之前（`d44a4113`）比較，列出分數有變化的 73 款軟體：寶藏在前，再依原本的分數由高到低排。這份是照協調 session 的審查修正後重掃的結果。

- 「最嚴重的一筆」是每款排序後的第一筆弱點；完整清單在每筆紀錄的 `security.findings`，工具頁也看得到。
- 分數變成 75.0 的幾款網頁，原本就有視覺缺陷：先套 79 分上限，再乘上視覺扣分的 0.95。

| 軟體 | 類型 | 品質 前 → 後 | 寶藏 | 弱點數 | 最嚴重的一筆 |
|---|---|---|---|---|---|
| flashagent | tui | 96.1 → 79.0 | 是 → **否** | 2 | crates:quinn-proto 0.11.17：RUSTSEC-2026-0340（HIGH，0.11.18 已修正） |
| praana | cli_tool | 96.1 → 79.0 | 是 → **否** | 5 | npm:seroval 1.5.6：GHSA-p6vx-979v-rg4c（CRITICAL，1.6.2 已修正） |
| pooprusteek | tui | 94.1 → 79.0 | 是 → **否** | 10 | crates:wasmtime 27.0.0：GHSA-897f-g5gm-fmxm（CRITICAL，36.0.19 已修正） |
| privateer-agent | cli_tool | 94.1 → 79.0 | 是 → **否** | 9 | npm:brace-expansion 5.0.9：GHSA-6j4f-fj2g-mc7p（HIGH，5.0.10 已修正） |
| jp-lit-mcp | mcp_server_or_agent_plugin | 92.2 → 79.0 | 是 → **否** | 1 | npm:zod 3.25.76：GHSA-mrhx-c7xc-m3w5（HIGH，4.6.6 已修正） |
| nlm-memory | cli_tool | 92.2 → 79.0 | 是 → **否** | 8 | npm:adm-zip 0.5.18：GHSA-7q85-xj36-vmfc（HIGH，0.6.1 已修正） |
| phantom | cli_tool | 92.2 → 79.0 | 是 → **否** | 4 | npm:@modelcontextprotocol/sdk 1.31.0：GHSA-22jm-h49p-29qw（HIGH，1.32.0 已修正） |
| batch-file-renamer | web_app | 91.1 → 79.0 | 是 → **否** | 6 | npm:react-router 7.12.0：GHSA-49rj-9fvp-4h2h（HIGH，7.14.2 已修正） |
| image-comparison-tool | web_app | 91.1 → 79.0 | 是 → **否** | 48 | npm:next 16.0.10：GHSA-2464-fhr4-w9xw（CRITICAL，16.4.1 已修正） |
| xipher | web_app | 91.1 → 79.0 | 是 → **否** | 1 | go:github.com/go-jose/go-jose/v4 v4.1.5：GHSA-mgcc-cww5-fp2q（HIGH，4.1.6 已修正） |
| all-code | cli_tool | 90.2 → 79.0 | 是 → **否** | 8 | crates:zip 8.6.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| pulsechain-mcp | mcp_server_or_agent_plugin | 90.2 → 79.0 | 是 → **否** | 5 | npm:@modelcontextprotocol/node 2.0.0：GHSA-f897-62hf-6gxq（HIGH，2.1.0 已修正） |
| rustcode | tui | 90.2 → 79.0 | 是 → **否** | 6 | crates:zip 2.4.2：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| vortelio | server_daemon | 89.3 → 79.0 | 是 → **否** | 13 | go:golang.org/x/crypto v0.51.0：GHSA-5cgq-3rg8-m6cv（CRITICAL，0.52.0 已修正） |
| dreamd | mcp_server_or_agent_plugin | 88.3 → 79.0 | 是 → **否** | 2 | crates:rmcp 1.7.0：GHSA-33f5-2c5q-wgwj（HIGH，2.0.0 已修正） |
| lumen | cli_tool | 88.3 → 79.0 | 是 → **否** | 1 | crates:rustls-webpki 0.103.10：GHSA-82j2-j2ch-gfr8（HIGH，0.103.13 已修正） |
| mithril | server_daemon | 87.2 → 79.0 | 是 → **否** | 2 | crates:quinn-proto 0.11.17：RUSTSEC-2026-0340（HIGH，0.11.18 已修正） |
| mergegate | self_hosted_web_app | 86.6 → 79.0 | 是 → **否** | 2 | crates:wasmtime 48.0.6：GHSA-mghf-wjfp-p5xm（CRITICAL，48.0.7 已修正） |
| free-online-tools-for-video-audio-pdfs-images-and-ai | web_app | 86.5 → 75.0 | 是 → **否** | 25 | npm:dompurify 3.4.12：GHSA-cg2g-xh64-v4q7（CRITICAL，3.4.17 已修正） |
| paintracker-ca | web_app | 86.5 → 75.0 | 是 → **否** | 41 | npm:next 16.2.4：GHSA-2464-fhr4-w9xw（CRITICAL，16.4.1 已修正） |
| goatedcontext | cli_tool | 83.1 → 79.0 | 是 → **否** | 1 | npm:zod 3.25.76：GHSA-mrhx-c7xc-m3w5（HIGH，4.6.6 已修正） |
| rvpm | cli_tool | 83.1 → 79.0 | 是 → **否** | 7 | crates:zip 6.0.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| fetchira | cli_tool | 82.7 → 79.0 | 是 → **否** | 4 | crates:quinn-proto 0.11.15：RUSTSEC-2026-0340（HIGH，0.11.18 已修正） |
| medha-agent | tui | 81.5 → 79.0 | 是 → **否** | 2 | crates:quinn-proto 0.11.16：RUSTSEC-2026-0340（HIGH，0.11.18 已修正） |
| mati | cli_tool | 80.8 → 79.0 | 是 → **否** | 13 | crates:zip 7.2.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| homebotbuild | self_hosted_web_app | 80.1 → 79.0 | 是 → **否** | 22 | npm:next 16.2.12：GHSA-2464-fhr4-w9xw（CRITICAL，16.4.1 已修正） |
| indexio | cli_tool | 100.0 → 79.0 | 否 | 7 | crates:gix 0.66.0：GHSA-f26g-jm89-4g65（HIGH，0.83.0 已修正） |
| tianshu-mcp | mcp_server_or_agent_plugin | 96.5 → 79.0 | 否 | 7 | npm:basic-ftp 5.3.1：GHSA-c475-qrg2-pj4r（HIGH，6.2.1 已修正） |
| nadzoring | cli_tool | 96.1 → 79.0 | 否 | 12 | pypi:aiohttp 3.13.5：GHSA-2g87-pp6c-29x5（HIGH，3.14.4 已修正） |
| codex-multi-auth | cli_tool | 94.8 → 79.0 | 否 | 5 | npm:undici 8.11.2：GHSA-2m5v-pch6-74hx（HIGH，8.12.2 已修正） |
| martty | tui | 94.8 → 79.0 | 否 | 4 | npm:undici 6.29.0：GHSA-2m5v-pch6-74hx（HIGH，6.29.1 已修正） |
| loci | mcp_server_or_agent_plugin | 94.1 → 79.0 | 否 | 4 | pypi:chromadb 1.5.9：GHSA-36p7-vc44-83pf（CRITICAL，尚無修正） |
| mnemoteca | cli_tool | 94.1 → 79.0 | 否 | 41 | npm:protobufjs 7.5.4：GHSA-xq3m-2v4x-88gg（CRITICAL，7.5.5 已修正） |
| eidetic-engine-cli | cli_tool | 93.7 → 79.0 | 否 | 2 | crates:pulldown-cmark 0.13.4：RUSTSEC-2026-0414（HIGH，0.13.5 已修正） |
| my-claude-code | server_daemon | 93.7 → 79.0 | 否 | 2 | crates:quick-xml 0.38.4：RUSTSEC-2026-0194（HIGH，0.41.0 已修正） |
| eullm | server_daemon | 92.2 → 79.0 | 否 | 2 | crates:quinn-proto 0.11.14：GHSA-4w2j-m93h-cj5j（HIGH，0.11.15 已修正） |
| openlore | cli_tool | 92.2 → 79.0 | 否 | 3 | npm:sharp 0.33.5：GHSA-f88m-g3jw-g9cj（HIGH，0.35.0 已修正） |
| podiom | server_daemon | 92.2 → 79.0 | 否 | 2 | npm:dompurify 3.4.16：GHSA-cg2g-xh64-v4q7（CRITICAL，3.4.17 已修正） |
| xrat | cli_tool | 92.2 → 79.0 | 否 | 13 | crates:zip 7.2.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| daidocs | mcp_server_or_agent_plugin | 92.0 → 79.0 | 否 | 1 | npm:zod 3.25.76：GHSA-mrhx-c7xc-m3w5（HIGH，4.6.6 已修正） |
| longhand | cli_tool | 91.2 → 79.0 | 否 | 3 | pypi:chromadb 0.6.3：GHSA-36p7-vc44-83pf（CRITICAL，尚無修正） |
| injection-monitor | web_app | 91.1 → 79.0 | 否 | 27 | npm:next 15.4.4：GHSA-2464-fhr4-w9xw（CRITICAL，15.5.28 已修正） |
| svelte-rs | web_app | 91.1 → 79.0 | 否 | 19 | npm:axios 1.18.0：GHSA-3pq3-5fj3-cg6v（HIGH，1.20.0 已修正） |
| wshm | cli_tool | 90.9 → 79.0 | 否 | 5 | npm:dompurify 3.4.15：GHSA-cg2g-xh64-v4q7（CRITICAL，3.4.17 已修正） |
| llm-router | cli_tool | 90.2 → 79.0 | 否 | 1 | pypi:filelock 3.32.7：GHSA-v4x8-3wr5-3wq8（HIGH，4.2.1 已修正） |
| c0mpute | cli_tool | 89.6 → 79.0 | 否 | 3 | crates:hickory-proto 0.25.2：GHSA-3v94-mw7p-v465（HIGH，尚無修正） |
| rms-memory-mcp | mcp_server_or_agent_plugin | 88.6 → 79.0 | 否 | 5 | crates:pulldown-cmark 0.13.5：RUSTSEC-2026-0433（HIGH，0.13.6 已修正） |
| mex | cli_tool | 88.1 → 79.0 | 否 | 5 | npm:@simple-git/argv-parser 1.1.1：GHSA-v5rq-49vh-5v5c（CRITICAL，2.0.1 已修正） |
| gamevault | web_app | 87.3 → 79.0 | 否 | 6 | npm:nanoid 3.3.11：GHSA-28wg-ghj8-5hjv（HIGH，3.3.16 已修正） |
| ogcode | cli_tool | 87.3 → 79.0 | 否 | 49 | go:github.com/lxc/incus/v6 v6.23.0：GO-2026-5798（CRITICAL，尚無修正） |
| detent | cli_tool | 87.0 → 79.0 | 否 | 14 | go:github.com/labstack/echo/v4 v4.15.1：GHSA-cxf3-9h37-7rr8（CRITICAL，4.16.1 已修正） |
| frink | cli_tool | 87.0 → 79.0 | 否 | 1 | npm:zod 4.4.3：GHSA-mrhx-c7xc-m3w5（HIGH，4.6.6 已修正） |
| gokin | cli_tool | 86.8 → 79.0 | 否 | 7 | go:github.com/ollama/ollama v0.20.3：GO-2025-4251（CRITICAL，尚無修正） |
| npassword | web_app | 86.5 → 75.0 | 否 | 26 | npm:next 15.1.3：GHSA-2464-fhr4-w9xw（CRITICAL，15.5.28 已修正） |
| lox | cli_tool | 85.4 → 79.0 | 否 | 9 | crates:zip 2.4.2：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| leviath | cli_tool | 84.7 → 79.0 | 否 | 3 | crates:pulldown-cmark 0.13.5：RUSTSEC-2026-0433（HIGH，0.13.6 已修正） |
| cortex | cli_tool | 84.5 → 79.0 | 否 | 1 | npm:zod 3.25.76：GHSA-mrhx-c7xc-m3w5（HIGH，4.6.6 已修正） |
| exomem | mcp_server_or_agent_plugin | 84.1 → 79.0 | 否 | 2 | pypi:filelock 3.32.7：GHSA-v4x8-3wr5-3wq8（HIGH，4.2.1 已修正） |
| turbollm | cli_tool | 83.2 → 79.0 | 否 | 13 | npm:brace-expansion 5.0.6：GHSA-3jxr-9vmj-r5cp（HIGH，5.0.7 已修正） |
| overtchat | self_hosted_web_app | 83.1 → 79.0 | 否 | 39 | pypi:pillow 12.3.0：GHSA-332p-7hrc-92wf（CRITICAL，13.0.0 已修正） |
| atmem | cli_tool | 82.7 → 79.0 | 否 | 2 | pypi:cryptography 48.0.1：GHSA-g6cj-pr64-35w5（HIGH，50.0.0 已修正） |
| spyc | tui | 82.7 → 79.0 | 否 | 3 | crates:pulldown-cmark 0.13.5：RUSTSEC-2026-0433（HIGH，0.13.6 已修正） |
| ajean | server_daemon | 82.5 → 79.0 | 否 | 9 | go:golang.org/x/crypto v0.51.0：GHSA-5cgq-3rg8-m6cv（CRITICAL，0.52.0 已修正） |
| supercli | cli_tool | 81.1 → 79.0 | 否 | 60 | npm:proxy-addr 2.0.7：GHSA-jqcg-44mw-7w3h（CRITICAL，2.0.8 已修正） |
| future-os | cli_tool | 80.8 → 79.0 | 否 | 4 | crates:pulldown-cmark 0.13.4：RUSTSEC-2026-0414（HIGH，0.13.5 已修正） |
| wtfi2 | cli_tool | 80.8 → 79.0 | 否 | 2 | crates:quinn-proto 0.11.16：RUSTSEC-2026-0340（HIGH，0.11.18 已修正） |
| gambletan-cortex | mcp_server_or_agent_plugin | 80.7 → 79.0 | 否 | 7 | crates:openssl 0.10.75：GHSA-8c75-8mhr-p7r9（HIGH，0.10.78 已修正） |
| opencode-swarm | mcp_server_or_agent_plugin | 80.7 → 79.0 | 否 | 5 | npm:toml 4.3.0：GHSA-4qx8-w7c3-pj3p（HIGH，5.0.1 已修正） |
| waywallen | desktop_app | 80.3 → 79.0 | 否 | 4 | crates:zip 2.6.1：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| lazydb | tui | 80.1 → 79.0 | 否 | 8 | crates:zip 6.0.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
| nerva | cli_tool | 79.7 → 79.0 | 否 | 20 | go:golang.org/x/crypto v0.51.0：GHSA-5cgq-3rg8-m6cv（CRITICAL，0.52.0 已修正） |
| hief | mcp_server_or_agent_plugin | 79.5 → 79.0 | 否 | 1 | crates:rustls-webpki 0.102.8：GHSA-82j2-j2ch-gfr8（HIGH，0.103.13 已修正） |
| xmatrix | cli_tool | 79.5 → 79.0 | 否 | 6 | crates:zip 8.6.0：GHSA-m665-v7pm-7grj（CRITICAL，9.0.5 已修正） |
