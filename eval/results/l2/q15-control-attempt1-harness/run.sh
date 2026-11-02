cd /work/whisper.cpp
ffmpeg -i /work/input/meeting.wav -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav
./build/bin/whisper-cli -m models/ggml-large-v3-turbo-q5_0.bin -f meeting.wav -l zh -t 8 --prompt "以下是一場會議的逐字稿，使用繁體中文與全形標點符號。" -osrt
opencc -i meeting.wav.srt -o meeting.zh-TW.srt -c s2twp.json
