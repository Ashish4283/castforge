"""Build CastForge's footstep library with Stable Audio Open (local GPU, Stability Community License).

For each floor, generate a few seconds of walking, then cut it into single steps at the onsets, so
every footstep in a scene can be a slightly different real sound.

    python generate/make_sfx_library.py ../sfx [--reslice | --missing]
writes sfx/footsteps/<floor>/<n>.wav, sfx/sfx/<name>/<n>.wav, sfx/beds/<name>/<n>.wav and sfx/library.json
--reslice re-cuts the saved recordings (_source.wav) without generating again.
--missing generates only what is not in library.json yet (new floors, effects, beds).
"""
import glob
import json
import os
import sys

import numpy as np
import soundfile as sf

out = sys.argv[1]
RESLICE = "--reslice" in sys.argv
ONESHOTS_ONLY = "--oneshots" in sys.argv
MISSING = "--missing" in sys.argv

# one-shot effects: name -> (prompt, seconds); 3 variants each, trimmed to the sound itself
ONESHOTS = {
    "door_bell": ("small brass shop door bell jingling once as a door opens, indoor, close, clean, no music", 3.0),
    "door_open": ("a wooden shop door opening, handle click and soft creak, indoor, close, no music", 2.0),
    "door_close": ("a wooden shop door closing softly with a latch click, indoor, close, no music", 2.0),
    "chair_sit": ("a person sitting down on a wooden chair, small creak, indoor, close, no music", 1.5),
    "cup_place": ("a ceramic coffee cup placed on a wooden table, indoor, close, no music", 1.0),
    "cabin_door_open": ("an old heavy wooden cabin door opening with a long creak, close, no music", 3.0),
    "cabin_door_close": ("an old heavy wooden cabin door closing with a thud and latch, close, no music", 2.0),
    "truck_door_open": ("a pickup truck door opening with a metal click, outdoor, close, no music", 1.5),
    "truck_door_close": ("a pickup truck door slamming shut, outdoor, close, no music", 1.5),
    "engine_start": ("an old pickup truck engine cranking and starting, then idling, outdoor, no music", 5.0),
    # fights: one dry impact per blow, plus the swing and a body going down
    "hit": ("a bare fist punching a body, dull dry thud, close, no music, no voices", 1.0),
    "hit_hard": ("a heavy punch landing on a body, deep dull impact with a short slap, close, no music", 1.2),
    "block": ("a forearm blocking a punch, dull slap of arm on arm, close, no music, no voices", 1.0),
    "whoosh": ("a fast arm swinging through the air, short air whoosh, close, no music, no voices", 0.8),
    "body_fall": ("a person falling onto a wooden floor, heavy body thud, close, no music, no voices", 1.5),
    # the film's missing cues (docs/ROADMAP.md)
    "door_slam": ("a heavy wooden door slamming shut hard, loud bang and frame rattle, close, no music", 2.0),
    "lock_bolt": ("a metal door bolt sliding and locking, single solid clack, close, no music, no voices", 1.2),
    "crowbar": ("a steel crowbar prying wood, metal scrape and sharp wood crack, close, no music", 2.0),
    "crash": ("a wooden shelf collapsing, glass jars and tins crashing onto a floor, close, no music", 3.0),
}

# beds: long sounds under a whole scene (ambience, music); 2 takes each, faded to loop
BEDS = {
    "cabin_night": ("inside a quiet wooden cabin at night, crackling wood stove fire, soft winter wind outside, "
                    "no music, no voices", 30.0),
    "winter_wind": ("outdoor winter wind in pine trees, light snowfall, quiet mountain, no music, no voices", 30.0),
    "truck_cab": ("inside an old pickup truck driving slowly on a snowy road, steady engine hum, tyres on snow, "
                  "no music, no voices", 30.0),
    "radio_christmas": ("cheerful festive christmas instrumental with sleigh bells, glockenspiel and warm "
                        "piano, nostalgic, 120 bpm", 45.0),
    "crowd_murmur": ("a small indoor crowd murmuring and shuffling in a queue, no clear words, no music", 30.0),
    "truck_driving": ("an old pickup truck driving steadily on a snowy country road, engine hum and tyre "
                      "crunch, heard from outside, no music, no voices", 30.0),
}


def trim(wave, sr):
    """Cut leading/trailing silence, short fades at both ends."""
    env = np.abs(wave)
    thresh = max(env.max() * 0.02, 1e-4)
    idx = np.nonzero(env > thresh)[0]
    if not len(idx):
        return wave
    a, b = max(idx[0] - int(0.01 * sr), 0), min(idx[-1] + int(0.05 * sr), len(wave))
    clip = wave[a:b].copy()
    f = min(int(0.01 * sr), len(clip) // 4)
    clip[:f] *= np.linspace(0, 1, f)
    clip[-f:] *= np.linspace(1, 0, f)
    return clip / max(np.abs(clip).max(), 1e-6) * 0.8


SOFT = {"snow", "carpet"}          # crunchy or muffled steps ring on longer: judge them more loosely


def slice_steps(wave, sr, keep=8, soft=False):
    """Single clean footsteps: one dominant hit near the start, no second strong hit, no ringing tail."""
    hop = int(0.01 * sr)
    env = np.sqrt(np.convolve(wave ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    thresh = env.mean() + 1.5 * env.std()
    peaks, last = [], -1e9
    for i in range(1, len(env) - 1):
        if env[i] > thresh and env[i] >= env[i - 1] and env[i] >= env[i + 1] and i - last > 30:
            peaks.append(i)
            last = i
    good = []
    L = int(0.35 * sr)
    for p in peaks:
        lo, hi = max(0, p * hop - int(0.05 * sr)), min(len(wave), p * hop + int(0.05 * sr))
        hit = lo + int(np.argmax(np.abs(wave[lo:hi])))          # the actual impact sample
        a = max(0, hit - int(0.015 * sr))
        clip = wave[a:a + L].copy()
        if len(clip) < L:
            continue
        peak = np.abs(clip[: int(0.04 * sr)]).max()
        later = np.abs(clip[int(0.06 * sr):]).max()
        tail = np.sqrt(np.mean(clip[int(0.12 * sr):] ** 2))
        head = np.sqrt(np.mean(clip[: int(0.04 * sr)] ** 2))
        if later > (0.8 if soft else 0.45) * peak or tail > (0.6 if soft else 0.18) * head:
            continue
        fade = int(0.08 * sr)
        clip[-fade:] *= np.linspace(1, 0, fade)
        good.append(clip / max(np.abs(clip).max(), 1e-6) * 0.8)
    return good[:keep]
FLOORS = {
    "wood": "footsteps of one person walking slowly on a wooden floor, hard shoes, indoor, close microphone, "
            "clear separate steps, no music",
    "concrete": "footsteps of one person walking slowly on concrete pavement, hard shoes, outdoor, close "
                "microphone, clear separate steps, no music",
    "carpet": "soft footsteps of one person walking slowly on carpet, indoor, close microphone, clear separate "
              "steps, no music",
    "tile": "footsteps of one person walking slowly on a tiled floor, heels, indoor hall, close microphone, "
            "clear separate steps, no music",
    "snow": "footsteps of one person walking slowly in fresh deep snow, crunching boots, outdoor, close "
            "microphone, clear separate steps, no music",
}

if not RESLICE:
    import torch
    from diffusers import StableAudioPipeline
    pipe = StableAudioPipeline.from_pretrained("stabilityai/stable-audio-open-1.0", torch_dtype=torch.float16)
    pipe.enable_model_cpu_offload()

lib_path = os.path.join(out, "library.json")
library = json.load(open(lib_path)) if os.path.exists(lib_path) else {}
library.setdefault("footsteps", {})
library.setdefault("sfx", {})
library.setdefault("beds", {})
if MISSING:
    ONESHOTS = {k: v for k, v in ONESHOTS.items() if k not in library["sfx"]}
    FLOORS = {k: v for k, v in FLOORS.items() if k not in library["footsteps"]}
    BEDS = {k: v for k, v in BEDS.items() if k not in library["beds"]}
    print("missing:", list(ONESHOTS), list(FLOORS), list(BEDS), flush=True)

if not RESLICE:
    for name, (prompt, secs) in ONESHOTS.items():
        d = os.path.join(out, "sfx", name)
        os.makedirs(d, exist_ok=True)
        files = []
        for v in range(3):
            audio = pipe(prompt, negative_prompt="music, voices, talking, low quality", num_inference_steps=100,
                         audio_end_in_s=secs, generator=torch.Generator("cuda").manual_seed(21 + v)).audios[0]
            sr = pipe.vae.sampling_rate
            clip = trim(audio.float().cpu().numpy().mean(axis=0), sr)
            f = os.path.join(d, f"{v}.wav")
            sf.write(f, clip, sr, subtype="PCM_16")
            files.append(os.path.relpath(f, out).replace("\\", "/"))
        library["sfx"][name] = files
        print(name, len(files), "variants", flush=True)
    json.dump(library, open(lib_path, "w"), indent=1)

if not RESLICE and not ONESHOTS_ONLY:
    for name, (prompt, secs) in BEDS.items():
        d = os.path.join(out, "beds", name)
        os.makedirs(d, exist_ok=True)
        files = []
        music = "music" not in prompt and "instrumental" in prompt
        for v in range(2):
            audio = pipe(prompt, negative_prompt="low quality, distorted" + ("" if music else ", music, voices"),
                         num_inference_steps=120, audio_end_in_s=secs,
                         generator=torch.Generator("cuda").manual_seed(31 + v)).audios[0]
            sr = pipe.vae.sampling_rate
            wave = audio.float().cpu().numpy().T                 # keep stereo for beds
            fade = int(1.5 * sr)
            wave[:fade] *= np.linspace(0, 1, fade)[:, None]
            wave[-fade:] *= np.linspace(1, 0, fade)[:, None]
            wave = wave / max(np.abs(wave).max(), 1e-6) * 0.8
            f = os.path.join(d, f"{v}.wav")
            sf.write(f, wave, sr, subtype="PCM_16")
            files.append(os.path.relpath(f, out).replace("\\", "/"))
        library["beds"][name] = files
        json.dump(library, open(lib_path, "w"), indent=1)
        print(name, len(files), "takes", flush=True)

for floor, prompt in ({} if ONESHOTS_ONLY else FLOORS).items():
    d = os.path.join(out, "footsteps", floor)
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "_source.wav")
    if RESLICE:
        if not os.path.exists(src):
            continue
        wave, sr = sf.read(src)
    else:
        audio = pipe(prompt, negative_prompt="music, voices, talking, low quality", num_inference_steps=100,
                     audio_end_in_s=10.0, num_waveforms_per_prompt=1,
                     generator=torch.Generator("cuda").manual_seed(11)).audios[0]
        sr = pipe.vae.sampling_rate
        wave = audio.float().cpu().numpy().mean(axis=0)
        sf.write(src, wave, sr, subtype="PCM_16")
    for old in glob.glob(os.path.join(d, "[0-9]*.wav")):
        os.remove(old)
    files = []
    for n, clip in enumerate(slice_steps(wave, sr, soft=floor in SOFT)):
        f = os.path.join(d, f"{n}.wav")
        sf.write(f, clip, sr, subtype="PCM_16")
        files.append(os.path.relpath(f, out).replace("\\", "/"))
    library["footsteps"][floor] = files
    print(floor, len(files), "clean steps", flush=True)
json.dump(library, open(os.path.join(out, "library.json"), "w"), indent=1)
