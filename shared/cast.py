"""Turn a character designed in the graphic novel into one CastForge can build (pure, tested).

The novel is where a cast is decided: each character gets an appearance written down, and a turnaround
of reference images - front, side, three-quarter, back, and a close detail - generated until the face
is locked. CastForge builds a body from exactly that: a photo for the figure, a second one for the
face, and a design for what the photo cannot show. So the novel's cast is already the suite's cast;
this file is the translation, and nothing else in either tool knows about the other.

    python castforge.py cast                 what the novel has, and what is already built
    python castforge.py cast Moses           build that one into the open movie

What the prose can honestly give is limited, and this is deliberate about it. `appearance` is free
writing by a person, not a form. Only phrases that plainly state a thing are read - "elderly",
"long white beard", "coarse brown woollen robe with hood" - and every character keeps the whole
sentence in its design, so nothing is lost by not being understood. Everything unread is REPORTED as
unread rather than guessed at, because a quiet wrong guess about a face is worse than a blank a person
fills in.

The photographs do the real work. CastForge reads the face from the front reference, which is the same
image the novel's LoRA was trained to hold steady - so the 3D build and the drawn panels are the same
person by construction, not by anyone matching them up afterwards.
"""
import json
import os
import re

PROJECT = os.path.join("05_app", "data", "project.json")   # inside the graphic-novel checkout
REFS = os.path.join("05_app", "data", "refs")

# A reference's angle is in its filename: `mosesfix_three_quarter_11.png`. Longest first, so
# "three_quarter" is never read as "quarter" or missed behind "front".
ANGLES = ("three_quarter", "front", "side", "back", "detail")

# Which angle CastForge wants for which job. The figure comes from a front shot; the face from the
# close detail if the novel made one, and otherwise from whatever view shows it. A three-quarter is a
# usable face and a usable figure - a back view is neither.
BODY_ANGLES = ("front", "three_quarter")
FACE_ANGLES = ("detail", "front", "three_quarter")

COLOURS = {"white": "#efefe9", "grey": "#9a978f", "gray": "#9a978f", "silver": "#c9c7c0",
           "black": "#1b1a19", "dark": "#2e2a26", "brown": "#5a4232", "auburn": "#6d3b24",
           "blonde": "#c9a96a", "blond": "#c9a96a", "red": "#8a3a22", "ginger": "#a85a2a",
           "charcoal": "#36383c", "cream": "#e4d9c3", "tan": "#b08a5c"}

# Each rule is (what to look for, which design field, what to put in it, what to call it in a report).
# Order matters only where one phrase contains another; those are written longest-first.
RULES = [
    (r"\bwoman\b|\bfemale\b|\bgirl\b|\bher\b|\bshe\b", "gender", "female", "a woman"),
    (r"\bman\b|\bmale\b|\bboy\b|\bhis\b|\bhe\b", "gender", "male", "a man"),

    # Decades are handled by `_age` below, which reads any of them; these are the phrases that are not
    # a decade at all.
    (r"\belderly\b|\bvery old\b|\bancient\b", "age", 72, "elderly"),
    (r"\bmiddle[- ]aged\b", "age", 50, "middle-aged"),
    (r"\bold man\b|\bold woman\b", "age", 68, "old"),
    (r"\bmature\b", "age", 45, "mature"),
    (r"\byoung\b|\byouth\b", "age", 24, "young"),

    # A build word only counts when it is describing the body. "heavy brow" is a face, not a figure,
    # and reading it as a heavy build is exactly the quiet wrong guess this module is supposed to avoid.
    (r"\bmuscular\b|\bpowerfully built\b|\bbroad[- ]shouldered\b|\bmassive shoulders\b",
     "build", "muscular", "muscular"),
    (r"\bathletic\b|\bwell[- ]built\b", "build", "athletic", "athletic"),
    (r"\bslim\b|\bslender\b|\blean\b|\bgaunt\b|\bthin (?:build|frame|figure)\b",
     "build", "slim", "slim"),
    (r"\b(?:heavy|stout|portly|thickset|broad)[- ](?:build|set|frame|figure|body|physique)\b"
     r"|\bstout\b|\bportly\b|\bthickset\b", "build", "heavy", "heavy"),

    (r"\bclean[- ]shaven\b|\bno beard\b|\bbeardless\b", "beard", "none", "clean-shaven"),
    (r"\blong [a-z]* ?beard\b|\bflowing beard\b", "beard", "long", "a long beard"),
    (r"\bfull beard\b|\bthick beard\b|\bbushy beard\b", "beard", "full", "a full beard"),
    (r"\bstubble\b|\bscruffy beard\b|\bshort beard\b", "beard", "scruffy", "stubble"),
    (r"\bmoustache\b|\bmustache\b", "beard", "moustache", "a moustache"),
    (r"\bbeard\b", "beard", "full", "a beard"),

    # "short styled modern dark hair" - a person puts several words between the length and the noun.
    (r"\bbald\b|\bshaven head\b|\bshaved head\b", "hair.length", "none", "bald"),
    (r"\blong (?:[a-z]+ ){0,3}hair\b|\bhair (?:falls|flowing)\b", "hair.length", "long", "long hair"),
    (r"\bshoulder[- ]length hair\b", "hair.length", "medium", "shoulder-length hair"),
    (r"\bshort (?:[a-z]+ ){0,3}hair\b|\bcropped hair\b", "hair.length", "short", "short hair"),

    (r"\brobe[sd]?\b|\bcassock\b", "outfit.style", "robe", "robes"),
    (r"\btunic\b", "outfit.style", "tunic", "a tunic"),
    (r"\bsuit\b(?! ?case)", "outfit.style", "suit", "a suit"),
    (r"\barmou?r(?:ed)?\b|\bbreastplate\b|\bcuirass\b", "outfit.style", "work", "armour"),
]

# Phrases that put a colour on a thing: "long white beard", "coarse brown woollen robe with hood".
# The colour word has to sit near the thing, so a brown robe does not become brown hair.
NEAR = [(r"((?:\w+ ){0,3})beard", "hair.color", "the beard's colour"),
        (r"((?:\w+ ){0,3})hair", "hair.color", "the hair's colour"),
        (r"((?:\w+ ){0,4})(?:robe|tunic|coat|suit|shirt|jacket)", "outfit.top", "what they wear on top"),
        (r"((?:\w+ ){0,3})(?:hood|cowl)", "costume.hood", "a hood")]

HEIGHTS = {"male": 178, "female": 165}      # a starting height, always reported as assumed

# CastForge builds people - MPFB makes a human body and Rigify rigs it. A novel's cast is not all
# people: "Devadatta" in this one is a cybernetic war-horse. Building it as a human would produce
# something absurd in silence, so a character that is plainly not a person is said to be not a person.
#
# A human noun settles it, because animal words turn up in descriptions of people far more often than
# the reverse: Hanuman has "a classically rugged 'Italian Stallion' face" and is a man. Only prose with
# an animal or a machine in it AND no human noun at all is treated as not a person.
A_PERSON = r"\b(?:man|men|woman|women|human|person|people|boy|girl|lady|gentleman|male|female)\b"
NOT_A_PERSON = (r"\bhorse\b|\bequine\b|\bsteed\b|\bstallion\b|\bmare\b|\bbeast\b|\bcreature\b"
                r"|\bdragon\b|\bwolf\b|\blion\b|\btiger\b|\beagle\b|\bserpent\b|\bdrone\b|\bmech\b"
                r"|\bvehicle\b|\bship\b")


def is_person(text):
    """Is this character something MPFB can build a body for?"""
    low = (text or "").lower()
    if re.search(A_PERSON, low):
        return True
    return not re.search(NOT_A_PERSON, low)


def _age(low):
    """Any decade a person might write: 'early 20s', 'in his early 50s', 'late thirties'.

    Enumerating decades one rule at a time missed 'early 50s' in the real cast, so this reads the
    number instead of listing the ones somebody thought of."""
    words = {"twenties": 20, "thirties": 30, "forties": 40, "fifties": 50, "sixties": 60,
             "seventies": 70, "eighties": 80}
    found = re.search(r"\b(early|mid|late)?[- ]?(\d0)s\b", low)
    if found:
        decade, when = int(found.group(2)), found.group(1)
    else:
        found = re.search(r"\b(early|mid|late)?[- ]?(" + "|".join(words) + r")\b", low)
        if not found:
            return None, None
        decade, when = words[found.group(2)], found.group(1)
    offset = {"early": 2, "mid": 5, "late": 8}.get(when, 5)
    return decade + offset, f"{when + ' ' if when else ''}{decade}s"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def angle(filename):
    """Which way a reference image faces, from its name. None when the name does not say."""
    stem = os.path.basename(filename).lower()
    for a in ANGLES:
        if a in stem:
            return a
    return None


def turnaround(ref_images):
    """{angle: [files]} for one character - the sheet the novel locked their face against."""
    out = {}
    for ref in ref_images or []:
        a = angle(ref)
        if a:
            out.setdefault(a, []).append(ref)
    return out


def pick(ref_images):
    """The two photographs CastForge wants: one for the figure, one for the face.

    Returns (body, face). Either can be None, and a character with no usable front reference is a
    character the novel has not finished designing yet."""
    sheet = turnaround(ref_images)
    body = next((sheet[a][0] for a in BODY_ANGLES if sheet.get(a)), None)
    face = next((sheet[a][0] for a in FACE_ANGLES if sheet.get(a)), None)
    return body, face


def _set(design, field, value):
    """Put a dotted field into a design, the way CastForge nests them."""
    if "." in field:
        head, tail = field.split(".", 1)
        design.setdefault(head, {})[tail] = value
    else:
        design[field] = value


def _colour_near(words, text):
    """The first colour word in a phrase, or None. 'coarse brown woollen' -> brown."""
    for word in re.findall(r"[a-z]+", words.lower()):
        if word in COLOURS:
            return COLOURS[word], word
    return None, None


def read_appearance(text):
    """What the prose plainly says, as a design, plus a line per thing read and a list left unread.

    Returns (design, read, missing). `read` is for showing a person what was understood, because the
    only safe way to run a parser over somebody's writing is to show your work."""
    design, said = {}, []
    low = (text or "").lower()
    years, how = _age(low)                 # a written decade beats every word-based age rule
    if years:
        design["age"] = years
        said.append(f"{how} -> age = {years}")
    for pattern, field, value, name in RULES:
        if field in design or (("." in field) and design.get(field.split(".")[0], {}).get(field.split(".", 1)[1])):
            continue                                  # an earlier, more specific rule already said it
        if re.search(pattern, low):
            _set(design, field, value)
            said.append(f"{name} -> {field} = {value}")
    for pattern, field, name in NEAR:
        for phrase in re.findall(pattern, low):
            hexa, word = _colour_near(phrase, low)
            if hexa:
                _set(design, field, hexa)
                said.append(f"{word} {name} -> {field} = {hexa}")
                break
    # A hood is usually named without a colour of its own - "a coarse brown woollen robe with hood" -
    # because it is part of the robe. Giving it the garment's colour is what the sentence means; a hood
    # left unset would simply not be built, which is the one reading the sentence rules out.
    if re.search(r"\bhood(?:ed)?\b|\bcowl\b", low) and not design.get("costume", {}).get("hood"):
        robe = design.get("outfit", {}).get("top")
        _set(design, "costume.hood", robe or COLOURS["brown"])
        said.append(f"a hood -> costume.hood = {robe or COLOURS['brown']}"
                    f"{' (the same colour as the robe)' if robe else ' (no colour given)'}")
    missing = [k for k in ("gender", "age", "build") if k not in design]
    return design, said, missing


def one(character, novel, movie_cast=(), read_appearance=read_appearance):
    """Everything about building one novel character in CastForge."""
    name = re.sub(r"[^a-z0-9]+", "_", (character.get("name") or "").lower()).strip("_")
    body, face = pick(character.get("ref_images"))
    design, said, missing = read_appearance(character.get("appearance"))
    design["name"] = name
    design.setdefault("gender", "male")
    design.setdefault("age", 35)
    design["height_cm"] = HEIGHTS.get(design["gender"], 175)
    design["from_novel"] = {"character": character.get("name"), "trigger": character.get("trigger"),
                            "appearance": character.get("appearance") or "",
                            "tier": character.get("tier"), "variant": character.get("variant") or ""}
    # project.json writes its reference paths with forward slashes whatever machine made them.
    refs = os.path.join(novel, REFS)
    here = lambda p: os.path.normpath(os.path.join(refs, p)) if p else None   # noqa: E731
    body, face = here(body), here(face)
    assumed = [f"height {design['height_cm']} cm (the prose does not say)"]
    assumed += [f"{k} (the prose does not say)" for k in missing]
    person = is_person(character.get("appearance"))
    return {"name": name, "novel_name": character.get("name"), "trigger": character.get("trigger"),
            "body": body, "face": face,
            "angles": sorted(turnaround(character.get("ref_images"))),
            "design": design, "read": said, "assumed": assumed,
            "built": name in set(movie_cast), "person": person,
            "ready": bool(body) and person}


def cast(novel, movie_cast=(), read=_read, exists=os.path.exists):
    """Every character the novel has, in the shape CastForge builds from."""
    path = os.path.join(novel, PROJECT)
    if not exists(path):
        return []
    got = read(path)
    return [one(c, novel, movie_cast) for c in got.get("characters", [])]


def novel_name(novel, read=_read, exists=os.path.exists):
    """What the novel is called, for a person reading a list."""
    path = os.path.join(novel, PROJECT)
    return (read(path).get("name") or "") if exists(path) else ""


def command(row, movie, python="python"):
    """The castforge.py line that builds this character. The design is written beside the movie first."""
    if not row["ready"]:
        return None
    parts = [python, "castforge.py", "character", row["body"], row["name"],
             "--design", f"<movie>/characters/{row['name']}.design.json"]
    if row["face"] and row["face"] != row["body"]:
        parts += ["--face-photo", row["face"]]
    return " ".join(f'"{p}"' if " " in p else p for p in parts) + f"   (into {movie})"


def check(novel, rows, exists=os.path.exists):
    """Plain-language reasons a character cannot be built yet."""
    out = []
    if not exists(os.path.join(novel, PROJECT)):
        out.append(f"the novel has no project at {os.path.join(novel, PROJECT)} - "
                   "open the graphic-novel app and design a cast first")
        return out
    for row in rows:
        if not row["person"]:
            out.append(f"{row['novel_name']} is not a person - CastForge builds human bodies, so this "
                       "one stays a drawn character (or becomes a prop or a set piece)")
        elif not row["ready"]:
            out.append(f"{row['novel_name']} has no front or three-quarter reference - "
                       "generate its turnaround in the novel before building it")
        elif not exists(row["body"]):
            out.append(f"{row['novel_name']}'s reference is listed but not on disk: {row['body']}")
    return out
