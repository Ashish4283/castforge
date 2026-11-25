# Gemini prompt: invent a character → CastForge character design

For characters without a photo (invented people for stories and demos). Copy everything inside the
box into Gemini, describe the character on the last line, and save Gemini's answer as
`<name>.design.json`. Then build it with
`python castforge.py character --design <name>.design.json <name>`.

```
You design characters for CastForge, a 3D animation tool. Reply with ONLY valid JSON, no comments,
no explanation. Format:

{
  "name": "<short lowercase name>",
  "gender": "male" or "female",
  "age": <years, 16-90>,
  "height_cm": <centimetres>,
  "build": "slim" | "average" | "athletic" | "heavy" | "muscular",
  "skin": "#rrggbb",
  "hair": {"length": "none" | "short" | "medium" | "long", "color": "#rrggbb",
           "style": "" (use the length) | "none" | "short" | "crew_cut" | "messy" | "afro" | "mid_length" | "bangs" | "shaggy" | "long" | "long_loose" | "ponytail" | "bun" | "bob" | "inverted_bob" | "bobcut" | "braid" | "french_braid" | "double_braid"},
  "eyebrows": "style_1" ... "style_12",
  "beard": "none" | "scruffy" | "full" | "long" | "faun" | "moustache" | "santa",
  "hat": "none" | "santa_made" | "santa" | "newsboy" | "fedora" | "cloche" | "flat_cap",
                                        // "santa_made" is built for that character's own head -
                                        // a deep fur roll, a cone that flops over, a bobble. Prefer
                                        // it to "santa", which is a fixed one-size asset.
  "cap": {"droop": 0.6,                 // 0 straight up, 1 right over
          "towards": 20,                // degrees round the head: 0 their left, 90 behind
          "band": 0.3,                  // how much of it is fur: 0.15 a trim, 0.45 a deep roll
          "bobble": 1.0},               // 0 none, 1.5 enormous
  // "parts" is left out: the studio writes it when someone clicks a part and resizes it by hand.
  "hat_size": 1.0,                      // 0.7 small, 1 as the asset comes, 1.6 oversized.
                                        // The assets are cut small: a Santa cap wants about 1.35.
  "eyes": "brown" | "brownlight" | "green" | "grey" | "blue" | "bluegreen" | "deepblue" | "lightblue" | "ice",
  "outfit": {"garment": "trousers" | "shorts" | "skirt" | "dress", "sleeves": "short" | "long",
             "top": "#rrggbb", "bottom": "#rrggbb", "shoes": "#rrggbb"},
  "outfit.style": "casual" | "suit" | "formal" | "work" | "robe" | "tunic",
  "costume": {"coat": "none" | "long", "fabric": "garment" | "velvet" | "leather" | "cotton",
              "trim": "#rrggbb", "belt": "#rrggbb", "buckle": "#rrggbb", "gloves": "#rrggbb",
              "boots": "#rrggbb", "cape": "#rrggbb", "cape_length": 0.75, "armour": "#rrggbb",
              "hood": "#rrggbb"}
  // Optional. The face and body, shaped feature by feature: every value is a number from -1 to +1, where
  // 0 is an ordinary face and the sign says which way (jaw_width -1 narrow, +1 wide). Leave out everything
  // you do not mean to change: a key you do not write is left alone. Use a few strong ones rather than
  // many small ones, and keep them within about -0.7..0.7 unless the person should look truly unusual.
  "face": {"head_shape": "none" | "oval" | "round" | "square" | "rectangular" | "triangular" | "invertedtriangular" | "diamond",
//   Head: head_width, head_height, head_depth, face_fat, forehead_height, brow_ridge, temples, neck_thickness
//   Jaw and chin: jaw_width, jawline, chin_height, chin_forward, chin_prominent, chin_cleft
//   Cheeks: cheekbones, cheek_fullness, cheek_inner
//   Eyes and brows: eye_size, eye_spacing, eye_height, eye_opening, eye_tilt, eye_depth, eye_bags, eyefold, brow_height, brow_angle
//   Nose: nose_width, nose_length, nose_depth, nose_bridge, nose_curve, nostril_width, nose_tip, nose_tip_width, nose_flaring
//   Mouth and lips: mouth_width, lip_height, upper_lip, lower_lip, lip_corners, cupids_bow, philtrum, mouth_height, laugh_lines
//   Ears: ear_size, ear_stickout, ear_lobes
          },
  "body": {
//   Frame: shoulders, chest, waist, hips, neck, torso_length, v_taper
//   Muscle: chest_muscle, back_muscle, shoulder_muscle, arm_muscle, forearm_muscle, leg_muscle, calf_muscle, abs
//   Weight: belly, arm_fat, leg_fat, buttocks, double_chin
          }
}

Rules:
- The character must be invented, not a real or famous person.
- Use realistic, natural colours for skin and hair that fit the character's background and age.
- For a dress, use the same colour for top and bottom.
- "face" and "body" are optional: use them to make the person recognisable (a heavy jaw, deep set eyes, a
  wrestler's shoulders). An ordinary person needs none of them.
- "costume" is only for costumes (Santa, uniforms, fantasy): leave it out for everyday clothes. Leave out
  any costume piece the character does not wear (no trim, no belt...).

Character: <DESCRIBE THE CHARACTER HERE>
```

Photo characters still work as before:
`python castforge.py character photo.png <name> --gender ... --age ... --height-cm ... --face-photo face.png`
