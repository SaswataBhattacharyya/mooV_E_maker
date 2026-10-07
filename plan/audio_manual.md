# Story Builder Audio Manual

This manual explains how to prepare recordings and validate the current audio-reconstruction and audio-effects features.

## Important current limitation

Audio Reconstruct currently accepts uploaded audio files. The browser microphone recorder, live ASR highlighting, automatic fragmented/continuous recording modes, and automatic dialogue advancement are not fully wired yet.

The current supported flow is:

1. Save a character calibration record.
2. Create a dialogue part.
3. Upload one audio take for that part.
4. Upload another take when repeating it.
5. Explicitly accept the preferred take.
6. Process accepted audio in Audio Studio or Audio Utilities.

Calibration currently stores the character sentence and settings. It does not yet attach the calibration audio file to the character record, so keep calibration recordings safely in the test folder for the later recorder/voice-map implementation.

## 1. Start and verify services

Confirm ComfyUI:

```bash
curl -sS http://127.0.0.1:3008/system_stats
```

Confirm Ollama:

```bash
curl -sS http://127.0.0.1:11434/api/tags
```

Start Story Builder:

```bash
cd /home/riki/web_dev/story_builder
./run_story_builder.sh
```

Open the application at:

```text
http://127.0.0.1:8080
```

Do not modify Docker or install packages for this test unless a specific failure proves it is necessary.

## 2. Prepare a recording folder

```bash
mkdir -p /home/riki/web_dev/story_builder/plan/audio_test
```

Inspect recording devices:

```bash
arecord -l
pactl list short sources
```

## 3. Record calibration samples

Use the same sentence for every character:

```text
This is my calibration sentence for the character voice.
```

Record Alice:

```bash
ffmpeg -f pulse \
  -i default \
  -t 8 \
  -ar 48000 \
  -ac 1 \
  -c:a pcm_s16le \
  /home/riki/web_dev/story_builder/plan/audio_test/alice_calibration.wav
```

Record Bob:

```bash
ffmpeg -f pulse \
  -i default \
  -t 8 \
  -ar 48000 \
  -ac 1 \
  -c:a pcm_s16le \
  /home/riki/web_dev/story_builder/plan/audio_test/bob_calibration.wav
```

If `default` is not available, replace it with a source name from `pactl list short sources`.

Verify both files:

```bash
ffprobe /home/riki/web_dev/story_builder/plan/audio_test/alice_calibration.wav
ffprobe /home/riki/web_dev/story_builder/plan/audio_test/bob_calibration.wav
```

## 4. Create a test project

The project can be created in the UI or with the API:

```bash
curl -sS -X POST http://127.0.0.1:3010/api/projects \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Audio Reconstruction Test",
    "story_input": "Alice and Bob discuss a mysterious signal in an abandoned station.",
    "automation_mode": false
  }'
```

Copy the returned project ID and set it in the shell:

```bash
export STORY_PROJECT_ID="PASTE_PROJECT_ID_HERE"
```

Verify the project:

```bash
curl -sS \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}" \
  | python3 -m json.tool
```

## 5. Save character calibration records

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/calibration" \
  -H 'Content-Type: application/json' \
  -d '{
    "character_name": "Alice",
    "sentence": "This is my calibration sentence for the character voice.",
    "settings": {
      "voice_overlay": "pending",
      "rvc_enabled": false,
      "pitch": 0,
      "depth": 0
    }
  }' | python3 -m json.tool
```

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/calibration" \
  -H 'Content-Type: application/json' \
  -d '{
    "character_name": "Bob",
    "sentence": "This is my calibration sentence for the character voice.",
    "settings": {
      "voice_overlay": "pending",
      "rvc_enabled": false,
      "pitch": 0,
      "depth": 0
    }
  }' | python3 -m json.tool
```

Check the saved session:

```bash
curl -sS \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct" \
  | python3 -m json.tool
```

## 6. Record dialogue takes

Use one file per highlighted dialogue part.

Alice's line:

```text
Did you hear that signal?
```

```bash
ffmpeg -f pulse -i default -t 8 -ar 48000 -ac 1 -c:a pcm_s16le \
  /home/riki/web_dev/story_builder/plan/audio_test/alice_line_001.wav
```

Bob's line:

```text
Yes. It is coming from below the station.
```

```bash
ffmpeg -f pulse -i default -t 8 -ar 48000 -ac 1 -c:a pcm_s16le \
  /home/riki/web_dev/story_builder/plan/audio_test/bob_line_002.wav
```

## 7. Create dialogue parts

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts" \
  -H 'Content-Type: application/json' \
  -d '{
    "part_id": "scene_001_line_001",
    "character_name": "Alice",
    "sequence": 1,
    "expected_text": "Did you hear that signal?"
  }' | python3 -m json.tool
```

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts" \
  -H 'Content-Type: application/json' \
  -d '{
    "part_id": "scene_001_line_002",
    "character_name": "Bob",
    "sequence": 2,
    "expected_text": "Yes. It is coming from below the station."
  }' | python3 -m json.tool
```

## 8. Upload takes

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts/scene_001_line_001/takes" \
  -F "recording=@/home/riki/web_dev/story_builder/plan/audio_test/alice_line_001.wav" \
  -F "transcript=Did you hear that signal?" | python3 -m json.tool
```

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts/scene_001_line_002/takes" \
  -F "recording=@/home/riki/web_dev/story_builder/plan/audio_test/bob_line_002.wav" \
  -F "transcript=Yes. It is coming from below the station." | python3 -m json.tool
```

Check the session and copy the returned `take_id` values:

```bash
curl -sS \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct" \
  | python3 -m json.tool
```

## 9. Test repeat and accept

Upload Alice's take again to simulate a repeat:

```bash
curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts/scene_001_line_001/takes" \
  -F "recording=@/home/riki/web_dev/story_builder/plan/audio_test/alice_line_001.wav" \
  -F "transcript=Did you hear that signal?" | python3 -m json.tool
```

This should create a new immutable take, such as `scene_001_line_001_take_002`, without deleting the first take.

Accept the preferred take:

```bash
export ALICE_TAKE_ID="PASTE_ALICE_TAKE_ID_HERE"

curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts/scene_001_line_001/accept/${ALICE_TAKE_ID}" \
  | python3 -m json.tool
```

```bash
export BOB_TAKE_ID="PASTE_BOB_TAKE_ID_HERE"

curl -sS -X POST \
  "http://127.0.0.1:3010/api/projects/${STORY_PROJECT_ID}/audio/reconstruct/parts/scene_001_line_002/accept/${BOB_TAKE_ID}" \
  | python3 -m json.tool
```

Expected project storage:

```text
storage/projects/<project-id>/audio/reconstruct/
├── session.json
├── takes/
│   ├── Alice_1_take_001.wav
│   ├── Alice_1_take_002.wav
│   └── Bob_2_take_001.wav
└── accepted/
    ├── Alice_1.wav
    └── Bob_2.wav
```

## 10. Test audio processing

Open:

```text
http://127.0.0.1:8080/audio-studio
```

Select the test project and upload an accepted WAV file. Test each operation separately:

- Voice Repair
- Voice Changer
- RVC Voice/Pitch
- Emotion Change
- Style Change

For Emotion and Style, provide the exact transcript. For RVC, select only a model shown by the application’s discovered RVC list. Do not type an unverified model name.

Noise cleanup has its own page:

```text
http://127.0.0.1:8080/audio-utilities
```

Choose **Noise Cleanup**, upload an accepted WAV file, run it, wait for completion, and play the output.

For every operation, verify:

1. The job changes from queued/running to completed.
2. An output audio player appears.
3. The output can be downloaded.
4. The output remains available after refreshing the page.

## 11. Test splitting and stitching

Create a combined test file:

```bash
ffmpeg \
  -i /home/riki/web_dev/story_builder/plan/audio_test/alice_line_001.wav \
  -i /home/riki/web_dev/story_builder/plan/audio_test/bob_line_002.wav \
  -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[out]" \
  -map "[out]" \
  -ar 48000 \
  -ac 1 \
  /home/riki/web_dev/story_builder/plan/audio_test/dialogue_combined.wav
```

In Audio Studio → Scene Surgery:

1. Upload `dialogue_combined.wav`.
2. Add two time ranges.
3. Run **Split**.
4. Confirm both clips appear.
5. Set a gap before the second clip, for example `0.5` seconds.
6. Run **Stitch**.
7. Play the stitched output.
8. Refresh and confirm the output remains available.

## 12. What to send before the live test

After preparing the recordings, send:

```text
Project ID:
Alice calibration file:
Bob calibration file:
Alice dialogue file:
Bob dialogue file:
```

Then say which scope to run:

```text
Uploaded reconstruction only
Uploaded reconstruction + Audio Studio effects
Full audio test including split, stitch, and final export
```

I will then run the API tests, Playwright UI checks, live ComfyUI jobs, output verification, and fix failures without changing unrelated workflows or Docker configuration.
