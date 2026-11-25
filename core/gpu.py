"""Where the heavy work runs: this laptop, or a rented GPU (pure, tested; no bpy, no network).

CastForge does nearly everything on the laptop and is right to: a character build is morphs, Rigify and
weight painting - all CPU - and scenes render in EEVEE, which is a rasteriser. The one job that genuinely
wants a big card is making a square of cloth with a diffusion model, and a 4 GB laptop card cannot hold
SDXL at 1024 without a fight.

So there are two places, and this says which can be used right now and what to do about the one that
cannot:

    local     a ComfyUI on this machine, if there is one. Nothing leaves the house, nothing costs
              anything, and it is as fast as the card in it.
    kaggle    a committed run on a rented T4. Pushed, run headless and fetched through the Kaggle API,
              so no browser has to stay open and no tunnel can go stale.

The arithmetic here is deliberately separate from the doing of it. `castforge.py gpu` gathers the facts -
is a port answering, is there a credentials file - and this decides what they mean. That way the rules
can be read and tested without a GPU, an account, or a network.
"""

PLACES = ("local", "kaggle")
DEFAULT = "kaggle"
LOCAL_PORT = 8188
# A swatch is 1024x1024 at six steps. On a 4 GB card SDXL needs --lowvram and takes minutes; below
# this there is no point pretending.
ENOUGH_VRAM = 6.0


def look(facts):
    """{place: {ready, why, how}} - what each place can do right now, and what to do if it cannot.

    `facts` is what the caller measured:
        local_comfy   True when something answers on this machine's ComfyUI port
        local_vram    GB on the local card, or None when there is no card
        kaggle_auth   True when the Kaggle CLI has credentials
        kaggle_cli    True when the kaggle module is installed
    """
    f = facts or {}
    out = {}

    if not f.get("local_comfy"):
        out["local"] = {"ready": False,
                        "why": f"nothing is answering on port {LOCAL_PORT}",
                        "how": "start a ComfyUI on this machine, or use kaggle"}
    elif (f.get("local_vram") or 0) < ENOUGH_VRAM:
        have = f.get("local_vram") or 0
        out["local"] = {"ready": True,
                        "why": f"a ComfyUI is here, but {have:.0f} GB is tight for SDXL at 1024",
                        "how": "it will work and it will be slow; kaggle is 15 GB"}
    else:
        out["local"] = {"ready": True,
                        "why": f"a ComfyUI is answering, {f.get('local_vram'):.0f} GB",
                        "how": "nothing leaves this machine"}

    if not f.get("kaggle_cli"):
        out["kaggle"] = {"ready": False, "why": "the kaggle package is not installed",
                         "how": "pip install kaggle"}
    elif not f.get("kaggle_auth"):
        out["kaggle"] = {"ready": False, "why": "not signed in to Kaggle",
                         "how": "run: kaggle auth login  (a browser opens; nothing is typed here)"}
    else:
        out["kaggle"] = {"ready": True, "why": "signed in; a T4 with 15 GB",
                         "how": "pushed, run headless and fetched - no browser stays open"}
    return out


def best(facts):
    """Where to send work when nobody has said. Local first when it is genuinely capable."""
    seen = look(facts)
    if seen["local"]["ready"] and (facts or {}).get("local_vram", 0) >= ENOUGH_VRAM:
        return "local"
    if seen["kaggle"]["ready"]:
        return "kaggle"
    return "local" if seen["local"]["ready"] else DEFAULT


def check(place, facts):
    """Plain-language problems with using `place` right now; empty when it can be used."""
    if place not in PLACES:
        return [f"{place!r} is not one of {', '.join(PLACES)}"]
    seen = look(facts)[place]
    return [] if seen["ready"] else [f"{seen['why']} - {seen['how']}"]


def describe(facts, chosen=None):
    """A few lines for a person: both places, which is in use, and what to do about the other."""
    seen = look(facts)
    rows = []
    for place in PLACES:
        mark = ">" if place == chosen else " "
        state = "ready" if seen[place]["ready"] else "not ready"
        rows.append(f"{mark} {place:7s} {state:9s} {seen[place]['why']}")
        if not seen[place]["ready"]:
            rows.append(f"            {seen[place]['how']}")
    return rows
