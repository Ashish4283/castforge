# CastForge roadmap (short; update when an item ships)

## Direction (2026-11-10)
Target: game-cinematic quality an enthusiast can make and publish: real motion, clear character designs,
fights that read well. Built as **mini projects**, each with a file contract (what it reads and writes), that
later combine into one studio. Phase 1: small test versions on the local GPU (RTX 3050, 4 GB). Phase 2, once
promising: a rented GPU with ComfyUI and FLORA character design feeding the 3D pipeline (movies and games).
Not reachable on 4 GB: battles of hundreds, film-grade fur/cloth, photoreal skin; a stylised look gets more
per GPU-second.

## Mini projects (in order)
| Project | Contract | State |
|---|---|---|
| Motion library | Mixamo FBX / CMU BVH -> `motions/clips/<name>.blend` + `.json`; scene step `perform` | v1 done 2026-11-10 |
| Hands and weapons | `hold`/`release` steps: carry grips (stick/palm, `acting.carry_grip`), props ride the hand through walks and clips (a held crowbar swings with a punch clip); `clap`; `duck` step; `crouch` posture | v1 done 2026-11-14 |
| Live character, dressed | The live view wears what the design picks - hair, beard, eyebrows, eyes, clothes, shoes, hat - with their own textures and the design's colours, all following the sliders. Each piece carries MakeHuman's own binding (3 body vertices, 3 weights, a scaled offset), so the browser reproduces a real fit to 0.0002 mm on any body, and the body under a garment is left undrawn exactly as the build leaves it | done 2026-11-23 |
| Live body in the designer | The shape changes under your hand as a slider moves: a "kit" (the body plus every morph it can take) is made once per sex, age band, build and height band in about nine seconds, then morphed in the browser. Drag to turn, green ring to spin, red ring to tip, wheel to zoom, and the camera closes in on whatever is being edited | done 2026-11-23 |
| Character creator | 68 sliders (48 face, 20 body) from -1 to +1 over MPFB's own morph targets, grouped by feature; the whole-head shape, 18 hair styles and 12 eyebrow shapes as choices. One table (`core/appearance.py`) feeds the design vocabulary, the app's form and the build | done 2026-11-23 |
| Hands v3 | The thumb closes across the fingers (`thumb.01`, measured: a fist's thumb tip sits 0.5 cm off the index and middle phalanges instead of 3.5 cm beside them); the wrist gained its second axis (deviation) and human limits (flex 80, extend 70, radial 20, ulnar 35 degrees) | v3 done 2026-11-23 |
| Hands v2 | grips measured off the built prop instead of a guessed cube, so a lantern hangs from the hand clear of the palm and the fingers close only as far as the prop allows; fists during fighting clips (clips carry no finger data); a wrist channel in `key_arms`; the clap rebuilt from rig measurements (palms meeting, fingers forward) | v2 done 2026-11-17 |
| Fight choreography | `strike` step: one beat = close to reach, attack clip, impact sound on the contact frame, hit-stop freeze, reaction (stagger/dodge/block); director covers a fight as two-shot -> push-in -> tight on contact -> reaction, with faster cuts | v1 done 2026-11-16 |
| Reusable sets | a set folder (picture + `set_blueprint.json` + shared depth) that many scenes use: scene key `set_folder` brings the picture, the geometry and everything standing in the room; a scene prop with a set object's id moves it without re-describing it | v1 done 2026-11-23 |
| Editor 1: 3D scene editor | app: the scene in 3D (preview.glb), play/scrub, timeline of steps, drag start spots and walk targets, undo, save history | v1 done 2026-11-10 |
| Editor 2: pose fixes | pick a character in the 3D view, scrub to the moment, turn a body part with X/Y/Z dials; stored in scene.json `fixes` and re-applied as the last layer of every render, fading in and out | v1 done 2026-11-17 |
| Editor 3: character design | design editor over `<name>.design.json` (body, face, hair, outfit, costume), ready-made looks, previews, rebuild; costume kit: long coat, fabric, fur trim, belt+buckle, gloves, boots | v1 done 2026-11-11 |
| Costume kit v2 | whole-body styles (suit, formal, work, robe, tunic), cape, metal armour (breastplate, pauldrons, bracers, greaves), 5 hats, 6 ready-made looks | v1 done 2026-11-18 |
| Costume kit v3 | hood as a shell of its own (`costume.hood`): rings from the shoulders over a domed crown, face open, back draping onto the shoulders, taken off the garment as its own object; ranger and monk looks | v3 done 2026-11-23 |
| Costume kit v4 | fur with hair strands; cloth simulation on capes and robes (both want GPU time we do not have on 4 GB at render); cleaner armour plate edges; accessories (scarf, bag, glasses) | |
| Editor 4: art | props are squares in the 3D view and move by dragging (a set object's move is written as an override); the editor's lights follow the scene's lighting mood and weather. Still open: light/weather/grade edited in the 3D view itself | part done 2026-11-23 |
| Empty sets | a set picture can be emptied of the furniture lifted into 3D (`/api/set/empty`, grows the wall and floor in behind each marked object) or given an empty version made elsewhere; scenes on the set stand their props in it | v1 done 2026-11-23 |
| Motion library page | app: search CMU, import Mixamo files, preview a clip, pick from/to visually | with canvas |
| City library v2 | 11 more buildings on the proven facade styles (apartment block, office block, warehouse, factory, school, bank, cafe, supermarket, petrol station, barn, church) and a new street-furniture family (fence, bus shelter, billboard, fountain). Facade details no longer land on trees, roads and street pieces, and the factory-startup cube no longer stands in every small asset | v2 done 2026-11-23 |
| 3D sets for action | free CC0 kits and the city library instead of the 2.5D picture | |
| Any humanoid character | imported rigged model (bone map like motion.py) + costume and armour props | |
| Face capture | webcam -> MediaPipe blendshapes -> face keys | |
| Publish kit | `castforge.py publish` + app button: delivery checks (picture, sound, loudness, subtitles, chapters), YouTube package (video at -14 LUFS, 1280x720 thumbnail, folded chapters, description); the title-card chapter bug is fixed at the source | v1 done 2026-11-12 |
| Phase 2 bridge | rented GPU: ComfyUI + FLORA designs -> image-to-3D -> rig -> CastForge | later |

Motion limits: fingers stay procedural (clips carry none; since 2026-11-17 a fighting clip's hands are closed
from the clip name, or the `hands` parameter). Since 2026-11-14 the root rides the clip's true hip path (follow
camera and gaze track it) and a measured counter-shift holds the grounded foot still (the clip says when a foot is planted; the character's own foot is measured and the drift keyed away). Mixamo files are downloaded by the
user (free Adobe account) and must not be redistributed: `motions/` is git-ignored.

| Sound mix v2 | effects fade with distance from the camera like footsteps do (`media.distance_gain`, one place for both); the background bed is spread left and right instead of sitting dead centre (`ambience_width`); how far music and background dip under dialogue is a scene setting (`music_duck_db`, `ambience_duck_db`) | v2 done 2026-11-23 |

| GPU queue | asking for a second GPU job while one is running queues it instead of refusing it: it starts on its own when the GPU frees up, the sidebar lists what is waiting with a way to drop it, and an episode waiting its turn says so (`/api/gpu`, `/api/gpu/cancel`) | v1 done 2026-11-23 |

| Quality pass | what a scene inherits from a set is one tested function (`sets.use_set`) instead of ten lines inside scene_kit; the Gemini prompts are now checked against every scene key and every design key, not just actions and props; README brought up to date | done 2026-11-23 |

## Maintenance
Check character skin/highlights under `Standard`; assemble acts into one film (`movies/<m>/film.json`);
disk clean-up command.

## Done
React app with sidebar (2026-11-11): Overview, Episodes (scene, script, 3D editor, output, finishing, JSON),
Characters + designer, Sets, Props, City library, Help. v2 (2026-11-02): render/finish split, BT.709 + 48 kHz + loudness mastering, set picture fidelity, expressions,
gaze, gestures, posture, pace, narrator, voice FX, ducking, panning, director + camera steps, lighting moods,
weather, 40 props, titles/credits/transitions/grades/subtitles/chapters/poster, storyboard, city library
(Copilot), schema-driven app forms. Motion library v1 (2026-11-10).

## Film needs (movies/santa_is_a_lie/STORY.md)
Missing: crowd queue. (Sounds done 2026-11-16: door_slam, lock_bolt, crowbar, crash, crowd_murmur,
truck_driving, plus the fight set hit/hit_hard/block/whoosh/body_fall.)
