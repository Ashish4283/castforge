"""Pick the best take of each sound effect without listening (method from ForgeFilms' rank_sounds.py).

Each take is scored with CLAP (laion/clap-htsat-unfused): similarity to its own description, and to "music" and
"a person speaking". Takes that sound more like music or speech than like their description are dropped; the rest
are kept best-first in sfx/library.json (the scene kit uses the best one or two). This screens; it does not
replace a listener.

    python generate/rank_sfx.py sfx
"""
import json
import os
import sys

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from transformers import ClapModel, ClapProcessor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1]
lib_path = os.path.join(out, "library.json")
library = json.load(open(lib_path))
PROMPTS = {
    "door_bell": "a small shop door bell jingling", "door_open": "a wooden door opening with a creak",
    "door_close": "a wooden door closing with a latch click", "chair_sit": "a person sitting down on a wooden chair",
    "cup_place": "a ceramic cup placed on a table",
}
PROBES = {"music": "music with a melody", "speech": "a person speaking"}

proc = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
model = ClapModel.from_pretrained("laion/clap-htsat-unfused").eval()


def scores(path, texts):
    """Cosine similarity of one take to each text (CLAP's joint audio/text space)."""
    a, sr = sf.read(os.path.join(out, path), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if sr != 48000:
        a = resample_poly(a, 48000, sr).astype(np.float32)
    with torch.no_grad():
        o = model(**proc(text=texts, audio=[a], sampling_rate=48000, return_tensors="pt", padding=True))
    ae = torch.nn.functional.normalize(o.audio_embeds, dim=-1)
    te = torch.nn.functional.normalize(o.text_embeds, dim=-1)
    return (ae @ te.T).squeeze(0).tolist()


for name, takes in library.get("sfx", {}).items():
    if name not in PROMPTS:
        continue
    scored = []
    for t in takes:
        sc = scores(t, [PROMPTS[name]] + list(PROBES.values()))
        scored.append((sc[0], max(sc[1:]), t))
    good = sorted([x for x in scored if x[1] < x[0]], reverse=True) or sorted(scored, reverse=True)[:1]
    library["sfx"][name] = [t for _, _, t in good]
    print(name, " ".join(f"{os.path.basename(t)}={sc_:.2f}(music/speech {p_:.2f})"
                         for sc_, p_, t in sorted(scored, reverse=True)),
          "-> keep", [os.path.basename(t) for _, _, t in good])
json.dump(library, open(lib_path, "w"), indent=1)
