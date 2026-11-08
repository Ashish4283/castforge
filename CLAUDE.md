# CastForge rule book (read this first; it replaces exploring the code)

Free, local 3D-animated-film maker: photo/design -> rigged character (Blender 5.2, MPFB, Rigify);
`scene.json` -> rendered, voiced, finished episode. One laptop, RTX 3050 4 GB, one GPU job at a time.

## Token rules (follow every session)
1. Do NOT explore. Use the code map below, then `grep -n` the anchor and read only that range (`Read offset/limit`).
2. Never read whole: `blender/scene_kit.py` (2.3k lines), `app/static/app.js` (1.2k), `blender/props.py`,
   `blender/build_character.py`, `core/schema.py`. Grep first.
3. Never open: `movies/`, `library/`, `test/`, `tools/`, `sfx/`, `asset_packs*/`, `.venv/`, `*.blend`, `*.json` under
   `set/` or `voices/` (huge machine-written data). `asset_index.json`, `face_map.json`: data, don't read.
4. One change = one place. The vocabulary lives only in `core/schema.py`; never re-list actions, props,
   voices or presets anywhere else (the app, checker and Gemini prompt read it; a test enforces the prompt).
5. Verify with the cheapest check that proves it: `pytest -q` (5 s) > `castforge.py check` > `storyboard`
   (about 1 min) > a blocking render (about 3 min). Never render `final` just to test.
6. Keep replies and diffs small. Don't paste logs: `grep -E "CF:|Error|Traceback"` them.
7. When something non-obvious is learned, add one line under "Gotchas" here instead of re-discovering it.

## Commands
```
.venv\Scripts\python -m pytest -q          # all unit + ffmpeg tests (~130, 5 s)
python castforge.py check|storyboard|episode|status|stop|finish FOLDER [--quality blocking] [--wait]
python castforge.py voice "text" --voice af_heart | transcribe f.wav | doctor | app (port 8765)
blender -b --python-exit-code 1 -P blender/catalog.py -- OUTDIR     # picture of every prop
```

## Flow
`castforge.py episode` -> `episode_job.py` (background, `.render.lock`):
1. expand: scene.json (one scene or `scenes:[...]`) -> `scenes/NN_id/scene.json`, paths made absolute
2. render (GPU): per scene, only if `core.config.render_key` changed -> Blender `scene_kit.py` ->
   `shot.mp4`, `shot.wav` (float mix), `shot.timeline.json`, `shot.blend`, `shot.sha256` (written last)
3. finish (CPU): `core/finish.py` -> `episode.mp4/.srt/.vtt`, `episode_chapters.txt`, `episode_poster.jpg`
Finishing keys (`schema.FINISH_KEYS`: title, credits, transition, grade, subtitles, master...) never re-render.

## Code map (file -> what; `grep -n` the anchor)
| Need to change... | Go to |
|---|---|
| a step type, parameter, prop size, preset name, voice | `core/schema.py` (`ACTIONS`, `PROP_TYPES`, `LIGHTING`...) |
| what a step does in Blender | `scene_kit.py` anchor `# --- script` then `elif do == "<name>"` |
| walking, sitting, turning, arms, fingers | `scene_kit.py` `class Actor` (`def walk`, `def key_arms`...) |
| expressions, gestures, postures, gaze maths | `blender/acting.py` (pure, tested) |
| per-frame life: blinks, nods, gaze, gestures applied | `scene_kit.py` anchor `# --- life` |
| which shot when | `blender/director.py` (pure, tested); cameras: `scene_kit.py` `def close_up`/`two_shot` |
| 2.5D set from the picture, floor map, A* walks | `generate/depth_set.py`; `scene_kit.py` anchor `# --- 3D set` |
| set picture shading, sun/world light | `scene_kit.py` anchor `# --- set:` (`def image_material`) |
| lighting moods, weather, flicker | `blender/world.py` |
| a prop's shape | `blender/props.py` `def build` (v1 types) / `def build_more` (v2 types) |
| sound mix, ducking, panning, footsteps | `scene_kit.py` anchor `# --- sound` |
| render settings, encode, storyboard, outputs | `scene_kit.py` anchor `# --- light, weather, render` |
| encode/loudness/voice effects | `core/media.py` |
| titles, transitions, grades, chapters, poster | `core/finish.py`; subtitles `core/subtitles.py` |
| paths, qualities, aspects, render key | `core/config.py` |
| CLI commands, lock, status text | `castforge.py` (`def main`, `def render_status`) |
| scene/episode job | `episode_job.py` |
| web API | `app/server.py` (`@app.get/post`); UI markup `app/index.html`, logic `app/static/app.js` |
| Studio page (next step, progress) | `server.py` `# --- studio`; `app.js` `renderStudio` |
| model props (seat / wheel objects) | `scene_kit.py` `def load_prop_file`, `def wheel_pivot` |
| character build | `blender/build_character.py` (photo spec: `generate/analyze_photo.py`, .venv only) |
| city library, set/prop builders | `blender/build_*_asset.py`, `build_set.py`, `library_geometry.py`, `core/buildings.py` |
| TTS / transcripts / SFX generation | `generate/tts.py`, `transcribe.py`, `make_sfx_library.py` |

Tests mirror modules: `tests/test_<module>.py`. Add a test with every pure-logic change.

## Rules of the codebase
- `core/` and `blender/acting.py`, `director.py` import no `bpy`: keep it that way (testable, cheap).
- Blender scripts add ROOT and `blender/` to `sys.path`, then `from core import ...`, `import acting`.
- Messages are plain language for non-programmers; log lines start with `CF:` (status parsing relies on it).
- All ffmpeg calls go through `core.media` (`run`, `to_bt709`, `video_args`, `AUDIO_ARGS`).
- Defaults must keep old scene.json files working. New features = optional keys.
- Commit on a branch, not `main`; the user also edits with GitHub Copilot, so run `git status` first.

## Three Pythons
system `python` (app, jobs, Kokoro, Depth Anything, faster-whisper) | `.venv` (MediaPipe, pytest) |
Blender's own (scene_kit, props, build_*). `core.config.AI_PYTHON` / `BLENDER` / `VENV_PY` locate them.

## Gotchas (verified)
- ffmpeg 9 ignores `-color_primaries`; colour tags need `setparams` (`media.to_bt709`).
- Blender exits 0 on script errors unless `--python-exit-code 1`.
- Blender 5.x has no `Action.fcurves`: use `bpy_extras.anim_utils.action_get_channelbag_for_slot`.
- Scenes render with view transform `Standard` (AgX greys the set picture; see DESIGN_V2 D12).
- Bash tool: heredocs with apostrophes break; write edit scripts to a file.
- The user's app runs on 8765; test servers use 8777.

## Docs
Roadmap and open work: `docs/ROADMAP.md`. Design and measurements: `docs/DESIGN_V2.md` (long; read one section).
Scene vocabulary for Gemini: `docs/GEMINI_SCENE_PROMPT.md`.
