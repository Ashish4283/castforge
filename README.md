# CastForge

Photo of a person → rigged, dressed, lip-sync-ready 3D character in Blender → animated, voiced episodes.
Goal: a very easy tool for making animation. Every step is a script, so the web app can run the whole chain.

**Free and local.** Everything runs on the laptop (RTX 3050 4 GB) with free tools and CC0 assets. Nothing uses AWS
or paid GPUs.

## Status (2026-11-02)

| Stage | State |
|---|---|
| 1. Photo → spec (`generate/analyze_photo.py`) | **Working.** MediaPipe on CPU: body proportions, skin/hair/top/bottom/shoe colours, garment (trousers/shorts/skirt/dress), sleeves, hair length, photo-quality warnings |
| 2. Spec → character (`blender/build_character.py`) | **Working, ~45 s.** MPFB body fitted to the photo, matching skin, hair, CC0 clothes recoloured to the photo, garment layering, Rigify rig, 15 visemes + 52 ARKit face shapes, A-pose |
| 3. Pose check (`blender/pose_test.py`) | Working: clothes, hair and shoes follow the rig; visemes and blinks work |
| 4. Face likeness | **Working.** MediaPipe 478 landmarks → ~40 MakeHuman face shapes fitted (error ~2.5 → ~1.3 mm) + the photo's face blended onto the head through a landmark-guided warp (eyes/mouth interior kept 3D); nearest eye colour. Needs a face close-up (`--face-photo`) for a sharp result |
| 5a. 3D set from the background (`generate/depth_set.py`) | **Working.** Depth Anything V2 (local) + floor calibration → solid relief set (characters stand among the furniture, hidden behind it, shadows on it) and a walkable-floor map; walks route around obstacles (A*), positions inside furniture snap to free floor; close-ups dolly in near the picture's viewpoint with shallow depth of field. `"set": "flat"` turns it off |
| 5b. Set-to-props (`generate/set_props.py`) | Camera-matched floor props from marked image-space paths; the generated road mesh uses the background's UV texture and is cut out of the relief to prevent overlapping surfaces. Photographed doors can be fitted as hinged picture props. |
| 5c. User-directed set assets (`app` → Sets) | Image-guided forms let users mark an image region, choose a procedural 3D object and its dimensions, and link a door to another set. **Build 3D set** creates a reusable `.blend` and preview without changing movie scenes. This is a depth-relief background plus modeled objects, not full automatic reconstruction of every pixel into 3D. |
| 5d. Reusable image-guided props (`app` → Props) | Choose a supported procedural prop, enter dimensions/material/color, and upload a reference image. CastForge builds a reusable `.blend` and preview; the image is kept in Blender as an editing reference, not converted into geometry or a texture. |
| 5e. Shared city asset library (`app` → Library) | Reusable procedural buildings, event arenas, landscapes, trees, vehicles, and road modules can be customized and used across movies. |
| 5. Scene kit (`blender/scene_kit.py`) | **Working.** scene.json → set picture shown true to its source (D12 fix: within ~6/255), cast, walk with pace (planted feet), face, look, say/think/narrate (Rhubarb or exact TTS lip-sync), facial expressions on the 52 ARKit shapes, eye contact with saccades, gestures (wave, point, shrug, nod, bow, ...), posture, doors, sitting; lighting moods matched to the picture's brightness, snow/rain/fog, 40 prop types with flickering firelight; an automatic director (establishing wide, medium then close, two-shots, reaction cutaways, push-ins) plus explicit camera steps; dialogue levelled and cleaned, voice effects, music/ambience ducking, stereo-placed footsteps and effects; float stereo mix |
| 5f. Finishing (`core/finish.py`) | **Working.** Without re-rendering: title card, scrolling credits, transitions (cut, fade, dissolve, wipes...), colour grade per scene, vignette and grain, subtitles (selectable track or burnt in, SRT/VTT), chapters, poster, loudness mastering (-16 LUFS, peak -1.5). Output: BT.709-tagged H.264, 48 kHz AAC 320k, fast-start MP4 |
| 6. Web app | **Working.** Schema-driven scene, cast, prop, action and finishing forms; dialogue with "Hear it" voice previews and WAV uploads; Storyboard, Render, Stop and Finish-only buttons; storyboard and download links; sets, props and the city library |
| 7. YouTube upload | not started |

Validated on three internal example photos. Their images and generated renders are not included in this
source-only repository.

## One-time setup

```
python -m venv .venv && .venv\Scripts\pip install mediapipe numpy pillow
# models/: pose_landmarker_heavy.task, selfie_multiclass_256x256.tflite (Google MediaPipe, free)
# Blender 5.2 + MPFB 2.0.18 extension (extensions.blender.org, GPL)
blender -b --factory-startup -P blender/install_assets.py     # installs asset_packs/*.zip into MPFB
.venv\Scripts\python generate/index_assets.py                 # measures skin tones -> asset_index.json
```

Asset packs in `asset_packs/` are MakeHuman CC0 packs: system assets, skins01, hair01, suits01, shirts01, pants01,
dress01, skirts01, system_clothes_materials01, visemes02, faceunits01. CC-BY packs are avoided on purpose.

## Run the unit tests

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

## Make a character

```
.venv\Scripts\python generate/analyze_photo.py photo.png spec.json --debug overlay.png
blender -b --factory-startup -P blender/build_character.py -- --spec spec.json --out char.blend ^
    --gender female --age 30 --height-cm 168 --preview previews/
```

Gender, age and height come from the user (a form field in the web app), not from the photo.

## Turn a set picture into a reusable set asset

Open the app and go to **Sets**. Add one or more details, mark each detail's region on the set image, adjust its
real-world width/depth/height, then save or choose **Build 3D set**. For a door, link another set to use its
background as the view beyond the door. The app writes `set_blueprint.json`, then creates `set.blend` and
`set_preview.png` in that set's folder. The source movie's scenes are not edited.

The generated asset combines the depth-relief background with modeled objects. It does not infer a complete
walkable 3D world from a single image; inspect and adjust dimensions and placements in the Blender asset as needed.

## Build a reusable prop

Open the app and go to **Props**. Give the asset a name, choose a supported procedural prop type, enter its
real-world dimensions and material, then upload a PNG, JPEG, or WEBP reference image. **Build Blender prop**
creates `movies/<movie>/props/<name>/<name>.blend` and a preview. The image is packed into the `.blend` in its
own non-rendering reference collection. In an open episode, choose **Add to open scene** on a completed prop
to reuse the model; save the episode to keep the reference.

This is the first step toward a reusable asset catalog. The current prop builder uses known procedural shapes;
it does not reconstruct arbitrary images, and uploaded prop builds are stored per movie. The shared starter
building library is separate; roads and vehicles should be added as dedicated asset families with reusable
templates, not treated as ordinary small props.

## Reuse city-library assets

The **Library** tab keeps the same scene studio and lets you switch the reusable asset layer by category:

- **Buildings:** hut, house, row house, store, big store, shopping mall, hospital, station, police station, castle,
  hotel, restaurant, diner, and jail.
- **Arenas & venues:** stadium, wrestling arena, Roman arena, fighting-game arena, and disco arena.
- **Landscapes:** garden with paths, planting beds, benches, and a fountain.
- **Trees:** oak, pine, and palm.
- **Vehicles:** car, jeep, truck, helicopter, and airplane.
- **Roads:** straight segment, curved segment, crossroads, and T-junction.

Choose a design, adjust dimensions, floors where relevant, and colors, then **Build and save to library**. The app
creates a reusable `.blend`, a preview, and a small JSON specification under `library/<category>/<name>/`.
Use **Add to open scene** to reference a shared model from any movie; the scene stores a relative path, so the model
does not get copied into movie folders. `python castforge.py library-build` creates any missing default starter
assets without replacing existing designs. `--refresh` rebuilds only starter assets whose specifications still
match the built-in defaults, so customized library assets are left untouched.

These are original procedural starter models, not copied assets from a commercial game or studio. They provide
recognizable exteriors and silhouettes, but most are not complete production-ready sets: building interiors,
openable architectural doors, articulated vehicle controls, and animated rotors/wheels are future work. Keep
movie-specific characters, reference photos, and scene files out of the shared catalog. Curated library `.blend`
files are intended to be reviewed before being added to GitHub so other CastForge users can reuse them.

**Photo tips (for the web app's upload screen):** one person, head to toe, facing the camera, plain background,
arms slightly away from the body (so the waist can be measured).

## How the "back of the body" works

The photo only shows the front, so we don't try to reconstruct pixels. The character is a complete MakeHuman body
whose shape controls are fitted to the photo's measurements:

- shoulder and hip width, leg and torso length, and waist width where visible;
- real garments that exist all the way round, recoloured to the photo while keeping their fabric detail;
- a matching skin texture.

The back, sides and top of the head are therefore always complete and animate correctly.

## Rendering

```
python castforge.py check <folder>                  # mistakes in scene.json, in plain words
python castforge.py storyboard <folder> [--wait]    # one still per shot -> storyboard.jpg (about a minute a scene)
python castforge.py episode <folder> [--quality blocking|draft|standard|final|ultra] [--wait]
python castforge.py status <folder>                 # progress; stop with: python castforge.py stop <folder>
python castforge.py finish <folder>                 # redo titles, transitions, grade, subtitles, sound only
python castforge.py voice "Ho ho ho" --voice am_santa [--fx phone]   # hear a line (CPU, works during a render)
python castforge.py transcribe line.wav             # the words in a recording (for lip-sync transcripts)
python castforge.py doctor                          # is every tool installed?
```

- Runs in the background (one GPU job at a time; the 4 GB GPU cannot run two) and resumes after a stop.
- Quality: blocking (480 wide), draft (640), standard (960), final (scene resolution), ultra (1920). `"aspect"`
  ("16:9", "2.39:1", "1.85:1", "4:3", "1:1") sets the picture shape. Timing, voices and sound are identical at every level.
- Every scene (a single-scene folder too) renders in its own Blender process into `scenes/NN_id/` (`shot.mp4`,
  `shot.wav` float stereo mix, `shot.timeline.json`, `shot.blend`). A scene re-renders only when its render key
  changes: the scene without its finishing settings, the quality, the render code, and the files it reads (a
  rebuilt character or new recording counts). Then finishing builds `episode.mp4`, `episode.srt/.vtt`,
  `episode_chapters.txt` and `episode_poster.jpg`.
- Finishing settings (no re-render): `"title"`, `"credits"`, `"transition"`, `"transition_seconds"`, `"grade"`,
  `"vignette"`, `"grain"`, `"subtitles"` (soft/burn/off), `"master"` (`loudness`, `true_peak`, `codec`: h264/hevc,
  `fade_in`, `fade_out`), `"poster"`, and per scene `"chapter"`. Design and measurements: `docs/DESIGN_V2.md`.

## Make a scene

```
blender -b -y -P blender/scene_kit.py -- --scene scene.json --out episode.mp4 [--stills 1,60,120]
```

See the docstring of `scene_kit.py` and `docs/GEMINI_SCENE_PROMPT.md` for the scene.json format and examples.
A `say` step can use `text` (spoken with the cast member's Kokoro voice) for a quick draft, or an `audio` WAV
for a performed/generated final line. For external dialogue, include both `audio` and the exact `text` transcript:
the transcript helps Rhubarb lip-sync the mouth to the supplied performance. Keep each line in its own file under
the scene's `voices/` folder, and use a consistent voice for each character. Example:

```json
{"who": "maya", "do": "say", "audio": "voices/maya_001.wav", "text": "I thought you weren't coming."}
```

Kokoro's local voices are currently draft-quality and can sound synthetic, especially when slowed down. Use them
to block timing; replace dialogue with reviewed performances before a final render. In the web app, add or edit
dialogue in the Dialogue and voices form, then upload a WAV performance on that line; the exact transcript is
saved for lip-sync. The Episodes editor also exposes scene settings, cast placement, procedural props, action
steps and finishing controls as forms generated from the shared schema. The advanced scene JSON editor remains
available for settings that do not yet have a dedicated control. `floor` picks footstep sounds
(wood/concrete/carpet/tile). Install Rhubarb Lip Sync 1.14 locally under the ignored
`tools/Rhubarb-Lip-Sync-1.14.0-Windows/` folder and generate local sound assets with
`python generate/make_sfx_library.py sfx`. Generated audio and third-party binaries are not included here.

### Story realism (actions)

- `enter` through a door prop: the door swings open (optional shop bell rings), the person steps in out of the
  daylight and walks to their spot, and the door closes behind them. The picture's wall is cut out inside
  each door opening.
- `open` walks a character within reach of a door prop, keys a reaching arm, and swings the hinged panel open.
  For a door already in a background image, use `match_picture` and `picture_rect` to fit and orient its panel
  from the set relief; optional `side_offset` moves the character toward the handle instead of standing in front.
- `picture_road` projects a marked `screen_path` and width onto the set floor using `generate/set_props.py`;
  the strip keeps the original image texture while behaving as a separate 3D surface.
- `sit` / `stand` on chair, stool, bench or sofa props; a cast member can start seated (`"sit": "<chair id>"`).
  Seated people turn head and shoulders, not the chair.
- `sound` plays a one-shot effect: door_bell, door_open, door_close, chair_sit, cup_place (Stable Audio Open,
  3 takes each, ranked by CLAP with `generate/rank_sfx.py`; the method comes from ForgeFilms).
- `python castforge.py check <folder>` validates Gemini's scene.json (broken JSON, missing files, unknown
  actions, people too close, talking to the camera).

## Tools considered and left out (2026-11-01)

| Tool | Why not |
|---|---|
| AudioCraft (MusicGen/AudioGen), AudioLDM 2 | model weights are non-commercial only; Stable Audio Open (community licence) used instead |
| Wav2Lip, LivePortrait | lip-sync for 2D video; our characters are 3D and lip-sync natively (Wav2Lip is also non-commercial) |
| MagicAnimate, Champ | 2D image-to-video; we animate real 3D rigs. Video-to-3D-mocap is a possible later feature |
| Bounding-box collision sound baker | fires constantly (a character's box always touches the floor); footsteps come from the walk's exact foot landings instead |
| Mixamo (free; Adobe's Blender add-on) | A promising source of pre-made motion clips. The add-on helps import Mixamo FBX animations, but our characters use Rigify; retargeting and motion quality (especially foot contact) must be tested rather than assumed to work automatically |
| X-Muscle System | Candidate for muscle deformation. Evaluate Blender 5.2 compatibility, licensing, performance, and whether it works with our generated characters before adopting it |
| Transformator | Candidate for advanced transformations. Evaluate its exact feature fit, Blender 5.2 compatibility, licensing, and interaction with our rigs before adopting it |

## Known limits

- A set made from one picture has no backs or sides: far camera moves away from the picture's
  viewpoint would show smearing (close-ups are kept near it, with soft background).
- Motion is procedural (heel-toe walk, pelvis/chest counter-turn, weight shifts, speech-synced nods
  and brows). Walk stride distance and footfall timing are synchronized; scene builds add subtle,
  rig-weighted arm/thigh flex correctives driven by elbow bend and stride. These are not a detailed
  muscle simulation, and outfits or non-CastForge rigs still need visual review. Motion-capture clips
  (e.g. CMU or Mixamo) retargeted to Rigify would be the next level.
- Face likeness needs a sharp face (≥ ~250 px wide): full-body photos alone give a soft face.
- The photo's lighting is baked into the face texture.
- Hair is chosen from length only (short/medium/long), or set with `--hair`. The web app should let the user
  pick from thumbnails. short02/short04 have stray strand cards; short01 is the clean male default.
- Never build likenesses of real people without their consent (that includes celebrities).
- Patterned clothes keep the asset's pattern; only colour follows the photo.
- Photo lighting shifts colours a little; the skin tint is deliberately gentle.
- There's a hairline sliver at the back hem of the male sweater.

## Closing the animation-quality gap

Blender Studio's results come from the whole production process—strong acting and shot choices, repeated animation
polish, cohesive art direction, lighting, sound, and review—not from a single add-on. A practical path for CastForge:

1. Pick one short benchmark scene and define the intended style, camera, and emotional beat before adding features.
2. Block poses and timing against video reference; refine silhouette, weight, foot contact, arcs, overlap, and facial
   acting. Review the shot at playback speed, not just as still frames.
3. Validate a small motion library on our Rigify characters. Retarget clips, then correct foot sliding, hand contact,
   transitions, and character scale before using them in scenes.
4. Add muscle/deformation tools only after the base rig and poses work; test extreme poses and render cost on the
   target laptop.
5. Polish the camera, lighting, materials, environment, sound, and edit together. Compare successive renders of the
   same benchmark shot and keep the improvements that survive playback.

Blender Studio shares production knowledge, training, and open-movie material at
[studio.blender.org](https://studio.blender.org/). Study a short sequence and recreate its process in a small test
shot; treat its films as a craft and production benchmark, not a feature checklist.

## Roadmap

See `docs/ROADMAP.md`. Working rules and the code map for contributors: `CLAUDE.md`.
