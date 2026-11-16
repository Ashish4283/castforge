# Gemini prompt: story idea → CastForge scene.json

Copy everything inside the box into Gemini and replace the last line with your idea. Save Gemini's
answer as `scene.json` in the scene folder, next to the background image (and any audio files).

```
You write scene files for CastForge, a 3D animation tool. Reply with ONLY valid JSON, no comments,
no explanation. Format:

{
  "background": "background.png",
  "ambience": "ambience.wav",
  "ambience_volume": 0.5,
  "floor": "wood",
  "cast": {
    "<name>": {"character": "<name>.blend", "voice": "<voice>", "position": [x, y], "facing": "camera"}
  },
  "props": [ ...props... ],
  "script": [ ...steps... ]
}

For a story with more than one place or moment, write an EPISODE instead: the cast once (character
file and voice), then one entry per scene. Each scene has its own background, floor, props and
script, and lists only the people who are in it, with their position:

{
  "cast": {"<name>": {"character": "<file>.blend", "voice": "<voice>"}},
  "scenes": [
    {"id": "<short name>", "background": "<picture>", "floor": "wood",
     "cast": {"<name>": {"position": [x, y], "facing": "camera"}},
     "props": [ ...props... ], "script": [ ...steps... ]},
    ...
  ]
}
Start a new scene whenever the place changes, or when time jumps. Keep each scene under about 40
seconds; split a long conversation into two scenes in the same place.

Rules:
- Output must be valid JSON: every key has a value, commas between items, all brackets closed.
- Stage is in metres: x left(-) to right(+), y = depth (0 = front, positive = further away).
  Keep everyone within x -2.5..2.5 and y 0..1.5. People talking stand 1.0-1.4 m apart, also after
  someone walks up to another person (never closer than 1.0 m).
- Only mention things the audience can see or hear: if a line talks about an object (a window, a
  door, a table), add it as a prop.
- floor is one of: wood, concrete, carpet, tile.
- voice is one of: af_heart, af_bella, af_nicole, am_michael, am_adam, am_eric (American),
  bf_emma, bf_isabella, bm_george, bm_lewis (British), hf_alpha, hf_beta, hm_omega, hm_psi (Hindi).
  Pick a voice that fits each character's gender and age.
- Steps run one after another. Add "with": "previous" to start a step together with the one before.
- Step types:
  {"who": "<name>", "do": "walk", "to": [x, y]}
  {"who": "<name>", "do": "face", "target": "<other name>" or "camera"}
  {"who": "<name>", "do": "say", "text": "<one spoken line, natural, under 25 words>"}
  For a final recorded/generated performance, the user will add an audio file beside the scene:
  {"who": "<name>", "do": "say", "audio": "voices/<name>_001.wav", "text": "<exact transcript>"}
  Do not invent audio files. Use text-only lines for drafts; the transcript is retained with audio for lip-sync.
  {"who": "<name>", "do": "enter", "door": "<door prop id>", "to": [x, y]}   (comes in through a door)
  {"who": "<name>", "do": "open", "door": "<door prop id>", "sound": "door_open",
   "side_offset": 0.24}   (walks up to the handle side and opens it)
  {"who": "<name>", "do": "sit", "on": "<chair, stool, bench or sofa prop id>"}
  {"who": "<name>", "do": "stand"}
  {"do": "sound", "sfx": "door_bell" | "door_open" | "door_close" | "chair_sit" | "cup_place"}
  {"do": "wait", "seconds": 1.0}
  {"who": "<name>", "do": "think", "text": "<an inner thought, heard but not spoken>"}
  {"who": "<name>", "do": "exit", "door": "<door prop id>"}   (walks out through a door)
  {"who": "<name>", "do": "drive", "seconds": 8, "wheel": "<steering_wheel prop id>", "turn": 0}
   (seated driver; hands grip that wheel and turn with it; "turn" = steady steering in degrees)
  {"do": "narrate", "text": "<voice-over>", "voice": "<voice>"}   (a narrator nobody sees)
  {"who": "<name>", "do": "perform", "clip": "<motion clip name>", "from": 0, "to": 2.5}
   (a motion-capture move: punch, sword swing, dance. Only use clip names the user lists for you;
   "from"/"to" pick seconds of the clip; "travel": false keeps the character on the spot)
  {"who": "<name>", "do": "hold", "prop": "<prop id>", "hand": "right"}
   (picks the prop up and carries it: walks and motion clips keep it in hand. Small props only)
  {"who": "<name>", "do": "release", "to": [x, y]}   (sets the held prop down; no "to": lets go in place)
  {"who": "<name>", "do": "duck", "seconds": 1.0}   (ducks down fast and comes back up; a dodge)
  {"who": "<name>", "do": "strike", "target": "<name>", "clip": "<attack clip>", "react": "stagger"}
   (one fight beat: closes to striking distance, lands the attack with an impact sound and a tiny freeze
   on contact; "react" is stagger, dodge, block or none. Write a fight as a few strikes in a row,
   alternating who attacks, not one long clip)
- Acting (use it: it makes the scene alive):
  add "expression" to a say/think line: neutral, smile, happy, sad, angry, surprised, scared,
  disgusted, worried, thinking, skeptical, determined, tired, smug.
  {"who": "<name>", "do": "emote", "expression": "<expression>", "seconds": 2}   (without seconds it stays)
  {"who": "<name>", "do": "gesture", "type": "<gesture>"}   gesture is one of: wave, raise_hand, point (add
   "target": "<name>" or [x, y]), shrug, nod, shake_head, hands_on_hips, beckon, bow, look_around,
   thumbs_up, cheer, clap
  {"who": "<name>", "do": "posture", "posture": "<posture>"}   neutral, confident, proud, relaxed, slumped,
   tense, tired, crouch (a cast member can also start with "expression" and "posture")
  {"who": "<name>", "do": "look", "target": "<name>" | "camera" | [x, y] | "left" | "right" | "up" | "down",
   "seconds": 1.5}   (head and eyes only)
  walk can have "pace": "stroll" | "normal" | "brisk" | "hurry".
  a line can have "fx": "phone" | "radio" | "megaphone" | "echo" | "robot" for a voice effect.
- Sound and camera:
  {"do": "music", "bed": "<library music name>", "volume": 0.35}   and later {"do": "music", "stop": true}
  {"do": "camera", "shot": "wide" | "medium" | "close" | "two_shot" | "over_shoulder", "on": "<name>",
   "move": "static" | "push_in" | "pull_out" | "pan_left" | "pan_right" | "handheld", "seconds": 4}
   (only for a shot that matters; the automatic director chooses good shots by itself)
- Scene settings (optional): "lighting": auto, day, golden_hour, overcast, night, interior_warm,
  interior_cool, candlelight, moonlight, noir, studio; "weather": "snow" or "rain" (or
  {"type": "snow", "amount": 0.5, "fog": 0.2}); "grade": neutral, warm, cool, teal_orange, night, noir,
  vintage, bleach, dream; for an episode: "title": {"text": "<film title>"}, "credits": {"lines": [...]},
  "transition": "cut" | "fade" | "dissolve" between scenes.
- Make it real: people who arrive come in through a door ("enter"; give that person no "position"
  in the cast). A door for arrivals stands at the back of the room (y about 2.3) with
  "rotation": 0; add "bell": true for a shop door bell. People who are waiting sit: give them
  "sit": "<chair id>" in the cast (and the chair's position), so they are seated from the start.
  A chair's back is at +y; "rotation": 0 means the person sitting faces the camera.
- Before two people talk, make them face each other. Keep the scene under 60 seconds.
- Props are solid 3D objects CastForge builds; people walk around them. Each prop:
  {"id": "<short id>", "make": "<type>", "position": [x, y], "rotation": <degrees>,
   "size": [width, depth, height], "color": "#rrggbb", "material": "<material>"}
  To put a prop on another one (a cup on a table) add "on": "<id of the table>" and use about the
  same position as the table.
  type is one of (typical size in metres, width/depth/height):
    table (1.2/0.7/0.75; add "shape": "round" for a round one, e.g. 0.8/0.8/0.75), chair (0.45/0.48/0.9),
    stool (0.38/0.38/0.75), bench (1.4/0.4/0.45), sofa (1.9/0.85/0.85), bed (1.6/2.0/0.55),
    shelf (0.9/0.32/1.8), counter (2.0/0.6/0.95), door (0.9/0.06/2.05), wall (3.0/0.12/2.6),
    window (1.2/0.08/1.2), lamp (0.35/0.35/1.6, gives warm light), cup (0.08/0.08/0.1),
    plant (0.45/0.45/1.0), box (0.5/0.5/0.5), tv (1.1/0.25/1.2),
    armchair (0.85/0.85/1.0), desk, bookshelf, fireplace, christmas_tree, pine_tree, lantern, candle,
    street_lamp, snowman, gift, sack, crate, barrel, riser, rug, picture_frame, bottle, book, phone, laptop,
    cash_register, crowbar, santa_hat, pickup_truck, steering_wheel, car_radio (each has a sensible default size).
  material is one of: wood, metal, fabric, leather, glass, plastic, ceramic, stone.
  Leave walking space: keep props at least 0.6 m from where people stand and walk, and do not put
  props between two people who talk. Use props only where they help the story (0-8 of them).
- A model made in Blender (or a .glb/.obj/.fbx) is a prop with "file" instead of "make":
  {"id": "cab", "file": "../sets/truck_cab/cab.blend", "position": [x, y], "rotation": 0,
   "seat": "<name of the seat object in the model>", "wheel": "<name of the steering wheel object>"}
  "seat" makes it something to sit on ("sit" "on": "cab"); "wheel" lets a "drive" step hold and turn that
  object ("wheel": "cab"). Object names are the ones in Blender's Outliner.
- For a photographed outdoor set, a picture-matched road surface can be generated with
  {"id":"road", "make":"picture_road", "screen_path":[[0.65,0.65],[0.60,0.9]], "width":3.5}.
  screen_path points are normalized [x,y] image coordinates; width is metres. To make a photographed
  door interactive, add a door prop with "match_picture": true and "picture_rect":[left,top,right,bottom]
  as normalized image coordinates, then use the "open" step with that door's id. Use "side_offset" to move
  the character beside the door center (toward the handle). Keep the rectangle tightly around the door panel.

Scene idea: <WRITE YOUR IDEA HERE>
```

## Then

1. Create the background image in Gemini too ("eye-level photo of an empty <place>, no people, wide
   angle, 16:9") and save it as `background.png`.
2. Optional: a sound-effects or ambience file as `ambience.wav` (or delete the `ambience` line).
3. Build each character once from a photo (see README), saved as `<name>.blend` in the scene folder.
4. Check, then render:
   `python castforge.py check <folder>` (catches broken JSON, missing files, people standing too close)
   `python castforge.py episode <folder>` (starts in the background and returns at once)
   `python castforge.py status <folder>` (progress)
   Quality: blocking (default, about 1 minute per minute of film), draft, standard (960x540, for
   publishing; about 3x faster than final), final. Add e.g. `--quality standard` to the episode command.

   For AI agents running these commands: start the render ONCE, then only check `status`. Never start a
   second render while one is running (the 4 GB GPU cannot run two; both crash). A stopped render
   continues where it stopped when `episode` is run again.

To use a recorded/Gemini voice file instead of a generated voice, replace `"text": "..."` with
`"audio": "line1.wav"` (Rhubarb then does the lip-sync from the audio).
