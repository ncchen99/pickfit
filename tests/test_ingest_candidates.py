"""scripts/ingest_candidates.py: the candidate list's tables as entries, and what the directory already has."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ingest_candidates", REPO / "scripts" / "ingest_candidates.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)

LIST = """\
## 2. 軟體類別
| 建議新類別 ID | 英文 / 中文名稱 | 涵蓋範圍 |
| `infra_devops` | **Infra & DevOps** | 容器（如 `lazydocker`） |

## 3. CLI / TUI
### A. 容器
| 名稱 | GitHub Repo | 授權 | 安裝 | 定位 |
| :--- | :--- | :--- | :--- | :--- |
| **lazydocker** | `jesseduffield/lazydocker` | MIT | Binary / `brew` | Docker TUI |
| **dust** / **duf** | `bootandy/dust` / `muesli/duf` | Apache-2.0 / MIT | Binary | 磁碟空間 |
| **go-task (`task`)** | `go-task/task` | MIT | Install script | Make 替代品 |

## 4. MCP Server
### A. 文件
| **MCP Server Fetch** | `modelcontextprotocol/servers` (`mcp-server-fetch`) | `uvx mcp-server-fetch` | 免 Key | 抓網頁 |
| **Time MCP** | `modelcontextprotocol/servers` (`mcp-server-time`) | `uvx mcp-server-time` | 離線 | 時間 |
| **Puppeteer MCP** | `@modelcontextprotocol/server-puppeteer` | `npx -y @modelcontextprotocol/server-puppeteer` | 免 Key | 瀏覽器 |

## 5. 網頁應用
### A. 工具
| **CyberChef** | `https://gchq.github.io/CyberChef/` (`gchq/CyberChef`) | `web_app` | 免登入 | 瑞士刀 |
| **Regex101** | `https://regex101.com` | `web_app` | 免登入 | 正規表達式 |
| **Kroki** | `https://kroki.io` (`yuzutech/kroki`) | `self_hosted_web_app` | Docker | 圖表 |
| **Glance** | `glanceapp/glance` | `self_hosted_web_app` | Docker | 儀表板 |
"""


def test_the_tables_become_entries_in_the_lists_order():
    entries = ingest.parse_list(LIST)
    assert [(e["section"], e["name"], e["repo"], e["flow"]) for e in entries] == [
        ("cli", "lazydocker", "jesseduffield/lazydocker", "repo"),
        ("cli", "dust", "bootandy/dust", "repo"),  # a row that names two tools is two entries
        ("cli", "duf", "muesli/duf", "repo"),
        ("cli", "go-task (`task`)", "go-task/task", "repo"),
        ("mcp", "MCP Server Fetch", "modelcontextprotocol/servers", "repo"),
        ("mcp", "Time MCP", "modelcontextprotocol/servers", "repo"),
        ("mcp", "Puppeteer MCP", None, "none"),  # a package name is not a repository
        ("web", "CyberChef", "gchq/CyberChef", "web"),
        ("web", "Regex101", None, "web"),
        ("web", "Kroki", "yuzutech/kroki", "repo"),  # self-hosted: a repository to install, not a site to visit
        ("web", "Glance", "glanceapp/glance", "repo"),
    ]
    assert [e["order"] for e in entries] == list(range(1, 12))
    assert entries[0]["group"] == "A. 容器" and entries[7]["url"] == "https://gchq.github.io/CyberChef/"
    assert entries[4]["packages"] == ["mcp-server-fetch"] and entries[9]["listed_as"] == "self_hosted_web_app"
    # The category table of section 2 is not a list of candidates.
    assert not any("Infra" in e["name"] for e in entries)


def test_what_the_directory_has_and_a_repository_named_twice_are_set_aside(tmp_path: Path):
    (tmp_path / "lazydocker.json").write_text(json.dumps({
        "slug": "lazydocker", "repo": {"full_name": "JesseDuffield/LazyDocker"}, "web": None}), encoding="utf-8")
    (tmp_path / "regex.json").write_text(json.dumps({
        "slug": "regex", "repo": None, "web": {"url": "https://www.regex101.com/"}}), encoding="utf-8")
    entries = ingest.parse_list(LIST)
    ingest.mark_known(entries, tmp_path)
    by_name = {e["name"]: e for e in entries}
    assert by_name["lazydocker"]["already_listed"] == "lazydocker"  # the repository's name, whatever its case
    assert by_name["Regex101"]["already_listed"] == "regex"  # the same address, however it is spelled
    assert by_name["CyberChef"]["already_listed"] is None and by_name["dust"]["already_listed"] is None
    assert by_name["MCP Server Fetch"]["same_repo_as"] is None
    assert by_name["Time MCP"]["same_repo_as"] == "MCP Server Fetch"  # one repository is one record

    class Args:
        section = None
        only = None
        limit = None

    repos = [e["name"] for e in ingest.chosen(entries, Args, "repo")]
    assert repos == ["dust", "duf", "go-task (`task`)", "MCP Server Fetch", "Kroki", "Glance"]
    assert [e["name"] for e in ingest.chosen(entries, Args, "web")] == ["CyberChef"]
    Args.section, Args.limit = ["cli"], 2
    assert [e["name"] for e in ingest.chosen(entries, Args, "repo")] == ["dust", "duf"]


def test_the_committed_list_parses_to_118_entries():
    entries = ingest.parse_list(ingest.LIST_MD.read_text(encoding="utf-8"))
    flows = {flow: sum(1 for e in entries if e["flow"] == flow) for flow in ("repo", "web", "none")}
    assert len(entries) == 118 and flows == {"repo": 99, "web": 18, "none": 1}
    assert len({e["repo"].lower() for e in entries if e["flow"] == "repo"}) == 93  # 7 rows share one repository
    assert ingest.submission_id("Owner/Repo") == ingest.submission_id("owner/repo")
