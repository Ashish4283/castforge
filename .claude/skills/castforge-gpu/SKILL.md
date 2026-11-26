---
name: castforge-gpu
description: Run heavy work on the rented Kaggle GPU - photoreal clips, image-to-video, fabric - by pushing a dataset and a kernel, watching it, and bringing the results home into the episode folder. Use when a job needs a GPU this laptop does not have, or when a Kaggle run has finished and its output has to be filed.
---

# The rented GPU

This laptop has no usable GPU for diffusion work. Kaggle gives a **T4 with 15 GB**, signed in already, and
`castforge.py real FOLDER --gpu` is the whole path: it packages the stills and workflows as a private
dataset, pushes a kernel that reads them, and Kaggle runs it headless for up to twelve hours.

```
python castforge.py real movies/<movie>/<ep> --gpu [SHOT_IDS...]   send it
kaggle kernels status ashishjiwa/castforge-clips                   watch it
python castforge.py real movies/<movie>/<ep> --fetch               bring it home
python castforge.py real movies/<movie>/<ep> --fetch --from DIR    file a run already downloaded
```

Results land in `<episode>/real/` and appear in the app's Output tab. **Nothing that lands outside the
movie folder has been delivered** - a file in `tmp/` is a file nobody can find.

## What the card can and cannot do

A T4 is **Turing (sm_75): it has no fp8 at all**. Weights named `fp8_scaled` load and are upcast, so they
buy nothing and cost VRAM.

- **Wan 2.2 i2v 14B** - two 14 GB experts. Does not fit. Do not try.
- **Wan 2.2 TI2V 5B** (9.3 GB) - fits, about 4-6 minutes for 81 frames at ~480k pixels.
- **SDXL / RealVisXL** (6.9 GB) - comfortable; a realism pass is 10-40 seconds a still.
- 81 frames is what Wan 2.2 was **trained** on: 5.06 s at 16 fps, 3.4 s at 24. Longer in one pass drifts.

## Two things the Kaggle CLI does that will cost a run

**It prints its errors and exits 0 anyway.** Read the words, never the return code:

```python
said = subprocess.run(push, capture_output=True, text=True)
if said.returncode or "error" in (said.stdout + said.stderr).lower():
    ...
```

**It SKIPS folders unless you pass `--dir-mode`**, and `--dir-mode zip` makes one zip per folder, losing
the folder names the kernel looks for. Send **one zip of the whole bundle** instead; Kaggle unpacks it,
and `boot.clips()` unpacks it itself if Kaggle has not.

A dataset is **private unless you pass `-u`**. Never pass `-u`: these are stills from the user's film.

## Changing what runs there

`tools/kaggle/boot.py` is the notebook, as a module. `make_kernel.py` builds the `.ipynb` from it, so
there is one source for the logic.

```
python tools/kaggle/make_kernel.py              the cloth kernel  -> kernel/
python tools/kaggle/make_kernel.py --job clips  the clips kernel  -> kernel-clips/
```

**Push the kernel after changing boot.py, before sending work.** A run that went up before a fix is a run
without the fix, and the log will not say so.

`make_kernel.py` refuses to build if `boot.py` calls a name it never defines - that check exists because
a NameError once surfaced twelve minutes into a GPU run.

## Where the output actually is

ComfyUI is started with `--output-directory`, so **its pictures do NOT land in `comfy/output`**. Look
under `place["keep"] / "swatches"` first. Getting this wrong reports "0 frames" while the frames sit on
disk.

`ffmpeg -pattern_type glob` is not compiled into every build (not into this laptop's), and the error,
"Function not implemented", points nowhere. Build a numbered pattern from the first frame's own name.

## Reading a finished run

```bash
kaggle kernels output ashishjiwa/castforge-clips -p tmp/clips
python -c "import json,io; rows=json.load(io.open('tmp/clips/castforge-clips.log',encoding='utf-8')); print(''.join(r['data'] for r in rows if r.get('stream_name')))"
```

The log is JSON, not text. Read it before filing the output into the episode: a run whose realism pass
silently failed will still produce clips, and they will quietly overwrite better ones.
