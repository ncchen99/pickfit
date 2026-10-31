# 固定版本的工具與檔案（9.3 B.4）

校準與 L2 用的工具、模型、字典檔、字型等，一律從官方來源下載到沙盒，以版本號與 sha256 固定，**不 commit 進 repo**；這份清單與 sha256 才 commit。產生方式：`uv run python eval/runner/pins.py resolve`（讀官方的 metadata，記下來源公布的雜湊）→ `verify --confirm-spend`（在 Modal 的 dev image 沙盒裡下載每個檔、自己算 sha256、和公布的比對）→ `render`。選擇照各題 `needs.json` 的第一個（建議的）候選，版本取固定當天的最新版。原始資料在 [pins.json](pins.json)。

metadata 讀取：2026-10-31T14:18:08+08:00

| 項目 | 用在 | 版本 | sha256（沙盒內下載後算的） | 和來源公布的一致 | 大小 | 來源 |
|---|---|---|---|---|---|---|
| `claude-code` | q01 | `2.1.316` | `0b23c8ff73a58c263e88aa740bd8647723141f70dad089df63061858e019c4c3` | 是 | 29,356 | https://registry.npmjs.org/@anthropic-ai/claude-code/-/claude-code-2.1.316.tgz |
| `claude-code-claude-code-linux-x64` | q01 (Linux x64 part of @anthropic-ai/claude-code) | `2.1.316` | `745e1b196eb475161a185a00f5e1144d7324ec6094e21149eae719fa42481000` | 是 | 152,154,727 | https://registry.npmjs.org/@anthropic-ai/claude-code-linux-x64/-/claude-code-linux-x64-2.1.316.tgz |
| `codex-cli` | q01 | `0.166.0` | `67ee6f4069d9328956401f54ac202c20369233159058af9f4ec1af731b87f5b7` | 是 | 4,992 | https://registry.npmjs.org/@openai/codex/-/codex-0.166.0.tgz |
| `codex-cli-codex-linux-x64` | q01 (Linux x64 part of @openai/codex) | `0.166.0-linux-x64` | `cbc00a26d3d0e2ceefc4be8891f8a81ef1e349b3b175bc0ae308762bc001fd93` | 是 | 172,325,449 | https://registry.npmjs.org/@openai/codex/-/codex-0.166.0-linux-x64.tgz |
| `gemini-cli` | q01 | `0.66.0` | `269734d35287fbd8ed2982534258ecf4a95f184b6e06e6732e0d6850c28701d9` | 是 | 20,889,095 | https://registry.npmjs.org/@google/gemini-cli/-/gemini-cli-0.66.0.tgz |
| `gemini-cli-node-pty-linux-x64` | q01 (Linux x64 part of @google/gemini-cli) | `1.1.0` | `8d2e043026672f11aafd5f1a831f794a90d8fdd9d5e3255e8bc121df64b9d8e4` | 是 | 27,201 | https://registry.npmjs.org/@lydell/node-pty-linux-x64/-/node-pty-linux-x64-1.1.0.tgz |
| `nodejs` | q01 (runtime of the agent CLIs) | `v26.13.0` | `d28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997` | 是 | 34,083,252 | https://nodejs.org/dist/v26.13.0/node-v26.13.0-linux-x64.tar.xz |
| `openai` | q12, q14, q20 | `3.42.0` | `efb9d089ecf66c668289f647717389df98b40b954cd86d4fe54eddce39aabb3f` | 是 | 2,397,860 | https://files.pythonhosted.org/packages/c5/79/904afac12186d9ab9e3f731eb798e36dc0f5b991a557c4304b0a43e393c1/openai-3.42.0-py3-none-any.whl |
| `srt` | q15 | `3.5.3` | `4884315043a4f0740fd1f878ed6caa376ac06d70e135f306a6dc44632eed0cc0` | 是 | 28,296 | https://files.pythonhosted.org/packages/66/b7/4a1bc231e0681ebf339337b0cd05b91dc6a0d701fa852bb812e244b7a030/srt-3.5.3.tar.gz |
| `openai-whisper` | q15 (baseline) | `20250625` | `37a91a3921809d9f44748ffc73c0a55c9f366c85a3ef5c2ae0cc09540432eb96` | 是 | 803,191 | https://files.pythonhosted.org/packages/35/8e/d36f8880bcf18ec026a55807d02fe4c7357da9f25aebd92f85178000c0dc/openai_whisper-20250625.tar.gz |
| `fasttext` | q16 | `0.9.3` | `eb03f2ef6340c6ac9e4398a30026f05471da99381b307aafe2f56e4cd26baaef` | 是 | 73,439 | https://files.pythonhosted.org/packages/9f/3b/9a10b95eaf565358339162848863197c3f0a29b540ca22b2951df2d66a48/fasttext-0.9.3.tar.gz |
| `fonttools` | q05 (static Regular and Bold instances of the variable font) | `4.68.0` | `d76f8fdcb6936f5e1045a0c9dd721a4bf11112e60d1e243bfa1d39f06a8b3104` | 是 | 1,248,357 | https://files.pythonhosted.org/packages/35/74/4ea331ecc65ba05a58b1e4e8ccd604c8a15565f876dfbf93fc2a2ea2e22b/fonttools-4.68.0-py3-none-any.whl |
| `opencc-STCharacters.txt` | q11, q15 (shared OpenCC scorer) | `ver.1.4.2` | `a0ca1601c70648cf48b33c3c6210ccbecc5c7eead4b4c3daf76587ba2c03582b` | （來源沒公布） | 36,026 | https://raw.githubusercontent.com/BYVoid/OpenCC/ver.1.4.2/data/dictionary/STCharacters.txt |
| `opencc-STPhrases.txt` | q11, q15 (shared OpenCC scorer) | `ver.1.4.2` | `f6eab5e5c6dd7640597878d3dfc6599ee1279d2bc91561eadd8e114194e2925a` | （來源沒公布） | 1,007,834 | https://raw.githubusercontent.com/BYVoid/OpenCC/ver.1.4.2/data/dictionary/STPhrases.txt |
| `opencc-TSCharacters.txt` | q11, q15 (shared OpenCC scorer) | `ver.1.4.2` | `737c21c66f55a419dd6956cb3089476cdefc5a36877452631617696df1e5d925` | （來源沒公布） | 104,516 | https://raw.githubusercontent.com/BYVoid/OpenCC/ver.1.4.2/data/dictionary/TSCharacters.txt |
| `opencc-TWVariants.txt` | q11, q15 (shared OpenCC scorer) | `ver.1.4.2` | `e187278e119c427ca561180ac5da5b20e9f8681190458f35c327ce499e95a6a5` | （來源沒公布） | 986 | https://raw.githubusercontent.com/BYVoid/OpenCC/ver.1.4.2/data/dictionary/TWVariants.txt |
| `ollama-linux-amd64` | q18, q19, q20 | `v0.40.13` | `c9490e0f520be21271d969e6703f012268b1d39f8b70dd58854e5bfef7a75bb6` | 是 | 1,525,346,571 | https://github.com/ollama/ollama/releases/download/v0.40.13/ollama-linux-amd64.tar.zst |
| `ollama-model-llama3.2:3b` | q18, q19 (tool-calling fixture model) | `llama3.2:3b` | `dde5aa3fc5ffc17176b5e8bdc82f587b24b2678c6c66101bf7da77af9f7ccdff` | 是 | 2,019,377,376 | https://registry.ollama.ai/v2/library/llama3.2/blobs/sha256:dde5aa3fc5ffc17176b5e8bdc82f587b24b2678c6c66101bf7da77af9f7ccdff |
| `ollama-model-qwen2.5:0.5b` | q20 (small model) | `qwen2.5:0.5b` | `c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515` | 是 | 397,807,936 | https://registry.ollama.ai/v2/library/qwen2.5/blobs/sha256:c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515 |
| `hf-Qwen2.5-1.5B-Instruct-4bit-.gitattributes` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361` | （來源沒公布） | 1,519 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/.gitattributes |
| `hf-Qwen2.5-1.5B-Instruct-4bit-README.md` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `a92215db397e14395a74b850e8e83d4f15d87551ecc4adc0093b671d556308ce` | （來源沒公布） | 748 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/README.md |
| `hf-Qwen2.5-1.5B-Instruct-4bit-added_tokens.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `58b54bbe36fc752f79a24a271ef66a0a0830054b4dfad94bde757d851968060b` | （來源沒公布） | 605 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/added_tokens.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-config.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `636d3e2a15e8914b8cf82b05cc2288a811f9bd93c3bf1afc00cab701a70b47c0` | （來源沒公布） | 784 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/config.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-merges.txt` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5` | （來源沒公布） | 1,671,853 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/merges.txt |
| `hf-Qwen2.5-1.5B-Instruct-4bit-model.safetensors` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `0979f33d1bc58afcf696d13f57977644e7b11a6f0eec3e631d8e9463d18c0717` | 是 | 868,628,559 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/model.safetensors |
| `hf-Qwen2.5-1.5B-Instruct-4bit-model.safetensors.index.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `6b98634d5044f0e2ad45228a374f8445904e571f1082392d08a6ce54f5d517ca` | （來源沒公布） | 51,569 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/model.safetensors.index.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-special_tokens_map.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `76862e765266b85aa9459767e33cbaf13970f327a0e88d1c65846c2ddd3a1ecd` | （來源沒公布） | 613 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/special_tokens_map.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-tokenizer.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `a8506e7111b80c6d8635951a02eab0f4e1a8e4e5772da83846579e97b16f61bf` | （來源沒公布） | 7,031,673 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/tokenizer.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-tokenizer_config.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `f7c61e32b7a17d19bf8e7037dcb74079a833e53ea9801f24008cac68458f03b7` | （來源沒公布） | 7,308 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/tokenizer_config.json |
| `hf-Qwen2.5-1.5B-Instruct-4bit-vocab.json` | q12 (Mac, MLX fixture model) | `8b403126fc14f14cfc99bb4cfa72ecbc129ea677` | `ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910` | （來源沒公布） | 2,776,833 | https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/resolve/8b403126fc14f14cfc99bb4cfa72ecbc129ea677/vocab.json |
| `hf-Qwen2.5-1.5B-Instruct-GGUF-qwen2.5-1.5b-instruct-q4_k_m.gguf` | q13 (GGUF fixture) | `91cad51170dc346986eccefdc2dd33a9da36ead9` | `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e` | 是 | 1,117,320,736 | https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf |
| `docker-nginx:1.27-alpine` | q08 | `nginx:1.27-alpine` | `sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10（公布值，未下載）` | — | — | docker.io/library/nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 |
| `docker-redis:7.2-alpine` | q08 | `redis:7.2-alpine` | `sha256:2c933526722b4126a61d5c170f766dc159adf97682f0b1cbbc27b1666ba96d84（公布值，未下載）` | — | — | docker.io/library/redis:7.2-alpine@sha256:2c933526722b4126a61d5c170f766dc159adf97682f0b1cbbc27b1666ba96d84 |
| `font-NotoSansTC[wght].ttf` | q05 (CJK font embedded in fixture.pdf) | `3be1884c48c3` | `864727d210d54f2537bbe23b3a839436c3992af72de9322af5270897246bd44f` | （來源沒公布） | 11,941,968 | https://raw.githubusercontent.com/google/fonts/3be1884c48c3e45b52ecc725676a08f87776373e/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf |
| `torch-cpu` | q15 (baseline: openai-whisper's dependency) | `2.15.0+cpu` | `0955c7e3446326293f48af18fad67872fa31dee5a36a87690eb9e5be8b465be3` | 是 | 209,530,490 | https://download-r2.pytorch.org/whl/cpu/torch-2.15.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl |
| `whisper-small.pt` | q15 (baseline) | `small` | `9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794` | 是 | 483,617,219 | https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt |
| `fasttext-lid.176.ftz` | q16 (language identifier) | `lid.176.ftz` | `8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83` | （來源沒公布） | 938,013 | https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz |

下載與雜湊：2026-10-31T14:13:18+08:00，Modal sandbox sb-01M689CQ3ND7AVBXCJ55ZK1Q0X (pickfit-eval-l2-dev:4acdd7fff6ab)；2026-10-31T14:14:21+08:00，Modal sandbox sb-01M689GC9XRGNWFHQTMMS0D6YX (pickfit-eval-l2-dev:4acdd7fff6ab)；2026-10-31T14:18:15+08:00，Modal sandbox sb-01M689QHT516JNBT55WW9AHRVA (pickfit-eval-l2-dev:4acdd7fff6ab)。Docker 映像只記 Hub 公布的 digest（Mac 實跑時才 pull）。

備註：

- `nodejs`：latest LTS (Lithium) at the pin date
- `openai`：openai-3.42.0-py3-none-any.whl
- `srt`：srt-3.5.3.tar.gz
- `openai-whisper`：openai_whisper-20250625.tar.gz
- `fasttext`：fasttext-0.9.3.tar.gz
- `fonttools`：fonttools-4.68.0-py3-none-any.whl
- `ollama-linux-amd64`：zstd archive: unpacking needs zstd
- `ollama-model-llama3.2:3b`：model layer, 2019377376 bytes; the manifest's other layers are templates and licenses
- `ollama-model-qwen2.5:0.5b`：model layer, 397807936 bytes; the manifest's other layers are templates and licenses
- `font-NotoSansTC[wght].ttf`：google/fonts ships a variable font; make_pdf.py prints the weight it uses (q05 needs.json)
- `torch-cpu`：torch-2.15.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl
