# CastForge roadmap (short; update when an item ships)

## Done (v2, 2026-11-02)
Render/finish split, BT.709 + 48 kHz + loudness mastering, set picture fidelity, expressions, gaze, gestures,
posture, pace, narrator, voice FX, ducking, panning, director + camera steps, lighting moods, weather, 40 props,
titles/credits/transitions/grades/subtitles/chapters/poster, storyboard, stop/finish/voice/transcribe/doctor,
city library (Copilot), schema-driven app forms.

## Next (in order)
1. Check character skin/highlights under `Standard` at standard quality; tune `world.NOMINAL` if needed.
2. One job queue for all GPU work (character, set, SFX builds still bypass `.render.lock`).
3. Stage map in the app (drag cast/props on `set/floor_map.png`).
4. Hand contact (IK): hold, carry, clap, dust sleeves — the Santa film needs hold/carry.
5. Assemble acts into one film (`movies/<m>/film.json` listing episodes).
6. Disk clean-up command (old frames, voices, sets).

## Later
Crowds, mocap retargeting (CMU/Mixamo), vehicles on paths, Chatterbox TTS engine, YouTube upload,
Origin check on the local server.

## Film needs (movies/santa_is_a_lie/STORY.md)
Missing: hold/carry, crouch/duck, crowd queue, Santa suit prop, sounds (door slam, lock bolt, crowbar,
crash, crowd murmur, truck driving: add prompts in `generate/make_sfx_library.py`, run `--missing`).
