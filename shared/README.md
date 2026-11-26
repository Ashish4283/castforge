# The suite

Three tools make art for the same films. They live together now so they can stop solving the same
problems separately.

```
castforge/                photo or design -> rigged 3D character -> rendered, voiced episode   :8765
  suite/
    forgefilms/           clips, parallax, sound, assembly                                     :8600
    graphic-novel/        dataset, LoRA training, panels                                       :8700
```

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

## Using it from forgefilms or graphic-novel

Two lines, and nothing is copied or restated:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))   # the castforge checkout
from shared import suite

checkpoints = suite.models("checkpoints")     # C:/AI-Models/checkpoints
comfy       = suite.comfy_url()               # http://127.0.0.1:8188
velvet      = suite.fabrics()                 # the cloth library
```

For the local-or-rented GPU choice, call CastForge's own rules rather than reimplementing them:

```python
from core import gpu                 # pure: no bpy, no network, 16 tests
import gpu_where                     # gathers the facts (is a port answering, is Kaggle signed in)

facts = gpu_where.facts()
place = gpu.best(facts)              # "local" or "kaggle"
for row in gpu.describe(facts, place):
    print(row)
```

## The one rule

**A path is written down once.** `shared/suite.py` is the only place that says where the models, the
ComfyUI, the fabrics or the cast live. If a second file starts spelling out `C:/AI-Models`, the two will
disagree within a week — that is exactly the duplication moving these folders together was meant to end.
