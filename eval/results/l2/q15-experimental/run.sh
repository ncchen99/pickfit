cd /work/whisper.cpp
ffmpeg -i /work/input/meeting.wav -ar 16000 -ac 1 -c:a pcm_s16le meeting.wav
./build/bin/whisper-cli -m models/ggml-large-v3-turbo-q5_0.bin -f meeting.wav -l zh -t 4 --prompt "以下是繁體中文的會議逐字稿。" --vad -vm models/ggml-silero-v5.1.2.bin -osrt -of meeting
opencc -i meeting.srt -o meeting.zh-TW.srt -c s2twp.json
