# Mac 題的 L2：q08、q11、q12（念誠親手做，`method: human`）

照 9.1 C7 依題號做（q08 → q11 → q12），兩組都做；每題的做法與判定在 `eval/fixtures/<題>/README.md`，起始環境與還原照 `eval/fixtures/_mac/CHECKLIST.md`（9.3 E：另開的乾淨 macOS 使用者帳號、只裝 Homebrew、每題前後各拍一次快照）。q11 的硬體與記憶體量法見 9.3 D。
下面是每個答案（第 1 次）原文裡的指令區塊，照原樣逐字執行；只能做第 5 節允許的調整（填版本號與佔位字、接受預設值）。截止 2026-11-03 12:00（台北）。

## q08 — 對照組

> # Recommendation: Colima + the open-source Docker CLI **Use [Colima](https://github.com/abiosoft/colima) (MIT license) with the Homebrew `docker`, `docker-compose`, and `docker-buildx` packages.** Colima runs a small Linux VM with the real Docker Engine (Moby) inside it, using A …

```bash
   brew install colima docker docker-compose docker-buildx
```

```json
   {
     "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
   }
```

```bash
# Start the VM: native arm64, VZ virtualization, Rosetta for any amd64 images, virtiofs mounts
colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu 4 --memory 8 --disk 100

# Colima creates and selects a "colima" docker context automatically
docker context ls

# Check that it works
docker run --rm hello-world
docker run --rm alpine uname -m        # should print aarch64
docker compose version
docker buildx version
```

```bash
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
```

完整答案：`eval/results/runs/run1/q08/control/attempt-1/answer.md`

## q08 — 實驗組

> I'd use **Colima** with the open-source Docker CLI and Compose from Homebrew. Your `docker` and `docker compose` commands stay the same; only the engine underneath changes. The tool I checked (pickfit) has no tested Docker Desktop replacement, so this advice comes from general k …

```sh
   brew install colima docker docker-compose docker-buildx
```

```json
   "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]
```

```sh
# Start the VM (adjust resources to suit; --vz-rosetta is only needed for amd64 images)
colima start --cpu 4 --memory 8 --disk 60 --vm-type vz --mount-type virtiofs --vz-rosetta

docker context ls                 # "colima" should be marked active
docker run --rm alpine uname -m   # should print: aarch64
docker compose version            # confirms the Compose plugin is found
docker compose up -d              # run this in one of your existing projects
```

```sh
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
```

```sh
  export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
```

完整答案：`eval/results/runs/run1/q08/experimental/attempt-1/answer.md`

## q11 — 對照組

> ## 推薦：用 **Ollama** 跑 **Llama-3-Taiwan-8B-Instruct**（Q4_K_M 量化版） **為什麼選這個組合：** - **Ollama** 免費、開源，終端機就能用，不用註冊帳號。下載模型後就能完全離線使用。 - **Llama-3-Taiwan-8B-Instruct** 是台大林彥廷團隊用大量繁體中文和台灣資料調整的模型，用詞偏台灣習慣，例如「軟體、資訊、影片」，不會講成「软件、信息、视频」。有使用者實測說它很守指令、中文也講得更自然，只是做摘要時偶爾會重複跳針。 - 8B 模型的 Q4 量化版大約 5 G …

```bash
ollama run hf.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF
```

```
FROM hf.co/phate334/Llama-3-Taiwan-8B-Instruct-Q4_K_M-GGUF
SYSTEM """你是一位台灣的助理。請一律使用繁體中文與台灣慣用語回答（例如：軟體、網路、影片、資訊、品質），絕對不要使用簡體字或中國大陸用語。"""
PARAMETER temperature 0.6
```

```bash
ollama create tw -f Modelfile
ollama run tw
```

```bash
brew install opencc
ollama run tw "你的問題" | opencc -c s2twp
```

完整答案：`eval/results/runs/run1/q11/control/attempt-1/answer.md`

## q11 — 實驗組

> 我只給建議，沒有在你的電腦上執行任何指令。 ## 主要推薦：Ollama ＋ 聯發科 Breeze 2（8B）＋ OpenCC 把簡體轉回繁體 前提假設：你的 Mac 裝了 Homebrew。如果沒有，可以改到 ollama.com 下載 Mac 版 App。 **為什麼這樣搭配：** - **Ollama**：免費，不用註冊，在終端機就能直接問，對 Apple Silicon 支援很好。 - **Llama-Breeze2-8B**：聯發科研究院專門為**繁體中文（台灣）**訓練的模型。用 Q4_K_M 版本（壓縮過的版本），模型檔大約 5 GB …

```bash
brew install ollama          # 安裝 Ollama
brew install opencc          # 安裝簡轉繁工具
brew services start ollama   # 讓 Ollama 在背景執行（也可以另開一個視窗跑 ollama serve）
ollama pull hf.co/DevQuasar-9/voidful.Llama-Breeze2-8B-Instruct-text-only-GGUF:Q4_K_M
```

```
FROM hf.co/DevQuasar-9/voidful.Llama-Breeze2-8B-Instruct-text-only-GGUF:Q4_K_M
SYSTEM 你是台灣的助理。一律使用繁體中文與台灣慣用詞（例如：軟體、影片、網路、資訊、程式），絕對不要使用簡體字或中國大陸用語。
PARAMETER temperature 0.6
```

```bash
ollama create tw -f Modelfile
```

```bash
# 互動式聊天（輸入 /bye 離開）
ollama run tw

# 單次提問，並保證輸出是台灣繁體
ollama run tw "用三句話解釋什麼是機器學習" | opencc -c s2twp.json
```

```bash
ollama pull hf.co/tetf/Llama-3.1-TAIDE-LX-8B-Chat-GGUF:Q4_K_M
```

完整答案：`eval/results/runs/run1/q11/experimental/attempt-1/answer.md`

## q12 — 對照組

> I recommend **`mlx-lm`**, Apple's own MLX package, which includes a built-in server called `mlx_lm.server`. It's MIT-licensed, terminal-only and needs no account. It provides OpenAI-style endpoints (`/v1/chat/completions`, `/v1/models`) and streams when a request includes `"strea …

```bash
# Option A: uv (recommended)
brew install uv            # or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install mlx-lm

# Option B: pipx
brew install pipx && pipx ensurepath
pipx install mlx-lm
```

```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write hello world in Rust"
```

```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --host 127.0.0.1 --port 8080
   # or a local folder:
   mlx_lm.server --model ~/models/my-mlx-model
```

```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"messages":[{"role":"user","content":"Say hi"}],"stream":true,"max_tokens":50}'
```

完整答案：`eval/results/runs/run1/q12/control/attempt-1/answer.md`

## q12 — 實驗組

> I recommend **mlx-lm**, the command-line package from Apple's ML Explore team. Its `mlx_lm.server` command runs a local OpenAI-compatible server. It meets each of your requirements: - **Uses MLX, not GGUF/llama.cpp:** it runs MLX-format models directly on Apple silicon. - **Term …

```bash
# Option A: uv (installs the CLI in its own isolated environment)
brew install uv
uv tool install mlx-lm

# Option B: pipx
brew install pipx && pipx ensurepath
pipx install mlx-lm

# Option C: a plain virtual environment
python3 -m venv ~/.venvs/mlx && source ~/.venvs/mlx/bin/activate
pip install -U mlx-lm
```

```bash
   mlx_lm.generate --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --prompt "Write a Python hello world"
```

```bash
   mlx_lm.server --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit --port 8080
   # or from a local folder:
   mlx_lm.server --model ~/models/my-mlx-model --port 8080
```

```bash
   curl -N http://127.0.0.1:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"mlx-community/Qwen2.5-Coder-7B-Instruct-4bit","messages":[{"role":"user","content":"Hi"}],"stream":true}'
```

```bash
mlx_lm.convert --hf-path Qwen/Qwen2.5-Coder-7B-Instruct -q --mlx-path ~/models/qwen-coder-7b-4bit
```

完整答案：`eval/results/runs/run1/q12/experimental/attempt-1/answer.md`

