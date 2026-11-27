# CastForge Easy Studio: architecture and work plan

**For:** AI agents (Claude Opus at low to high effort) and people picking up CastForge UI and flow work.
**How to use this file:** read Part A once. Then take the FIRST unchecked ticket at or below your level in
Part D, do only that ticket, tick it, add one line to the Status log (Part G), commit. Then take the next.
Part B is the map of what exists today, Part C is what the finished app looks like, Part E is the bug list,
Part F is how to do the common things.

`castforge/CLAUDE.md` is still the rule book for the ENGINE (Blender, renders, schema). This file is the
rule book for the APP: what the person using it sees and does.

---

## Part A. What we are building, and the rules

### A1. The promise

> A child with an idea gets a movie, without filling in a form and without asking anyone what to do next.

Six promises. Every change must keep all six true; together they are the acceptance test for the app.

| # | Promise | You can tell it holds when |
|---|---|---|
| P1 | **One path.** The app always shows where you are and what comes next. | The Story Path bar is on every making page and the Next button always does something useful. |
| P2 | **Pictures, not forms.** | Text boxes exist in three places only: the words a character says, a name (born filled, renaming optional), and the Pro-only JSON tab. Everything else is a picture card, a chip, a slider with picture ends, a pad you drag on, or a big button. |
| P3 | **Born playable.** | Anything new (movie, episode, scene, a person put in a scene, a story block) works the moment it exists. Nothing has a required field. |
| P4 | **Everything made is in My movies.** | Films, graded cuts, photographed stills and clips, local or from the rented GPU, show up in My movies by themselves, newest first. Deleting an episode never deletes rented-GPU work. |
| P5 | **You can see what is cooking.** | One "Working on it" place lists everything running in plain words with progress, and ends with "Ready: watch it" and a button. |
| P6 | **Every problem comes with its fix.** | No error is only words. Each one carries the button that fixes it ("Scene 2 has nobody in it" + **Put someone in**). |

### A2. The path (the spine of the app)

Seven stops, always in this order. Kids see the middle column; the code uses the right one.

| Stop | Kid words | In the code | Done when |
|---|---|---|---|
| 1 | **Who** | characters (built `.blend` in `movies/<film>/characters/`) | every character the episode uses is built |
| 2 | **Where** | per scene: `set_folder` (a built set) or `background` (a picture) | every scene has a place |
| 3 | **What happens** | per scene: `cast` + `script` | every scene has someone in it and at least one step |
| 4 | **Try it** | 3D preview (`scenes/NN_id/preview.glb`) | optional: every scene has a preview |
| 5 | **Make the movie** | render + finish -> `<episode>/episode.mp4` | the film exists and is newer than `scene.json` |
| 6 | **Make it real** | rented GPU: photographed stills + Wan 2.2 clips | optional: a run for this episode came home |
| * | **My movies** | `#/results` | always open |

The path is DECIDED on the server by one pure function (`core/journey.py`, ticket E1.1) and only DRAWN by
the browser. Never work out "what is next" inside a React component: it will disagree with the server the
first time anything changes.

### A3. The layers (do not cross them)

```
 web/src (React 18 + TS)   shell: Sidebar, StoryPath, NextButton, WorkingOn, Simple/Pro switch
                           stops: Who, Where, What happens, Try it, Make, Make it real, My movies
                           kit:   components/controls.tsx, ParamInput.tsx (by TYPE), glyphs.ts, guide.ts, words.ts
        |  JSON over HTTP (web/src/api.ts: api(), post())
 app/server.py             THIN routes: gather facts from disk -> call a pure module -> return JSON
        |
 core/, shared/ (pure)     decisions and vocabulary: schema, journey, remote_runs, real, housekeeping, sets
 background jobs           episode_job.py (render), builds (.build.lock), the remote-run watcher thread
 blender/ (bpy)            the actual making; never imported by core/
 movies/<film>/            THE ONLY place results live
```

1. **Decisions live in pure modules, with a test.** A route that decides something (what is next, where
   a file goes, what a Kaggle status means) calls a function in `core/` or `shared/` that has a test in
   `tests/test_<module>.py`.
2. **One source per fact.** Engine vocabulary: `core/schema.py`. Kid words (menu, tabs, stops):
   `web/src/words.ts`. Explanations (the `?` panels): `web/src/guide.ts`. Never type a label twice.
3. **Results live in `movies/<film>/`.** Episode outputs in `<episode>/`; rented-GPU runs in
   `movies/<film>/gpu/<run>/`, which no episode delete touches, ALSO copied into `<episode>/real/` so the
   episode's own Output tab shows them.
4. **Every place is a route.** If the Next button cannot link to it (`#/episodes/act1/scene/2`), it is
   not reachable. localStorage is for preferences (Simple/Pro, last tab) and never the only record of
   WHERE you are.
5. **One copy of state.** Where heavy work runs: `components/GpuPicker.tsx`. Running jobs, route, mode,
   journey: `app/store.tsx`. Never a second copy in a page.

### A4. Simple and Pro

One switch in the sidebar foot: **Simple** (the default) and **Pro**.

- **Simple** shows the path, pictures and big buttons. Hidden: the JSON tab, The cut tab, the Suite, City
  library and Props pages, numeric fine-tuning (a **More** chip opens it per step), and every word on the
  jargon list in A5.
- **Pro** shows everything that exists today.
- Nothing is deleted to make Simple. It is hidden behind `mode === "pro"`.

### A5. Kid design rules (check every screen against these)

1. One primary button per screen (filled, warm colour): the thing to do next. Everything else is quiet.
2. Tap targets at least 44 x 44 px. Body text at least 15 px. Step titles at least 20 px.
3. Every choice shows a picture: a thumbnail, a glyph from `glyphs.ts`, or an emoji. Words go under the
   picture, never instead of it.
4. At most two levels deep: a page and one panel. No modal on a modal, no form in a tab in a card in a tab.
5. Empty is never blank: a big picture, one sentence, and the button that fills it.
6. Plain words. **Jargon list (never in Simple):** render, JSON, schema, param, preset, denoise, fps,
   LUFS, kernel, glb, blend, workflow, ControlNet, checkpoint, LoRA, seed, CFG, pipeline, queue.
   Say instead: make, the movie, look, speed, sound level, rented GPU, picture, waiting.
7. Anything that takes time shows a moving bar and a sentence ("Making your movie: scene 2 of 3") and ends
   with a button ("Watch it").
8. Colour is never the only signal: a done stop has a tick AND a colour.
9. No accent colour is laid over the 3D view (a character is judged against a quiet ground).

### A6. Rules for agents (every session)

1. Follow the token rules in `castforge/CLAUDE.md`. Do not explore: use the map in Part B and that file's
   code map, `grep -n` the anchor, read only that range. Never open `movies/` (a top-level `ls` of one
   film is fine), `library/`, `test/`, `tools/`, `sfx/`, `motions/`, `asset_packs*/`, `.venv/`,
   `web/node_modules/`, `app/ui/`, `*.blend`.
2. `git status` first: the user also edits with GitHub Copilot. Work on branch `castforge-v2`, never
   `main`. One ticket = one commit, ending with the attribution line your session gives you.
3. Ports: the user's app is **8765** (never stop or restart it). Your test server is **8787**
   (`.claude/skills/run-castforge`). `npm run dev` proxies its API to 8777.
4. Never make a Kaggle dataset public (no `-u`): it holds frames from the user's film.
5. Bash heredocs break on apostrophes and backslashes on this machine. Write files with your file tool, or
   write a script to a file and run it.
6. **Done means seen.** A UI ticket is done when you have built the bundle (`cd web && npm run build`),
   started the 8787 server, driven the page in headless Chrome (run-castforge skill: CDP over
   `websockets`, `--use-angle=swiftshader --enable-unsafe-swiftshader`) and LOOKED at the screenshot.
   Write what you saw in the Status log.
7. Add a test with every pure-logic change. `.venv/Scripts/python -m pytest -q` must be green (about 600
   tests, under a minute) before every commit.
8. Cannot finish? Write what you found under the ticket as **Notes:** and stop. A half-done ticket that
   says so beats a "done" that is not.
9. Never ship a feature the user cannot find. The path, the menu or the Next button must reach it.
10. The user's word for what is wrong beats your theory of it. Reproduce what they describe, in the app.

---

## Part B. Where things are today (UI map, 2026-11-27)

| What the user sees | File | Notes |
|---|---|---|
| Left menu, GPU lines, running jobs | `web/src/layout/Sidebar.tsx` (`NAV` list; status in the foot) | groups Produce / Assets / Support |
| Page switch | `web/src/main.tsx` `switch (route[0])` | studio, episodes, results, characters[/name], sets, props, library, suite, help |
| Route, toasts, polling | `web/src/app/store.tsx` (`go(...parts)`, `route`, polls `/api/gpu` + `/api/jobs` every 3 s) | `go("a","b")` sets `#/a/b`; each part is URI-encoded |
| Open episode, current scene | `web/src/app/episode.tsx` (`open`, `part`, `setPart`, `update`, `save`, `scene()`, `cast()`) | episode in localStorage `cf.episode.<movie>`, tab in `cf.epTab`, scene in memory only (E1.2 fixes) |
| Overview | `web/src/pages/Studio.tsx` <- `/api/movie/progress` (`server.py` `def movie_progress`, `def episode_progress`) | movie-level steps: story, cast, sets, storyboard, render, finish |
| Episode page and its tabs | `web/src/pages/episodes/Episodes.tsx`: tab ids `scene` (Stage), `script`, `3d`, `output`, `finishing` (The cut), `json` | |
| Scene strip and set shelf | `pages/episodes/Scenes.tsx` | drag a set onto a scene |
| Stage: floor, actors, props | `pages/episodes/SceneSetup.tsx` (exports `PutSomeoneIn`, `Actor`, `PropPanel`, `NewProp`) | |
| Script | `pages/episodes/Script.tsx` (add palette at the top) | each step row picks who/what with `<Select>` drop-downs: form-like |
| 3D editor and its dock | `pages/episodes/Editor3D.tsx` + `viewer.ts` | needs `preview.glb`: the **Build 3D preview** button |
| Output: render, film, photoreal clips | `pages/episodes/Output.tsx` | |
| Space on disk, rename, delete episode | `pages/episodes/Space.tsx` | |
| My movies (menu label today: Results) | `pages/Results.tsx` <- `/api/movie/results` | reads episode folders only |
| Make it real | `pages/Suite.tsx` <- `/api/suite/real` | shows a PLAN and a CLI command; cannot start anything (E2) |
| Where heavy work runs | `components/GpuPicker.tsx` (`GpuWhereLine` in the sidebar foot) | `local` / `kaggle` |
| `?` panels | `web/src/guide.ts` + `<Guide topic>` from `components/ui.tsx` | |
| Controls | `components/controls.tsx`, `components/ParamInput.tsx`, `components/glyphs.ts` | |

**The rented GPU today.** `python castforge.py real FOLDER --gpu` pushes a dataset and the
`castforge-clips` kernel to Kaggle. `python castforge.py real FOLDER --fetch [--from DIR]` downloads the
finished run and files it. Only ONE remote run can be in flight: the kernel slug is fixed, so a new push
replaces the old one. Kaggle tells you the state with `kaggle kernels status ashishjiwa/castforge-clips`
("KernelWorkerStatus.RUNNING" / "COMPLETE" / "ERROR"). Details: `.claude/skills/castforge-gpu`.

**Form inventory** (count of `<input>` / `<textarea>` / `<Select>` per file, 2026-11-27; `controls.tsx`,
`ui.tsx` and `ParamInput.tsx` are the kit itself and do not count):

| File | inputs | textareas | Selects | Notes |
|---|---|---|---|---|
| `pages/Sets.tsx` | 6 | 0 | 3 | biggest offender |
| `pages/Library.tsx` | 5 | 0 | 1 | Pro only |
| `pages/Characters.tsx` | 3 | 1 | 2 | |
| `pages/CharacterDesigner.tsx` | 3 | 0 | 2 | |
| `pages/episodes/Editor3D.tsx` | 3 | 0 | 1 | |
| `pages/episodes/Script.tsx` | 1 | 1 | 4 | the line textarea STAYS (spoken words) |
| `pages/episodes/Episodes.tsx` | 2 | 0 | 1 | new-episode name |
| `pages/episodes/Finishing.tsx` | 2 | 1 | 0 | Pro only (titles, credits) |
| `pages/Props.tsx` | 2 | 0 | 2 | Pro only |
| `pages/episodes/Space.tsx` | 2 | 0 | 0 | rename + typed delete confirm: keep, it is a safety catch |
| `pages/SetAnnotator.tsx` | 2 | 0 | 1 | Pro only |
| `pages/episodes/SceneSetup.tsx` | 1 | 0 | 1 | |
| `pages/episodes/Scenes.tsx` | 1 | 0 | 0 | new-scene name |
| `pages/characters/LivePreview.tsx`, `LookPicker.tsx` | 3 | 0 | 0 | check each |

---

## Part C. The target (what the finished app looks like)

### C1. Screen layout in Simple mode

```
+-----------+---------------------------------------------------------------------------+
| CastForge | (1) Who v -- (2) Where v -- (3) What happens * -- (4) Try it -- (5) Make -- (6) Real  * My movies |  <- StoryPath (E1.3)
|           +---------------------------------------------------------------------------+
| Home      |                                                   [ Working on it: 1 ]    |  <- WorkingOn (E3.2)
| Make      |                                                                           |
| My movies |   the current stop: pictures, pads, big buttons                           |
| Who       |                                                                           |
| Places    |                                                                           |
| Help      |                                              +------------------------+   |
|           |                                              |  Next: Try it   ->     |   |  <- NextButton (E1.4)
| (Simple)  |                                              +------------------------+   |
|  Pro      |                                                                           |
+-----------+---------------------------------------------------------------------------+
```

### C2. Data contracts (new)

**1. The journey** (E1.1). `GET /api/journey?movie=M&episode=E`:

```json
{"episode": "act1",
 "steps": [{"key": "who", "title": "Who", "state": "done", "say": "Santa and Arthur are ready",
            "go": ["characters"]},
           {"key": "where", "title": "Where", "state": "now", "say": "Scene 2 needs a place",
            "go": ["episodes", "act1", "scene", "2"]}],
 "next": {"key": "where", "say": "Scene 2 needs a place", "button": "Pick a place",
          "go": ["episodes", "act1", "scene", "2"], "do": null,
          "skip": null}}
```

- `state` is one of `done`, `now` (exactly one step: the next thing), `todo`, `blocked` (needs an earlier
  stop; `say` names it), `optional` (Try it, Make it real: can be skipped).
- `go` is a route: the parts passed to `store.go(...)`. `do` (optional) is an action the target page
  performs when it was reached by pressing Next: `preview` (Build 3D preview), `render` (Make the movie),
  `real` (start the rented-GPU run). The page does exactly what its own primary button does.
- `skip` (optional) is a second, quieter choice with the same shape (e.g. skip Try it -> Make the movie).
- `say` is plain words (A5.6). A test checks every `say` the module can produce for jargon.

**2. A remote run** (E2.1). One folder per run, `movies/<film>/gpu/<run-id>/`:

```
run.json      {"id": "20261127-1830-act1", "episode": "act1", "kernel": "ashishjiwa/castforge-clips",
               "state": "sending|running|fetching|home|failed", "sent": 1764268200, "home": null,
               "note": "", "clips": ["clips/first_scene_1.mp4"], "stills": ["stills/first_scene_1.png"],
               "posters": {"clips/first_scene_1.mp4": "clips/first_scene_1.png"}}
clips/        the animated clips (.mp4) and each clip's starting picture (.png)
stills/       the photographed stills (the realism pass), when the run made them
log.txt       what the GPU said, as plain text
```

Run ids are `YYYYMMDD-HHMM-<episode, / replaced by _>`. Clip names lose Kaggle's suffix
(`first_scene_1-5b-1.mp4` -> `first_scene_1.mp4`).

**3. Routes for remote runs** (E2.2). `GET /api/real/runs?movie=M` -> the runs, newest first, with urls.
`POST /api/real/start {movie, episode}` starts one (refuses in a plain sentence while another is in
flight). `POST /api/real/fetch {movie, run}` = "bring it home now".

**4. What is running** (E3.1). `/api/gpu` gains `"remote": [{"id", "episode", "state", "say", "since"}]`
for runs not yet home.

**5. The route grammar** (E1.2). `#/episodes/<episode>/<tab>/<scene number from 1>`, tab ids as today
(`scene`, `script`, `3d`, `output`, `finishing`, `json`). Old links (`#/episodes`) still work: they open
the last episode.

### C3. A first-timer's whole journey

1. Opens the app. Home says "Make your first movie" with starter stories as big cards (E5.3), or "Start
   from nothing".
2. **Who**: picture cards of built characters; **Make a new one** opens the designer, which has one
   button back.
3. **Where**: the scene strip and set pictures. Tap a set: done.
4. **What happens**: story blocks. Tap Say / Walk / Wave / Look... each block is born with values that
   work; tap a block to change it with pictures. Only Say asks for typing.
5. **Try it**: the 3D view plays the scene; drag people on the floor. "Looks good" -> Make the movie.
6. **Make the movie**: one button. Progress shows in Working on it; when done, a toast "Your movie is
   ready" + **Watch it** -> My movies.
7. **Make it real** (optional): one button, "on the rented GPU, about 15 minutes". Working on it shows
   it; the watcher brings it home on its own; toast; My movies shows the photographed stills and clips.

---

## Part D. Tickets

**Levels.** **L1**: one file, mechanical (Opus, low effort). **L2**: a component or a route that follows an
existing pattern (Opus, medium). **L3**: a new pure module + route + UI, or anything cross-cutting
(Opus, high). Take the first unchecked ticket at or below your level whose dependencies are ticked.

Each ticket: **Why**, **Files**, **Do**, **Done when**, **Don't**.

### E0. Unstick

- [ ] **E0.1 (L1) File the rented-GPU runs that are already on disk.**
  Why: four runs came back from Kaggle but sit in `tmp/clips2`, `tmp/clips3`, `tmp/clips4` (gitignored
  scratch); the copy filed into `act1/real/` was lost when act1 was deleted and remade. My movies is empty.
  Depends on E2.1. Do: file each with `python castforge.py real movies/santa_is_a_lie/act1 --fetch --from
  tmp/clipsN`. Done when: My movies shows the three runs with stills and clips.
- [ ] **E0.2 (L2) Walk the golden path and write down every break.**
  Why: "the project is buggy and stuck". Nobody has walked the whole path since the shell changed.
  Do: on the 8787 server, in headless Chrome, do C3 steps 2 to 6 on `santa_is_a_lie/act1` (blocking
  quality, one scene). Every place it fails, needs a form, or leaves you not knowing what to press: one
  line in Part E with the route and a screenshot path. Do NOT fix during the walk.
  Done when: Part E lists each break with how to reproduce it.
- [ ] **E0.3 (L1) A new episode is born broken.**
  Why (P3): `server.py` `TEMPLATE` gives the first scene `"background": "../sets/<set>/background.png"`, a
  path that does not exist, so a brand-new episode fails its check. Do: drop that key; if the movie has a
  built set, put the first scene on it (`set_folder` + `background`, exactly as `Scenes.tsx` `setOn`
  does). Done when: a new episode passes `castforge.py check` with no ERROR; test in `tests/`.

### E1. Connect the stops (the path)

- [ ] **E1.1 (L3) `core/journey.py` and `GET /api/journey`.**
  Why (P1): Overview says what is next for the MOVIE, nothing says it for the episode you are in.
  Files: new `core/journey.py`, `tests/test_journey.py`, `app/server.py` (route only; reuse
  `episode_progress` and the movie listing for facts).
  Do: `journey(facts) -> {"steps": [...], "next": {...}}` exactly as C2.1. `facts` is a plain dict the
  route gathers: `{"episode", "characters": {name: built}, "scenes": [{"id", "place": bool, "people": int,
  "missing": [names], "steps": int, "preview": bool}], "film": bool, "current": bool, "remote": state or
  None}`. Order and rules are A2. Make is `blocked` while Who, Where or What happens is not done; Make it
  real is `blocked` until the film exists. `next` is the first step that is not done, counting Try it only
  before the film exists (offer `skip` to Make). When everything is done, `next` is "Watch it" -> results.
  Done when: tests cover an empty movie, a missing character, a scene with no place, a scene with no
  steps, a stale film, everything done, a run in flight; and no `say` contains a jargon word (A5.6).
  Don't: touch the disk inside `journey()`.
- [ ] **E1.2 (L2) Every place is a route.** Depends on nothing.
  Files: `pages/episodes/Episodes.tsx`, `app/episode.tsx`, `pages/episodes/Scenes.tsx`.
  Do: read `route[1..3]` (episode, tab, scene number). Arriving with an episode that is not open: `open()`
  it. Arriving with a tab or scene: show it. Clicking a tab or a scene card writes the route with
  `history.replaceState` (so Back is not flooded). Keep the localStorage memory as the fallback.
  Done when: pasting `#/episodes/act1/script/1` into a fresh tab opens act1 on the Script of scene 1.
- [ ] **E1.3 (L2) The Story Path bar.** Depends on E1.1, E1.2.
  Files: new `web/src/layout/StoryPath.tsx`, `app/store.tsx` (hold `journey`, refresh it on route change,
  after `save`, and when a job ends), `main.tsx` (draw it above the page on studio, episodes, results,
  characters, sets), `styles.css`.
  Do: seven stops as in C1: number or glyph, kid word from `words.ts`, a tick when done, a pulse on `now`,
  a lock and the `say` as a tooltip when `blocked`. Click = `go(...step.go)`.
  Done when: screenshot shows the bar; clicking each stop lands on the right tab and scene.
- [ ] **E1.4 (L2) The Next button.** Depends on E1.3.
  Files: new `web/src/layout/NextButton.tsx`, `app/store.tsx` (`pending` action), the pages that honour a
  `do`: `Editor3D.tsx` (`preview`), `Output.tsx` (`render`, `real`).
  Do: fixed bottom-right, the only primary button on screen; label `next.button`, `next.say` under it;
  click -> `go(...next.go)` and set `pending = next.do`; the target page performs it once and clears it.
  `skip` shows as a small link beside it.
  Done when: from an episode with one empty scene, pressing Next only, a person reaches a played film.
- [ ] **E1.5 (L1, one per page) Every empty state has its fix button.**
  Do, for each `<Empty>` in `pages/**`: it gets an `action` that fixes the emptiness (Empty already takes
  `action`). List what you changed here. Done when: grep finds no `<Empty` without `action=` outside Pro.

### E2. The rented GPU, inside the app

- [ ] **E2.1 (L2) `core/remote_runs.py`: where a run lives and what it means.**
  Files: new `core/remote_runs.py`, `tests/test_remote_runs.py`, `castforge.py` (`real --fetch` files
  through it).
  Do: `run_id(episode, when)`, `clean_name(name)` (drops `-5b-1`, `-fast-1`, `-full-1`), `sort_out(paths)`
  (which downloaded file is a clip, a clip's poster, a photographed still, a log; pure, by name and
  folder), `kaggle_state(text)` ("KernelWorkerStatus.COMPLETE" -> `done`, RUNNING/QUEUED -> `running`,
  ERROR/CANCEL... -> `failed`, anything else -> None), `say(run, now)` in plain words, plus small IO
  helpers `file_download(src, run_dir)`, `load(run_dir)`, `save(run_dir, run)`, `listing(movie_dir)`.
  `--fetch` writes a run into `movies/<film>/gpu/<id>/` AND copies clips + stills into `<episode>/real/`.
  Done when: tests cover the names, the sorting, each Kaggle state, the words; `--fetch --from` on a
  download makes a run folder.
- [ ] **E2.2 (L3) Start, watch and bring home a run from the app.** Depends on E2.1.
  Files: `app/server.py` (routes in C2.3 + one watcher thread started with the app).
  Do: `/api/real/start` refuses while a run is `sending`/`running`/`fetching` ("One photoreal run at a
  time: act1 is still on the rented GPU"); otherwise writes `run.json` (`sending`), runs
  `python castforge.py real <episode> --gpu` in the background with its words in `<run>/send.log`, and
  sets `running` when that succeeds (read the WORDS, not the exit code: the Kaggle CLI exits 0 on
  failure). The watcher, every 90 s while any run is `running`: `kaggle kernels status`; `done` ->
  `fetching` -> `kaggle kernels output ... -p <run>/download` -> `file_download` -> `home`; `failed` ->
  `failed` with the log's last useful line as `note`. A restart of the app resumes a `fetching` run.
  Done when: start from the app, close the laptop lid for an hour, open it: My movies shows the clips.
  Don't: make the dataset public; run two at once.
- [ ] **E2.3 (L2) A Make it real button where the film is.** Depends on E2.2.
  Files: `pages/episodes/Output.tsx` (the Photoreal clips card), `pages/Suite.tsx` (point to it).
  Do: show the plan in one line (`/api/suite/real`: clips, seconds) and one button **Make it real on the
  rented GPU**; while a run is out, show its `say` and a spinner instead. Honour `do: "real"` (E1.4).
  Done when: the button starts a run and the card shows it running, in the browser.
- [ ] **E2.4 (L2) My movies shows the runs.** Depends on E2.1.
  Files: `app/server.py` (`/api/real/runs`), `pages/Results.tsx`.
  Do: a "Made real on the rented GPU" section: one card per run (episode, when, state words), its
  photographed stills as pictures and its clips as videos with their poster. Runs in flight show a spinner
  and their `say`.
  Done when: E0.1's runs show with pictures and play.

### E3. What is cooking

- [ ] **E3.1 (L1) `/api/gpu` says which remote runs are out.** Depends on E2.1. Add `remote` (C2.4).
- [ ] **E3.2 (L2) The Working on it pill.** Depends on E3.1.
  Files: new `web/src/layout/WorkingOn.tsx`, `app/store.tsx`, `main.tsx`, `styles.css`.
  Do: top-right pill, hidden when nothing runs: "Working on it: 2". Click opens one panel listing the
  render (from `running`), builds (`jobs`), the GPU queue (`queue`) and remote runs (`remote`), each with
  its sentence and a **Show me** link. Move the sidebar-foot lines into it (the foot keeps one dot).
  Done when: a render and a build both show, in kid words, in the screenshot.
- [ ] **E3.3 (L1) A finished job says so, with a button.**
  Do: when something leaves the running lists, toast "Your movie is ready" / "Santa is built" /
  "Your real clips are home" with a **Watch it** / **See him** action. Done when: seen in the browser.

### E4. Simple mode and no forms

- [ ] **E4.1 (L2) The Simple/Pro switch.**
  Files: `app/store.tsx` (`mode`, `setMode`, localStorage `cf.mode`, default `simple`), `layout/Sidebar.tsx`
  (`pro: true` on props, library, suite; the switch in the foot), `pages/episodes/Episodes.tsx` (hide
  `finishing` and `json` in Simple).
  Done when: switching hides and shows them; the choice survives a reload.
- [ ] **E4.2 (L1) `web/src/words.ts`: the kid words, once.**
  Do: `WORDS.nav` (studio Home, episodes Make, results My movies, characters Who, sets Places, props
  Things, library City library, suite Other tools, help Help), `WORDS.tabs` (scene Where and who, script
  What happens, 3d Try it, output Watch, finishing The cut, json JSON), `WORDS.steps` (A2). Sidebar,
  tabs and StoryPath read it. `tests/test_words.py` fails on a jargon word outside the `json`/`finishing`
  entries. Done when: the menu and tabs read the kid words in the screenshot.
- [ ] **E4.3 (L2) Only the parameters that matter, in Simple.**
  Files: `core/schema.py` (`"simple": True` on the one to three params per action that matter: walk `to`,
  say `text` + `expression`, look `at`...), `describe()` passes it, `Script.tsx` + `ParamInput` callers.
  Do: in Simple a step shows its simple params and a **More** chip; Pro shows all. Test: every action
  with parameters has at least one simple one.
- [ ] **E4.4 (L1, one file each) Turn the forms in Part B's inventory into pictures.**
  Do, per field, pick one: **name** -> born filled (E4.5) with a pencil to rename; **choice** -> `ChipPick`
  or picture cards (`CastThumbs` for people, set pictures for places); **number** -> `Regulator` with a
  span in `schema.RANGES`; **file** -> a drop zone with a picture; **expert** -> Pro only. Tick the file in
  the inventory table when it has no form left outside Pro. Order: Script, Scenes, Episodes, SceneSetup,
  Sets, Characters, Editor3D, CharacterDesigner.
- [ ] **E4.5 (L1) Names are born filled.**
  Do: New movie / episode / scene / set are created at once with a name ("My movie 2", "Part 2",
  "Scene 3", the picture's own name), and a pencil renames them. No text box stands between a person and
  a new thing.

### E5. Kid design

- [ ] **E5.1 (L1) Tokens.** `styles.css` top: tap size 44 px, body 15 px, step titles 20 px, radius,
  focus ring; `.btn.lg` for the Next button. Check one page of each kind in the screenshot.
- [ ] **E5.2 (L2) Faces and places as pictures everywhere a person or place is chosen.** Replace the
  who-`<Select>` in Script, Editor3D and SceneSetup with avatar chips (`CastThumbs` style).
- [ ] **E5.3 (L3) Starter stories.** New `core/starters.py` (pure, tested): a starter + the movie's
  characters and sets -> a ready `scene.json` (two or three scenes, people placed, a few steps).
  `/api/episode/new` takes `starter`. Home shows them as big cards. Done when: one press makes an episode
  whose path is all ticked up to Make the movie.

### E6. Story blocks

- [ ] **E6.1 (L3) The story as a strip of picture blocks (Simple mode Script).** Each block: glyph +
  who's face + a few words ("Santa: Ho ho ho!", "walks to the door"); tap -> a panel with the simple
  params; drag to reorder; the add palette as big tiles at the end of the strip. Pro keeps today's list.

---

## Part E. Known bugs (newest first; one line each, with how to reproduce)

- The push of commit `0a727ce` hangs in Git Credential Manager (a sign-in window). Most likely the GitHub
  token was rotated: the user signs in once and pushes work again. Agents: commit; do not retry pushes in a
  loop.
- My movies has no rented-GPU work: runs were downloaded to `tmp/clips*`, filed into `act1/real/`, and
  lost when act1 was deleted and remade. -> E0.1, E2.
- The Next step cannot link into an episode: tab and scene are not in the route. -> E1.2.
- Make it real (Suite page) shows a CLI command instead of a button. -> E2.3.
- A new episode's first scene points at `../sets/<set>/background.png`, which does not exist. -> E0.3.

## Part F. Recipes

**F1. A route that decides something.** Write the decision as a pure function in `core/<name>.py` with
`tests/test_<name>.py` (plain dicts in, plain dicts out). The route in `app/server.py` gathers facts from
disk, calls it, returns the result. The page draws what came back.

**F2. A choice instead of a form field.** Find the control by the TYPE of the value in
`components/ParamInput.tsx`: number -> `Regulator` (needs `schema.RANGES`), point -> `StagePad`, enum ->
`ChipPick` (needs a glyph in `glyphs.ts`), person -> `CastThumbs`, voice -> `VoicePicker`, sound ->
`SoundPick`, clip -> `ClipPick`, picture -> `PicturePick`. Never write a control inside a page.

**F3. See a UI change (do all of it).**
```
cd web && npm run build && cd ..                  # tsc + vite; fix every error it prints
# start the test server on 8787: .claude/skills/run-castforge (never touch 8765)
# drive headless Chrome over CDP to the route, click what a person would click, screenshot, LOOK at it
.venv/Scripts/python -m pytest -q                 # green before the commit
git add -A && git commit                          # app/ui/ is committed: the user's app serves it
```

**F4. A `?` topic.** Add an entry to `web/src/guide.ts` (`what`, `how[]`, `next`, `mind`), then put
`<Guide topic="name" />` beside the title it explains.

**F5. A kid word.** Add it to `web/src/words.ts`; read it from there. If the jargon test fails, use the
plain word.

## Part G. Status log (append one line per ticket: date, model, ticket, what you saw)

- 2026-11-27 Opus 5.5: wrote this plan. Fetched the depth-held Kaggle run (`tmp/clips4`): faces and shapes
  both held; the room keeps its layout (window, table, shelves, coat, chairs, stove in place) where the
  previous run turned the cabin into a stone barn; walls still change material in places.
