// Controls you play with instead of forms you fill in.
//
// Every one of these is a direct way to say a thing that used to be typed: a stage you drag people around
// on instead of writing "1.4, -0.8"; a dial for which way someone faces; a slider for every number, with the
// span it is allowed to live in coming from core/schema.py; a gallery of voices you listen to; pictures for
// the words in the vocabulary. ParamInput.tsx chooses between them from the parameter's own type, so a new
// action in the schema arrives in the app already playable.
import {ReactNode, useEffect, useMemo, useRef, useState} from "react";
import {ChevronDown, Circle, Crosshair, Hand, Move, Pause, Play, RotateCcw, Search, Square, Volume2, X, ZoomIn, ZoomOut} from "lucide-react";
import {Json, ParamDef} from "../api";
import {useStore} from "../app/store";
import {aspectBox, GLYPHS, GRADE_COLORS, initials, words} from "./glyphs";
import {Button} from "./ui";

export const STAGE_COLORS = ["#e0574d", "#4f9dde", "#5cc985", "#e5a54a", "#b07fe0", "#4fc6c0"];
export const stageColor = (i: number) => STAGE_COLORS[((i % STAGE_COLORS.length) + STAGE_COLORS.length) % STAGE_COLORS.length];

const round = (v: number, to: number) => Math.round(v / to) * to;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
/** Trailing zeros are noise: 1.5 s, not 1.50 s, and 0.05 still shows its two places. */
export const tidy = (v: number, step = 0.01) => {
  const places = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
  return Number(v.toFixed(places)).toString();
};

// ---------------------------------------------------------------------------------------------------------
// One audio element for the whole app: pressing play on a second voice stops the first, which is what
// anyone comparing two voices expects.
let sound: HTMLAudioElement | null = null;
export function playSound(url: string, onEnd?: () => void) {
  sound?.pause();
  sound = new Audio(url);
  sound.addEventListener("ended", () => onEnd?.());
  sound.addEventListener("error", () => onEnd?.());
  return sound.play().catch(() => onEnd?.());
}
export const stopSound = () => { sound?.pause(); sound = null; };

// ---------------------------------------------------------------------------------------------------------
/** A number with a slider over the span core/schema.py says it lives in, and the exact value still typeable. */
export function Regulator({def, value, onChange, onError}: {
  def: ParamDef; value: Json; onChange: (v: Json) => void; onError?: (m: string) => void;
}) {
  const [typing, setTyping] = useState<string | null>(null);
  const lo = def.lo!, hi = def.hi!, step = def.step!, unit = def.unit ?? "";
  const fallback = typeof def.default === "number" ? def.default : (lo + hi) / 2;
  const set = typeof value === "number" && Number.isFinite(value);
  const at = set ? (value as number) : fallback;
  const shown = clamp(at, Math.min(lo, at), Math.max(hi, at));      // a hand-written 40 s still shows where it is
  const commit = (text: string) => {
    setTyping(null);
    if (text.trim() === "") return onChange(null);
    const n = Number(text);
    if (!Number.isFinite(n)) return onError?.("Enter a number.");
    onChange(n);
  };
  return (
    <div className={`reg ${set ? "" : "unset"}`}>
      <input className="reg-slide" type="range" min={Math.min(lo, shown)} max={Math.max(hi, shown)} step={step}
             value={shown} aria-label={def.help}
             onChange={e => onChange(round(Number(e.target.value), step))}
             onDoubleClick={() => onChange(def.default ?? null)} />
      {typing === null ? (
        <button type="button" className="reg-value" title="Type an exact value" onClick={() => setTyping(set ? String(at) : "")}>
          {tidy(shown, step)}<small>{unit}</small>
          {unit === "rad" && <em>{Math.round(shown * 180 / Math.PI)}&deg;</em>}
          {!set && <em>default</em>}
        </button>
      ) : (
        <input className="input reg-type" autoFocus value={typing} inputMode="decimal"
               onChange={e => setTyping(e.target.value)} onBlur={e => commit(e.target.value)}
               onKeyDown={e => { if (e.key === "Enter") commit((e.target as HTMLInputElement).value); if (e.key === "Escape") setTyping(null); }} />
      )}
      {set && def.default !== undefined && (
        <button type="button" className="reg-clear" title={`Back to ${def.default}${unit}`} onClick={() => onChange(null)}>
          <RotateCcw size={12} />
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
export type Person = {name: string; at: [number, number] | null; color: string; self?: boolean};
export type Thing = {id: string; at: [number, number]; size?: [number, number]};

/**
 * The floor, seen from above, with everyone already standing on it: drag the marker to say where.
 *
 * x runs right (the red line), y runs away from the camera (the green line) - the same axes the render
 * uses, which is why the camera sits at the bottom edge looking up the page. It replaces a text box that
 * asked for "two coordinates, for example -1.2, 0.5": nobody can picture a room from that.
 */
export function StagePad({value, onChange, people = [], things = [], height = 230, onPick, onPickThing}: {
  value: [number, number] | null; onChange: (p: [number, number]) => void;
  people?: Person[]; things?: Thing[]; height?: number;
  onPick?: (who: string) => void; onPickThing?: (id: string) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [span, setSpan] = useState(0);
  const reach = useMemo(() => {
    const xs = [2.5], ys = [2.5];
    for (const p of people) if (p.at) { xs.push(Math.abs(p.at[0]) + 0.8); ys.push(Math.abs(p.at[1]) + 0.8); }
    for (const t of things) { xs.push(Math.abs(t.at[0]) + 0.8); ys.push(Math.abs(t.at[1]) + 0.8); }
    if (value) { xs.push(Math.abs(value[0]) + 0.8); ys.push(Math.abs(value[1]) + 0.8); }
    return Math.ceil(Math.max(...xs, ...ys));
  }, [people, things, value]);
  const size = span || reach;                                 // auto until somebody zooms
  const metres = (clientX: number, clientY: number, coarse: boolean): [number, number] => {
    const box = svg.current!.getBoundingClientRect();
    const x = -size + (clientX - box.left) / box.width * 2 * size;
    const y = size - (clientY - box.top) / box.height * 2 * size;
    const to = coarse ? 0.5 : 0.05;
    return [clamp(round(x, to), -size, size), clamp(round(y, to), -size, size)];
  };
  const drag = (e: React.PointerEvent) => {
    if ((e.target as Element).closest(".sp-who, .sp-pick")) return;    // clicking someone selects them, not the floor
    (e.target as Element).setPointerCapture?.(e.pointerId);
    onChange(metres(e.clientX, e.clientY, e.shiftKey));
  };
  const ticks = [];
  for (let t = -Math.floor(size); t <= Math.floor(size); t++) ticks.push(t);
  const nudge = (dx: number, dy: number) => {
    const [x, y] = value || [0, 0];
    onChange([round(x + dx, 0.05), round(y + dy, 0.05)]);
  };
  return (
    <div className="floor">
      {/* The box is kept square on purpose: the svg is mapped to metres by its own width and height, and a
          letterboxed one would put the marker where the pointer is not. */}
      <div className="floor-box" style={{["--pad" as string]: `${height}px`}}>
      <svg ref={svg} viewBox={`${-size} ${-size} ${2 * size} ${2 * size}`} tabIndex={0}
           role="application" aria-label="Where on the floor"
           onPointerDown={drag}
           onPointerMove={e => { if (e.buttons === 1) onChange(metres(e.clientX, e.clientY, e.shiftKey)); }}
           onKeyDown={e => {
             const by = e.shiftKey ? 0.5 : 0.1;
             const go: Record<string, [number, number]> = {
               ArrowLeft: [-by, 0], ArrowRight: [by, 0], ArrowUp: [0, by], ArrowDown: [0, -by],
             };
             if (go[e.key]) { e.preventDefault(); nudge(...go[e.key]); }
           }}>
        <rect x={-size} y={-size} width={2 * size} height={2 * size} className="sp-floor" />
        {ticks.map(t => (
          <g key={t}>
            <line x1={t} y1={-size} x2={t} y2={size} className="sp-grid" />
            <line x1={-size} y1={t} x2={size} y2={t} className="sp-grid" />
          </g>
        ))}
        <line x1={-size} y1={0} x2={size} y2={0} className="sp-x" />
        <line x1={0} y1={-size} x2={0} y2={size} className="sp-y" />
        {things.map(t => {
          const [w, d] = t.size || [0.45, 0.45];
          return (
            <g key={t.id} className={onPickThing ? "sp-pick" : ""} onPointerDown={() => onPickThing?.(t.id)}>
              <rect x={t.at[0] - w / 2} y={-t.at[1] - d / 2} width={w} height={d} className="sp-thing" />
              <text x={t.at[0]} y={-t.at[1] + d / 2 + size * 0.075} className="sp-label"
                    style={{fontSize: size * 0.07}}>{t.id}</text>
            </g>
          );
        })}
        {people.map(p => p.at && (
          <g key={p.name} className={`sp-who ${p.self ? "self" : ""}`} onPointerDown={() => onPick?.(p.name)}>
            <circle cx={p.at[0]} cy={-p.at[1]} r={0.3} fill={p.color} opacity={p.self ? 1 : 0.55} />
            <text x={p.at[0]} y={-p.at[1] + size * 0.028} className="sp-initials" style={{fontSize: size * 0.075}}>
              {initials(p.name)}
            </text>
          </g>
        ))}
        {value && (
          <g className="sp-puck" transform={`translate(${value[0]} ${-value[1]})`}>
            <circle r={0.42} />
            <line x1={-0.2} y1={0} x2={0.2} y2={0} />
            <line x1={0} y1={-0.2} x2={0} y2={0.2} />
          </g>
        )}
        <g className="sp-cam" transform={`translate(0 ${size - 0.3})`}>
          <path d={`M ${-0.34} ${0.26} L 0 ${-0.26} L ${0.34} ${0.26} Z`} />
        </g>
      </svg>
      </div>
      <div className="floor-bar">
        <span className="floor-at">
          {value ? <><b style={{color: "var(--axis-x)"}}>x</b> {tidy(value[0])} <b style={{color: "var(--axis-y)"}}>y</b> {tidy(value[1])} m</>
                 : <span className="muted">click the floor</span>}
        </span>
        <span className="grow" />
        <span className="muted small">{size} m</span>
        <button type="button" title="Closer in" onClick={() => setSpan(Math.max(2, size - 2))}><ZoomIn size={13} /></button>
        <button type="button" title="Further out" onClick={() => setSpan(Math.min(40, size + 2))}><ZoomOut size={13} /></button>
        <button type="button" title="Fit everything" onClick={() => setSpan(0)}><Crosshair size={13} /></button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/**
 * Which way a body is turned. 0 is looking straight at the camera and + turns to their left, which is the
 * convention the render uses (blender/acting.py `bearing`), so the arrow points where the person will look.
 */
export function Dial({value, onChange, size = 74, nullLabel = "camera", presets = true}: {
  value: number | "camera" | null; onChange: (v: number | null) => void;
  size?: number; nullLabel?: string; presets?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const deg = typeof value === "number" ? value : 0;
  const rad = deg * Math.PI / 180;
  const set = (clientX: number, clientY: number, coarse: boolean) => {
    const r = box.current!.getBoundingClientRect();
    const dx = clientX - (r.left + r.width / 2), dy = clientY - (r.top + r.height / 2);
    let d = Math.atan2(dx, dy) * 180 / Math.PI;               // 0 points at the camera, + turns left
    d = coarse ? round(d, 45) : round(d, 1);
    onChange(((d + 540) % 360) - 180);
  };
  return (
    <div className="dial-row">
      <div ref={box} className="dial" style={{width: size, height: size}} tabIndex={0} role="slider"
           aria-valuenow={deg} aria-label="Which way they face"
           onPointerDown={e => { (e.target as Element).setPointerCapture?.(e.pointerId); set(e.clientX, e.clientY, e.shiftKey); }}
           onPointerMove={e => { if (e.buttons === 1) set(e.clientX, e.clientY, e.shiftKey); }}
           onKeyDown={e => {
             const by = e.shiftKey ? 15 : 5;
             if (e.key === "ArrowLeft") { e.preventDefault(); onChange(((deg - by + 540) % 360) - 180); }
             if (e.key === "ArrowRight") { e.preventDefault(); onChange(((deg + by + 540) % 360) - 180); }
           }}>
        <svg viewBox="-1 -1 2 2">
          <circle r={0.94} className="dial-face" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map(a => {
            const t = a * Math.PI / 180;
            return <line key={a} className="dial-tick" x1={Math.sin(t) * 0.78} y1={Math.cos(t) * 0.78}
                         x2={Math.sin(t) * 0.92} y2={Math.cos(t) * 0.92} />;
          })}
          <g className={typeof value === "number" ? "" : "dim"}>
            <line className="dial-arm" x1={0} y1={0} x2={Math.sin(rad) * 0.72} y2={Math.cos(rad) * 0.72} />
            <circle className="dial-head" cx={Math.sin(rad) * 0.72} cy={Math.cos(rad) * 0.72} r={0.14} />
          </g>
          <circle r={0.1} className="dial-pin" />
        </svg>
        <span className="dial-cam" title="The camera is this way">&#x1F3A5;</span>
      </div>
      <div className="stack sm">
        <b className="dial-read">{typeof value === "number" ? `${Math.round(deg)}°` : nullLabel}</b>
        {presets && (
          <div className="row nowrap" style={{gap: 4}}>
            {([["camera", null], ["away", 180], ["left", -90], ["right", 90]] as [string, number | null][]).map(([l, v]) => (
              <button key={l} type="button" className={`mini ${(v === null ? value == null || value === "camera" : value === v) ? "on" : ""}`}
                      onClick={() => onChange(v)}>{l}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** A picture for every choice. Falls back to the name's initials, so a new word is never hidden. */
export function ChipPick({value, onChange, options, placeholder, placeholderHint, kind, columns}: {
  value: string | null; onChange: (v: string | null) => void; options: string[];
  placeholder?: string; placeholderHint?: string; kind?: "grade" | "aspect" | "plain"; columns?: number;
}) {
  const [find, setFind] = useState("");
  const many = options.length > 12;
  const shown = many && find ? options.filter(o => words(o).includes(find.toLowerCase())) : options;
  const face = (name: string): ReactNode => {
    if (kind === "grade" && GRADE_COLORS[name]) {
      const [a, b] = GRADE_COLORS[name];
      return <span className="chip-grade" style={{background: `linear-gradient(135deg, ${a}, ${b})`}} />;
    }
    if (kind === "aspect") {
      const {w, h} = aspectBox(name, 16);
      return <span className="chip-aspect" style={{width: w, height: h}} />;
    }
    return GLYPHS[name] ? <span className="chip-glyph">{GLYPHS[name]}</span> : <span className="chip-ini">{initials(name)}</span>;
  };
  return (
    <div className="chips-wrap">
      {many && (
        <div className="chip-find">
          <Search size={13} />
          <input value={find} onChange={e => setFind(e.target.value)} placeholder={`Find one of ${options.length}`} />
          {find && <button type="button" onClick={() => setFind("")}><X size={12} /></button>}
        </div>
      )}
      <div className="chips" style={columns ? {gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`} : undefined}>
        {placeholder && (
          <button type="button" className={`chip ${value ? "" : "on"}`} title={placeholderHint || placeholder}
                  onClick={() => onChange(null)}>
            <span className="chip-ini">&mdash;</span>{placeholder}
          </button>
        )}
        {shown.map(o => (
          <button key={o} type="button" className={`chip ${o === value ? "on" : ""}`} onClick={() => onChange(o)} title={words(o)}>
            {face(o)}{words(o)}
          </button>
        ))}
        {!shown.length && <span className="muted small">Nothing matches &ldquo;{find}&rdquo;.</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** The camera move as a stick: push in, pull out, pan either way, or hold it still in the middle. */
const MOVE_SPOTS: Record<string, [number, number]> = {
  push_in: [1, 0], pull_out: [1, 2], pan_left: [0, 1], pan_right: [2, 1], static: [1, 1],
};
export function MovePad({value, onChange, options}: {value: string | null; onChange: (v: string | null) => void; options: string[]}) {
  const placed = options.filter(o => MOVE_SPOTS[o]);
  const rest = options.filter(o => !MOVE_SPOTS[o]);
  const now = value || "static";
  return (
    <div className="movepad-row">
      <div className="movepad" role="radiogroup"
           aria-label="Where the camera goes during the shot; the middle holds it still">
        {placed.map(o => {
          const [c, r] = MOVE_SPOTS[o];
          return (
            <button key={o} type="button" className={`mp ${o === now ? "on" : ""} ${o === "static" ? "mid" : ""}`}
                    style={{gridColumn: c + 1, gridRow: r + 1}} title={words(o)}
                    onClick={() => onChange(o === "static" ? null : o)}>
              <span>{GLYPHS[o] || initials(o)}</span>
              <small>{o === "static" ? "hold" : words(o).replace("pan ", "").replace(" in", " in").replace(" out", " out")}</small>
            </button>
          );
        })}
      </div>
      <div className="stack sm">
        <b className="mp-read">{words(now)}</b>
        <span className="muted small" style={{maxWidth: 190}}>
          Where the camera goes while the shot runs. The middle holds it still.
        </span>
        {rest.map(o => (
          <button key={o} type="button" className={`mini ${o === now ? "on" : ""}`} onClick={() => onChange(o)}>
            {GLYPHS[o] || ""} {words(o)}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
const SAMPLE = "The snow came early this year, and the road up the hill is closed.";

/** All the voices as a gallery you listen to, grouped by language, instead of 54 codes in a drop-down. */
export function VoicePicker({value, onChange, sample, placeholder = "No voice"}: {
  value: string | null; onChange: (v: string | null) => void; sample?: string; placeholder?: string;
}) {
  const {schema, toast} = useStore();
  const [open, setOpen] = useState(false);
  const [find, setFind] = useState("");
  const [lang, setLang] = useState("");
  const [sex, setSex] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const facts = schema?.voice_facts || {};
  const langs = useMemo(() => [...new Set(Object.values(facts).map(f => f.language))].sort(), [facts]);
  const list = useMemo(() => Object.entries(facts)
    .filter(([name, f]) => (!lang || f.language === lang) && (!sex || f.gender === sex)
      && (!find || name.includes(find.toLowerCase()) || f.language.toLowerCase().includes(find.toLowerCase())))
    .sort(([, a], [, b]) => a.language.localeCompare(b.language) || a.gender.localeCompare(b.gender)),
    [facts, lang, sex, find]);
  const hear = async (name: string) => {
    setBusy(name);
    try {
      const r = await fetch("/api/voice/preview", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: (sample || "").trim() || SAMPLE, voice: name}),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      await playSound(URL.createObjectURL(await r.blob()), () => setBusy(null));
    } catch (e) { toast((e as Error).message, "err"); setBusy(null); }
  };
  const chosen = value ? facts[value] : null;
  return (
    <div className="picker">
      <button type="button" className={`picked ${value ? "" : "empty"}`} onClick={() => setOpen(o => !o)}>
        {chosen
          ? <><span className="v-tag">{chosen.short}</span><b>{chosen.person}</b>
              <span className="muted small">{chosen.gender}</span></>
          : <span className="muted">{placeholder}</span>}
        <span className="grow" />
        {value && <span className="as-icon" role="button" aria-label="Hear it"
                        onClick={e => { e.stopPropagation(); hear(value); }}>
                    {busy === value ? <Pause size={13} /> : <Volume2 size={13} />}
                  </span>}
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="picker-panel">
          <div className="row" style={{gap: 6}}>
            <div className="chip-find grow">
              <Search size={13} />
              <input autoFocus value={find} onChange={e => setFind(e.target.value)} placeholder="Find a voice" />
            </div>
            <button type="button" className={`mini ${sex === "" ? "on" : ""}`} onClick={() => setSex("")}>all</button>
            <button type="button" className={`mini ${sex === "female" ? "on" : ""}`} onClick={() => setSex("female")}>women</button>
            <button type="button" className={`mini ${sex === "male" ? "on" : ""}`} onClick={() => setSex("male")}>men</button>
          </div>
          <div className="row" style={{gap: 4, marginTop: 8}}>
            <button type="button" className={`mini ${lang === "" ? "on" : ""}`} onClick={() => setLang("")}>every language</button>
            {langs.map(l => (
              <button key={l} type="button" className={`mini ${lang === l ? "on" : ""}`} onClick={() => setLang(l)}>
                {Object.values(facts).find(f => f.language === l)?.short} {l.replace(/ English| \(Brazil\)/, "")}
              </button>
            ))}
          </div>
          <div className="v-grid">
            {placeholder && (
              <button type="button" className={`v-card ${value ? "" : "on"}`} onClick={() => { onChange(null); setOpen(false); }}>
                <b>{placeholder}</b>
              </button>
            )}
            {list.map(([name, f]) => (
              <div key={name} className={`v-card ${name === value ? "on" : ""}`}>
                <button type="button" className="v-play" title={`Hear ${f.person}`} onClick={() => hear(name)}>
                  {busy === name ? <Pause size={12} /> : <Play size={12} />}
                </button>
                <button type="button" className="v-take" onClick={() => { onChange(name); setOpen(false); }}>
                  <b>{f.person}</b>
                  <small>{f.short} &middot; {f.gender === "female" ? "woman" : "man"}</small>
                </button>
              </div>
            ))}
            {!list.length && <span className="muted small">No voice matches that.</span>}
          </div>
          <div className="row" style={{marginTop: 8}}>
            <span className="muted small grow">{list.length} of {Object.keys(facts).length} voices &middot; play to hear the line</span>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Close</Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** Library sounds you hear before you commit to one. A file path is still allowed: some beds are files. */
export function SoundPick({kind, names, value, onChange, allowFile = true}: {
  kind: "sfx" | "beds" | "footsteps"; names: string[]; value: string | null;
  onChange: (v: string | null) => void; allowFile?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [find, setFind] = useState("");
  const [path, setPath] = useState(value && !names.includes(value) ? value : "");
  const shown = find ? names.filter(n => words(n).includes(find.toLowerCase())) : names;
  const hear = (name: string) => {
    setBusy(name);
    playSound(`/api/sound/preview?kind=${kind}&name=${encodeURIComponent(name)}`, () => setBusy(null));
  };
  return (
    <div className="stack sm">
      {names.length > 8 && (
        <div className="chip-find">
          <Search size={13} />
          <input value={find} onChange={e => setFind(e.target.value)} placeholder={`Find one of ${names.length}`} />
        </div>
      )}
      <div className="sound-grid">
        <button type="button" className={`chip ${value ? "" : "on"}`} onClick={() => onChange(null)}>
          <span className="chip-ini">&mdash;</span>none
        </button>
        {shown.map(n => (
          <div key={n} className={`chip pair ${n === value ? "on" : ""}`}>
            <button type="button" className="pair-play" title={`Hear ${words(n)}`} onClick={() => hear(n)}>
              {busy === n ? <Pause size={12} /> : <Play size={12} />}
            </button>
            <button type="button" className="pair-take" onClick={() => onChange(n)}>{words(n)}</button>
          </div>
        ))}
      </div>
      {allowFile && (
        <div className="row nowrap">
          <span className="muted small">or a file</span>
          <input className="input sm grow" value={path} placeholder="sound/my_bed.wav"
                 onChange={e => setPath(e.target.value)}
                 onBlur={() => path.trim() && path !== value && onChange(path.trim())} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
export type Clip = {name: string; seconds: number | null; source: string | null; fps: number | null};
let clipCache: Clip[] | null = null;

/** The motion library, fetched once: a picker that says a clip is 16 seconds of samba before you use it. */
export function useClips() {
  const [clips, setClips] = useState<Clip[] | null>(clipCache);
  useEffect(() => {
    if (clipCache) return;
    fetch("/api/motion/clips").then(r => r.json()).then((c: Clip[]) => { clipCache = c; setClips(c); }).catch(() => setClips([]));
  }, []);
  return clips || [];
}

export function ClipPick({value, onChange}: {value: string | null; onChange: (v: string | null) => void}) {
  const clips = useClips();
  const [find, setFind] = useState("");
  const shown = find ? clips.filter(c => words(c.name).includes(find.toLowerCase())) : clips;
  if (!clips.length)
    return <p className="hint">No motion clips yet. Add some with <code>python castforge.py motion add</code>.</p>;
  return (
    <div className="stack sm">
      {clips.length > 8 && (
        <div className="chip-find">
          <Search size={13} />
          <input value={find} onChange={e => setFind(e.target.value)} placeholder={`Find one of ${clips.length}`} />
        </div>
      )}
      <div className="clip-grid">
        {shown.map(c => (
          <button key={c.name} type="button" className={`clip ${c.name === value ? "on" : ""}`} onClick={() => onChange(c.name)}>
            <Move size={14} />
            <b>{words(c.name)}</b>
            <small>{c.seconds ? `${c.seconds}s` : "length unknown"}{c.source ? ` · ${c.source}` : ""}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** Characters as faces. The thumbnail is the build's own front render, so you pick the person you can see. */
export function CastThumbs({names, value, onChange, multi, size = 56, extra}: {
  names: string[]; value: string | string[] | null; onChange: (v: Json) => void;
  multi?: boolean; size?: number; extra?: ReactNode;
}) {
  const {current} = useStore();
  const picture = (name: string) => current?.characters?.find(c => c.name === name)?.preview || null;
  const chosen = (name: string) => (multi ? Array.isArray(value) && value.includes(name) : value === name);
  const take = (name: string) => {
    if (!multi) return onChange(value === name ? null : name);
    const had = Array.isArray(value) ? value : [];
    const next = had.includes(name) ? had.filter(n => n !== name) : [...had, name];
    onChange(next.length ? next : null);
  };
  return (
    <div className="face-grid">
      {names.map((n, i) => (
        <button key={n} type="button" className={`face ${chosen(n) ? "on" : ""}`} onClick={() => take(n)} title={n}>
          {picture(n)
            ? <img src={picture(n)!} alt="" style={{width: size, height: size}} />
            : <span className="face-ini" style={{width: size, height: size, background: stageColor(i)}}>{initials(n)}</span>}
          <span className="face-name">{n}</span>
        </button>
      ))}
      {extra}
      {!names.length && <span className="muted small">No characters in this film yet.</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** Who or what someone turns to: a face, the camera, a direction, or a spot you drag on the floor. */
export function TargetPick({value, onChange, cast, directions, people, things}: {
  value: Json; onChange: (v: Json) => void; cast: string[]; directions?: string[];
  people?: Person[]; things?: Thing[];
}) {
  const spot = Array.isArray(value) ? (value as [number, number]) : null;
  const [onFloor, setOnFloor] = useState(!!spot);
  const words_ = ["camera", ...(directions || [])];
  return (
    <div className="stack sm">
      <CastThumbs names={cast} value={typeof value === "string" && cast.includes(value) ? value : null}
                  size={44} onChange={v => { setOnFloor(false); onChange(v); }}
                  extra={<>
                    {words_.map(w => (
                      <button key={w} type="button" className={`face word ${value === w ? "on" : ""}`}
                              onClick={() => { setOnFloor(false); onChange(w); }}>
                        <span className="face-ini word" style={{width: 44, height: 44}}>{GLYPHS[w] || initials(w)}</span>
                        <span className="face-name">{w}</span>
                      </button>
                    ))}
                    <button type="button" className={`face word ${onFloor ? "on" : ""}`} onClick={() => setOnFloor(o => !o)}>
                      <span className="face-ini word" style={{width: 44, height: 44}}><Crosshair size={18} /></span>
                      <span className="face-name">a spot</span>
                    </button>
                  </>} />
      {onFloor && <StagePad value={spot} onChange={onChange} people={people} things={things} height={200} />}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
/** A stick for flying the 3D view: hold a direction to swing round, and the wheel to come closer. */
export function NavPad({onOrbit, onZoom, onReset, children}: {
  onOrbit: (dx: number, dy: number) => void; onZoom: (d: number) => void;
  onReset?: (top: boolean) => void; children?: ReactNode;
}) {
  const pad = useRef<HTMLDivElement>(null);
  const held = useRef<[number, number] | null>(null);
  const timer = useRef(0);
  const run = () => {
    if (!held.current) return;
    onOrbit(held.current[0], held.current[1]);
    timer.current = requestAnimationFrame(run);
  };
  const grab = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    move(e);
    cancelAnimationFrame(timer.current);
    timer.current = requestAnimationFrame(run);
  };
  const move = (e: React.PointerEvent) => {
    const r = pad.current!.getBoundingClientRect();
    const dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2);
    const dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2);
    held.current = [clamp(dx, -1, 1), clamp(dy, -1, 1)];
  };
  const drop = () => { held.current = null; cancelAnimationFrame(timer.current); };
  useEffect(() => () => cancelAnimationFrame(timer.current), []);
  const knob = held.current;
  return (
    <div className="navpad">
      <div ref={pad} className="np-stick" onPointerDown={grab}
           onPointerMove={e => { if (e.buttons === 1) move(e); }} onPointerUp={drop} onPointerCancel={drop}
           role="application" aria-label="Swing the view">
        <span className="np-ring" />
        <span className="np-knob" style={knob ? {transform: `translate(${knob[0] * 16}px, ${knob[1] * 16}px)`} : undefined}>
          <Hand size={13} />
        </span>
      </div>
      <div className="np-side">
        <button type="button" title="Closer" onPointerDown={() => onZoom(-1)}><ZoomIn size={14} /></button>
        <button type="button" title="Further" onPointerDown={() => onZoom(1)}><ZoomOut size={14} /></button>
        {onReset && <button type="button" title="Eye level" onClick={() => onReset(false)}><Circle size={14} /></button>}
        {onReset && <button type="button" title="From above" onClick={() => onReset(true)}><Square size={14} /></button>}
      </div>
      {children}
    </div>
  );
}
