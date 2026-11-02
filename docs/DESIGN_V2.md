# CastForge v2: architecture and design

Status: proposal for review (2026-11-02). Audience: whoever builds or maintains CastForge (people and AI
agents). Read "How CastForge works today" first if you have not seen the code.

## 0. Summary

CastForge turns photos (or invented character designs) into rigged 3D characters, and `scene.json` scripts into
animated, voiced, lip-synced episodes, entirely on one laptop (RTX 3050, 4 GB) with free tools. v1 works end to
end. v2 makes the output look and sound like a finished film, gives the director more tools, and makes the web
app the main place to work.

v2 has four parts:

1. **Fix measured defects in the output.** Today's MP4s have 96 kHz audio, an untagged colour matrix, miss their
   loudness target by about 1 LU, and keep the MP4 index at the end of the file; and every set picture renders
   20-75 % darker and less colourful than the picture it was made from (details in section 3).
2. **Split rendering from finishing.** Blender renders each scene once (the expensive part). Titles, transitions,
   colour grade, subtitles, chapters, poster and loudness mastering run afterwards in ffmpeg and can be changed
   and re-run in seconds without re-rendering.
3. **Better performances and craft tools inside the scene:** facial expressions, eye contact, gestures,
   posture, walk pace, narrator, voice effects, automatic ducking and stereo placement of sounds, lighting moods
   matched to the picture, falling snow/rain/fog, more props, and a director that varies shot sizes.
4. **A studio-style web app:** a form-based script editor for every action, a stage map, storyboard previews,
   voice auditioning, render stop/progress, a sound library browser and a publish panel.

## 1. Goals, constraints, non-goals

Goals, in priority order:

1. Picture and sound of the delivered file meet common delivery norms: BT.709 tagged H.264, 48 kHz AAC,
   integrated loudness within 0.5 LU of the target, true peak at or below -1.0 dBTP after AAC encoding,
   fast-start MP4. Where no shadow falls, the set picture renders within 8/255 mean error of its source.
2. Changing anything that does not affect the 3D animation (titles, transitions, grade, subtitles, loudness)
   never triggers a Blender re-render.
3. Characters act: they show emotion, look at each other, gesture, and hold a posture.
4. A first-time user can make, preview and publish an episode from the web app without editing JSON.
5. Existing `scene.json` files keep working unchanged.

Constraints (unchanged from v1):

- Free and local. No paid services, no cloud GPUs. Only free or permissively licensed models and assets.
- One GPU job at a time (4 GB VRAM). CPU-only jobs (ffmpeg finishing, CPU TTS previews) may run alongside.
- Every step stays a script that the CLI can run; the web app only calls the CLI and reads files.
- Same timing, voices and lip-sync at every render quality.
- Plain-language messages for non-programmers.

Non-goals for v2 (see section 10): crowds, motion-capture retargeting, real 3D set reconstruction, vehicles with
physics, IK hand contact (hold, carry, clap), a new TTS engine, Cycles rendering, YouTube upload.

## 2. How CastForge works today

### 2.1 Processes and data flow

```
browser ── app/index.html ──HTTP──> app/server.py (FastAPI, system Python, 127.0.0.1:8765)
                                        │  runs `python castforge.py ...` as subprocesses
                                        v
                                   castforge.py  (CLI: app, help, gemini-prompt, character, check, episode, status)
             ┌──────────────────────────┴───────────────────────────┐
             v                                                      v
  build a character                                         render an episode (background, .render.lock)
  generate/analyze_photo.py (.venv: MediaPipe)              episode_job.py
  blender/build_character.py (Blender: MPFB, Rigify)          for each scene: blender/scene_kit.py (+ props.py)
                                                                 ├─ generate/depth_set.py  (system Python: Depth Anything V2)
                                                                 ├─ generate/tts.py        (system Python: Kokoro)
                                                                 ├─ tools/.../rhubarb.exe  (lip-sync for WAV files)
                                                                 └─ frames (PNG) + mixdown (WAV) → ffmpeg → shot.mp4
                                                              ffmpeg concat + loudnorm → episode.mp4
```

Three Python environments are involved:

| Environment | Runs | Has |
|---|---|---|
| system `python` (3.12) | `castforge.py`, the web app, `episode_job.py`, `depth_set.py`, `tts.py`, `make_sfx_library.py` | fastapi, uvicorn, kokoro, torch (CUDA), transformers, soundfile, Pillow, numpy, faster-whisper |
| `.venv` | `analyze_photo.py`, the unit tests | mediapipe, numpy, Pillow, fastapi, pytest |
| Blender 5.2's Python | `blender/*.py` | bpy, numpy; runs in UTF-8 mode |

### 2.2 Files

A movie lives in `movies/<movie>/` with `characters/`, `sets/` and one folder per episode or scene. A folder's
`scene.json` is either one scene (`background`, `cast`, `props`, `script`) or an episode (`cast` library plus
`scenes: [...]`). `episode_job.py` writes each scene of an episode to `scenes/NN_id/scene.json` with absolute
paths, renders it to `scenes/NN_id/shot.mp4`, and skips scenes whose `shot.sha256` (scene text + `scene_kit.py`
+ `props.py` + quality) is unchanged. A single scene renders straight to `<folder>/episode.mp4`.

`scene_kit.py` (1,850 lines) does everything inside Blender in one top-to-bottom script: loads characters and
props, builds the 2.5D set (relief mesh from the background picture), runs the script steps into keyframes
(walk with planted feet, face, sit, enter/exit/open doors, say/think with lip-sync), adds "life" (breathing,
blinks, nods, talking hands), places cameras (wide, automatic close-ups per line, follow cameras for walks),
lays sound strips (dialogue, ambience, music, footsteps, effects), sets render quality, renders PNG frames
(resumable), mixes the sound and encodes with ffmpeg.

## 3. Review findings

### 3.1 Defects (measured on `movies/santa_is_a_lie/act1/episode.mp4` and its shots)

| # | Defect | Evidence | Cause |
|---|---|---|---|
| D1 | Audio is 96 kHz AAC | ffprobe: `sample_rate=96000` | `loudnorm` outputs 192 kHz; no `-ar 48000`, so the AAC encoder picks its highest rate and spreads 192 kbps over inaudible bandwidth |
| D2 | Colour matrix untagged, transfer tagged sRGB | ffprobe: `color_space=unknown color_transfer=iec61966-2-1` | RGB PNG → YUV conversion uses swscale defaults (BT.601) and copies the PNG's sRGB tag; players may shift hues. Note: ffmpeg 9 takes stream colour tags from the frames, so `-color_primaries`/`-color_trc` alone do nothing; the fix needs the `setparams` filter (verified) |
| D3 | MP4 index at the end | atom order `ftyp free mdat moov` | no `-movflags +faststart` |
| D4 | Loudness misses target | ebur128: -17.0 LUFS for a -16 target | single-pass `loudnorm` is dynamic (rides gain) and runs twice (shot, then episode) |
| D5 | Possible clipping before mastering | mixdown format `S16` | many sources summed above 0 dBFS are clipped before `loudnorm` can lower them |
| D6 | Vehicle camera shake does nothing | Blender 5.2: `Action.fcurves` no longer exists | `getattr(action, "fcurves", [])` silently returns `[]` |
| D7 | A half-written `.render.lock` crashes `status` | `pid, folder = open(LOCK).read().split("\n")[:2]` | unpacking fails on a one-line file |
| D8 | No way to stop a render | CLI and app have no stop | |
| D9 | Blender path hard-coded twice | `castforge.py`, `episode_job.py` | |
| D10 | `uvicorn` missing from requirements | `.venv` cannot run the app | app runs on system Python by accident |
| D11 | Docs do not mention working features | `beard`, `hat` designs; `think`, `exit`, `drive` steps; `music`, `set_pitch`, `shots`, `seed` keys | prompt docs fell behind the code |
| D12 | The set picture renders darker and greyer than its source | Frame 1 (the picture's own viewpoint) vs the source picture, mean brightness per band from dark to white: `test/scene_assets` 0.63 / 0.79 / 0.84 / 0.80 / 0.75 (cinematic: 0.28 ... 0.74); the snowy `02_to_the_truck` whites 0.76 with colour halved. A set-only probe render: mean error 21.1/255 | (a) the shadow catcher's Diffuse BSDF keeps Blender's default 0.8 grey, so unshadowed ratio is at most 0.8; (b) the "expected light" uses the pre-cinematic world strength and ignores light colour; (c) the default AgX view transform remaps the picture's tones (whites to ~0.75) |
| D13 | A rebuilt character or a new recording does not re-render a scene | `shot.sha256` covers scene.json text and code only | referenced files are not in the fingerprint |

### 3.2 Quality gaps

- Faces only move for lip-sync, blinks and stressed-syllable brows. No emotions; eyes never look at anyone.
- Arms only swing, rest, or open in small talking gestures. No wave, point or shrug; no posture change (the story
  needs "shoulders square, stance shifts").
- Every spoken line cuts to a close-up of the speaker, sometimes on the scene's first frame, so dialogue
  ping-pongs between near-identical shots.
- Key, fill and rim light have fixed energy (170/140/50 W) whatever the picture, so characters in a dark cabin are
  lit like daytime.
- No weather (the story needs falling snow), and ten of the props the story needs do not exist.
- Music and ambience never duck under dialogue; every sound plays in the centre of the stereo field.
- No titles, credits, scene transitions, subtitles, chapters or poster.

### 3.3 Workflow and UX gaps

- The script can only be edited as JSON, except dialogue lines.
- A line cannot be heard until the whole scene renders.
- No preview cheaper than a full render; no stop button; no log view; no ETA.
- Sets and sounds cannot be added or browsed from the app.
- Changing a title or a transition would require re-rendering (there is nowhere to change them yet).

### 3.4 Technical debt

- The scene vocabulary (actions, prop types, voices, floors) is listed in three places: `castforge.py` (check),
  `props.py`/`scene_kit.py` (behaviour), and the Gemini prompt doc. They have drifted.
- `scene_kit.py` is one 1,850-line script; new features would make it unmanageable.
- Two code paths for single scenes and episodes.

## 4. Design principles

1. **scene.json stays the contract.** Every new feature is an optional key or a new step type with sensible
   defaults. The app writes the same JSON a person or Gemini would.
2. **Expensive once, cheap forever.** Blender work is cached per scene by a fingerprint of only what affects the
   picture and the in-scene sound. Everything after it is cheap and re-runnable.
3. **One vocabulary.** A single pure-Python module lists every action, parameter, preset and asset name. The
   checker, the web forms, the props builder and a docs consistency test all read it.
4. **Pure where possible.** Planning code (expressions, gestures, shot choice, subtitle timing, ffmpeg command
   building) lives in modules without `bpy`, so it is unit-tested in seconds.
5. **Measure, don't assume.** Delivery claims are tested with ffprobe/ebur128 on real files; animation features
   are checked on rendered stills.

## 5. Target architecture

### 5.1 Process map v2

```
browser ── app/index.html + app/static/{app.js, app.css}
              │ HTTP (FastAPI app/server.py)
              v
castforge.py  app | check | episode | status | stop | storyboard | finish | voice | transcribe | doctor | character
              │
              v
episode_job.py FOLDER [--quality q] [--storyboard] [--finish-only]
   1. expand  : scene.json → scenes/NN_id/scene.json        (a single scene becomes scenes/01_<id>/)
   2. render  : per scene, if its render key changed:  blender scene_kit.py → shot.mp4, shot.wav,
                shot.timeline.json, shot.blend                                   (GPU, one at a time)
   3. finish  : core/finish.py → episode.mp4, episode.srt, episode.vtt, episode_chapters.txt,
                episode_poster.jpg                                                (CPU, ffmpeg)

core/   (pure Python, stdlib only at import time; used by CLI, server, episode_job and Blender)
   config.py     paths and settings (Blender, ffmpeg, Pythons), quality and aspect presets, render code list
   schema.py     the scene vocabulary; validation used by `check`; the web app's /api/schema
   media.py      ffmpeg/ffprobe helpers: encode settings, two-pass loudness, voice FX chains, grades
   subtitles.py  timed lines → SRT / WebVTT
   finish.py     episode assembly: cards, transitions, grade, subtitles, chapters, poster, mastering
   storyboard.py storyboard contact sheet (Pillow)

blender/
   scene_kit.py  orchestration in Blender (as today, slimmer)
   acting.py     NO bpy: visemes, expressions, postures, gestures, gaze rules, easing tracks
   director.py   NO bpy: shot planning (which shot when) from lines, moves and camera steps
   world.py      bpy: lighting moods, weather, practical light flicker
   props.py      bpy: prop factory (more types; sizes from core/schema.py)
```

### 5.2 The render stage and the finishing stage

**Render keys vs finishing keys.** `core/schema.py` defines `FINISH_KEYS = {"title", "credits", "transition",
"transition_seconds", "grade", "vignette", "grain", "subtitles", "master", "poster", "chapter"}`. The render key
of a scene is the SHA-256 of: the scene JSON with `FINISH_KEYS` removed (sorted keys), the quality name, the
contents of every file in `core/config.RENDER_CODE` (`blender/scene_kit.py`, `acting.py`, `director.py`,
`world.py`, `props.py`, `core/schema.py`, `core/media.py`, `core/config.py`), and the path, size and
modification time of every file the scene reads (background, character `.blend` files, prop models, recorded
lines), which fixes D13. `episode_job.py` and `scene_kit.py` both call `core.config.render_key(...)`, so the shot
cache and the resumable-frames cache agree. Grades and transition filters live in `core/finish.py`, which is not
render code.

**Shot outputs** (written by `scene_kit.py` into the scene folder):

| File | Content |
|---|---|
| `shot.mp4` | H.264, BT.709 tagged, CRF 14 (standard and above) or 18 (blocking/draft), AAC 320 kbps 48 kHz, fast-start. A clean intermediate: no grain, no grade. Playable on its own in the app. |
| `shot.wav` | The scene's stereo mix, 48 kHz, 32-bit float, not normalised. The finishing stage masters from this file, never from AAC. |
| `shot.timeline.json` | Facts the finishing stage needs (below). |
| `shot.blend` | As today, for hand edits. |

`shot.timeline.json`, version 1:

```json
{"version": 1, "id": "cabin_inside", "fps": 24, "frames": 1240, "duration": 51.667,
 "resolution": [1280, 720], "quality": "standard",
 "lines": [{"start": 2.04, "end": 6.31, "who": "Arthur", "kind": "think", "text": "Forty winters..."}],
 "shots": [{"time": 0.0, "kind": "wide", "on": []}, {"time": 2.5, "kind": "close", "on": ["Arthur"]}]}
```

Times are seconds from the shot's first frame. `kind` for lines is `say`, `think` or `narrate`.

**Finishing** (`core/finish.py`, run by `episode_job.py` after rendering, or alone by `castforge.py finish`):

1. Read every scene's `shot.mp4` and `shot.timeline.json`; refuse with a plain message if a scene is missing or
   its render key is stale ("scene 2 changed since it was rendered: render first").
2. Build segments: optional title card, the shots joined by their transitions, optional credits.
3. Assemble the audio from the `shot.wav` files with the same joins into `episode_mix.wav` (float), measure its
   loudness (pass 1), then encode video and audio together with linear loudness correction (pass 2).
4. Write subtitles, chapters and a poster from the timelines, offset by where each shot lands in the episode.

A single-scene folder is treated as an episode with one scene, so it renders to `scenes/01_<id>/` and finishes to
`episode.mp4` like any other. One code path.

### 5.3 `core/` modules

- `config.py`: `ROOT`; `BLENDER` (env `CASTFORGE_BLENDER`, else the Blender 5.2 default path, else `blender` on
  PATH); `FFMPEG`, `FFPROBE` (PATH); `AI_PYTHON` (env `CASTFORGE_AI_PYTHON`, else `python` on PATH, the
  interpreter with Kokoro/torch); `VENV_PY`; `QUALITY` presets; `ASPECTS`; `RENDER_CODE`; `render_key()`.
- `schema.py`: plain dicts. `ACTIONS` (name → description and parameters with types), `PROP_TYPES` (name →
  default size, default material, description), `MATERIALS`, `FLOORS`, `VOICES`, `EXPRESSIONS`, `GESTURES`,
  `POSTURES`, `PACES`, `LIGHTING`, `WEATHER`, `TRANSITIONS`, `GRADES`, `VOICE_FX`, `SHOT_KINDS`, `CAMERA_MOVES`,
  `FINISH_KEYS`, and `check_scene(folder)` (moved from `castforge.py`, same output format). Preset *contents* for
  expressions and gestures live in `blender/acting.py`; schema only lists the names, so the two are compared by a
  unit test.
- `media.py`: `encode_args(quality)`, `audio_args()`, `loudness_measure(wav)`, `loudnorm_filter(measured, target)`,
  `voice_chain(fx)`, `process_voice(src, fx) -> cached path`, `grade_filter(grade, vignette, grain)`,
  `probe_duration(path)`.
- `subtitles.py`: `to_srt(lines)`, `to_vtt(lines)`, time formatting, line wrapping at 42 characters.
- `finish.py`: `finish(folder, spec, scenes, quality)` as described in 5.2.
- `storyboard.py`: `contact_sheet(tiles, out)`.

## 6. Feature designs

Each feature lists its `scene.json` surface, how it works, and how we know it works.

### 6.1 Mastering and delivery

- Video (shots and master): `-vf scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=
  color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv` plus the matching `-colorspace` flags,
  `-movflags +faststart`. Master: CRF 17, preset `slow` (blocking/draft: CRF 20, `veryfast`). Optional
  `"master": {"codec": "hevc"}` → libx265 10-bit (`yuv420p10le`, `-tag:v hvc1`).
- Audio: Blender mixdown as stereo, 48 kHz, `F32` (fixes D5). Master: measure integrated loudness (pass 1,
  `loudnorm=print_format=json`), then one constant gain to the target followed by a peak limiter 0.5 dB under
  the ceiling (`alimiter` with `level=0` so it never re-levels, `latency=1` so it adds no delay), `aresample=48000`,
  AAC 320 kbps. A constant gain keeps the mix's dynamics, unlike single-pass `loudnorm`, and unlike `loudnorm`'s
  linear mode it never silently falls back to dynamic mode. Defaults `"master": {"loudness": -16, "true_peak":
  -1.5}`. Presets in the app: -16 (dialogue, default), -14 (YouTube), -23 (broadcast EBU R128).
- Aspect ratio (a render key): `"aspect": "16:9" | "1.85:1" | "2.39:1"`. Width comes from the
  quality; height = width / ratio, rounded to even. The set camera keeps its horizontal field of view, so wider
  ratios crop the picture vertically, as cinema does. Narrower ratios (4:3, 1:1) are not offered: they would show past
  the edges of the 16:9 set picture (review B6).
- New quality `ultra`: 1920 wide, 128 samples, full detail.

- **Set picture fidelity (D12).** The shadow catcher's Diffuse BSDF is white, and its "expected light" is built
  from the light actually in the scene: sun strength × luminance of the sun colour, world strength × luminance
  of the world colour, decided before any material is made. Scenes render with the `Standard` view transform,
  which shows the picture's pixels as they are; the film "look" (contrast, colour) moves to the finishing grade,
  where it treats picture and characters alike. Measured on a set-only probe render of `test/scene_assets`
  (mean error vs the source): today 21.1/255; white diffuse + AgX 12.8; white diffuse + `Standard` 6.4;
  white diffuse + Khronos PBR Neutral 18.9 (it crushes shadows). Character light strengths are re-checked on
  stills, because `Standard` shows highlights AgX used to compress.

Acceptance: an integration test renders synthetic shots through `finish` and asserts with ffprobe: h264 yuv420p,
`color_space=bt709`, `color_primaries=bt709`, `color_transfer=bt709`, AAC 48000 Hz stereo, `moov` before `mdat`,
ebur128 integrated loudness within 0.5 LU of the target and true peak at or below -1.0 dBTP; pure red and green
frames decode back within 14/255. A Blender probe render shows the set picture within 8/255 of its source.

### 6.2 Finishing: titles, credits, transitions, grade, subtitles, chapters, poster

```json
{"title": {"text": "Santa is a Lie", "subtitle": "Act I", "seconds": 4, "music": "radio_christmas"},
 "credits": {"lines": ["Written by A. Jiwa"], "cast": true, "seconds": 8},
 "transition": "dissolve", "transition_seconds": 1.0,
 "grade": "warm", "vignette": 0.3, "grain": 0.2,
 "subtitles": "soft", "master": {"loudness": -14}, "poster": {"time": 12.0},
 "scenes": [{"id": "cabin", "chapter": "The cabin", "transition": "fade", "grade": "night", ...}]}
```

- **Cards** (title, credits) are drawn with Pillow at the output resolution, held for `seconds` with fades.
  Credits list custom lines then, if `cast` is true, "Cast" and every cast name; a long list scrolls upwards
  (ffmpeg `overlay` with `y=H-t*speed`). Optional `music` plays a library bed or file under the card, faded out.
- **Transitions** between scene k-1 and k: the scene's own `transition`, else the episode's, else `cut`.
  `cut` concatenates. Everything else maps to ffmpeg `xfade` (`fade`→`fadeblack`, `fade_white`→`fadewhite`,
  `dissolve`→`fade`, `wipe_left`, `wipe_right`, `slide_left`, `slide_right`, `circle_open`, `circle_close`,
  `pixelize`, `radial`) with audio `acrossfade` of the same length, overlapping the two shots by
  `transition_seconds` (default 0.6 for fades, 1.0 for dissolves). The joined length is tracked so every later
  offset (subtitles, chapters) is exact. The episode always fades in from black (0.5 s) and out to black (1.0 s);
  `"master": {"fade_in": 0, "fade_out": 0}` turns this off.
- **Grade** per scene (scene key, else episode key) is an ffmpeg filter chain applied to that scene's frames only:
  `neutral`, `warm`, `cool`, `teal_orange`, `night`, `noir` (black and white), `vintage`, `bleach`, `dream`
  (soft glow). `vignette` and `grain` (0..1) are added after the grade. The cinematic look's grain moves here
  from the shot encode so it is applied once, at the end.
- **Subtitles**: every `say`, `think` and `narrate` line with text, offset into episode time, written as
  `episode.srt` and `episode.vtt` (think and narrate lines in italics). `"subtitles": "soft"` (default) also
  muxes them as a selectable MP4 text track; `"burn"` draws them into the picture; `"off"` writes only the
  sidecar files.
- **Chapters**: one per scene (its `chapter`, else its id in title case), plus the title card (named after the
  title) and `Credits`, so chapters cover the film from 0:00 as players and YouTube expect, in the MP4 metadata
  and in `episode_chapters.txt` (`0:00 Title` lines for a YouTube description). With titled chapters the MP4
  muxer also writes a QuickTime chapter track (a `data` stream); that is expected.
- **Poster**: `episode_poster.jpg`, the frame at `poster.time`, else the middle of the first close shot with
  dialogue, else one third in; the title is drawn on it when there is one.

Acceptance: unit tests for offset arithmetic (cut, xfade, title card); integration test asserts the output
duration equals title + shots - overlaps (±1 frame), that the subtitle stream exists, and that the SRT cue times
equal the expected offsets.

### 6.3 Sound inside the scene

- **Float stereo mix** (6.1).
- **Voice chain and effects**: every dialogue WAV is processed by ffmpeg before it is placed, cached next to the
  source as `<line>.wav.<fx>.wav`. Default `clean`: high-pass 75 Hz, slight low-mid cut, presence lift, de-esser,
  2.5:1 compression, then two-pass normalisation of the line to -20 LUFS so all lines sit at the same level.
  `"fx"` on a step (or `"voice_fx"` on a cast member) picks `none`, `clean`, `radio`, `phone`, `megaphone`,
  `echo` (dream, flashback, cave), `robot`. Lip-sync is still computed from the original file; no filter in the
  chains changes timing (`alimiter` uses `latency=1`).
- **Automatic ducking** (on by default, `"duck": false` turns it off): music falls 9 dB and ambience 4 dB under
  dialogue (lines closer than 1.2 s count as one), 0.25 s before the line and back 0.6 s after, by keyframing the
  volume of the bed strips.
- **Stereo placement**: effects and footsteps are panned by where their source appears in the wide camera
  (pan = clamp(2·(x - 0.5)·0.7, -0.8, 0.8)); dialogue only gently (factor 0.25), as film mixes do. Footsteps also
  fall off with distance from the camera (up to -6 dB at 8 m). The wide camera is used for every frame, so the
  stereo picture does not jump at each cut.
- **Narrator**: `{"do": "narrate", "text": "...", "voice": "bm_lewis"}` (or episode-level `"narrator":
  {"voice": ...}`); voice-over with no lip-sync and no close-up; ducks the music and is subtitled.
- **Music cues**: `{"do": "music", "bed": "radio_christmas", "volume": 0.35, "fade": 1.5}` starts a bed at that
  point in the script; `{"do": "music", "stop": true, "fade": 2}` fades it out. Scene-level `music` still starts
  at frame 1.
- **Voices**: the voice list grows from 14 to the 41 Kokoro voices that work with the installed packages (all
  American and British English including `am_santa`, Hindi, Spanish, French, Italian, Portuguese).
- **Transcription**: when a WAV performance is uploaded without a transcript, faster-whisper (`small.en`, CPU,
  already in the model cache) fills it in for lip-sync. Also `castforge.py transcribe FILE.wav`.

Acceptance: unit tests for `voice_chain` strings and duck envelope; a Blender run whose `shot.wav` shows music
RMS at least 6 dB lower inside dialogue than outside it, and a left-placed footstep louder in the left channel.

### 6.4 Acting

All preset tables and curve maths live in `blender/acting.py` (no `bpy`), so they are unit-tested.

- **Expressions** on the 52 ARKit face shapes every character has. Presets: `neutral`, `happy`, `smile`, `sad`,
  `angry`, `surprised`, `scared`, `disgusted`, `worried`, `thinking`, `skeptical`, `determined`, `tired`,
  `smug`. A preset never touches a shape that lip-sync drives (jaw, lip, funnel, pucker, press, stretch,
  visemes); a unit test enforces this. Brows combine with the stressed-syllable brow lifts by taking the larger
  value; `tired` lowers the eyelids and blinks combine with it the same way. Expressions also nudge the body
  (sad: chest and head drop; angry: head forward; surprised: head back).
  - `"expression"` on a cast member: the starting baseline.
  - `{"who": "maya", "do": "emote", "expression": "sad", "intensity": 0.8}`: changes the baseline (blends over
    0.35 s); with `"seconds"` it returns to the previous baseline afterwards.
  - `"expression"` on a `say`/`think` line: held for the line plus 0.5 s, then back to the baseline.
- **Eye contact** (on by default; `"gaze": false` on the scene or a cast member turns it off): eyes look at the
  speaker while listening, at the listener while speaking (with brief look-aways at 20 % of stressed syllables),
  down and away while thinking, and at the target of a `look` step. Small saccades every 0.6 to 2 s. Driven by
  the Rigify `eye_common` control (both eyes damped-track it), placed 8 cm in front of the face along the gaze
  direction relative to the head; the head's own yaw is subtracted so eyes and head share the turn.
- **Gestures**: `{"who": "arthur", "do": "gesture", "type": "wave", "seconds": 2}` with types `wave`, `point`
  (needs `target`), `shrug`, `nod`, `shake_head`, `hands_on_hips`, `raise_hand`, `beckon`, `bow`,
  `look_around`, `thumbs_up`. Gestures are forward-kinematics curves on shoulder swing, raise (new), elbow bend,
  forearm twist (new), finger shapes, shoulder lift (new), head and chest. They blend in and out over 25 % of
  their length and override the idle arm motion; one-arm gestures leave the other arm on its idle or walk motion.
  Gestures with hand contact (clap, facepalm, hold, carry) need IK and are deferred.
- **Posture**: `"posture"` on a cast member, or `{"do": "posture", "posture": "confident"}`, with `neutral`,
  `confident`, `proud`, `relaxed`, `slumped`, `tense`, `tired`. Persistent; blends over 0.8 s. Changes chest and
  head pitch, shoulder height and stance width.
- **Walk pace**: `"pace": "stroll" | "normal" | "brisk" | "hurry"` on `walk` (0.8, 1.1, 1.4, 1.7 m/s, with
  matching stride length, arm swing and forward lean). Footstep timing follows automatically.
- **Look**: `{"who": "maya", "do": "look", "target": "tom" | "camera" | [x, y] | "left" | "right" | "up" |
  "down", "seconds": 1.5}` turns head and eyes only, then returns.

Acceptance: unit tests (no shared shapes with lip-sync; blends start and end at the baseline; gesture curves are
continuous). A `tests/blender_smoke` scene renders stills at gesture and expression peaks for visual review; eyes
must visibly point at the partner in a two-person close-up.

### 6.5 World

- **Lighting moods**: `"lighting": "auto" | "classic" | "day" | "golden_hour" | "overcast" | "night" |
  "interior_warm" | "interior_cool" | "candlelight" | "moonlight" | "noir" | "studio"`. A mood sets key, fill and
  rim colour and strength, the world tint and the sun (which casts the characters' shadows onto the set);
  every scene renders with the `Standard` view transform (6.1), so moods never change how the picture looks. `auto` (default) scales the character lights by the background picture's mean luminance
  (factor clamp((L/0.35)^0.8, 0.3, 1.4)), so characters in a dark picture are lit darkly; `classic` keeps v1's
  fixed lights. Moods affect only the cast and props (light linking), never the picture. Measured L (sRGB
  luminance) of the film's sets: cabin inside 0.14 (factor 0.48), truck cab 0.30 (0.88), test café 0.34 (0.98),
  toy street 0.57 and snowy cabin outside 0.66 (both 1.4).
- **Weather**: `"weather": {"type": "snow" | "rain", "amount": 0.5, "wind": 0.3, "fog": 0.2}` (or the shorthand
  `"weather": "snow"`). Particles fall in the volume between the camera and the set and are already falling at
  frame 1 (negative start frame); snow drifts (Brownian motion, slow fall), rain streaks (fast fall, motion blur).
  `fog` adds a thin EEVEE world volume (range covers the backdrop so no seam shows). At blocking quality the
  particle count is cut to 30 %.
- **Props**: new types `armchair`, `christmas_tree` (with fairy lights), `fireplace` (with fire light), `lantern`,
  `candle`, `gift`, `sack`, `crowbar`, `cash_register`, `riser`, `rug`, `bookshelf`, `picture_frame`, `desk`,
  `laptop`, `phone`, `bottle`, `book`, `snowman`, `street_lamp`, `crate`, `barrel`, `pine_tree`. Sizes and default
  materials come from `core/schema.py`. Fire-based lights flicker (energy keyed every two frames from a smooth
  sum of sines with random phases; deterministic per seed). `armchair` is also a seat for `sit`.
- **Sound library prompts** for the story's missing sounds (door slam, lock bolt, crowbar, crash, crowd murmur,
  truck driving, rain, fireplace) are added to `make_sfx_library.py` so `--missing` generates them.

Acceptance: a prop catalogue render (every prop in a row, one still) reviewed visually; a snow still shows flakes
in front of and behind a character; the dark-picture test shows lower character exposure with `auto` than with
`classic`.

### 6.6 Direction

- `blender/director.py` (no `bpy`) turns lines, walks and `camera` steps into a shot list; `scene_kit.py`
  builds the cameras. `"shots": "auto"` uses the new director, `"classic"` the v1 rules, `"none"` the wide shot
  only (as today).
- Rules of the new director:
  1. Hold the wide (establishing) shot for at least 2 s.
  2. A speaker's first line is a medium shot (waist up), later lines close-ups; lines with a strong expression or
     longer than 6 s get a slow push-in.
  3. Rapid exchanges (lines under 1.5 s, or speakers alternating within 1 s) hold a two-shot instead of cutting
     every line.
  4. Lines longer than 5 s with a listener get one reaction cutaway to the listener (about 1.2 s, around the
     middle of the line).
  5. No shot shorter than 1 s; narrator lines never cut; walks longer than 1 s use the existing follow camera.
  6. Back to the wide shot after more than 1 s without dialogue.
- Shot size is set by lens and framing height (close 0.45 m, medium 1.0 m, two-shot both heads plus 0.6 m),
  keeping the camera near the picture's viewpoint so the 2.5D set does not smear.
- `{"do": "camera", "shot": "wide" | "medium" | "close" | "two_shot" | "over_shoulder" | "auto", "on": "maya" |
  ["maya", "tom"], "move": "static" | "push_in" | "pull_out" | "pan_left" | "pan_right" | "handheld",
  "lens": 50, "seconds": 4}` forces a shot from that point; the director does not cut until it ends.
  `over_shoulder` falls back to `close` on 2.5D sets when the angle would leave ±25° of the set camera.
- `handheld` and the vehicle shake use F-curve noise through `bpy_extras.anim_utils.action_get_channelbag_for_slot`
  (fixes D6).

Acceptance: unit tests on the director (rules 1 to 6 on synthetic inputs). A storyboard of the café test scene
shows at least three shot sizes.

### 6.7 Workflow

| Command | What it does |
|---|---|
| `castforge.py stop FOLDER` | Stops the running render of FOLDER (the job and its Blender), keeps finished frames; `episode` resumes. |
| `castforge.py storyboard FOLDER` | Builds each scene in Blender without the full render and renders one small still per shot; writes `storyboard.jpg` (contact sheet with shot number, time, shot kind and the line being spoken) and per-scene sheets. Takes about a minute per scene instead of an hour. Uses the GPU lock. |
| `castforge.py finish FOLDER` | Re-runs only the finishing stage (CPU). |
| `castforge.py voice "TEXT" --voice am_santa [--speed 0.9] [--fx phone]` | Speaks a line on the CPU (works while a render uses the GPU) and prints the WAV path. |
| `castforge.py transcribe FILE.wav` | Prints the transcript (faster-whisper, CPU). |
| `castforge.py doctor` | Checks Blender, MPFB, ffmpeg, Rhubarb, both Pythons and their packages, models and the sound library, with a fix for each problem. |
| `castforge.py episode FOLDER --quality ultra` | New 1920-wide quality. |

`episode_job.py` gains `--storyboard` and `--finish-only`. Status text and the lock work as today; `stop` kills
the process tree recorded in the lock (`taskkill /T /F` on Windows) and removes the lock.

### 6.8 Web app v2

The app stays a single FastAPI file plus static files, with no build step (vanilla JavaScript), and keeps
calling the CLI. The page is split into `app/index.html`, `app/static/app.css` and `app/static/app.js`.

**Current working-tree progress:** `GET /api/schema` now serves the shared vocabulary, and `app/index.html`
renders scene and finishing settings, cast placement/voice/expression/posture, procedural prop creation and
editing, schema-driven non-dialogue actions, and dialogue expression/voice-effect/speed/pause controls as forms.
The advanced JSON editor remains available. This is a first usable editor pass, not completion of the full
studio plan below: there is no draggable stage map, storyboard/stop/finish toolbar, voice audition, or per-step
reordering/duplication yet. The UI and render pipeline still need end-to-end browser and Blender validation.

Screens:

- **Header**: movie picker, new movie, GPU/render status pill with progress (click opens the render panel).
- **Studio** (home): getting-started checklist (characters → set → scene → storyboard → render → publish) and
  the movie's episodes with status badges per scene: rendered, out of date, not rendered.
- **Scene editor** (the main screen):
  - Scene settings form: background (picked from the movie's sets), floor, ambience, music, lighting, weather,
    look, shots, aspect.
  - Cast panel: add a character from the movie, voice picker with an audition button, position, facing,
    expression, posture, start seated.
  - Props panel: add from the catalogue, edit id, position, rotation, size, colour, material.
  - Script panel: one card per step, form fields generated from `/api/schema` for every action; insert, move up
    and down, duplicate, delete; "starts with previous" toggle; a play button on every line that speaks it with
    the chosen voice and effect; WAV upload with automatic transcript.
  - Stage map: top-down SVG of the stage (x -3..3 m, y -0.5..3.5 m) with the set's walkable floor map
    (`set/floor_map.png`) underneath when it exists; cast and props are draggable; walk targets are drawn as
    arrows.
  - Advanced JSON editor (kept, in sync).
  - Toolbar: Save (Ctrl+S), Check, Storyboard, Render (quality, with time estimate), Stop, Finish.
- **Preview**: storyboard sheet, episode video, per-scene shots, render log tail with ETA (frames per minute from
  the log).
- **Characters**: as today, plus previews (front/side/back) and the design JSON.
- **Sets**: upload a picture as a new set; see each set's picture and floor map.
- **Sounds**: footsteps, effects and beds from `sfx/library.json` with players; copy a name into a step.
- **Publish**: title card, credits, default transition, grade, subtitles, loudness target, poster time; Finish
  button; download links for MP4, SRT, VTT, chapters and poster.
- **Help**: how-to plus a reference of every action and preset generated from the schema.

New endpoints: `GET /api/schema`, `POST /api/episode/stop`, `POST /api/episode/storyboard`,
`POST /api/episode/finish`, `GET /api/episode/log`, `POST /api/voice/preview`, `POST /api/transcribe`,
`GET /api/sounds` (plus `/sfx` static files), `POST /api/set/upload`. `GET /api/episode` adds per-scene status,
storyboard images and downloads.

Acceptance: FastAPI tests for every endpoint; `node --check` on `app.js`; headless Edge screenshots of each screen
at 1400 px and 390 px wide reviewed visually.

## 7. Compatibility and migration

- Every v1 key and step still works. New keys are optional.
- Output changes by default, all improvements: encoding (D1 to D5); episode fade in and out; voice chain `clean`;
  ducking; gentle stereo placement; eye contact; `auto` lighting; the new director. Each has an off switch listed
  in its section, and `"shots": "classic"` / `"lighting": "classic"` give v1's camera and light.
- Single-scene folders now render into `scenes/01_<id>/` (and their `voices/` and `set/` caches are rebuilt there
  once). `episode.mp4` stays where it was. README and help text explain where `shot.blend` now lives.
- Every scene re-renders once after the upgrade because the render code changed. Nothing else needs migration.

## 8. Testing and verification

| Layer | How | Runs in |
|---|---|---|
| Vocabulary and checker | pytest: every action validates; schema names equal `acting.py` preset names; the Gemini prompt mentions every action and prop | seconds |
| Pure planning | pytest: acting curves, director rules, subtitle offsets, transition arithmetic, ffmpeg argument builders | seconds |
| ffmpeg integration | pytest (skipped without ffmpeg): synthetic shots from `testsrc`/`sine` through `finish`; ffprobe and ebur128 assertions from 6.1 and 6.2 | under a minute |
| Server | pytest with FastAPI's TestClient; subprocess calls mocked | seconds |
| Blender | `tests/blender_smoke.py` scene using the test characters: stills of gestures, expressions, gaze, weather, props; a short draft render through the whole pipeline | minutes, by hand |
| Web UI | `node --check`; headless Edge screenshots | by hand |

## 9. Implementation order and risks

1. **Foundation**: `core/config.py`, `core/schema.py` (move the checker), fixes D6 to D11. Risk: low.
2. **Delivery**: `core/media.py`, `subtitles.py`, `finish.py`; `scene_kit.py` writes `shot.wav` and
   `shot.timeline.json`; `episode_job.py` render/finish split and render keys; `finish`, `stop`, `doctor`,
   `voice`, `transcribe` commands. Risk: medium (filter graphs); mitigated by integration tests.
3. **Sound in the scene**: voice chain, ducking, panning, narrator, music cues. Risk: low.
4. **Acting**: `acting.py`, expressions, gaze, gestures, posture, pace, look. Risk: high (rig axis
   conventions); mitigated by rendering stills of every gesture before moving on.
5. **World**: lighting moods, weather, props, flicker. Risk: medium (look); verified on stills.
6. **Direction**: `director.py`, camera step, storyboard mode. Risk: medium.
7. **Web app v2**. Risk: medium (size); schema-driven forms keep it small.
8. **Docs**: README, both Gemini prompts, STORY.md feature status.

If time runs short, ship complete phases in this order rather than partial features.

## 10. Deferred, and why

| Item | Why not now |
|---|---|
| Crowds | Many characters exceed 4 GB VRAM; needs instancing and a lighter character LOD first |
| Motion capture (CMU, Mixamo) retargeted to Rigify | Largest motion-quality step, but needs a retarget and foot-contact clean-up pipeline of its own |
| Real 3D sets | Multi-view reconstruction is a project on its own; the 2.5D relief stays |
| Vehicles and physics fights | Need vehicle rigs and rigid-body baking; story uses cuts for now |
| IK hand contact (hold, carry, clap, facepalm) | Needs IK/FK switching with pose snapping to avoid pops |
| Chatterbox expressive TTS | Not installed; VRAM shared with rendering; the voice step keeps an `engine` field open for it |
| Cycles for final renders | Too slow on 4 GB for long episodes; EEVEE with ray tracing is the default |
| YouTube upload | Needs OAuth and the synthetic-content disclosure; chapters, poster and subtitles are made ready for it |

## 11. Open questions

1. Default loudness target: keep -16 LUFS (current), or -14 to match YouTube? Proposed: keep -16, offer presets.
2. Should the new director, eye contact and `auto` lighting be default for existing films? Proposed: yes, with
   the off switches above.

## 12. Review and decisions (Elephant Goldfish, 2026-11-02)

Seven independent reviewers (design, scope, implementation readiness, codebase accuracy x2, comprehension,
structure, style) reviewed this document against the v1 code: 6 blockers, 16 majors, 3 minors. Full report:
the session's `egm_review_DESIGN_V2.md`. How each blocker was resolved in the implementation:

| # | Finding | Decision |
|---|---|---|
| B1 | Code that only finishing uses must not force re-renders | Grades, transitions, cards and subtitles live in `core/finish.py` and `core/subtitles.py`, which are not render code. `core/media.py` stays render code (its voice chain shapes the shot's sound). Editing render code re-rendering once is accepted |
| B2 | The render key must be computed once | `episode_job.py` computes it before Blender starts and passes `--render-key`; the frames cache and the shot cache use the same value; the stamp is written last, after all outputs exist |
| B3 | Generated `scenes/NN_id` folders listed as episodes | The app no longer lists a `scenes/` folder that sits beside a `scene.json` (test added) |
| B4 | View transform contradiction | `Standard` everywhere; moods change only lights (fixed in 6.5); the AgX look names were removed from the presets |
| B5 | Gaze control may not exist | Verified on the film's rigs: Rigify `eye_common` drives both eyes (damped track); measured eye direction in head space changes per frame in a rendered scene |
| B6 | 4:3 and 1:1 render past the picture | Removed; aspects are 16:9, 1.85:1, 2.39:1 |

Majors acted on: non-English voices without phoneme timing fall back to Rhubarb lip-sync; a frame cut off by
`stop` is rendered again on resume; `tts.py --device cpu` for previews; finishing runs with a 30-minute timeout
in the app; finishing writes to a temporary file and renames it; finishing-key changes are tested not to change
the render key. Deferred, with the reviewers: a job queue for all GPU work (character, set and sound builds
still bypass the lock), Origin checks on the local server, a movie-level set cache, disk clean-up, cross-act
assembly, a hook for AI-processed shots, and hand-contact acting (hold, carry) the film needs.

Scope cuts considered: the reviewers asked for fewer transitions, grades, props, expressions and gestures.
These were already built and tested by the time the review finished; they stay, because each is a small table
entry checked by the schema and prompt-sync tests. Their advice to keep English voices only until lip-sync had
a fallback was met by the Rhubarb fallback instead.

Not yet measured: character skin and highlights under `Standard` at standard/final quality (checked only at
blocking quality), and render time at `ultra`.
