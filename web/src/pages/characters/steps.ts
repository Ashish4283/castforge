// The studio's steps: what you are asked, in the order a person actually decides it.
//
// Each step names the design keys it covers, where the camera should be looking while you are in it, and
// a line saying what the step is for. The slider groups come from the schema (core/appearance.py), so a
// feature added there turns up in the right step on its own.
export interface Step {
  id: string;
  title: string;
  text: string;
  look: "whole" | "face" | "body";
  keys?: string[];                   // plain controls, drawn as fields
  sliders?: "face" | "body";         // the grouped sliders of one half of the table
  looks?: {key: string; from: string; title: string; none?: string}[];   // pick-a-picture rows
  colours?: {key: string; title: string; swatches: string[]}[];
}

const SKIN = ["#f6ded0", "#edc8ab", "#dcab86", "#c58d64", "#a46a45", "#7d4a2e", "#563021"];
const HAIR = ["#120e0c", "#2b1d16", "#4a2f1e", "#7a4a24", "#a9763f", "#c9a86a", "#9a9a9a", "#e6e2dc", "#8c2f1d"];
const CLOTH = ["#2c2f36", "#3b4150", "#40506a", "#5a6b52", "#6b4a33", "#8e1b22", "#b8872f", "#d8d2c6", "#111214"];

export const STEPS: Step[] = [
  {id: "who", title: "Who are they?", look: "whole",
   text: "The person underneath everything else. These four shape the body the rest is built on.",
   keys: ["gender", "age", "height_cm", "build"]},

  {id: "head", title: "The shape of the head", look: "face",
   text: "Start with the whole head, then the jaw and cheeks. Drag a slider and watch: the middle is an ordinary face.",
   keys: ["face.head_shape"], sliders: "face"},

  {id: "hair", title: "Hair and brows", look: "face",
   text: "Pick a style, then its colour. A hat will hide the hair, so choose the hat last if you want one.",
   looks: [{key: "hair.style", from: "hair", title: "Hair", none: "Bald"},
           {key: "eyebrows", from: "eyebrows", title: "Eyebrows"}],
   colours: [{key: "hair.color", title: "Hair colour (the beard takes it too)", swatches: HAIR}]},

  {id: "beard", title: "Beard", look: "face",
   text: "Nothing, or one of these. It takes the hair colour.",
   looks: [{key: "beard", from: "beard", title: "Beard", none: "Clean shaven"}]},

  {id: "skin", title: "Skin and eyes", look: "face",
   text: "The colouring. The build matches the nearest real skin it has to the colour you pick.",
   keys: ["eyes"], colours: [{key: "skin", title: "Skin", swatches: SKIN}]},

  {id: "body", title: "Build", look: "body",
   text: "The frame, the muscle and the weight, over whatever the build preset already gave you.",
   sliders: "body"},

  {id: "clothes", title: "Clothes", look: "whole",
   text: "A whole outfit, or a top and something below. Pick the shapes here and the colours underneath.",
   looks: [{key: "outfit.style", from: "outfit", title: "Outfit", none: "Separates"},
           {key: "outfit.garment", from: "garment", title: "Below the waist"},
           {key: "hat", from: "hat", title: "Hat", none: "No hat"}],
   keys: ["outfit.sleeves"],
   colours: [{key: "outfit.top", title: "Top", swatches: CLOTH},
             {key: "outfit.bottom", title: "Trousers or skirt", swatches: CLOTH},
             {key: "outfit.shoes", title: "Shoes", swatches: CLOTH}]},

  {id: "costume", title: "Costume", look: "whole",
   text: "Pieces over the clothes: a coat, fur trim, a belt, gloves, boots, a cape, armour, a hood. Leave a colour empty to leave the piece off.",
   keys: ["costume.coat", "costume.fabric", "costume.trim", "costume.belt", "costume.buckle",
          "costume.gloves", "costume.boots", "costume.cape", "costume.cape_length", "costume.armour",
          "costume.hood"]},

  {id: "build", title: "Ready", look: "whole",
   text: "That is the character. Building makes the real one: the rig, the skin, the textures and the face.",
   keys: []},
];

export const stepOf = (id: string) => Math.max(0, STEPS.findIndex(s => s.id === id));
