# CastForge

Photo of a person → rigged, dressed, lip-sync-ready 3D character in Blender → animated, voiced episodes.
Goal: a very easy tool for making animation. Every step is a script, so the web app can run the whole chain.

**Free and local.** Everything runs on the laptop (RTX 3050 4 GB) with free tools and CC0 assets. Nothing uses AWS
or paid GPUs.

## Status (2026-11-01)

| Stage | State |
|---|---|
| 1. Photo → spec (`generate/analyze_photo.py`) | **Working.** MediaPipe on CPU: body proportions, skin/hair/top/bottom/shoe colours, garment (trousers/shorts/skirt/dress), sleeves, hair length, photo-quality warnings |
| 2. Spec → character (`blender/build_character.py`) | **Working, ~45 s.** MPFB body fitted to the photo, matching skin, hair, CC0 clothes recoloured to the photo, garment layering, Rigify rig, 15 visemes + 52 ARKit face shapes, A-pose |
| 3. Pose check (`blender/pose_test.py`) | Working: clothes, hair and shoes follow the rig; visemes and blinks work |
| 4. Face likeness | **Working.** MediaPipe 478 landmarks → ~40 MakeHuman face shapes fitted (error ~2.5 → ~1.3 mm) + the photo's face blended onto the head through a landmark-guided warp (eyes/mouth interior kept 3D); nearest eye colour. Needs a face close-up (`--face-photo`) for a sharp result |
| 5a. 3D set from the background (`generate/depth_set.py`) | **Working.** Depth Anything V2 (local) + floor calibration → solid relief set (characters stand among the furniture, hidden behind it, shadows on it) and a walkable-floor map; walks route around obstacles (A*), positions inside furniture snap to free floor; close-ups dolly in near the picture's viewpoint with shallow depth of field. `"set": "flat"` turns it off |
| 5b. Set-to-props (`generate/set_props.py`) | Camera-matched floor props from marked image-space paths; the generated road mesh uses the background's UV texture and is cut out of the relief to prevent overlapping surfaces. Photographed doors can be fitted as hinged picture props. |
| 5. Scene kit (`blender/scene_kit.py`) | **Working (lip-sync under test).** scene.json → background with shadow-receiving floor, cast placement, walk (planted feet), face, say (Rhubarb lip-sync), open/enter/exit doors, wait; blinks, breathing, talking head motion; Kokoro draft voices and WAV dialogue for final performances; footsteps on every landing (Stable Audio Open library); MP4 with mixed audio |
| 6. Web app | Working: local movie/scene browser, character and render controls, form-based dialogue editing and WAV voice uploads; advanced scene JSON remains available |
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
python castforge.py episode <folder> [--quality blocking|draft|standard|final] [--wait]
python castforge.py status <folder>
```

- Runs in the background (one render at a time; the 4 GB GPU cannot run two) and resumes after a stop.
- Quality: blocking (default, 480x270), draft (640x360), standard (960x540), final (scene resolution).
  Timing, voices, lip-sync and sound are identical at every level.
- An episode can be split into scenes (`"cast"` once + `"scenes": [...]`). Each scene is rendered in its own
  Blender process into `scenes/NN_id/shot.mp4` (+ .blend), unchanged scenes are reused, and the shots are
  joined into `episode.mp4`. The per-scene shots are the hand-off unit for ForgeFusion (CastForge +
  ComfyUI/ForgeFilms).

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
saved for lip-sync. The advanced scene JSON editor is optional. `floor` picks footstep sounds
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

1. Face likeness from the photo (project the face onto the head texture; FLAME-style shape fit later).
2. Scene kit: import Gemini backgrounds/audio/dialogue; place characters; walk/stop/turn/sit clips (free mocap,
   e.g. CMU, retargeted to Rigify); lip-sync from dialogue audio (Rhubarb Lip Sync → the visemes already on the
   character).
3. More scene actions (each one a step type in scene.json):
   - `hold`: IK hands pinned to a prop (cup, phone, gun grip, handlebars);
   - `sit`;
   - `drive`/`fly`: vehicle on a path;
   - `hit`/`crash`: Blender rigid-body physics, with impact sounds placed at the simulated contact frames;
   - fog/clouds as volume shaders (light on VRAM);
   - baked cloth (parachute, capes);
   - props from TripoSR (MIT).
4. Set builder (real 3D rooms/streets instead of a 2.5D background image):
   - props with options (`spin` for fans; hinged windows and doors);
   - cloth curtains/bedsheets with a pinned top edge and wind;
   - Cycles option for final renders (OptiX, Fast GI, fewer bounces).
5. Toon style (`"style": "toon"`): Line Art ink outlines + cel shading, the OpenToonz look without hand drawing.
6. Web app (local FastAPI): upload photo → form (gender/age/height) → preview turntable → download .blend.
4. Render + YouTube Data API upload (with the synthetic-content disclosure).

Alternative for photo-exact geometry: `generate/space_reconstruct.py` (PSHuman on a free Hugging Face Space). The
free GPU quota is too small for regular use.
