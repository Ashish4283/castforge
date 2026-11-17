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
  "hair": {"length": "none" | "short" | "medium" | "long", "style": "auto", "color": "#rrggbb"},
  "beard": "none" | "scruffy" | "full" | "long" | "faun" | "moustache" | "santa",
  "hat": "none" | "santa" | "newsboy" | "fedora" | "cloche" | "flat_cap",
  "eyes": "brown" | "brownlight" | "green" | "grey" | "blue" | "bluegreen" | "deepblue" | "lightblue" | "ice",
  "outfit": {"garment": "trousers" | "shorts" | "skirt" | "dress", "sleeves": "short" | "long",
             "top": "#rrggbb", "bottom": "#rrggbb", "shoes": "#rrggbb"},
  "outfit.style": "casual" | "suit" | "formal" | "work" | "robe" | "tunic",
  "costume": {"coat": "none" | "long", "fabric": "garment" | "velvet" | "leather" | "cotton",
              "trim": "#rrggbb", "belt": "#rrggbb", "buckle": "#rrggbb", "gloves": "#rrggbb",
              "boots": "#rrggbb", "cape": "#rrggbb", "armour": "#rrggbb"}
}

Rules:
- The character must be invented, not a real or famous person.
- Use realistic, natural colours for skin and hair that fit the character's background and age.
- For a dress, use the same colour for top and bottom.
- "costume" is only for costumes (Santa, uniforms, fantasy): leave it out for everyday clothes. Leave out
  any costume piece the character does not wear (no trim, no belt...).

Character: <DESCRIBE THE CHARACTER HERE>
```

Photo characters still work as before:
`python castforge.py character photo.png <name> --gender ... --age ... --height-cm ... --face-photo face.png`
