// A picture for every word in the vocabulary (core/schema.py), so choosing is looking instead of reading.
// Only the names CastForge already knows are listed; anything missing falls back to its own first letters,
// which is why a new expression or grade shows up as a chip without being added here first.

export const GLYPHS: Record<string, string> = {
  // expressions
  neutral: "\u{1F610}", smile: "\u{1F642}", happy: "\u{1F604}", sad: "\u{1F622}", angry: "\u{1F620}",
  surprised: "\u{1F62E}", scared: "\u{1F628}", disgusted: "\u{1F922}", worried: "\u{1F61F}",
  thinking: "\u{1F914}", skeptical: "\u{1F928}", determined: "\u{1F624}", tired: "\u{1F634}", smug: "\u{1F60F}",
  // postures (neutral and tired are shared with the faces above; a posture row reads them as a stance)
  confident: "\u{1F4AA}", proud: "\u{1F451}", relaxed: "\u{1F6CB}", slumped: "\u{1FAE0}", tense: "\u{1F62C}",
  crouch: "\u{1F9CE}",
  // how fast someone walks
  stroll: "\u{1F422}", normal: "\u{1F6B6}", brisk: "\u{1F3C3}", hurry: "⚡",
  // gestures
  wave: "\u{1F44B}", raise_hand: "✋", point: "\u{1F449}", shrug: "\u{1F937}", nod: "⬇️",
  shake_head: "↔️", hands_on_hips: "\u{1F9CD}", beckon: "\u{1FAF4}", bow: "\u{1F647}",
  look_around: "\u{1F440}", thumbs_up: "\u{1F44D}", cheer: "\u{1F64C}", clap: "\u{1F44F}", block: "\u{1F6E1}️",
  // shot sizes
  wide: "\u{1F5BC}️", medium: "\u{1F9CD}", close: "\u{1F441}️", two_shot: "\u{1F46B}",
  over_shoulder: "\u{1F9D1}‍\u{1F91D}‍\u{1F9D1}", auto: "✨",
  // camera moves
  static: "\u{1F4F7}", push_in: "⬆️", pull_out: "⬇️", pan_left: "⬅️",
  pan_right: "➡️", handheld: "\u{1F590}️",
  // lighting moods
  classic: "\u{1F3AC}", day: "☀️", golden_hour: "\u{1F305}", overcast: "☁️",
  night: "\u{1F319}", interior_warm: "\u{1F4A1}", interior_cool: "\u{1F506}", candlelight: "\u{1F56F}️",
  moonlight: "\u{1F315}", noir: "\u{1F3A9}", studio: "\u{1F4AB}",
  // floors you hear underfoot
  wood: "\u{1FAB5}", concrete: "\u{1F9F1}", carpet: "\u{1F9F6}", tile: "◼️", snow: "❄️",
  // weather
  rain: "\u{1F327}️",
  // voice effects
  none: "\u{1F6AB}", clean: "\u{1F399}️", radio: "\u{1F4FB}", phone: "\u{1F4DE}",
  megaphone: "\u{1F4E3}", echo: "\u{1F50A}", robot: "\u{1F916}",
  // materials
  metal: "⚙️", fabric: "\u{1F9F5}", leather: "\u{1F7EB}", glass: "\u{1FA9F}", plastic: "\u{1F9F4}",
  ceramic: "\u{1F3FA}", stone: "\u{1FAA8}", paper: "\u{1F4C4}", wax: "\u{1F56F}️", brass: "\u{1F536}",
  rubber: "⚫",
  // transitions
  cut: "✂️", fade: "\u{1F311}", fade_white: "⬜", dissolve: "\u{1F4A7}", wipe_left: "⬅️",
  wipe_right: "➡️", slide_left: "↩️", slide_right: "↪️", circle_open: "⭕",
  circle_close: "⚪", pixelize: "\u{1F533}", radial: "\u{1F300}", zoom_in: "\u{1F50D}",
  // hands, sides and reactions
  fist: "✊", open: "\u{1F590}️", right: "\u{1F91B}", left: "\u{1F91C}",
  stagger: "\u{1F635}", dodge: "\u{1F4A8}",
  // where someone looks
  up: "⬆️", down: "⬇️", camera: "\u{1F3A5}",
};

// Actions get their own table: "open" is a door here and an open hand in the list above, and one flat
// namespace would quietly give the wrong one to whichever came second.
export const ACTION_GLYPHS: Record<string, string> = {
  say: "\u{1F4AC}", think: "\u{1F4AD}", narrate: "\u{1F399}️",
  walk: "\u{1F6B6}", face: "\u{1F9ED}", look: "\u{1F440}", turn: "\u{1F504}",
  emote: "\u{1F60A}", gesture: "\u{1F44B}", posture: "\u{1F9CD}",
  hold: "\u{1F932}", release: "\u{1FAF4}",
  strike: "\u{1F94A}", duck: "\u{1F4A8}", block: "\u{1F6E1}️",
  enter: "\u{1F6AA}", exit: "\u{1F6B6}‍➡️", open: "\u{1F513}",
  sit: "\u{1FA91}", stand: "\u{1F9CD}", drive: "\u{1F697}",
  sound: "\u{1F514}", music: "\u{1F3B5}", camera: "\u{1F3A5}", perform: "\u{1F57A}", wait: "⏳",
};

/** The colour a grade pushes the picture towards, so a grade chip can show it rather than spell it. */
export const GRADE_COLORS: Record<string, [string, string]> = {
  neutral: ["#8b93a7", "#c9cfdd"],
  warm: ["#e08a3c", "#f3c99a"],
  cool: ["#4f8fd8", "#a9c9ef"],
  teal_orange: ["#1f8a8a", "#e8863c"],
  night: ["#2a3a6b", "#5a73b8"],
  noir: ["#1a1a1a", "#e8e8e8"],
  vintage: ["#9a7d4f", "#ded0ad"],
  bleach: ["#b9b4a8", "#f2efe6"],
  dream: ["#b06fd8", "#f0c2ec"],
};

/** A short readable word for a vocabulary name ("two_shot" -> "two shot"). */
export const words = (name: string) => String(name).replace(/_/g, " ");

/** The two letters shown when a name has no picture of its own. */
export const initials = (name: string) =>
  words(name).split(" ").map(w => w[0] || "").join("").slice(0, 2).toUpperCase() || "?";

/** Width/height of an aspect name like "16:9", so a chip can be drawn in that shape. */
export function aspectBox(name: string, high = 18): {w: number; h: number} {
  const [a, b] = String(name).split(":").map(Number);
  if (!a || !b || !Number.isFinite(a) || !Number.isFinite(b)) return {w: high, h: high};
  return a >= b ? {w: Math.round(high * (a / b)), h: high} : {w: high, h: Math.round(high * (b / a))};
}
