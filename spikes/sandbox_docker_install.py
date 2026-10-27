#!/usr/bin/env python3
"""驗證 agent 的沙盒 spike：在全新、受限的 Docker 容器裡照 README 安裝真實的 CLI 工具，記錄每一步。

每個工具一個全新容器（python:3.12-slim），條件：
  非 root（uid 1000）、--cpus/--memory/--pids-limit、--cap-drop ALL、no-new-privileges、
  唯讀根目錄 + 有大小上限的 tmpfs（等於磁碟上限）、每步 `timeout -s KILL`（在容器內砍，不是只砍 docker exec）、
  容器本身最多活 --container-ttl 秒；沙盒內不放任何金鑰。
每步記錄：指令、exit code、秒數、stdout/stderr 尾端；另外從宿主機讀容器 netns 的 /proc/<pid>/net/tcp* 抽樣外連。
關鍵步驟失敗時走「讀錯誤 → 修正 → 重試」：規則表（代替 Muse Spark）給修法；
  一般修法在同一容器補一步再重試；缺系統函式庫則換成預裝常見函式庫的 base image，從全新容器重來（最多 3 次）。
最後依檢查表給分級（安裝驗證／功能驗證／推論驗證），輸出「實際可行的安裝步驟」，
並把範例指令的輸出用 Pillow 畫成 PNG（交給視覺模型用）。

工具（2026-10-28 挑選）：
  graphtty  近一年新專案、星數少；README 只寫 pip install → agent 改用 uv tool install（隔離環境）
  evnx      近一年新專案、星數少；README 列 5 種裝法 → 依優先順序選 pipx
  ripgrep   知名專案當對照；走 GitHub release 二進位 + sha256 驗證
  llama.cpp （--with-llm）本地 LLM 工具：release 二進位 + 1.2 MB 的 stories260K.gguf，啟動 llama-server 並打 /health、/v1/models、/v1/completions

執行：
    dockerd > /tmp/dockerd.log 2>&1 &          # daemon 沒在跑時
    python3 spikes/sandbox_docker_install.py                     # 三個 CLI 工具
    python3 spikes/sandbox_docker_install.py --with-llm          # 加上 llama.cpp 推論驗證
    python3 spikes/sandbox_docker_install.py --only evnx --out /tmp/pf-verify
    python3 spikes/sandbox_docker_install.py --local             # 沒有 Docker：本機 subprocess + 暫存 HOME（不是隔離！）
    python3 spikes/sandbox_docker_install.py --limits-test       # 防護自我檢查：fork bomb、塞磁碟、吃記憶體、吃 CPU、讀 env
環境需要 HTTPS 中間人 proxy 時（例如 Claude Code 雲端環境），--ca-bundle 指向 CA 檔，會唯讀掛進容器。
只用標準函式庫；Pillow 有裝才產生 PNG。不需要任何金鑰。
"""
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

IMAGE = "python:3.12-slim"
SBX_HOME = "/home/sbx"
CA_IN_CONTAINER = "/etc/pickfit-ca.crt"

GRAPH_JSON = {  # 取自 graphtty README 的 Quick start
    "nodes": [
        {"id": "start", "name": "User Input", "type": "entry"},
        {"id": "router", "name": "Router", "type": "condition"},
        {"id": "search", "name": "Web Search", "type": "tool"},
        {"id": "calc", "name": "Calculator", "type": "tool"},
        {"id": "respond", "name": "Respond", "type": "model"},
    ],
    "edges": [
        {"source": "start", "target": "router"},
        {"source": "router", "target": "search", "label": "search"},
        {"source": "router", "target": "calc", "label": "calc"},
        {"source": "search", "target": "respond"},
        {"source": "calc", "target": "respond"},
    ],
}

RG_VER = "15.2.0"
RG_TGZ = f"ripgrep-{RG_VER}-x86_64-unknown-linux-musl.tar.gz"
RG_URL = f"https://github.com/BurntSushi/ripgrep/releases/download/{RG_VER}/{RG_TGZ}"
LLAMA_TAG = "b11935"
LLAMA_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-ubuntu-x64.tar.gz"
GGUF_URL = "https://huggingface.co/ggml-org/models/resolve/main/tinyllamas/stories260K.gguf"

# 容器裡沒有 curl；下載一律用 python。sha256 有給就驗。
FETCH = ("python3 -c \"import sys,urllib.request,hashlib;u,o=sys.argv[1],sys.argv[2];"
         "d=urllib.request.urlopen(u,timeout=120).read();open(o,'wb').write(d);"
         "print(o,len(d),'bytes sha256',hashlib.sha256(d).hexdigest())\"")

TOOLS = {
    "graphtty": {
        "kind": "cli", "repo": "https://github.com/uipath/graphtty", "fame": "新（PyPI 首發 2026-02）、約 14 星",
        "readme_install": "pip install graphtty", "chosen": "uv tool install（官方套件管理器、隔離環境）",
        "steps": [
            ("setup", "python3 -m pip install --user --no-warn-script-location --disable-pip-version-check uv", 180),
            ("install", "uv tool install graphtty", 180),
            ("path", "command -v graphtty", 10),
            ("version", "graphtty --version", 20),
            ("help", "graphtty --help", 20),
            ("example", "graphtty graph.json", 30),
        ],
        "files": {"graph.json": json.dumps(GRAPH_JSON, indent=2)},
        "expect": {"exit": [0], "contains": ["User Input", "Router", "Respond"]},
    },
    "evnx": {
        "kind": "cli", "repo": "https://github.com/urwithajit9/evnx", "fame": "新（crates.io 首發 2026-02）、約 42 星",
        "readme_install": "curl|bash、brew tap、npm -g、pipx、cargo", "chosen": "pipx（README 推薦；不走 curl|bash）",
        "steps": [
            ("setup", "python3 -m pip install --user --no-warn-script-location --disable-pip-version-check pipx", 180),
            ("install", "python3 -m pipx install evnx", 180),
            ("path", "command -v evnx", 10),
            ("version", "evnx --version", 20),
            ("help", "evnx --help", 20),
            ("example", "evnx validate", 30),
        ],
        "files": {".env": 'DEBUG="False"\nSECRET_KEY=CHANGE_ME\nDATABASE_URL=postgres://app:app@localhost:5432/app\n'},
        # README：validate 有錯時 exit 1。這裡故意放兩個問題，exit 1 + 指出問題才算「輸出合理」
        "expect": {"exit": [0, 1], "contains_any": ["DEBUG", "CHANGE_ME", "placeholder"]},
    },
    "ripgrep": {
        "kind": "cli", "repo": "https://github.com/BurntSushi/ripgrep", "fame": "知名對照組（數萬星）",
        "readme_install": "brew/apt/cargo/GitHub release", "chosen": "GitHub release 二進位（musl 靜態）+ sha256",
        "steps": [
            ("install", f"mkdir -p ~/.local/bin ~/dl && cd ~/dl && {FETCH} {RG_URL} {RG_TGZ} && "
                        f"{FETCH} {RG_URL}.sha256 {RG_TGZ}.sha256 && sha256sum -c {RG_TGZ}.sha256 && "
                        f"tar xzf {RG_TGZ} && cp ripgrep-{RG_VER}-x86_64-unknown-linux-musl/rg ~/.local/bin/", 180),
            ("path", "command -v rg", 10),
            ("version", "rg --version", 20),
            ("help", "rg --help | head -5", 20),
            ("example", "rg -n 'def ' sample.py", 30),
        ],
        "files": {"sample.py": "import os\n\ndef hello():\n    return 'hi'\n\ndef bye():\n    pass\n"},
        "expect": {"exit": [0], "contains": ["3:def hello", "6:def bye"]},
    },
    "llama.cpp": {
        "kind": "llm", "repo": "https://github.com/ggml-org/llama.cpp", "fame": "知名；這裡測的是「本地 LLM 工具」的驗證流程",
        "readme_install": "brew/nix/winget/release/源碼", "chosen": f"GitHub release 二進位（{LLAMA_TAG} ubuntu-x64）",
        "steps": [
            ("install", f"mkdir -p ~/llama && cd ~/llama && {FETCH} {LLAMA_URL} llama.tgz && tar xzf llama.tgz && "
                        "ls -d */ | head -3", 300),
            ("path", "cd ~/llama && B=$(dirname $(find . -name llama-server -type f | head -1)) && "
                     "ln -sf $PWD/$B/llama-server ~/.local/bin/ && command -v llama-server", 20),
            ("version", "llama-server --version", 30),
            ("model", f"cd ~/llama && {FETCH} {GGUF_URL} stories260K.gguf", 120),
            ("serve", "cd ~/llama && nohup llama-server -m stories260K.gguf --host 127.0.0.1 --port 8080 -c 256 -t 2 "
                      "> server.log 2>&1 & P=$!; for i in $(seq 1 60); do python3 -c \"import urllib.request;"
                      "print(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).read().decode())\" 2>/dev/null && exit 0; "
                      "kill -0 $P 2>/dev/null || break; sleep 1; done; tail -20 server.log; exit 1", 90),
            ("models", "python3 -c \"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/v1/models').read().decode()[:400])\"", 20),
            ("example", "python3 -c \"import json,urllib.request;r=urllib.request.Request('http://127.0.0.1:8080/v1/completions',"
                        "data=json.dumps({'prompt':'Once upon a time','max_tokens':24,'temperature':0}).encode(),"
                        "headers={'Content-Type':'application/json'});d=json.load(urllib.request.urlopen(r,timeout=60));"
                        "print('TEXT:',repr(d['choices'][0]['text']));print('USAGE:',d.get('usage'))\"", 90),
        ],
        "files": {},
        "expect": {"exit": [0], "contains": ["TEXT:", "USAGE:"]},
    },
}


# ---------- 外連抽樣：從宿主機讀容器 netns 的 /proc/<pid>/net/tcp* ----------
def _hex_ip(h):
    if len(h) == 8:
        return socket.inet_ntop(socket.AF_INET, struct.pack("<I", int(h, 16)))
    b = bytes.fromhex(h)
    return socket.inet_ntop(socket.AF_INET6, b"".join(b[i:i + 4][::-1] for i in range(0, 16, 4)))


class ConnSampler(threading.Thread):
    """每 0.2 秒讀一次；短連線可能漏掉。正式版應改用 proxy／Modal 的 domain allowlist 日誌。"""

    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid, self.seen, self.stop = pid, {}, threading.Event()

    def run(self):
        while not self.stop.is_set():
            for f in ("tcp", "tcp6"):
                try:
                    lines = open(f"/proc/{self.pid}/net/{f}").read().splitlines()[1:]
                except OSError:
                    continue
                for ln in lines:
                    p = ln.split()
                    if p[3] not in ("01", "02"):  # ESTABLISHED / SYN_SENT
                        continue
                    ip, port = p[2].split(":")
                    addr = _hex_ip(ip)
                    if addr.startswith("127.") or addr in ("::1", "::ffff:127.0.0.1"):
                        continue
                    key = f"{addr}:{int(port, 16)}"
                    self.seen[key] = self.seen.get(key, 0) + 1
            time.sleep(0.2)


# ---------- 執行器 ----------
def sh(args, timeout=None):
    t = time.time()
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr, time.time() - t
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "host timeout", time.time() - t


class DockerBox:
    def __init__(self, name, a, image):
        self.name = name
        ca = a.ca_bundle if a.ca_bundle and os.path.exists(a.ca_bundle) else None
        env = {"HOME": SBX_HOME, "PATH": f"{SBX_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin",
               "PIP_NO_INPUT": "1", "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color", "COLUMNS": "100"}
        if ca:
            env.update({k: CA_IN_CONTAINER for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "CURL_CA_BUNDLE")})
        cmd = ["docker", "run", "-d", "--rm", "--name", name, "--label", "pickfit=verify",
               "--user", "1000:1000", f"--cpus={a.cpus}", f"--memory={a.memory}", f"--memory-swap={a.memory}",
               f"--pids-limit={a.pids}", "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "--ulimit", "nofile=1024:1024", "--read-only",
               "--tmpfs", "/tmp:rw,exec,nosuid,size=256m",
               "--tmpfs", f"{SBX_HOME}:rw,exec,nosuid,size={a.disk},uid=1000,gid=1000,mode=0755"]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        if ca:
            cmd += ["-v", f"{ca}:{CA_IN_CONTAINER}:ro"]
        cmd += [image, "sleep", str(a.container_ttl)]
        t = time.time()
        rc, out, err, _ = sh(cmd, timeout=120)
        if rc != 0:
            raise RuntimeError(f"docker run failed: {err.strip()}")
        self.start_s = time.time() - t
        sh(["docker", "exec", name, "mkdir", "-p", f"{SBX_HOME}/work", f"{SBX_HOME}/.local/bin"])
        self.pid = int(sh(["docker", "inspect", "-f", "{{.State.Pid}}", name])[1].strip())

    def put(self, rel, content):
        p = subprocess.run(["docker", "exec", "-i", self.name, "sh", "-c", f"cat > {SBX_HOME}/work/{shlex.quote(rel)}"],
                           input=content, text=True, capture_output=True)
        return p.returncode

    def run(self, cmd, timeout):
        # 在容器內用 timeout -s KILL 砍：只砍宿主機的 docker exec，容器裡的程序會繼續跑
        return sh(["docker", "exec", "-w", f"{SBX_HOME}/work", self.name, "timeout", "-s", "KILL", str(timeout), "bash", "-c", cmd],
                  timeout=timeout + 15)

    def disk_kb(self):
        rc, out, _, _ = self.run(f"du -sk {SBX_HOME} /tmp 2>/dev/null | awk '{{s+=$1}} END {{print s}}'", 30)
        return int(out.strip() or 0)

    def close(self):
        sh(["docker", "rm", "-f", self.name], timeout=60)


class LocalBox:
    """沒有 Docker 時的退路：暫存 HOME + rlimit。和宿主機共用網路、檔案系統、核心，不能拿來跑陌生程式。"""

    def __init__(self, name, a, image=None):
        self.home = tempfile.mkdtemp(prefix=f"pf-{name}-")
        os.makedirs(f"{self.home}/work"), os.makedirs(f"{self.home}/.local/bin")
        self.env = {k: v for k, v in os.environ.items() if k in ("HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "SSL_CERT_FILE")}
        # --user 裝進暫存 HOME/.local，不碰系統的 site-packages（Ubuntu 24.04 的 PEP 668 會擋 --user，這裡明確放行）
        self.env.update({"HOME": self.home, "PATH": f"{self.home}/.local/bin:/usr/local/bin:/usr/bin:/bin", "PIP_NO_INPUT": "1",
                         "PIP_BREAK_SYSTEM_PACKAGES": "1"})
        if a.ca_bundle and os.path.exists(a.ca_bundle):
            self.env.update({k: a.ca_bundle for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT")})
        self.mem = _parse_size(a.memory)
        self.start_s, self.pid = 0.0, None

    def _limits(self):
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (self.mem * 4, self.mem * 4))  # 虛擬記憶體，寬鬆
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
        os.setsid()

    def put(self, rel, content):
        open(os.path.join(self.home, "work", rel), "w").write(content)
        return 0

    def run(self, cmd, timeout):
        t = time.time()
        try:
            p = subprocess.run(["bash", "-c", cmd], cwd=f"{self.home}/work", env=self.env, capture_output=True,
                               text=True, timeout=timeout, preexec_fn=self._limits)
            return p.returncode, p.stdout, p.stderr, time.time() - t
        except subprocess.TimeoutExpired:
            return 124, "", "timeout", time.time() - t

    def disk_kb(self):
        return int(sh(["du", "-sk", self.home])[1].split()[0])

    def close(self):
        subprocess.run(["pkill", "-f", self.home], capture_output=True)
        shutil.rmtree(self.home, ignore_errors=True)


def _parse_size(s):
    m = re.fullmatch(r"(\d+)([kmg]?)", s.lower())
    return int(m.group(1)) * {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}[m.group(2)]


# ---------- 證據：把終端輸出畫成 PNG ----------
SGR_FG = {30: "#4d4d4d", 31: "#e06c75", 32: "#98c379", 33: "#e5c07b", 34: "#61afef", 35: "#c678dd", 36: "#56b6c2", 37: "#dcdfe4",
          90: "#7f848e", 91: "#ff7b86", 92: "#b5e890", 93: "#ffd68a", 94: "#82c4ff", 95: "#e09cf0", 96: "#7fd8e2", 97: "#ffffff"}
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/System/Library/Fonts/Menlo.ttc"]
CJK_FONTS = ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
             "/System/Library/Fonts/PingFang.ttc"]


def render_png(text, path, title=""):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return "Pillow 未安裝，跳過"
    font_path = next((f for f in FONTS if os.path.exists(f)), None)
    if not font_path:
        return "找不到等寬字型，跳過"
    size = 15
    font = ImageFont.truetype(font_path, size)
    cjk_path = next((f for f in CJK_FONTS if os.path.exists(f)), None)
    cjk = ImageFont.truetype(cjk_path, size) if cjk_path else font
    cw, lh = font.getlength("M"), int(size * 1.45)
    # 解析 SGR，其餘控制序列丟掉
    rows, cur, color, bold = [], [], "#dcdfe4", False
    for tok in re.split(r"(\x1b\[[0-9;?]*[A-Za-z])", text.replace("\r\n", "\n").replace("\t", "    ")):
        if tok.startswith("\x1b["):
            if tok.endswith("m"):
                for c in [int(x) for x in (tok[2:-1] or "0").split(";") if x.isdigit()]:
                    if c == 0:
                        color, bold = "#dcdfe4", False
                    elif c == 1:
                        bold = True
                    elif c in SGR_FG:
                        color = SGR_FG[c]
            continue
        for ch in re.sub(r"\x1b[^\[]|[\x00-\x08\x0b-\x1f]", "", tok):
            if ch == "\n":
                rows.append(cur)
                cur = []
            else:
                cur.append((ch, color, bold))
    rows.append(cur)
    rows = rows[:80]
    wide = lambda ch: ord(ch) > 0x2E80  # 粗略：CJK 與全形佔兩格
    cols = max([sum(2 if wide(c) else 1 for c, _, _ in r) for r in rows] + [40])
    W, H = int(max(min(cols, 140), len(title[:100]) + 8) * cw) + 40, len(rows) * lh + 60
    img = Image.new("RGB", (W, H), "#1e2127")
    d = ImageDraw.Draw(img)
    for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        d.ellipse((14 + i * 20, 12, 26 + i * 20, 24), fill=c)
    d.text((80, 9), title[:100], font=font, fill="#7f848e")
    y = 40
    for r in rows:
        x = 20
        for ch, col, b in r:
            f = cjk if wide(ch) else font
            d.text((x, y), ch, font=f, fill=col, stroke_width=1 if b else 0, stroke_fill=col)
            x += cw * (2 if wide(ch) else 1)
        y += lh
    img.save(path)
    return path


# ---------- 判定 ----------
def judge(tool, results):
    ok = {name: r["exit"] == 0 for name, r in results.items()}
    ex = results.get("example")
    exp = tool["expect"]
    example_ok = False
    if ex:
        out = ex["stdout"] + ex["stderr"]
        example_ok = ex["exit"] in exp["exit"] and all(s in out for s in exp.get("contains", [])) and \
            (not exp.get("contains_any") or any(s in out for s in exp["contains_any"]))
    install_ok = ok.get("install") and ok.get("path") and (ok.get("help") or ok.get("version"))
    if tool["kind"] == "llm":
        level = "推論驗證" if install_ok and ok.get("serve") and example_ok else ("安裝驗證" if install_ok else "未通過")
    else:
        level = "功能驗證" if install_ok and example_ok else ("安裝驗證" if install_ok else "未通過")
    return {"install_ok": bool(install_ok), "example_ok": example_ok, "level": level}


# ---------- 讀錯誤 → 修正 → 重試 ----------
# 正式版由 Muse Spark 讀「README + 失敗步驟的 stderr」輸出 {diagnosis, fix_cmd, needs_root}；這裡用規則表代替。
SYS_LIB_PKG = {"libgomp.so.1": "libgomp1", "libcurl.so.4": "libcurl4", "libssl.so.3": "libssl3"}
FIXES = [
    {"match": r"error while loading shared libraries: (lib[^:]+)", "kind": "image",
     "diagnosis": "缺系統函式庫；非 root 裝不了 → 換成預先裝好常見執行期函式庫的 base image，從全新容器重來"},
    {"match": r"Create it with `evnx sync`", "kind": "cmd", "cmd": "evnx sync",
     "diagnosis": "validate 需要 .env.example；錯誤訊息自己給了修法（evnx sync 從 .env 產生範本）"},
]
CRITICAL = {"setup", "install", "path", "help", "model", "serve", "example"}
SBX_IMAGE = "pickfit-sbx:py312"
SBX_DOCKERFILE = f"FROM {IMAGE}\nRUN apt-get update && apt-get install -y --no-install-recommends " \
                 f"{' '.join(sorted(set(SYS_LIB_PKG.values())))} git curl ca-certificates && rm -rf /var/lib/apt/lists/*\n"


def ensure_sbx_image():
    if sh(["docker", "image", "inspect", SBX_IMAGE])[0] == 0:
        return 0.0
    d = tempfile.mkdtemp(prefix="pf-img-")
    open(os.path.join(d, "Dockerfile"), "w").write(SBX_DOCKERFILE)
    t = time.time()
    rc, _, err, _ = sh(["docker", "build", "-q", "-t", SBX_IMAGE, d], timeout=600)
    shutil.rmtree(d, ignore_errors=True)
    if rc != 0:
        raise RuntimeError(f"build {SBX_IMAGE} failed: {err[-500:]}")
    return time.time() - t


def find_fix(text, used):
    for i, f in enumerate(FIXES):
        m = re.search(f["match"], text)
        if m and i not in used:
            fx = dict(f, id=i)
            if f["kind"] == "image":
                fx["needs"] = SYS_LIB_PKG.get(m.group(1), m.group(1))
            return fx
    return None


def run_once(slug, a, image, out_dir, attempt):
    tool = TOOLS[slug]
    name = f"pf-{re.sub(r'[^a-z0-9]', '', slug)}-{attempt}-{int(time.time())}"
    box = (LocalBox if a.local else DockerBox)(name, a, image)
    sampler = ConnSampler(box.pid) if box.pid else None
    if sampler:
        sampler.start()
    rec = {"attempt": attempt, "runner": "local" if a.local else f"docker {image}",
           "container_start_s": round(box.start_s, 2), "steps": [], "fixes": [], "verified_steps": [], "escalate": None}
    results, used = {}, set()
    try:
        for rel, content in tool["files"].items():
            box.put(rel, content)
        queue = list(tool["steps"])
        while queue:
            step, cmd, tmo = queue.pop(0)
            rc, out, err, dt = box.run(cmd, tmo)
            r = {"step": step, "cmd": cmd, "exit": rc, "seconds": round(dt, 2),
                 "stdout": out[-3000:], "stderr": err[-2000:], "timed_out": rc in (124, 137)}
            rec["steps"].append(r)
            exp_exit = tool["expect"]["exit"] if step == "example" else [0]
            last = (out or err).strip().splitlines()[-1][:90] if (out or err).strip() else ""
            print(f"  [{slug}#{attempt}] {step:8s} exit={rc:<3d} {dt:6.1f}s  {last}", flush=True)
            failed = rc not in exp_exit  # example 用 expect 判（evnx validate 抓到問題本來就 exit 1）；其他步驟 exit 0 才算過
            if step == "example" and rc in exp_exit:
                ex_text = out + err
                if not all(x in ex_text for x in tool["expect"].get("contains", [])) or \
                        (tool["expect"].get("contains_any") and not any(x in ex_text for x in tool["expect"]["contains_any"])):
                    failed = True
            if not failed:
                results[step] = r
                if step in ("setup", "install", "path", "model", "serve", "fix"):
                    rec["verified_steps"].append(cmd)
                continue
            results[step] = r
            if step not in CRITICAL:
                continue  # 例如 --version 不支援：記下來，不擋
            fx = find_fix(out + err, used)
            if not fx:
                if step in ("install", "setup"):
                    break
                continue
            used.add(fx["id"])
            rec["fixes"].append({"after_step": step, "diagnosis": fx["diagnosis"], "kind": fx["kind"],
                                 "action": fx.get("cmd") or f"image {SBX_IMAGE}（含 {fx.get('needs')}）"})
            if fx["kind"] == "image":
                rec["escalate"] = fx
                break
            queue = [("fix", fx["cmd"], 60), (step, cmd, tmo)] + queue
        rec["disk_kb"] = box.disk_kb()
    finally:
        if sampler:
            sampler.stop.set()
            sampler.join(1)
            rec["outbound"] = sampler.seen
        box.close()
    rec["verdict"] = judge(tool, results)
    ex = results.get("example")
    if ex:
        shot = os.path.join(out_dir, f"{re.sub(r'[^a-z0-9]', '_', slug)}.png")
        rec["screenshot"] = render_png(f"$ {ex['cmd'] if len(ex['cmd']) < 90 else ex['step']}\n{ex['stdout']}{ex['stderr']}",
                                       shot, f"{slug} · {rec['runner']} · attempt {attempt}")
    rec["total_s"] = round(sum(s["seconds"] for s in rec["steps"]) + rec["container_start_s"], 1)
    return rec


def verify(slug, a, out_dir, max_attempts=3):
    tool = TOOLS[slug]
    image, runs = a.image, []
    for attempt in range(1, max_attempts + 1):
        run = run_once(slug, a, image, out_dir, attempt)
        runs.append(run)
        if not run["escalate"] or a.local:
            break
        build_s = ensure_sbx_image()
        print(f"  [{slug}] escalate → {SBX_IMAGE}（build {build_s:.1f}s），全新容器重跑", flush=True)
        run["image_build_s"] = round(build_s, 1)
        image = SBX_IMAGE
    final = runs[-1]
    return {"slug": slug, "repo": tool["repo"], "fame": tool["fame"], "readme_install": tool["readme_install"],
            "chosen_method": tool["chosen"], "attempts": len(runs), "verdict": final["verdict"],
            "verified_install": {"image": final["runner"], "system_packages": [r["escalate"]["needs"] for r in runs if r["escalate"]],
                                 "steps": final["verified_steps"]},
            "fixes": [f for r in runs for f in r["fixes"]],
            "total_s": round(sum(r["total_s"] for r in runs) + sum(r.get("image_build_s", 0) for r in runs), 1),
            "runs": runs}


# ---------- 防護自我檢查：在同樣受限的容器裡故意做壞事，確認限制真的生效 ----------
PROBES = [
    ("whoami", "id; cat /proc/self/status | grep -E 'CapEff|NoNewPrivs'", 10),
    ("env_secrets", "env | grep -i -E 'key|token|secret|passw|proxy' || echo 'no secret-like env'", 10),
    ("write_rootfs", "touch /usr/local/bin/evil 2>&1; echo exit=$?", 10),
    ("disk_fill", "dd if=/dev/zero of=$HOME/fill bs=1M count=4000 2>&1 | tail -1; df -h $HOME | tail -1; rm -f $HOME/fill", 60),
    ("mem_hog", "python3 -c \"b=[]\nwhile True: b.append(bytearray(100*1024*1024))\" ; echo exit=$?", 60),
    ("fork_bomb", "python3 -c \"import os,time\nn=0\ntry:\n  while True:\n    if os.fork()==0: time.sleep(30); os._exit(0)\n    n+=1\n"
                  "except OSError as e: print('fork stopped after',n,'children:',e)\"; sleep 1; ps -e --no-headers 2>/dev/null | wc -l || true", 60),
    ("cpu_burn", "timeout 5 python3 -c \"import multiprocessing as m\nimport itertools\n"
                 "def f(_):\n  [x*x for x in itertools.count()]\nm.Pool(8).map(f,range(8))\"; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us /sys/fs/cgroup/cpu.max 2>/dev/null", 30),
    ("metadata_ip", "python3 -c \"import urllib.request;print(urllib.request.urlopen('http://169.254.169.254/',timeout=3).status)\" 2>&1 | tail -1", 15),
]


def limits_test(a):
    box = DockerBox(f"pf-probe-{int(time.time())}", a, a.image)
    out = []
    try:
        for name, cmd, tmo in PROBES:
            rc, o, e, dt = box.run(cmd, tmo)
            last = " | ".join((o + e).strip().splitlines()[-3:])[:220]
            out.append({"probe": name, "exit": rc, "seconds": round(dt, 1), "tail": last})
            print(f"| {name} | {rc} | {dt:.1f} | {last} |", flush=True)
    finally:
        box.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="逗號分隔，例如 graphtty,evnx")
    ap.add_argument("--with-llm", action="store_true", help="加跑 llama.cpp + stories260K.gguf")
    ap.add_argument("--local", action="store_true", help="不用 Docker，改用本機 subprocess（不是隔離）")
    ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--cpus", default="2")
    ap.add_argument("--memory", default="2g")
    ap.add_argument("--disk", default="1536m", help="HOME tmpfs 上限（也算進記憶體）")
    ap.add_argument("--pids", default="256")
    ap.add_argument("--container-ttl", type=int, default=900)
    ap.add_argument("--ca-bundle", default=os.environ.get("PICKFIT_CA_BUNDLE", "/root/.ccr/ca-bundle.crt"))
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "pickfit-verify"))
    ap.add_argument("--limits-test", action="store_true", help="只跑防護自我檢查（fork bomb、塞磁碟、吃記憶體…）")
    a = ap.parse_args()
    if not a.local and sh(["docker", "info"], timeout=20)[0] != 0:
        sys.exit("docker daemon 沒在跑；先啟動 dockerd，或加 --local")
    os.makedirs(a.out, exist_ok=True)
    if a.limits_test:
        print("| probe | exit | 秒 | 結果 |\n|---|---|---|---|")
        json.dump(limits_test(a), open(os.path.join(a.out, "limits.json"), "w"), ensure_ascii=False, indent=2)
        return
    slugs = a.only.split(",") if a.only else ["graphtty", "evnx", "ripgrep"] + (["llama.cpp"] if a.with_llm else [])
    if not a.local:
        t = time.time()
        sh(["docker", "pull", "-q", a.image], timeout=300)
        print(f"image ready in {time.time() - t:.1f}s")
    report = []
    for s in slugs:
        print(f"== {s}", flush=True)
        report.append(verify(s, a, a.out))
    path = os.path.join(a.out, "report.json")
    json.dump(report, open(path, "w"), ensure_ascii=False, indent=2)
    print("\n| 工具 | 方法 | 分級 | 嘗試 | 修正 | 安裝 s | 總秒數 | 磁碟 MB | 外連端點 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in report:
        last = r["runs"][-1]
        inst = next((s["seconds"] for s in last["steps"] if s["step"] == "install"), None)
        print(f"| {r['slug']} | {r['chosen_method']} | {r['verdict']['level']} | {r['attempts']} | {len(r['fixes'])} | "
              f"{inst} | {r['total_s']} | {last.get('disk_kb', 0) / 1024:.0f} | {len(last.get('outbound', {}))} |")
    print(f"\nreport: {path}")


if __name__ == "__main__":
    main()
