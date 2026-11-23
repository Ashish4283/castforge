# CastForge rule book (read this first; it replaces exploring the code)

Free, local 3D-animated-film maker: photo/design -> rigged character (Blender 5.2, MPFB, Rigify);
`scene.json` -> rendered, voiced, finished episode. One laptop, RTX 3050 4 GB, one GPU job at a time.

## Token rules (follow every session)
1. Do NOT explore. Use the code map below, then `grep -n` the anchor and read only that range (`Read offset/limit`).
2. Never read whole: `blender/scene_kit.py` (2.3k lines), `blender/props.py`, `blender/build_character.py`,
   `core/schema.py`. Grep first.
3. Never open: `movies/`, `library/`, `test/`, `tools/`, `sfx/`, `motions/`, `asset_packs*/`, `.venv/`, `web/node_modules/`,
   `app/ui/` (built), `*.blend`, `*.json` under
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
cd web && npm run build                    # the React app -> app/ui/ (commit app/ui; `npm run dev` = hot reload on 5173, API on 8777)
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
| pose fixes (fix it in the shot) | scene.json `"fixes"`; parts `acting.FIX_PARTS`, timing `acting.fix_frames`; applied last in `scene_kit.py` `def apply_fixes`; UI panel in `Editor3D.tsx` + `viewer.previewFix` |
| hands: fingers, wrist, grip, fists in a clip | `acting.HAND_SHAPES`/`finger_curls`/`grip_curl`/`clip_hands`; `scene_kit.py` `def key_fingers` (curl_* scales the close), `def key_arms` wrist_*; per-frame choice in the `# --- life` loop (`act.clip_hands`, `act.holding`) |
| hold/carry a prop, duck, crouch | `scene_kit.py` `elif do == "hold"`/`"release"`/`"duck"`; grips `acting.carry_grip` on `measure_prop`; crouch = posture `"drop"` (`Actor.pdrop`); foot planting `motion.stance_windows` + `motion_rig._plant` (measures the character's own feet) |
| motion clips: bone maps, placement maths | `blender/motion.py` (pure, tested); import `import_motion.py`; playback `motion_rig.py` (`def play`); step `elif do == "perform"`; CLI `motion add/cmu/list` |
| per-frame life: blinks, nods, gaze, gestures applied | `scene_kit.py` anchor `# --- life` |
| which shot when | `blender/director.py` (pure, tested; fights: `_fight`, `beats=`); cameras: `scene_kit.py` `def close_up`/`two_shot` |
| a fight beat (strike), hit-stop timing | `scene_kit.py` `elif do == "strike"` (reuses `run_perform`/`run_duck`); hit-stop maths `motion.to_scene`/`to_clip`/`hold_shift` |
| a reusable set used by many scenes | `core/sets.py` (pure, tested: blueprint, merge_props, geometry_dir); scene key `set_folder`; `scene_kit.py` anchor `# --- a built set`; build `castforge.py set-build` |
| 2.5D set from the picture, floor map, A* walks | `generate/depth_set.py`; `scene_kit.py` anchor `# --- 3D set` |
| set picture shading, sun/world light | `scene_kit.py` anchor `# --- set:` (`def image_material`) |
| lighting moods, weather, flicker | `blender/world.py` |
| a prop's shape | `blender/props.py` `def build` (v1 types) / `def build_more` (v2 types) |
| sound mix, ducking, panning, footsteps | `scene_kit.py` anchor `# --- sound` |
| render settings, encode, storyboard, outputs | `scene_kit.py` anchor `# --- light, weather, render` |
| encode/loudness/voice effects | `core/media.py` |
| titles, transitions, grades, chapters, poster | `core/finish.py`; subtitles `core/subtitles.py` |
| publish package, delivery checks, platform rules | `core/publish.py` (`PLATFORMS`, `fold_chapters`, `package`); CLI `publish`; route `/api/episode/publish` |
| paths, qualities, aspects, render key | `core/config.py` |
| CLI commands, lock, status text | `castforge.py` (`def main`, `def render_status`) |
| scene/episode job | `episode_job.py` |
| web API | `app/server.py` (`@app.get/post`) |
| the app (React 18 + TS + Vite, sidebar layout) | `web/src/`: `main.tsx` routes, `app/store.tsx` (movies, GPU, jobs, toasts, hash route), `app/episode.tsx` (open scene model: `update`, `save`, `scene()`, `cast()`), `components/ui.tsx` (Button, Card, Field...), `components/ParamInput.tsx` (any schema parameter), `pages/*`; design tokens at the top of `styles.css`. Old page at `/classic` (`app/index.html`, `static/app.js`) until removed |
| Overview page (next step, progress) | `server.py` `/api/movie/progress`; `web/src/pages/Studio.tsx` |
| 3D scene editor (view, timeline, drag spots) | `web/src/pages/episodes/viewer.ts` (three.js) + `Editor3D.tsx`; export `scene_kit.py` `if args.preview3d`; job `--preview3d` |
| what the live view wears (hair, beard, clothes) | export `blender/preview_wear.py` -> `library/preview_kits/worn/<folder>-<asset>/`; the wardrobe itself `appearance.wearables` (pure, tested); route `/api/character/wear`; drawing `bodyview.setWearing` |
| the designer's live body (morphs as the sliders move) | export `blender/preview_kit.py` -> `library/preview_kits/<sex>-<age>-<build>-<height>/kit.json+bin`; what is needed and whether it is there `core/preview_kit.py` (pure, tested, `VERSION`); route `/api/character/preview-kit`; drawing `web/src/pages/characters/bodyview.ts` + `LivePreview.tsx` |
| what a face or body can be shaped into (sliders) | `core/appearance.py` (pure, tested: `FACE`, `BODY`, `targets_for`, `photo_vars`, hair styles, eyebrows). One table: `schema.CHARACTER` grows from it, the app groups from `face_groups`/`body_groups`, the build applies it |
| character designer, costumes | vocabulary `schema.CHARACTER`/`COSTUMES`/`check_design`; routes `/api/character`, `/api/character/rebuild`; UI `pages/CharacterDesigner.tsx`; build `build_character.py` anchor `# --- costume`; maths `blender/costume.py` (pure, tested: openings, bands, hem/cape rings, hood cut) |
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
- Bash tool: heredocs with apostrophes or backslash escapes break; write edit scripts to a file.
- A pose layer that reads the pose back must read every frame before writing any key, or it compounds onto itself.
- The user's app runs on 8765; test servers use 8777.
- A route that starts GPU work calls `server.gpu_job(kind, name, movie, start)`: it starts `start()` when the
  GPU is free and otherwise queues it (one worker thread, `/api/gpu` lists the queue). Never refuse a job
  with a 409 again.
- One GPU at a time, two locks: `.render.lock` (renders) and `.build.lock` (character/set/prop/building builds,
  written by `castforge.claim_build`). Renders and builds refuse each other; `gpu_busy` reads both.
- A just-appended object's `matrix_world` is not evaluated (reads identity): build on `matrix_basis`.
- Preview export (glTF): MakeHuman meshes need `export_apply` (masks, `cf_layer` cloth offset) and come as BLEND
  materials (editor draws them cut-out); someone who exits is keyed hidden, so select by `ever_shown`.
- Every save of scene.json keeps the previous one in `<episode>/.history/` (newest 50).
- Costume pieces are made after the Rigify rig (copies of garment/skin faces keep their DEF- weights); a garment
  is too coarse to pick a belt by whole faces, so `cut()` bisects it. bmesh faces are flat-shaded unless `smooth`.
- A photo + design build: the photo gives face, body and colours; the design adds hat, beard, costume and overrides
  what it states. `<name>.design.json` `use_photo` records how the character was last built.
- MPFB ships 1258 morph targets INSIDE the addon (`<addon>/data/targets/…`), not in the user asset library,
  which only carries expressions and visemes. `TargetService.target_full_path(name)` finds one by bare name
  (`chin-width-incr`) and `load_target` adds it as a weighted shape key. Paired features are `l-`/`r-`.
- A MakeHuman asset already carries its own fitting: `Mhclo.verts[i]` gives 3 body vertices, 3 weights and
  an offset, and `x_scale`/`y_scale`/`z_scale` give the spans that offset is measured against. Rebuilding a
  garment is that weighted sum plus offset x span - exact to 0.0002 mm on any body, which is why the live
  view fits clothes without Blender. Do NOT bind by nearest triangle: shoes and hats explode.
  MakeHuman's y is up, so its y_scale measures Blender/viewer z and its z_scale measures y.
- `Mhclo.delverts` is the body a garment hides. Dropping those triangles is what keeps a belly out of its
  own shirt, and it is what the build does too.
- Putting a garment on the body ADDS A MASK to the body. Read the body's vertices before dressing it, and
  turn every mask off when you do (`preview_mesh.shaped_coords` raises if the count is wrong) - a hidden
  vertex is a missing vertex, which renumbers the mesh and sends every binding somewhere else.
- A preview kit exports TWO different meshes and mixing them up silently ignores age, build and height:
  positions come from the EVALUATED body (macros applied), deltas from the "Basis" shape key (every target
  is a delta from the untouched base). Targets apply additively on top, which is what MakeHuman does too.
  Verified: a kit morphed by a design matches that design's built character to the millimetre (1.870 m,
  0.749 m across the shoulders, both).
- MakeHuman's mesh carries helper geometry that stands taller than the person. Height must be bisected
  against the "body" vertex group alone (as `build_character` does) or every preview comes out short. A
  built character measured with its masks ON is shorter again: clothes hide geometry.
- Preview kits are cached on disk for ever, so `preview_kit.VERSION` must be bumped whenever the exporter
  changes what it writes - otherwise a fixed exporter keeps serving the broken one's bodies.
- The photo fit and the designer's sliders deliberately use DIFFERENT lists (`appearance.photo_vars` vs
  `FACE`/`BODY`). Widening the fit gives the solver freedom one front-on photo cannot support and changes
  every face already built from a photo; sliders are applied on top of the fit, so both can grow apart.
- `hair.style` in a design was already passed to `--hair` as a raw MPFB asset name (build_character line ~55).
  A friendly style name has to be translated THERE, not where the hair is loaded, or `args.hair` wins and
  the asset is looked up under a name that does not exist (silently: it only warns).
- Mixamo FBX imports with x0.01 scale and a 90° axis turn on the armature object; CMU BVH (cgspeed) at 120 fps.
- A set folder (`movies/<film>/sets/<name>/`) holds the picture, `set_blueprint.json`, shared depth under
  `.castforge_geometry/` and the built `set.blend`. A scene naming it with `set_folder` inherits the picture,
  that geometry (derived once for every scene on the set) and its objects; the scene's own props are added
  after, and a scene prop with a set object's id moves it in place. Set file paths are anchored to the set
  folder, and `episode_job.py` must make `set_folder` absolute like any other path.
- A set folder can hold an empty version of its picture (`sets.EMPTY`, made by `/api/set/empty` or uploaded);
  a scene on that set uses it as the background so 3D furniture does not stand in front of its painted twin.
  Which file is the set's own picture is decided only by `sets.is_picture_name` - never re-list the exceptions.
- Picture-fitted prop roots carry a scale: hold constrains with COPY_LOCATION + COPY_ROTATION, never COPY_TRANSFORMS.
- A prop made by `make` has no "size" in scene.json: measure the built object (`measure_prop`), never assume one,
  or every grip is computed for a 30 cm cube and the prop ends up through the palm and into the wrist.
- Motion clips carry no finger movement (the bone map stops at `hand`): a punch keeps whatever the life loop
  keyed, so fighting clips need their fists made here (`acting.clip_hands`, `Actor.clip_hands`).
- A bone-parented child sits at the bone's TAIL with +Y along the bone, so the palm is about half a hand back.
- A scene poses the arms in IK (`IK_FK` = 1 on the shot rig), NOT in FK as a character .blend sits (0). So
  `hand_fk` drives the hand AND feeds the arm solve, and the wrist belongs there: `hand_tweak` moves the hand
  just as far but leaves the arm out of it, which silently changes every gesture tuned with the wrist on.
  Measure hand rigs on a scene's `shot.blend`, never on the character file: they are in different modes.
- The wrist is two axes, not three: bend about hand_fk's local X (the same sign on both hands) and deviation
  about its local Z (mirrored: the thumb side is -Z on the left, +Z on the right). The twist belongs to the
  forearm, which spreads it over its own twist bones; forcing it at the wrist pinches the mesh.
- `key_arms` already has a local called `bend` and it is the ELBOW. Anything else bend-ish needs its own name
  (`w_bend`): shadowing it moves the forearm instead, which no test catches and only a render shows.
- A fist needs `thumb.01` (`acting.THUMB_CLOSE`): curl alone leaves the thumb standing beside the hand. The
  swing across the palm mirrors between the hands, the curl does not.
- A hood is not the head's surface. Copying head faces or banding the collar reads as a flat band every
  time; build a shell of rings (`costume.hood_rings`), domed over the crown, open at the face, and take it
  off the garment as its own object like the cape. The head's deform bone is `DEF-spine.006`, not `DEF-head`.
- Gesture poses may carry `arm_L`/`arm_R` beside `arm` when the two hands must differ (a clap).
- Hand-to-hand gestures can't be eyeballed: pose the rig headlessly and score the result (palm gap, height,
  which way the palms and fingers point). The clap needed a negative twist and a wrist; no arm-only pose works.

## Docs
Roadmap and open work: `docs/ROADMAP.md`. Design and measurements: `docs/DESIGN_V2.md` (long; read one section).
Scene vocabulary for Gemini: `docs/GEMINI_SCENE_PROMPT.md`.
