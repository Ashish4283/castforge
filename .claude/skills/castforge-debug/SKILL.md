---
name: castforge-debug
description: Work out what is actually wrong in CastForge before changing anything - reproduce the report, tell a stale build from a real bug, and check the traps this project falls into. Use whenever something is reported as broken, missing, not rendering, or not appearing.
---

# Finding out what is really wrong

The expensive mistakes in this project were not hard bugs. They were fixing the wrong thing because
nobody reproduced the report first.

## Reproduce before you touch anything

A report like "I picked the set and it would not render" is a recipe. Follow it exactly and get the
error on your own screen. Two minutes here has repeatedly saved an hour:

```bash
python castforge.py check movies/<movie>/<ep>        # what the app's Check button runs
python castforge.py episode movies/<movie>/<ep>      # then watch render.log
grep -iE "Traceback|ERROR|CF: " movies/<movie>/<ep>/render.log | tail -20
```

Build the smallest version in a temp folder and run `schema.check_scene` on it. If the reported error
does not appear, the report is about something else - say so and keep looking, rather than fixing a
thing that was never broken.

## "Nothing changed" is usually one of three things

Work through them in order; the first two are the answer most of the time.

1. **The bundle was not rebuilt.** `cd web && npx vite build` writes into `app/ui/`. Prove it:
   `grep -c "<a new string>" app/ui/assets/index-*.js`
2. **The server was not restarted.** A new route answering 404 is old Python.
   `curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8765/api/<new route>"`
3. **They are looking at a page you did not change.** Overview is where people land; most work lives
   inside an episode. That is a discoverability bug of yours, not a mistake of theirs.

Only after all three: suspect the code.

## Missing files have a shape

Before concluding that something deleted data, look at **what else is missing**. `real/`, `post/`,
`publish/`, `check/` and `storyboard.jpg` all gone at once is not a sweep (a sweep takes named kinds) -
it is an episode that was deleted and made again. One folder missing is a bug; everything missing is a
different event.

`core/housekeeping.py` says exactly what any sweep may take. Nothing outside `KINDS` is ever touched,
and `KEEP` is never touched at any depth.

## Traps this project falls into

- **The Kaggle CLI prints its errors and exits 0.** Read the words, never the return code. It also
  SKIPS folders unless you pass `--dir-mode`.
- **ComfyUI is started with `--output-directory`**, so its pictures are not under `comfy/output`.
- **Headless Chrome with `--disable-gpu`** screenshots the whole page black once a WebGL canvas is on
  it. Use `--use-angle=swiftshader --enable-unsafe-swiftshader`.
- **`ffmpeg -pattern_type glob`** is not in every build; the error says "Function not implemented".
- **Heredocs in the Bash tool eat backslash escapes.** `\n` inside a Python string written through a
  heredoc becomes a real newline and breaks the file. Use the editor for anything with escapes.
- **Three Pythons.** System `python` has torch, transformers, Kokoro, Depth Anything. `.venv` has
  MediaPipe and pytest and NO torch. Blender has its own. `config.AI_PYTHON` is the first one.
- **`npx tsc` from the repo root** installs an unrelated package. Run it from `web/`.

## Run it against real data

Invented test data agrees with you. Real data does not, and it is where the interesting bugs are:

- the real cast caught "heavy brow" being read as a heavy build, a decade nobody listed, and a war-horse
  being built as a human being
- the real designs caught a navy coat being named purple, because nearest-in-RGB is not nearest to the eye
- the real film caught a close-up that image-to-video barely changed, which is the whole reason the
  realism pass exists

After a pure module passes its tests, run it over `movies/santa_is_a_lie` before believing it.

## When you report back

Say what you reproduced, what caused it, and what you changed - in that order. If something is still
broken or untested, say which. A fix reported as working that was never run is worse than no fix: it
costs the next person the same hour to find out.
