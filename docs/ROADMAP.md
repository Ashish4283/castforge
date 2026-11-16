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
| Fight choreography | `strike` step: one beat = close to reach, attack clip, impact sound on the contact frame, hit-stop freeze, reaction (stagger/dodge/block); director covers a fight as two-shot -> push-in -> tight on contact -> reaction, with faster cuts | v1 done 2026-11-16 |
| Editor 1: 3D scene editor | app: the scene in 3D (preview.glb), play/scrub, timeline of steps, drag start spots and walk targets, undo, save history | v1 done 2026-11-10 |
| Editor 2: pose fixes | grab a body part at a moment and rotate it; stored as fixes in scene.json, re-applied on every render (animation layer) | next |
| Editor 3: character design | design editor over `<name>.design.json` (body, face, hair, outfit, costume), ready-made looks, previews, rebuild; costume kit: long coat, fabric, fur trim, belt+buckle, gloves, boots | v1 done 2026-11-11 |
| Costume kit v2 | more looks (uniforms, armour, robes); capes/hoods as real garments; fur with hair strands | |
| Editor 4: art | light, weather, grade, props per scene, previewed in the 3D view; move seats and props by dragging | |
| Motion library page | app: search CMU, import Mixamo files, preview a clip, pick from/to visually | with canvas |
| 3D sets for action | free CC0 kits and the city library instead of the 2.5D picture | |
| Any humanoid character | imported rigged model (bone map like motion.py) + costume and armour props | |
| Face capture | webcam -> MediaPipe blendshapes -> face keys | |
| Publish kit | `castforge.py publish` + app button: delivery checks (picture, sound, loudness, subtitles, chapters), YouTube package (video at -14 LUFS, 1280x720 thumbnail, folded chapters, description); the title-card chapter bug is fixed at the source | v1 done 2026-11-12 |
| Phase 2 bridge | rented GPU: ComfyUI + FLORA designs -> image-to-3D -> rig -> CastForge | later |

Motion limits: fingers stay procedural. Since 2026-11-14 the root rides the clip's true hip path (follow
camera and gaze track it) and a measured counter-shift holds the grounded foot still (the clip says when a foot is planted; the character's own foot is measured and the drift keyed away). Mixamo files are downloaded by the
user (free Adobe account) and must not be redistributed: `motions/` is git-ignored.

## Maintenance
Check character skin/highlights under `Standard`; one GPU job queue (character, set, SFX builds bypass
`.render.lock`); assemble acts into one film (`movies/<m>/film.json`); disk clean-up command.

## Done
React app with sidebar (2026-11-11): Overview, Episodes (scene, script, 3D editor, output, finishing, JSON),
Characters + designer, Sets, Props, City library, Help. v2 (2026-11-02): render/finish split, BT.709 + 48 kHz + loudness mastering, set picture fidelity, expressions,
gaze, gestures, posture, pace, narrator, voice FX, ducking, panning, director + camera steps, lighting moods,
weather, 40 props, titles/credits/transitions/grades/subtitles/chapters/poster, storyboard, city library
(Copilot), schema-driven app forms. Motion library v1 (2026-11-10).

## Film needs (movies/santa_is_a_lie/STORY.md)
Missing: crowd queue. (Sounds done 2026-11-16: door_slam, lock_bolt, crowbar, crash, crowd_murmur,
truck_driving, plus the fight set hit/hit_hard/block/whoosh/body_fall.)
