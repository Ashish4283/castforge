"""Dialogue voices for CastForge: text -> WAV with Kokoro (Apache-2.0, runs locally).

The voice name's first letter picks the language, e.g. af_heart / am_michael (American English),
bf_emma / bm_george (British English), hf_alpha / hm_omega (Hindi).

    python generate/tts.py jobs.json [--device cpu]   # [{"text": ..., "voice": ..., "out": ..., "speed": 1.0}, ...]

--device cpu keeps the GPU free (voice previews while a render runs); the default uses CUDA when there is one.
"""
import json
import sys

import numpy as np
import soundfile as sf
from kokoro import KPipeline

#  Kokoro knows which sounds it speaks and when; turn them into mouth-shape (viseme) cues so the
#  lip-sync is exact for text lines (<out>.visemes.json, read by blender/scene_kit.py)
VISEME = {}
for chars, v in (("pbm", "viseme_PP"), ("fv", "viseme_FF"), ("θð", "viseme_TH"), ("tdT", "viseme_DD"),
                 ("kgŋ", "viseme_kk"), ("ʧʤʃʒ", "viseme_CH"), ("sz", "viseme_SS"), ("nl", "viseme_nn"),
                 ("ɹrɝ", "viseme_RR"), ("w", "viseme_U"), ("j", "viseme_I"),
                 ("ɑaæʌɐIW", "viseme_aa"), ("ɛeA", "viseme_E"), ("iɪ", "viseme_I"), ("ɔoOYɒQ", "viseme_O"),
                 ("uʊ", "viseme_U"), ("əɜɚᵊ", "viseme_E")):
    for c in chars:
        VISEME[c] = v
VOWELS = set("ɑaæʌɐIWɛeAiɪɔoOYɒQuʊəɜɚᵊ")


def word_cues(phonemes, start, end):
    sounds = [c for c in phonemes if c in VISEME]
    if not sounds or end <= start:
        return []
    weights = [1.6 if c in VOWELS else 1.0 for c in sounds]
    scale = (end - start) / sum(weights)
    cues, t = [], start
    for c, w in zip(sounds, weights):
        strength = 0.6 if c in "əɜɚᵊ" else 1.0
        cues.append({"start": round(t, 3), "end": round(t + w * scale, 3), "viseme": VISEME[c],
                     "weight": strength})
        t += w * scale
    return cues


jobs = json.load(open(sys.argv[1], encoding="utf-8"))
device = sys.argv[sys.argv.index("--device") + 1] if "--device" in sys.argv else None
pipes = {}
for job in jobs:
    lang = job["voice"][0]
    if lang not in pipes:
        pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M", device=device)
    chunks, cues, offset = [], [], 0.0
    for r in pipes[lang](job["text"], voice=job["voice"], speed=job.get("speed", 1.0)):
        audio = r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio)
        for tok in (r.tokens or []):
            if tok.start_ts is not None and tok.end_ts is not None and tok.phonemes:
                cues += word_cues(tok.phonemes, offset + tok.start_ts, offset + tok.end_ts)
        chunks.append(audio)
        offset += len(audio) / 24000
    audio = np.concatenate(chunks)
    sf.write(job["out"], audio, 24000, subtype="PCM_16")
    with open(job["out"] + ".visemes.json", "w") as f:
        json.dump({"duration": offset, "cues": cues}, f)
    print("voiced", job["out"], f"{len(audio) / 24000:.1f}s", f"{len(cues)} mouth cues", flush=True)
