z_turbo_text_to_image= 

High-fashion editorial tight portrait, ultra-crisp detail
clean modern sheen, faint high-key digital gloss
hyper-saturated pale-lilac flat sky background
harsh unfiltered desert noon glare
female model standing, subtle head tilt to the side
calm yet piercing direct eye contact, quiet self-assured intensity
expression of someone who just solved a complex node chain perfectly
glossy dark-chocolate brown medium-length hair
soft centre-part, slight forward-falling fringe, air-dried natural texture
hair tucked behind one ear revealing matte-black wireless earbud
thin matte-black sports headband pushed up on forehead
off-white/bone technical half-zip mock-neck pullover
prominent tiny tonal micro-raised “comfy” monospaced embroidery on right chest
layered semi-sheer pale-grey long-sleeve base tee
very faint terminal-green command-line micro-grid subtly visible through top
low-rise wide-leg washed charcoal parachute-nylon track pants, tonal drawcord, slightly open zip cargo pocket showing phone edge, exposed toned midriff + iliac line

qwen 2512

Urban alleyway at dusk. Tall, statuesque high-fashion model striding elegantly, mid distant full body shot from an angular perspective, cinematic/editorial with bold contrasts and tactile materials. They wear a rose-gold metallic trench coat with deconstructed elements over a black long-sleeved turtleneck with subtle texture; paired with forest-green pleated pants with raw hems and a soft texture. Long braided dark hair, medium complexion. They carry a vibrant yellow designer handbag with geometric details and a structured silhouette. White architectural sneakers with bold geometric cutouts. Bold, high-contrast, tactile, urban-grit meets high-fashion impact, extreme clarity, extreme layering, post-processing with transparent light-transmitting ultra-smooth high-definition film effect, removing all noise and grain, removing all blur, removing all vintage feel, removing all roughness, drawn with 32K pixel precision, unparalleled fine line drawing of every single detail, the entire image like a brand new photograph, photorealistic

qwen 2511

Place two characters naturally into the lake scene.
Use image2 as the female character and image3 as the male character.
Scene setup:
A calm lake with a large fallen log near the shore. Maintain original lighting, reflections, and perspective of the environment.
Character placement:
- Female character is sitting on top of the log, slightly off-center, facing diagonally toward the lake.
- She is holding a phone in a natural selfie position, as if taking a picture.
- Her posture is relaxed, balanced on the log.
- Male character is positioned on the ground, leaning against the same log below her.
- He is lying or resting with his back supported by the log.
- His head is tilted upward, looking at the sky/clouds.
Interaction and composition:
- Both characters should feel part of the same moment but not directly interacting.
- Maintain realistic scale, perspective, and depth relative to the log and environment.
- Ensure shadows and lighting match the harsh outdoor daylight.

Clothing:
Both characters are wearing trekking / outdoor casual outfits, consistent with a hiking scenario.
Style:
Photorealistic, natural integration, consistent lighting and color grading.
No distortion, no floating artifacts, no unnatural blending.


TTS-audio SRT prompt -


1
00:00:01,000 --> 00:00:06,500
Hello I'm Tony the narrator! Here is Alice:
[En:Alice] Hey Tony! ,,, Bob... can you speak German for us?

2
00:00:05,850 --> 00:00:08,500
[German:Bob] Ja natürlich! Ich spreche gerne Deutsch.

3
00:00:08,500 --> 00:00:18,000
[USA:Alice] Wow that's cool, you are the man Bob! [Bob] Thanks! I know I'm amazing! [pause:500ms] 
Hum, he is a showman... I can do that too! 

4
00:00:16,100 --> 00:00:20,000
[En:Alice] And what about Norwegian, can you speak that?

5
00:00:17,100 --> 00:00:21,500
[Norwegian:Bob] Hei Alice an Tony! Jeg snakker norsk også!

6
00:00:21,000 --> 00:00:22,500
[En:Alice] You're talking over me Bob, calm down!

7
00:00:22,100 --> 00:00:24,500
[En:Bob] Sorry Alice, I got too excited about languages.

8
00:00:24,500 --> 00:00:29,500
The narrator can switch languages too.
[German:] Ich kann auch Deutsch sprechen, natürlich!

9
00:00:29,500 --> 00:00:36,500
[pause:1500ms] And that's ChatterBox with SRT multilingual character conversations and overlaps!!.


Prompt to emotion and voice change center-

  JSON format, preferred, from ./TTS-Audio-Suite/utils/audio/scene_splitter.py:50:

  [
    {
      "start": 5.0,
      "end": 10.0,
      "text": "Make this line sad",
      "edit_type": "emotion",
      "emotion": "sad"
    },
    {
      "start": 12.5,
      "end": 15.0,
      "text": "Convert this to another voice",
      "edit_type": "voice",
      "voice": "David_Attenborough CC3.wav"
    }
  ]

  Or wrapped as:

  {
    "edits": [
      {
        "start": 5.0,
        "end": 10.0,
        "text": "Make this line sad",
        "edit_type": "emotion",
        "emotion": "sad"
      }
    ]
  }


root@df21e535a0c89b35:~/Art_ist_min# source venv/bin/activate
(venv) root@df21e535a0c89b35:~/Art_ist_min# python3 ComfyUI/custom_nodes/TTS-Audio-Suite/scripts/split_scene_audio.py \
    --audio assets/ComfyUI_temp_dcuqg_00001_.flac \
    --instructions assets/test_scene_edits.json \
    --output-dir assets/scene_test_run \
    --transcript assets/test.txt


(venv) root@df21e535a0c89b35:~/Art_ist_min# python3 ComfyUI/custom_nodes/TTS-Audio-Suite/scripts/partition_scene_edits.py \
    --instructions assets/scene_test_run/test_scene_edits_enriched.json \
    --output-dir assets/scene_test_run
{
  "step_json_path": "/root/Art_ist_min/assets/scene_test_run/test_scene_edits_enriched_step.json",
  "voice_json_path": "/root/Art_ist_min/assets/scene_test_run/test_scene_edits_enriched_voice.json",
  "unsupported_json_path": "/root/Art_ist_min/assets/scene_test_run/test_scene_edits_enriched_unsupported.json",
  "step_count": 5,
  "voice_count": 0,
  "unsupported_count": 0
}




  cd /home/saswata/web_dev/website_design/Agentic_art_bare_min

  mkdir -p assets/scene_test_run

  python3 TTS-Audio-Suite/scripts/split_scene_audio.py \
    --audio assets/ComfyUI_temp_dcuqg_00001_.flac \
    --instructions assets/test_scene_edits.json \
    --output-dir assets/scene_test_run \
    --transcript assets/test.txt

  python3 TTS-Audio-Suite/scripts/partition_scene_edits.py \
    --instructions assets/scene_test_run/test_scene_edits_enriched.json \
    --output-dir assets/scene_test_run

cd /root/Art_ist_min/ComfyUI/custom_nodes/TTS-Audio-Suite

  PYTHONPATH=/root/Art_ist_min/ComfyUI:. \
  python3 -m scripts.edit_scene_clips \
    --clips-dir /root/Art_ist_min/assets/scene_test_run \
    --instructions /root/Art_ist_min/assets/scene_test_run/test_scene_edits_enriched_step.json \
    --output-dir /root/Art_ist_min/assets/scene_test_run \
    --keep-originals

  After that, concat with:
cd /root/Art_ist_min/ComfyUI/custom_nodes/TTS-Audio-Suite

  PYTHONPATH=/root/Art_ist_min/ComfyUI:. \
  python3 -m scripts.concat_scene_audio \
    --clips-dir /root/Art_ist_min/assets/scene_test_run \
    --output /root/Art_ist_min/assets/scene_test_run/final_scene.wav

  If edit_scene_clips.py cannot find ComfyUI automatically, run it like this instead:

  python3 TTS-Audio-Suite/scripts/edit_scene_clips.py \
    --clips-dir assets/scene_test_run \
    --instructions assets/scene_test_run/test_scene_edits_enriched_step.json \
    --output-dir assets/scene_test_run \
    --comfyui-root /absolute/path/to/ComfyUI \
    --keep-originals


  python3 TTS-Audio-Suite/scripts/convert_audio_to_mp3.py \
    --input assets/ComfyUI_temp_dcuqg_00001_.flac \
    --output assets/ComfyUI_temp_dcuqg_00001_.mp3 \
    --overwrite

  python3 TTS-Audio-Suite/scripts/timed_concat_scene_audio.py \
    --clips-dir assets \
    --manifest assets/test_timed_concat_manifest.json \
    --output assets/test_timed_concat_output.wav