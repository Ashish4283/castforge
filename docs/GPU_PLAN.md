# Which GPU does what

Four now, and they are good at different things. Putting a job on the wrong one is how an afternoon
disappears.

| | what it is | what it is for | why |
|---|---|---|---|
| **This laptop** | RTX 3050, 4 GB | every Blender build, every EEVEE render, screen tests, the studio | None of it is GPU-hungry. A character build is morphs, Rigify and weight painting - CPU and single-threaded Python - and scenes render in EEVEE, which is a rasteriser. Moving any of it costs 943 MB of addons and gains nothing. |
| **Colab** | T4, 15 GB, free | **interactive** texture work: a tunnel, and somebody at the other end | Right when a person is watching and wants this swatch, then that one. Wrong for anything long: 90 minutes idle and it is gone. |
| **Kaggle** | T4 x2, 2x16 GB, 30 h a week | **batch** texture work: Save Version > Run All, headless, up to 12 hours | No tunnel to go stale, nothing to keep open, and twice the VRAM. This is where a whole fabric library gets made, and later where a LoRA gets trained. |
| **gpubox** | L40S, 48 GB, ~$2.24/h | anything that must finish, or needs more than 16 GB: Wan 2.2 video, FLUX, big LoRAs | Already built, already safe - it arms its own shutdown, queues by lane, syncs to S3 every two minutes and audits every region for anything still billing. Costs money, so it is for work that is worth money. |

## The rule

**Interactive goes to Colab. Batch goes to Kaggle. Expensive-and-must-not-fail goes to gpubox.
Everything Blender stays here.**

## Two modes, one notebook

`docs/colab/castforge_comfyui.ipynb` runs on Colab and Kaggle and knows which it is on.

* **Tunnel** (cell 5) - prints a `trycloudflare` address. The laptop talks to it live:
  `castforge.py gpu connect <url>` then `castforge.py gpu fabric "..." --kind denim`.
* **Batch** (cell 5b) - a list of fabrics, generated with nothing open, saved to the output folder.
  Download it, then `python generate/make_fabric.py --folder <that folder>`.

## Where the 6.5 GB checkpoint lives

It is fetched once, never once a session - but the two machines keep things in completely different
places and getting it wrong means downloading it every time.

* **Colab** - Google Drive, mounted in cell 2.
* **Kaggle** - there is no Drive, and `/kaggle/working` is wiped unless you commit. Use a **dataset**:
  download it once, then **Output > New Dataset** (call it `castforge-models`), and from then on
  **Add Input > Datasets > castforge-models** in any notebook. It is mounted read-only at
  `/kaggle/input/...` and there is nothing to download at all. Cell 4 finds it by itself.

## What never leaves this machine

Tokens. A Hugging Face token goes in Colab's **Secrets** panel (the key icon) as `HF_TOKEN`, never in a
cell - anything typed into a cell is saved in the notebook and goes wherever the notebook goes. Nothing
here needs one anyway: RealVisXL Lightning is not gated.
