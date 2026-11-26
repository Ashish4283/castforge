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
| where the models, ComfyUI, fabrics or the other two tools live | `shared/suite.py` (pure, tested); CLI `castforge.py suite`; `shared/README.md` |
| handing a rendered episode to forgefilms for post | `shared/handoff.py` (pure, tested); CLI `castforge.py post FOLDER [--run]`; `/api/suite/post`; Suite page |
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
| showing what a slider moves | `bodyview.showTargets` (the kit already lists each target's vertices); the sliders report a hand on them through `CharacterDesigner.touching` |
| the live view's own controls (light, backdrop, mesh, spin, photo) | `bodyview.setLook`/`snapshot` (`LIGHTS`, `BACKDROPS`); the bar is in `LivePreview.tsx` |
| undo, redo, what changed since the last build | `CharacterDesigner.edit`/`undo`/`redo` (whole designs as text on two stacks) and the `changed` diff |
| the studio's steps, look pickers, thumbnails | steps `web/src/pages/characters/steps.ts`; tiles `LookPicker.tsx`; pictures `blender/preview_thumbs.py` -> `library/preview_kits/thumbs/`; routes `/api/character/looks` (what to offer) and `/api/character/thumbs` (take the missing ones) |
| is a character fit to animate? | `core/rigging.py` (pure, tested: `keep_strongest`, `problems`, `verdict`), measured and repaired by `blender/rig_check.py`; CLI `castforge.py rig NAME [FOLDER] [--fix]`; route `/api/character/rig`; panel `CharacterDesigner.RigPanel`; every build tidies and writes `<name>.rig.json` |
| how a body's size and build change the way it walks | `core/gait.py` (pure, tested: `shape_of`, `walk_like`, `describe`) - Froude scaling, hip width for weight, head share for a child; `scene_kit.Actor.shape`/`.gait` measure it off the body and `Actor.walk` uses it instead of the flat `acting.PACES` |
| can a character ACT? (walk, run, jump, bend, head, wrists, fingers) | `core/screening.py` (pure, tested: `MOVES`, `look`, `bad`, `card`, `verdict`), posed and measured by `blender/screen_test.py` (`POSES`, `hold`, `stretched`); CLI `castforge.py screen NAME [FOLDER] [--shots]`; route `/api/character/screen`; panel `CharacterDesigner.ScreenPanel`; writes `<name>.screen.json` |
| socks, shoes, a tie, a scarf, a watch, a band (nothing in the wardrobe) | `blender/tailor.py` (pure, tested: `cut`, `measure`, `asked_for`, `sweep`); the build makes them at the costume anchor, the live view mirrors it in `web/src/pages/characters/tailor.ts`; design keys `outfit.shoe_style` and `costume.socks/tie/scarf/watch/wristband` |
| picking a part of a mesh and reshaping it (size, slide, turn) | `costume.part_at`/`shape_part`/`neighbours` (pure, tested) mirrored in `web/src/pages/characters/parts.ts`; design key `parts`; picked by `bodyview.setParts`/`choose`, applied by `build_character.resize_parts` |
| a Santa cap made for the head (not an asset) | `costume.santa_cap`/`ball` (pure, tested); the build makes it at the costume anchor and weights it to `DEF-spine.006`; the live view mirrors it in `web/src/pages/characters/cap.ts`; `appearance.MADE_HATS`, design keys `cap.*` |
| pieces people cut themselves (an asset + their own edits) | `core/wardrobe.py` (pure, tested: `check`, `named`, `slot`, `load_all`); stored in `library/wardrobe/*.json`; routes `/api/wardrobe` (GET/POST/DELETE); resolved by `appearance.wearables(design, pieces)`; applied by `build_character.cut_edits` and in the live view inside `bodyview.dress` |
| the wardrobe warm-up (why picking a hat is instant) | `appearance.catalogue()` (pure, tested) lists all 57 pieces; `preview_wear.py --many JOBS.json` exports them in ONE Blender session; route `/api/character/wardrobe` (POST warms, GET reports); the studio calls it on arrival |
| the costume in the live view (trim, belt, buckle, gloves) | `costume.trim_bands`/`boot_bands`/`beyond` (pure, tested); the bands travel in `preview_wear.py` (`regions`), the hands and joints in `preview_kit.py`; drawn by `bodyview.setCostume` |
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
- A sibling tool's port is NOT ours to choose: forgefilms :8700 and graphic-novel :8500 come from their own
  `START.bat`, and `tests/test_suite.py` reads those files so the table cannot drift. (Both were invented
  wrong first time, and the app sent people to doors nobody was behind.)
- A scene's length for post comes from its own `scenes/NN_id/shot.timeline.json`, never from
  `episode.timeline.json` - the latter says where a scene SITS in the cut, the former is the untrimmed render.
- forgefilms captions only the voice layer it placed itself. A CastForge handoff has none (the voices are
  already inside each scene's `shot.wav`), so its `.vtt` comes out empty and `shared/handoff.captions`
  writes the real one. `--run` copies ours over it.
- `.item-body` is padding only. A row that wants a name on the left and a button on the right has to lay
  itself out (see `.suite-row`).
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
- The app CAN be looked at: Playwright + headless Chromium works here (WebGL 2.0 via SwiftShader). Install
  it in a scratch folder, not in `web/`. Use `waitUntil: "domcontentloaded"` - the app polls, so networkidle
  never comes - give `page.screenshot` its own long timeout (it waits on fonts), and log responses with
  status >= 400: a console "400" says nothing about which request it was.
- The build does NOT tint a garment by multiplying its texture: that turns a dark knit black. It uses
  colour x (luminance / the texture's MEDIAN luminance), with less of that contrast for pale colours
  (`build_character.recolour`). The live view does the same in a shader, from the median measured at export.
- Any script that RENDERS under `--factory-startup` must delete the startup objects first, or Blender's
  default cube stands in the picture (it cost the asset catalogue once and the look thumbnails again).
- Putting a garment on adds a mask modifier to the body. When taking it off again, remove only the
  modifiers that asset added - never the body's own "Hide helpers", or the helper cages render as a white
  slab across everything.
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
- The live view shows the costume WITHOUT making its geometry: fur trim, a belt, a buckle, gloves and a
  boot cuff are all regions of a surface that is already there, so the same faces are drawn again in the
  piece's colour and pushed out along their normals in the vertex shader (`bodyview.liftOffSurface`),
  sharing the garment's own position and normal attributes so they follow the body for nothing. A cape, a
  hood, a long coat and armour are new geometry and stay build-only.
- Fur trim must be chosen in ONE place or the preview trims a different coat from the one that gets built:
  `costume.trim_bands` (hem 0.075 m, collar 0.04, cuff 0.055, measured along the surface) and
  `costume.boot_bands`. The band is topological, so it is the same on every body and is measured once, at
  export. Cuffs are exported whichever sleeves are asked for; the app leaves them off unless they are long.
- The base MakeHuman body has NO hand, arm or leg vertex group - only `body`, the helpers and the
  `joint-*` cubes a rig is built from. So a region like a glove comes from two joints (`costume.beyond`:
  past the wrist, towards the middle fingertip, within reach of it - a plane alone runs on across the body
  and the glove swallows the far leg), and `joint-l-hand` IS the wrist. Joints must be measured on the
  SHAPED body (`preview_mesh.joint_centres(human, coords)`) or a tall person's wrist lands in the wrong
  place; the kit carries them so the live view knows a waist from a shoulder without having a rig.

- These hat assets come in ONE size and it is a child's; `hat_size` grows them (`costume.grow_hat`, the
  build applies it to the hat mesh so the fit, the weights and the rig are untouched; the live view
  mirrors it in `bodyview.growHat`). It must grow away from the hat's OPENING, whose vertices do not move
  at all (`costume.rim_of`, exported as a region bit). Both obvious alternatives look wrong and were
  tried: scaling the whole hat lifts the brim clear of the skull all round, and scaling about a horizontal
  plane through the lowest vertex stretches the front of the brim up off the forehead, because these hats
  are worn tilted back.
- Which boundary loop is a hat's opening cannot be guessed from the geometry alone, and both guesses are
  wrong on real assets: the LOWEST loop of the Santa cap is the 4 mm hole at the tip of its bobble (anchor
  to it and the hat balloons round the pompom - it reads as a lampshade), and the WIDEST loop of a fedora
  is the outer edge of its brim. `costume.rim_of` therefore asks the BODY: the opening is the loop lying
  closest to it. Both callers sample the body for it (every 7th vertex is plenty).

- A hat takes NO tint (`appearance.WEAR_KINDS["hat"]` has none), in the build and in the live view alike:
  it keeps the red its artist painted (#dc204c on the Santa cap). So a costume's cloth colour has to be
  chosen in that neighbourhood by hand - ask for a dark brick red and the suit will not match the cap,
  and nothing is wrong with the recolouring when that happens.
- `bpy_prop_collection` takes no slice STEP: `human.data.vertices[::7]` raises, and only at build time.
  Use `enumerate` with `i % 7`.

- A resized part is remembered as the POINT that was clicked plus a reach and a scale, never as vertex
  numbers: the build's mesh is subdivided one level more than the live view's, so a vertex number means
  something different there. The body's parts are applied BEFORE anything is fitted to it (so clothes
  follow), the worn ones after each garment is on - the same order the live view works in.
- `liftOffSurface` only works on a LIT material: `objectNormal` is declared by the normal chunk, which a
  MeshBasicMaterial leaves out, and the shader fails to compile. Unlit overlays (the part highlight) use
  `polygonOffset` instead.

- Automatic weighting leaves vertices pulled by eight or nine bones. No exporter keeps more than four and
  the extra ones make a shoulder or jaw mushy, so every build now limits and normalises deform weights
  (`rig_check.tidy`, which uses Blender's own operators - about 5 s for a whole character). Measured on a
  built Santa: 2494 over-weighted vertices on the body, 4253 on the beard, 2391 on the suit.
- When auditing a rig, count the SKIN only (the "body" vertex group). The body mesh also carries helper
  cages and joint cubes, which are legitimately unweighted - counting them reports 16 faults that are not
  faults. (The metarig left in the file is not a fault either: Rigify needs it to generate the rig again.)

- A part that covers a WHOLE object has no border by adjacency - nothing is outside it - and bailing there
  is wrong, because that is the ordinary case for a hat. What holds it on is then its open boundary (the
  ring the head goes through), so `costume.part_depth` falls back to `boundary_loops` and needs the faces
  passed, not just the adjacency.
- A part is remembered in the design with `move` (metres) and `turn` (degrees) beside `scale`, all in the
  BUILD's axes (x across, y front-back, z up). The live view is y-up, so it swaps them on the way in:
  move -> [x, z, -y]. Getting that wrong slides a hat into the head instead of to the side.
- The studio says what fraction of a thing a part covers. It is not decoration: a part covering 92% of a
  hat, doubled, is not a part at all - it is a different hat, and it looks like one (this is exactly what
  made a built Santa come out wearing a bowl).

- Every blob in a worn export must start on a 4-BYTE boundary. `regions` is one byte a vertex, so it
  pushes whatever follows off alignment, and the browser then throws "start offset of Uint32Array should
  be a multiple of 4" while dressing - which took the hat out of the live view and made its size dial
  look dead. `preview_wear.py` pads between blobs; `bodyview.setWearing` also puts on one thing at a time
  so a single unreadable piece cannot leave the character naked.
- Bump `preview_kit.VERSION` IN THE SAME EDIT as the exporter change. A lost bump is silent and vicious:
  the exporter writes a new field, every cached export keeps the old shape, and the feature that needs
  that field just quietly does nothing (here: a hat with no opening recorded, so it refused to grow).
  The viewer now also finds a hat's opening itself (`parts.openRings`) rather than trusting the export.

- Blender + MPFB take about FOUR seconds to start and about one second to do the work, so anything that
  exports many assets must do it in one session (`preview_wear.py --many`, like `preview_thumbs.py`).
  Exporting the wardrobe one asset at a time cost five seconds every time someone tried a different hat;
  warming all 57 in one session costs about 22 s once, and a pick then takes under a second.
- A grid item is `min-width: auto`, so it refuses to shrink below its own content. The live view's button
  row could not wrap, which forced the whole view 146 px wider than the card holding it - and the
  overflow painted on top of the panel beside it. `minmax(0, 1fr)` on the column and `min-width: 0` on
  the children. When a panel looks like it is "coming on top", measure the boxes in the browser first.
- A setting that belongs to the WHOLE studio must live in the app chrome, not inside one step of one
  page. Where heavy work runs (`local` / `kaggle`) was built correctly and put in the Costume step of the
  character studio, which meant it did not exist as far as anyone using the app was concerned. It is one
  piece of state now (`components/GpuPicker.tsx`: `GpuProvider`, `GpuPicker`, `GpuWhereLine`), shown as a
  line in the sidebar foot on every page and as the two buttons wherever a GPU is about to be used - two
  copies of the state would let the two disagree on screen.
- MakeHuman's skin group ships its pore, subsurface and roughness inputs almost switched off, which is
  what makes a face read as candle wax; no GPU and no texture work is needed, only better numbers
  (`build_character.LIFELIKE_SKIN`, chosen by rendering a head at a dozen settings and looking). Pore
  strength 0.60, SSS 0.45, radius 0.35, roughness 0.56. Past roughness ~0.62 the subsurface glow dies and
  the face goes chalky; clearcoat was tried and puts a hard white blob on the cheek.
- A head is NOT round and a cap must not be either. Measured at the band on a built Santa: 17.0 cm
  across, 21.6 cm front to back. `santa_cap` sized one circle from the AVERAGE of those, so the fur roll
  stood 3.0 cm proud at the temples and 0.7 cm at the forehead - a shelf of fur beside the ears. It now
  takes `squash` (across / front-back) and the build measures both half-extents; the cone's length still
  comes from their average so no existing cap got longer.
- `cap.towards` is an angle in the HORIZONTAL plane and the build's x is ACROSS the body, so towards=180
  flops the cap sideways over an ear and towards=90 flops it backwards, which is what a Santa cap does.
  180 was never a bug, it just reads as one.
- Photograph a cap from ABOVE the bottom of its band. A cap is an open tube, so a camera even 2 cm below
  that rim looks straight up inside it and the far wall reads as a second, floating piece of hat. Two
  rounds of "the cap is in two bits" were the camera, not the model - the geometry measured continuous,
  nested, non-degenerate and outward-facing every time.
- Moving a sibling project into `suite/` does NOT make it part of this repo. It keeps its own `.git`,
  its history and its remote, and castforge ignores `suite/` entirely - so `git add -A` here will
  never pick up their work and their uncommitted changes survive the move untouched.
- The studio is colourful on purpose (yellow, orange, lime, pink, cyan - `--paint-*`), but NO accent
  colour is ever laid over the 3D view itself: a character has to be judged against a quiet ground.

- A piece's edits are kept against the PIECE, by VERTEX NUMBER, not against the character by a point in
  space. The garment is refitted to whoever wears it (MakeHuman's binding), so an edit recorded this way
  is refitted for free on every body - cut a coat longer once and it is longer on everyone, at their own
  size. A vertex number means the same place in the live view and in the build, because the build's
  subdivision modifier leaves the base mesh and its numbering alone. A point in space would not.
- `appearance.catalogue()` (every asset) and `core/wardrobe.py` (pieces people cut) are different things:
  the first is what the wardrobe ships, the second is what someone made from it.

- A hat that is MADE (`appearance.MADE_HATS`, e.g. `santa_made`) is not worn from the library: nothing is
  exported and `wearables` returns no item for it - but it still covers the hair. The build and the live
  view each build it from the head's own measurements, which is why it can never bulge through a skull.
- Measuring a head: take the middle from the band's EXTENT, never the average of its vertices. A head is
  not evenly meshed (the face carries far more vertices than the back of the skull), so an average sits
  forward of the real centre and the far side then measures as twice the radius - 0.140 m for a head of
  0.07. And take the width as the average of the two half-extents: a head is longer than it is wide.
- A Santa cap is a fur ROLL plus a cone, and the roll's depth comes from the HEAD (about 6 cm on a 9.8 cm
  head), not from the cap's length: scaling the roll with the cap turns it into a fez.
- When a change seems not to reach the live view, check it is in the key that triggers a repaint
  (`LivePreview.colourKey` / `outfitKey`). Twice now a feature was built correctly and did nothing
  because its design key was in neither.

- A MADE cap sits ON hair and nobody goes bald: `wearables` keeps the hair, and what is under the band is
  hidden where it is DRAWN (the live view drops those triangles, the build masks them), so sideburns and
  the hair at the back still show. An ASSET hat is a solid shell and still takes the hair off, because
  hair underneath pokes straight through it.

- A made wearable is cut from the body's own joint markers and NO pattern in `tailor.py` names a global
  axis: up is this ankle to this knee, forward is the way the foot points. That is why one implementation
  serves the build (z up) and the live view (y up) - where the Santa cap needed two and got it wrong
  twice. Note a y<->z SWAP is a reflection, not a rotation: it flips every ring's winding.
- Cut a garment from a proportion of a BONE and it fits an ordinary body and no other. The mesh is to
  hand in both places, so `tailor.measure` measures the ankle, calf, wrist and foot instead. Three things
  that bit: the slice must be WIDE at the calf (the leg mesh is coarse, about 5 cm between rings, and a
  thin slice held across a leaning shin falls between two of them and catches only the far leg) and THIN
  at the ankle (a wide one reaches the heel and measures the ankle wider than the calf); and a foot is
  half as deep as it is wide, so a mean radius is the wrong number for it - `tailor.span` takes the
  half-width across its own length.
- A sole lies on the FLOOR, not across the shin. The shin leans, so laying a shoe out perpendicular to it
  tips the shoe onto its edge and stands it 2 cm up the leg. `leg()` hands back both: `up` (the shin's,
  what a sock wraps) and `stand` (the body's, what a shoe sits on).
- What a made thing is DRAWN as is not what it is worn as. A sock under a trouser is only visible between
  the trouser and the shoe - draw the rest and it shows through a trouser that clings - and it has to
  clear the top of the shoe or it fills nothing. A boot is worn OVER the trouser, so its shaft needs 3 cm
  of room; cut close to the calf it sits inside the trouser and puts triangles of boot through it.

- The screen test poses the rig as a SCENE does, not as the file sits: `scene_kit.Actor` sets
  `upper_arm_parent["IK_FK"] = 1` (arms FK) and `thigh_parent["IK_FK"] = 0` (legs IK) before it poses
  anybody. Testing the file as Rigify left it turns controls nothing is listening to, and every arm and
  wrist pose comes back "the controls turn but the body does not".
- Measuring whether a pose worked: `reach` must come from the bone's whole ROTATION, not from the angle
  its direction swung through - a bone points along its own length, so turning a head (a twist about that
  length) leaves its direction untouched and measured as 18% of the way. And a control can turn perfectly
  while moving no skin at all, which only a measurement of the SURFACE catches.
- Judge skin by how MUCH of it is pulled about, never by the worst edge. Measured over seven built
  characters, the worst edge in the arms pose runs 2.4x to 8.7x on characters that all look right - every
  armpit has one hot edge. The fraction past 1.8x is 0.00% for most moves, about 0.20% at the shoulders,
  and 0.40% on the one character that is visibly worse (`screening.ROUGH_SKIN`).
- Anything that measures the body mesh must turn the garment MASKS off first, or the evaluated mesh comes
  back with 10,070 vertices where the real one has 19,158 and every index past the first hidden vertex
  means a different place. `screen_test.only_the_rig` leaves the armature modifier on and nothing else.
- `lock_rotation` on a pose bone blocks Blender's own transform and NOT a script writing
  `rotation_euler`, so it does not break scripted animation and the screen test is right to pass it. A
  zero-range LIMIT_ROTATION constraint does block it, and is caught as "frozen".
- `--card` was never a colour this stylesheet defines: `.step-bar` is sticky and had no background at
  all, so a long step read straight through it. Check a token exists before trusting it.

- `acting.PACES` is ONE speed and ONE step for everybody (1.1 m/s, 0.62 m), tuned on a 1.70 m adult.
  `core/gait.py` scales it to the body: speed with the SQUARE ROOT of leg length (Froude similarity -
  half the leg is 0.71 of the speed, not half), step straight with it, so cadence goes as 1/sqrt(L) and
  small bodies scurry. Weight is read from hip width RELATIVE to leg (not height, so a tall slim body and
  a short slim one both read slim) and gives a wider stance, a shorter step, more roll and less arm
  swing. A child is read from the share of the body above the neck, which is what tells a toddler from an
  elf - an elf is a small ADULT and must walk like one. Unscaled, a 0.62 m step is 114% of an elf's leg
  and 176% of a toddler's, which no leg does: the foot gets dragged.
- Calibrate against this project's OWN bodies, not a textbook. Hip-to-leg runs 0.211 (slimmest) to 0.255
  (heaviest) over nine built characters; `gait.HIPS_REF` set at the slim end called every character in
  the film heavy. And anything that scales a pose in METRES (the screen test's stride, lift and drop)
  must scale with the body, or a 1.28 m girl is tested with an adult's stride - 97% of her own leg - and
  reports a tear that is the test's fault (her worst edge in `run` fell 3.08x -> 1.97x once it was).
- Measuring a built character: the macros are SHAPE KEYS, so the base mesh is the 1.60 m default
  MakeHuman and not that person. Reading bones (posed on the morphed body) and `data.vertices` (not) in
  the same breath made every character 1.60 m tall and gave a 1.28 m girl a toddler's head. Take the
  joint markers off the EVALUATED mesh, as `preview_mesh.joint_centres` does.

## The suite
`suite/forgefilms` (clips, sound, assembly, :8700) and `suite/graphic-novel` (dataset, LoRA, panels,
:8500) live under this checkout and are EACH their own git repo with their own remote; castforge
gitignores `suite/` and never looks inside. Shared: models `C:/AI-Models` (22 GB, via ComfyUI's
`extra_model_paths.yaml`), ComfyUI on :8188, `core/gpu.py` for local-or-rented, `library/fabrics/`,
and the built cast. Paths are stated ONLY in `shared/suite.py` - see `shared/README.md`.
Each sibling imports `suite_link` (one file in its own root) to get those paths and the GPU choice.

**Post is the step after `episode`.** CastForge stops at a rendered, voiced episode; forgefilms grades,
crossfades, masters to -16 LUFS and captions it. `python castforge.py post FOLDER [--run]`, or the Suite
page in the app. The contract between the two shapes is `shared/handoff.py` and nothing else.

## Docs
Which GPU does what, and the two notebook modes: `docs/GPU_PLAN.md`.
Roadmap and open work: `docs/ROADMAP.md`. Design and measurements: `docs/DESIGN_V2.md` (long; read one section).
Scene vocabulary for Gemini: `docs/GEMINI_SCENE_PROMPT.md`.
