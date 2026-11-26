# The suite

Three tools make art for the same films. They live together now so they can stop solving the same
problems separately.

```
castforge/                photo or design -> rigged 3D character -> rendered, voiced episode   :8765
  suite/
    forgefilms/           clips, parallax, sound, assembly                                     :8700
    graphic-novel/        dataset, LoRA training, panels                                       :8500
```

Those two port numbers belong to those two tools - they are what their own `START.bat` files set, and
`tests/test_suite.py` reads those files so this table cannot drift away from them.

`suite/` is **gitignored by castforge on purpose**. Each tool is still its own git repository with its
own history and its own remote; castforge does not track them and does not look inside. Moving them
here changed nothing about how they are version-controlled — `git -C suite/forgefilms log` is the same
history it always was.

Run `python castforge.py suite` to see what is installed and where the shared things are. It exits
non-zero when something is missing and says how to point it elsewhere.

## What they share

| | Where | Why it is shared |
|---|---|---|
| **Models** | `C:/AI-Models` (22 GB) | Downloaded once. ComfyUI reads it through its own `extra_model_paths.yaml`, so a second ComfyUI or a rented pod points at the same folders. Nothing is duplicated per project. |
| **ComfyUI** | `C:/ComfyUI`, answering on `:8188` | All three tools already used this address before they were related. |
| **GPU: local or rented** | `core/gpu.py`, `generate/gpu_where.py`, `tools/kaggle/` | CastForge works out whether a ComfyUI is answering, whether the card is big enough and whether Kaggle is signed in. The other two get the same choice by calling it rather than writing their own. |
| **Fabrics** | `library/fabrics/` | Cloth made on a GPU and turned into a material: albedo, relief, roughness, seam score. The same velvet can dress a 3D costume and fill a drawn panel. |
| **Characters** | `movies/*/characters/` | A built character carries its design, what its rig can do (`.rig.json`), what it can act (`.screen.json`) and how its body moves. That is reference the other two cannot work out for themselves. |

Every path can be overridden, because one of these machines is a laptop, one is a rented GPU and one is
somebody else's PC:

```
CASTFORGE_MODELS      the shared model library        (default C:/AI-Models)
CASTFORGE_COMFYUI     the ComfyUI install             (default C:/ComfyUI)
CASTFORGE_COMFY_URL   where a running ComfyUI answers (default http://127.0.0.1:8188)
```

## The chain

```
graphic-novel          castforge                        forgefilms
reference sheets  -->  a rigged 3D character       -->  a graded, captioned film   (shared/handoff.py)
and the script         rendered into a voiced       -->  the same shots, photographed (shared/real.py)
                       episode
       \__ shared/cast.py __/
```

Each arrow is one tested module, and nothing else in either tool knows about the other side.

## Real: the shots, photographed

`post` finishes the 3D cut. `real` takes the same shots and runs them through image-to-video, so what
comes back is photographed rather than rendered:

```
python castforge.py real movies/santa_is_a_lie/act1 --run
```

Two things make this worth a module rather than a folder of typed prompts:

* **The cut is already there.** `shot.timeline.json` holds the shots the director cut - when each starts,
  whether it is wide or close, who it is on, which way the camera moves and on what lens. A clip cannot
  contain a cut, so those are the only honest boundaries, and they are the ones this uses.
* **The prompt is a fact.** CastForge knows who is on screen, roughly how old they are, what colour their
  hair and their coat are, what the light is doing, whether it is snowing, and whether a person is
  speaking aloud or thinking with their mouth shut. Told to make someone speak over a thought, the model
  opens their mouth and the shot is wasted.

The one hard limit is the model's: **Wan 2.2 image-to-video was trained on 81 frames, 5.06 s at 16 fps.**
A longer take is split into windows of equal length, and each window after the first should start from
the last frame of the clip before it, or the face and the clothes reset at the join. Those stills do not
exist until the first pass has run, so every window is given the render's own frame to start with and the
command prints which ones to replace afterwards.

## Cast: the step before `character`

The novel is where a cast is designed and its faces are locked against a turnaround - front, side,
three-quarter, back and a close detail, generated until they hold. CastForge builds a body from exactly
that. So the novel's cast is already the suite's cast:

```
python castforge.py cast                 what the novel has, and what it could read about each one
python castforge.py cast Moses           just that one
```

The Suite page shows the same thing with a reference photo per character and a **Give it a body** button.
Because the build uses the same front reference the novel's LoRA was trained to hold steady, the 3D
character and the drawn panels are the same person by construction, rather than by anyone matching them
up afterwards.

`appearance` is free prose somebody wrote, not a form, so `shared/cast.py` reads only what it plainly
says and **reports everything else as guessed** - the app shows "read 7, guessed 1" per character and
will list both. Three things the real cast taught it, each now a test:

* **"heavy brow" is a face, not a heavy build.** A build word only counts when it describes the body.
* **Decades have to be parsed, not listed.** A hand-written table of "early 20s", "late 20s"... missed
  "in his early 50s" entirely.
* **Not every character is a person.** "Devadatta" is a cybernetic war-horse; MPFB builds human bodies,
  so it is refused with a reason instead of being built into something absurd.

## Post: the step after `episode`

CastForge stops at a rendered, voiced episode. forgefilms starts at a shot list and does the post -
colour, 0.5 s crossfades, a mix mastered to -16 LUFS, captions. One command joins them:

```
python castforge.py post movies/santa_is_a_lie/act1 --run
```

It writes three files into `suite/forgefilms/shots/` (shot list, picks, captions), runs forgefilms'
`assemble.py`, and leaves one graded film with correct subtitles. Without `--run` it writes the files and
prints the command, so the post can be run by hand. The Suite page in the app does the same thing with a
button. The whole contract is `shared/handoff.py`; it is pure and tested, and it encodes two rules that
are otherwise silent and ruinous:

* **A scene's length comes from its own `shot.timeline.json`**, never from `episode.timeline.json`. The
  episode timeline says where a scene sits in the finished cut; the shot files are the untrimmed renders.
* **`shot.wav` is already mixed and already in time.** It goes in as the ambience bed with no offset and
  no voice layer. forgefilms only ducks a voice it placed itself; handing it a finished mix as a "voice"
  would pump the whole scene against itself. That is also why forgefilms' own `.vtt` comes out empty for
  a CastForge cut, and why `handoff.captions` writes the real one from the per-line times.

## Using it from forgefilms or graphic-novel

Each sibling has one file in its own root, `suite_link.py`. Import it and the shared layer is there:

```python
import suite_link

checkpoints = suite_link.suite.models("checkpoints")   # C:/AI-Models/checkpoints
comfy       = suite_link.suite.comfy_url()             # http://127.0.0.1:8188
velvet      = suite_link.suite.fabrics()               # the cloth library
place       = suite_link.gpu_place()                   # "local" or "kaggle"
```

`gpu_place()` asks CastForge rather than deciding for itself: `core/gpu.py` already works out whether a
ComfyUI is answering, whether the card is big enough and whether Kaggle is signed in, and it returns
whatever the person chose in the app. Three tools that each decided this separately would disagree.

Run `python suite_link.py` inside either tool to see what it can reach:

```
castforge   C:\Projects\3D Model Generator\castforge
  models       C:/AI-Models
  comfyui      C:/ComfyUI
  ...
  gpu          kaggle
```

If a tool is ever moved out of `castforge/suite/`, set `CASTFORGE_HOME` to the folder holding
`castforge.py` and the same import keeps working.

## The one rule

**A path is written down once.** `shared/suite.py` is the only place that says where the models, the
ComfyUI, the fabrics or the cast live. If a second file starts spelling out `C:/AI-Models`, the two will
disagree within a week — that is exactly the duplication moving these folders together was meant to end.
