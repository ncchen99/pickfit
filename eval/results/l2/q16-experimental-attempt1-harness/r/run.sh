cd /work/llama.cpp
./build/bin/llama-server -hf bartowski/EuroLLM-9B-Instruct-GGUF:Q4_K_M \
  --jinja -c 4096 --temp 0 --host 127.0.0.1 --port 8080 > /results/server-$Q16_RUN.log 2>&1 &
SRV=$!
for i in $(seq 1 900); do curl -sf http://127.0.0.1:8080/health > /dev/null && break; kill -0 $SRV 2> /dev/null || break; sleep 2; done
cd /work
nohup python3 md2ptpt.py docs/ docs-pt-PT/ > translate.log 2>&1 &
wait $!
rc=$?
kill $SRV 2> /dev/null
exit $rc
