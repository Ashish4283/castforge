// The character designer: every design key (core/schema.py CHARACTER) as a control, ready-made looks, the
// front/side/back previews, and Rebuild. Photo characters keep their face and body from the photo.
import {lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState} from "react";
import {ArrowLeft, ArrowRight, Bone, Check, ChevronRight, Clapperboard, Dumbbell, Hammer, ListChecks,
        Film, Footprints, PersonStanding, Play, Redo2, RotateCcw, Shirt, Sparkles,
        TriangleAlert, Undo2,
        UserRound, Wand2, X} from "lucide-react";
import {GpuPicker, useGpu} from "../components/GpuPicker";
import {api, CharacterDetail, Fabric, Json, label, ParamDef, post, q, RigReport,
        ScreenReport, ScreenRow} from "../api";
import {useStore} from "../app/store";
import {Badge, Button, ColorField, Field, Notice, PageHead, Segmented, Select, Switch} from "../components/ui";
// three.js is 500 kB: it loads the first time someone opens the live body, not with the app
const LivePreview = lazy(() => import("./characters/LivePreview").then(m => ({default: m.LivePreview})));
import {Look, LookPicker, Piece, Swatches} from "./characters/LookPicker";
import {STEPS} from "./characters/steps";

const SECTIONS: {title: string; text: string; keys: string[]}[] = [
  {title: "Body", text: "Who they are. Age and build shape the whole body.", keys: ["gender", "age", "height_cm", "build"]},
  {title: "Face and hair", text: "A hat hides the hair; a beard takes the hair colour. A hair style overrides the length.",
   keys: ["skin", "eyes", "hair.length", "hair.style", "hair.color", "eyebrows", "beard", "hat", "hat_size"]},
  {title: "Outfit", text: "The base clothes, coloured to your choice. A style other than casual is one whole-body outfit.",
   keys: ["outfit.style", "outfit.garment", "outfit.sleeves", "outfit.top", "outfit.bottom", "outfit.shoes"]},
  {title: "Costume", text: "Pieces over the outfit: a long coat, fur trim, a belt, gloves and boots. Leave a colour empty to leave the piece out.",
   keys: ["costume.coat", "costume.fabric", "costume.trim", "costume.belt", "costume.buckle", "costume.gloves",
          "costume.boots", "costume.cape", "costume.cape_length", "costume.armour"]},
];
const BLANK: Json = {gender: "female", age: 30, height_cm: 168, build: "average", skin: "#e0b89a", eyes: "brown",
  hair: {length: "medium", color: "#3b2a20"}, beard: "none", hat: "none",
  outfit: {garment: "trousers", sleeves: "long", top: "#40506a", bottom: "#2c2f36", shoes: "#2a2420"}};

const get = (d: Json, key: string) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), d);
function set(d: Json, key: string, value: Json) {
  const parts = key.split("."), last = parts.pop()!;
  let o = d;
  for (const p of parts) o = o[p] = o[p] && typeof o[p] === "object" ? o[p] : {};
  if (value === "" || value == null) delete o[last]; else o[last] = value;
}

export function CharacterDesigner({name}: {name: string}) {
  const {movie, schema, jobs, toast, go, reload} = useStore();
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [design, setDesign] = useState<Json>(null);
  const [saved, setSaved] = useState("");
  const [view, setView] = useState<"front" | "side" | "back">("front");
  const [stage, setStage] = useState<"live" | "built">("live");     // the shape as it is now, or the last build
  const [focus, setFocus] = useState<"whole" | "face" | "body">("whole");
  const [usePhoto, setUsePhoto] = useState(true);
  const [step, setStep] = useState(0);                              // where we are in the studio
  const [mode, setMode] = useState<"studio" | "all">("studio");     // one step at a time, or every control
  const [looks, setLooks] = useState<Record<string, Look[]> | null>(null);
  const [busy, setBusy] = useState(false);
  const wasBuilding = useRef(false);
  // Every change can be taken back. The two stacks hold whole designs as text, which is small (a few kB)
  // and cannot go stale the way a list of "what changed" can.
  const past = useRef<string[]>([]);
  const future = useRef<string[]>([]);
  const [steps, setSteps] = useState(0);            // only so the buttons know when to light up
  const [rig, setRig] = useState<RigReport | null>(null);
  const [screen, setScreen] = useState<ScreenReport | null>(null);
  const [screening, setScreening] = useState(false);
  // Short clips of the built character: a turntable, and a walk at its OWN pace (core/gait.py). The live
  // shape cannot be animated - it is a morphed mesh with no skeleton in it - so both play here.
  const [clips, setClips] = useState<Partial<Record<"turntable" | "walk", string>>>({});
  const [clipping, setClipping] = useState("");
  const [playing, setPlaying] = useState<"turntable" | "walk" | "">("");
  const [checking, setChecking] = useState(false);
  const [touching, setTouching] = useState<string | null>(null);   // the slider the hand is on
  const [pieces, setPieces] = useState<Piece[]>([]);               // what people have cut themselves

  const load = useCallback(async () => {
    if (!movie) return;        // the store has not said which movie yet: asking now only gets a 400
    try {
      const d = await api<CharacterDetail>(`/api/character?${q({movie, name})}`);
      setDetail(d);
      setRig(d.rig || null);
      setScreen(d.screen || null);        // what the last screen test found, if there was one
      setClips(d.clips || {});
      setIsNew(false);
      const start = Object.keys(d.design).length ? d.design : structuredClone(BLANK);
      setUsePhoto(start.use_photo ?? (!!d.photo && !start.costume));     // as it was last built
      setDesign(structuredClone(start));
      setSaved(JSON.stringify(start));
      past.current = []; future.current = [];        // a freshly loaded character has nothing to take back
    } catch {
      setDetail({name, design: {}, photo: null, face: null, previews: {}, log: []});
      setIsNew(true);
      setDesign(structuredClone(BLANK));
      setSaved("");
      past.current = []; future.current = [];
    }
  }, [movie, name]);
  useEffect(() => { load(); }, [load]);

  // Make sure every piece of the wardrobe has been exported, once, in one Blender session. Without this
  // the first time you try a hat or a different hair it costs five seconds of Blender starting up.
  useEffect(() => { post("/api/character/wardrobe", {}).catch(() => { /* picking still works, slower */ }); }, []);

  const loadPieces = useCallback(async () => {
    try { setPieces((await api<{pieces: Piece[]}>("/api/wardrobe")).pieces || []); } catch { /* none yet */ }
  }, []);
  useEffect(() => { loadPieces(); }, [loadPieces]);

  useEffect(() => {                   // the pictures the studio offers; taken on the first visit ever
    (async () => {
      try {
        const got = await api<Record<string, Look[]> & {taking: boolean}>("/api/character/looks");
        setLooks(got);
        const missing = Object.entries(got).some(([, v]) => Array.isArray(v) && v.some(l => !l.thumb));
        if (missing && !got.taking) {
          await post("/api/character/thumbs", {});
          setTimeout(async () => { try { setLooks(await api("/api/character/looks")); } catch { /* later */ } }, 50000);
        }
      } catch { /* the studio still works without pictures: the tiles show names */ }
    })();
  }, []);

  const here = STEPS[Math.min(step, STEPS.length - 1)];
  useEffect(() => { setStage("live"); setFocus(here.look); }, [here.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const job = jobs.find(j => j.movie === movie && j.name === name && j.state === "building");
  useEffect(() => {          // a build of this character finished: show the new previews
    if (wasBuilding.current && !job) { load(); reload(); }
    wasBuilding.current = !!job;
  }, [job, load, reload]);

  const dirty = design && JSON.stringify(design) !== saved;

  /** Every design key that differs from the last build, so you can see - and undo - exactly what changed. */
  const changed = useMemo(() => {
    if (!design || !saved) return [] as {key: string; was: Json; now: Json}[];
    const before = JSON.parse(saved);
    const flat = (d: Json, at = ""): Record<string, Json> => {
      const out: Record<string, Json> = {};
      for (const [k, v] of Object.entries((d || {}) as Record<string, Json>)) {
        const key = at ? `${at}.${k}` : k;
        if (v && typeof v === "object" && !Array.isArray(v)) Object.assign(out, flat(v, key));
        else out[key] = v;
      }
      return out;
    };
    const a = flat(before), b = flat(design);
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...keys].filter(k => JSON.stringify(a[k]) !== JSON.stringify(b[k]))
                    .sort()
                    .map(k => ({key: k, was: a[k] ?? null, now: b[k] ?? null}));
  }, [design, saved, steps]);                         // eslint-disable-line react-hooks/exhaustive-deps
  // put a whole group of sliders back to the middle: the quickest way out of a face gone wrong
  /** Make a change, remembering the design as it was so it can be taken back. */
  const edit = (make: (d: Json) => Json) => {
    setDesign((d: Json) => {
      past.current.push(JSON.stringify(d));
      if (past.current.length > 80) past.current.shift();
      future.current = [];
      return make(d);
    });
    setSteps(n => n + 1);
  };
  const undo = () => {
    const was = past.current.pop();
    if (was === undefined) return;
    setDesign((d: Json) => { future.current.push(JSON.stringify(d)); return JSON.parse(was); });
    setSteps(n => n + 1);
  };
  const redo = () => {
    const next = future.current.pop();
    if (next === undefined) return;
    setDesign((d: Json) => { past.current.push(JSON.stringify(d)); return JSON.parse(next); });
    setSteps(n => n + 1);
  };
  useEffect(() => {                                  // the shortcuts every tool has
    const keys = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      const field = (e.target as HTMLElement)?.tagName;
      if (field === "INPUT" || field === "TEXTAREA") return;          // let a text box have its own undo
      e.preventDefault();
      (e.shiftKey ? redo : undo)();
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, []);                                            // eslint-disable-line react-hooks/exhaustive-deps

  const resetGroup = (part: string, keys: string[]) =>
    edit((d: Json) => { const n = structuredClone(d); for (const k of keys) set(n, `${part}.${k}`, null); return n; });
  const groupTouched = (part: string, keys: string[]) => keys.some(k => Number(get(design, `${part}.${k}`) || 0) !== 0);
  const change = (key: string, value: Json) => edit((d: Json) => { const n = structuredClone(d); set(n, key, value); return n; });
  const applyLook = (look: Record<string, string>) => {
    edit((d: Json) => { const n = structuredClone(d); for (const [k, v] of Object.entries(look)) set(n, k, v); return n; });
    toast("Look applied: check the colours, then Rebuild.", "info");
  };
  const problems = useMemo(() => {
    if (!schema || !design) return [];
    return Object.entries(schema.character).filter(([k, d]) => d.required && (get(design, k) == null || get(design, k) === "")).map(([k]) => label(k));
  }, [schema, design]);

  const rebuild = async () => {
    setBusy(true);
    try {
      await post("/api/character/rebuild", {movie, name, design, use_photo: !!detail?.photo && usePhoto});
      setSaved(JSON.stringify(design));
      toast(`Rebuilding ${name}: about 4 minutes. The previews update when it is done.`, "info");
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };

  if (!schema || !design || !detail) return <div className="page"><PageHead title={name} eyebrow="Characters" /></div>;
  const img = detail.previews[view] || detail.previews.front;
  return (
    <div className="page">
      <PageHead
        eyebrow={<><a href="#/characters">Characters</a><ChevronRight size={12} />{isNew ? "New" : "Design"}</>}
        title={<span className="row" style={{gap: 12}}>{name}{job && <Badge kind="warn"><span className="spinner" style={{width: 9, height: 9}} />Building</Badge>}
          {isNew && <Badge kind="accent">Not built yet</Badge>}{dirty && !job && <Badge>Unsaved changes</Badge>}</span>}
        text="Change anything, then Rebuild: the character is made again with the same rig, so every scene that uses it picks up the new look."
        actions={<>
          <Button variant="ghost" icon={<Undo2 size={15} />} disabled={!past.current.length}
                  title="Take back the last change (Ctrl+Z)" onClick={undo}>Undo</Button>
          <Button variant="ghost" icon={<Redo2 size={15} />} disabled={!future.current.length}
                  title="Put it back (Ctrl+Shift+Z)" onClick={redo}>Redo</Button>
          <Button variant="ghost" icon={<RotateCcw size={15} />} disabled={!dirty} title="Put every control back to how this character was last built"
                  onClick={() => edit(() => JSON.parse(saved || JSON.stringify(BLANK)))}>Reset</Button>
          <Button variant="primary" icon={<Hammer size={15} />} busy={busy} disabled={!!job || problems.length > 0} onClick={rebuild}>{isNew ? "Build character" : "Rebuild"}</Button>
        </>} />
      <div className="designer">
        <div className="viewer card">
          <div className="stage-pick">
            <Segmented value={stage} onChange={setStage}
                       options={[["live", "Live shape"], ["built", isNew ? "Not built yet" : "Last build"]]} />
          </div>
          {stage === "live" && schema.slider_targets && (
            <Suspense fallback={<div className="live-preview"><div className="live-stage"><div className="live-cover"><span className="spinner" /></div></div></div>}>
              <LivePreview design={design} schema={schema} focus={focus} touching={touching}
                           onParts={v => change("parts", v as unknown as Json)}
                           onPiece={({role, slot}) => {
                             change(role === "hat" ? "hat" : "outfit.style", slot);
                             loadPieces();
                             toast("Saved. It is in your pieces now.");
                           }} />
            </Suspense>
          )}
          <div className="stage" style={stage === "live" ? {display: "none"} : undefined}>
            {playing && clips[playing]
              ? <video src={clips[playing]} autoPlay loop muted playsInline />
              : img ? <img src={img} alt={`${name} ${view}`} /> : <UserRound size={64} className="muted" />}
            {job && <div className="building"><div className="stack" style={{justifyItems: "center"}}><span className="spinner" style={{width: 26, height: 26, borderWidth: 3}} /><b>Building…</b><span className="muted small">{job.last || "starting"}</span></div></div>}
          </div>
          {!isNew && (
            <div className="clip-bar">
              {([["turntable", "Turn it round", <Film size={14} key="t" />],
                 ["walk", "Watch it walk", <Footprints size={14} key="w" />]] as const).map(
                ([what, label, icon]) => (
                  <Button key={what} variant={playing === what ? "primary" : "ghost"}
                          icon={icon} busy={clipping === what}
                          onClick={async () => {
                            setStage("built");
                            if (clips[what]) { setPlaying(playing === what ? "" : what); return; }
                            setClipping(what);
                            try {
                              const got = await post<{clips: Record<string, string>}>(
                                "/api/character/clips", {movie, name, what});
                              setClips(c => ({...c, ...got.clips}));
                              setPlaying(what);
                            } catch (e) { toast((e as Error).message, "err"); }
                            finally { setClipping(""); }
                          }}>{clips[what] ? label : `Make the ${what}`}</Button>
                ))}
              {playing && <Button variant="ghost" icon={<Play size={14} />}
                                  onClick={() => setPlaying("")}>Back to stills</Button>}
              <span className="muted small">
                {clipping ? "rendering - about a minute" : "the walk is cut to this body's own stride"}
              </span>
            </div>
          )}
          {stage === "built" && !playing && <div className="views"><Segmented value={view} onChange={setView} options={[["front", "Front"], ["side", "Side"], ["back", "Back"]]} /></div>}
          {detail.log.length > 0 && (
            <details style={{borderTop: "1px solid var(--line)", padding: "12px 16px"}}>
              <summary className="muted small" style={{cursor: "pointer"}}>Last build log</summary>
              <pre className="log" style={{marginTop: 10}}>{detail.log.join("\n")}</pre>
            </details>
          )}
        </div>
        <div className="card">
          <div className="studio-top">
            <Segmented value={mode} onChange={setMode}
                       options={[["studio", "Step by step"], ["all", "Everything"]]} />
          </div>
          {mode === "studio" && (
            <>
              <div className="steps-rail">
                {STEPS.map((st, i) => (
                  <button type="button" key={st.id}
                          className={`step-dot ${i === step ? "on" : ""} ${i < step ? "done" : ""}`}
                          onClick={() => setStep(i)} title={st.title}>
                    <span>{i + 1}</span><b>{st.title}</b>
                  </button>
                ))}
              </div>
              <div className="design-section">
                <h3>{here.title}</h3>
                <p>{here.text}</p>
                {here.looks?.map(row => (
                  <LookPicker key={row.key} title={row.title} none={row.none}
                              looks={[...(looks?.[row.from] || []),
                                      ...pieces.filter(p_ => p_.role === row.from)
                                               .map(p_ => ({value: `piece:${p_.id}`, asset: p_.base,
                                                            thumb: null, mine: p_.name}))]}
                              value={get(design, row.key)}
                              onPick={v => change(row.key, v)} />
                ))}
                {here.colours?.map(row => (
                  <Swatches key={row.key} title={row.title} swatches={row.swatches}
                            value={get(design, row.key)} onPick={v => change(row.key, v)} />
                ))}
                {here.keys && here.keys.length > 0 && (
                  <div className="form-grid">
                    {here.keys.filter(k => schema.character[k]).map(k => (
                      <DesignField key={k} k={k} def={schema.character[k]} value={get(design, k)}
                                   onChange={v => change(k, v)} />
                    ))}
                  </div>
                )}
                {here.scales && here.scales.length > 0 && (
                  <div className="sliders" style={{marginTop: 10}}>
                    {here.scales.filter(row => schema.character[row.key]).map(row => (
                      <SliderField key={row.key} name={row.key} label={row.title}
                                   def={schema.character[row.key]} range={row.range} middle={row.middle}
                                   value={Number(get(design, row.key) ?? row.middle)}
                                   onChange={v => change(row.key, v)} />
                    ))}
                  </div>
                )}
                {here.sliders && Object.entries(
                  (here.sliders === "face" ? schema.face_groups : schema.body_groups) || {}).map(([group, keys]) => (
                  <details key={group} className="slider-group" open={groupTouched(here.sliders!, keys)}
                           onToggle={e => { if ((e.target as HTMLDetailsElement).open) { setStage("live"); setFocus(here.look); } }}>
                    <summary>
                      <span>{group}</span>
                      {groupTouched(here.sliders!, keys) && <Badge>changed</Badge>}
                      <span className="spacer" />
                      <button className="btn ghost sm"
                              onClick={e => { e.preventDefault(); resetGroup(here.sliders!, keys); }}>Reset</button>
                    </summary>
                    <div className="sliders">
                      {keys.filter(k => schema.character[`${here.sliders}.${k}`]).map(k => (
                        <SliderField key={k} name={k} def={schema.character[`${here.sliders}.${k}`]}
                                     onTouch={on => setTouching(on ? `${here.sliders}.${k}` : null)}
                                     range={schema.slider_range || [-1, 1]}
                                     value={Number(get(design, `${here.sliders}.${k}`) || 0)}
                                     onChange={v => { setStage("live"); setFocus(here.look); change(`${here.sliders}.${k}`, v || null); }} />
                      ))}
                    </div>
                  </details>
                ))}
                {here.id === "costume" && (
                  <div style={{marginTop: 14}}>
                    <h3 style={{marginBottom: 4}}><Sparkles size={15} color="var(--accent-2)" />Ready-made looks</h3>
                    <div className="presets">
                      {Object.entries(schema.costumes).map(([id, ready]) => (
                        <button key={id} className="preset" onClick={() => applyLook(ready)}>
                          <Shirt size={16} />
                          <b style={{textTransform: "capitalize"}}>{id.replace(/_/g, " ")}</b>
                          <span className="swatches">{Object.values(ready).filter(v => /^#/.test(v)).slice(0, 5).map((c, i) => <i key={i} style={{background: c}} />)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {here.id === "costume" && (
                  <FabricPanel value={String(get(design, "costume.fabric") || "garment")}
                               toast={toast}
                               onPick={name => change("costume.fabric", name)} />
                )}
                {here.id === "build" && <RigPanel rig={rig} checking={checking} isNew={isNew}
                                                  onCheck={async (fix: boolean) => {
                                                    setChecking(true);
                                                    try {
                                                      setRig(await post<RigReport>("/api/character/rig",
                                                                                   {movie, name, fix}));
                                                      toast(fix ? "The rig is tidied." : "Rig checked.");
                                                    } catch (e) { toast((e as Error).message, "err"); }
                                                    finally { setChecking(false); }
                                                  }} />}
                {here.id === "build" && <ScreenPanel screen={screen} busy={screening} isNew={isNew}
                                                     name={name}
                                                     onRun={async (shots: boolean) => {
                                                       setScreening(true);
                                                       try {
                                                         setScreen(await post<ScreenReport>(
                                                           "/api/character/screen", {movie, name, shots}));
                                                       } catch (e) { toast((e as Error).message, "err"); }
                                                       finally { setScreening(false); }
                                                     }} />}
                {here.id === "build" && (
                  <div className="ready">
                    {problems.length > 0
                      ? <Notice kind="warn">Still needed: {problems.join(", ")}</Notice>
                      : <Notice kind="ok">Everything is set. Building takes about four minutes.</Notice>}
                    <Button variant="primary" icon={<Hammer size={15} />} busy={busy}
                            disabled={!!job || problems.length > 0} onClick={rebuild}>
                      {isNew ? "Build this character" : "Rebuild with these changes"}
                    </Button>
                  </div>
                )}
              </div>
              <div className="step-bar">
                <Button variant="ghost" icon={<ArrowLeft size={15} />} disabled={step === 0}
                        onClick={() => setStep(x => x - 1)}>Back</Button>
                <span className="muted small">{step + 1} of {STEPS.length}</span>
                <span className="spacer" />
                {step < STEPS.length - 1
                  ? <Button variant="primary" onClick={() => setStep(x => x + 1)}>Next<ArrowRight size={15} /></Button>
                  : <Button variant="ghost" icon={<ListChecks size={15} />} onClick={() => setMode("all")}>See everything</Button>}
              </div>
            </>
          )}
          {mode === "all" && <>
          <div className="design-section">
            <h3><Sparkles size={15} color="var(--accent-2)" />Ready-made looks</h3>
            <p>One click sets the costume pieces and colours; adjust anything afterwards.</p>
            <div className="presets">
              {Object.entries(schema.costumes).map(([id, look]) => (
                <button key={id} className="preset" onClick={() => applyLook(look)}>
                  <Shirt size={16} />
                  <b style={{textTransform: "capitalize"}}>{id.replace(/_/g, " ")}</b>
                  <span className="swatches">{Object.values(look).filter(v => /^#/.test(v)).slice(0, 5).map((c, i) => <i key={i} style={{background: c}} />)}</span>
                </button>
              ))}
            </div>
          </div>
          {detail.photo && (
            <div className="design-section">
              <h3><Wand2 size={15} color="var(--accent-2)" />Photo</h3>
              <div className="row nowrap" style={{alignItems: "flex-start", gap: 16}}>
                <img src={detail.photo} alt="" style={{width: 72, height: 96, objectFit: "cover", borderRadius: 8, border: "1px solid var(--line)"}} />
                <div className="stack" style={{gap: 8}}>
                  <Switch checked={usePhoto} onChange={setUsePhoto}>Use the photo for face and body</Switch>
                  <span className="hint">On: the photo shapes the face and body, the design adds everything else. Off: built from the design only (better for costumes and invented characters).</span>
                </div>
              </div>
            </div>
          )}
          {([["face", "Face shape", schema.face_groups,
              "Every feature from -1 to +1; the middle is an ordinary face. These are in addition to the photo, if there is one."],
             ["body", "Body shape", schema.body_groups,
              "The frame underneath the clothes. Height and build are up at the top; these shape the rest."]] as const).map(
            ([part, heading, groups, text]) => (
            <div key={part} className="design-section">
              <h3>{part === "face" ? <UserRound size={15} color="var(--accent-2)" /> : <Dumbbell size={15} color="var(--accent-2)" />}{heading}</h3>
              <p>{text}</p>
              {Object.entries(groups || {}).map(([group, keys]) => (
                <details key={group} className="slider-group" open={groupTouched(part, keys)}
                         onToggle={e => { if ((e.target as HTMLDetailsElement).open) { setStage("live"); setFocus(part === "face" ? "face" : "body"); } }}>
                  <summary>
                    <span>{group}</span>
                    {groupTouched(part, keys) && <Badge>changed</Badge>}
                    <span className="spacer" />
                    <button className="btn ghost sm" onClick={e => { e.preventDefault(); resetGroup(part, keys); }}>Reset</button>
                  </summary>
                  <div className="sliders">
                    {keys.filter(k => schema.character[`${part}.${k}`]).map(k => (
                      <SliderField key={k} name={k} def={schema.character[`${part}.${k}`]}
                                   onTouch={on => setTouching(on ? `${part}.${k}` : null)}
                                   range={schema.slider_range || [-1, 1]}
                                   value={Number(get(design, `${part}.${k}`) || 0)}
                                   onChange={v => { setStage("live"); setFocus(part === "face" ? "face" : "body"); change(`${part}.${k}`, v || null); }} />
                    ))}
                  </div>
                </details>
              ))}
              {part === "face" && schema.character["face.head_shape"] && (
                <div className="form-grid">
                  <DesignField k="face.head_shape" def={schema.character["face.head_shape"]}
                               value={get(design, "face.head_shape")} onChange={v => change("face.head_shape", v)} />
                </div>
              )}
            </div>
          ))}
          {SECTIONS.map(s => (
            <div key={s.title} className="design-section">
              <h3>{s.title}</h3>
              <p>{s.text}</p>
              <div className="form-grid">
                {s.keys.filter(k => schema.character[k]).map(k => (
                  <DesignField key={k} k={k} def={schema.character[k]} value={get(design, k)} onChange={v => change(k, v)} />
                ))}
              </div>
            </div>
          ))}
          </>}
          {changed.length > 0 && (
            <details className="changes" open>
              <summary>
                <span>What you have changed since the last build</span>
                <Badge kind="accent">{changed.length}</Badge>
                <span className="spacer" />
                <button className="btn ghost sm" onClick={e => { e.preventDefault(); undo(); }}
                        disabled={!past.current.length}>Undo last</button>
              </summary>
              <ul className="change-list">
                {changed.map(c => (
                  <li key={c.key}>
                    <b>{title(c.key)}</b>
                    <Swatchy value={c.was} /><span className="arrow">-&gt;</span><Swatchy value={c.now} />
                    <span className="spacer" />
                    <button className="btn ghost sm" title="Put this one back as it was built"
                            onClick={() => change(c.key, c.was)}>Put back</button>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {mode === "all" && <div className="sticky-bar">
            {problems.length > 0 ? <Notice kind="warn">Fill in: {problems.join(", ")}</Notice>
              : <span className="muted small">{job ? "Building… you can keep editing." : dirty ? "Changes are not built yet." : "Up to date with the last build."} A build takes about 4 minutes on the GPU.</span>}
            <div className="spacer" />
            <Button variant="ghost" onClick={() => go("characters")}>Back</Button>
            <Button variant="primary" icon={<Hammer size={15} />} busy={busy} disabled={!!job || problems.length > 0} onClick={rebuild}>{isNew ? "Build character" : "Rebuild"}</Button>
          </div>}
        </div>
      </div>
    </div>
  );
}

// "hair.color" -> "Hair colour", "height_cm" -> "Height (cm)", "outfit.top" -> "Top"
function title(k: string) {
  const [group, last] = k.includes(".") ? k.split(".") : ["", k];
  const words = (group === "hair" ? `hair ${last}` : last).replace("height_cm", "height (cm)").replace("color", "colour");
  return label(words).replace(/^./, c => c.toUpperCase());
}

// One feature, from one end to the other, with the middle marked. The number says where it is so a look can
// be written down and repeated; double-click the handle (or Reset above) to come back to the middle.
/** Is this character fit to animate? What the last build measured, in words, with a way to put it right.
 *
 *  The measuring is `blender/rig_check.py` and the wording `core/rigging.py`; this only shows it. */
function RigPanel({rig, checking, isNew, onCheck}: {
  rig: RigReport | null; checking: boolean; isNew: boolean; onCheck: (fix: boolean) => void;
}) {
  if (isNew) return null;
  const ok = rig && rig.problems.length === 0;
  return (
    <div className="rig-panel">
      <h3><Bone size={15} color={ok ? "var(--ok)" : "var(--accent-2)"} />The rig</h3>
      {!rig && <p className="muted small">Not looked at yet. The check takes a few seconds and needs no GPU.</p>}
      {rig && (
        <>
          <div className="rig-facts">
            <span><b>{rig.bones}</b> bones</span>
            <span><b>{rig.deform}</b> move the skin</span>
            <span><b>{rig.visemes}</b>/15 visemes</span>
            <span><b>{rig.vertices.toLocaleString()}</b> skin vertices</span>
          </div>
          {ok ? <Notice kind="ok">Ready to animate: every vertex is held by at most four bones.</Notice>
              : <Notice kind="warn">
                  <ul className="rig-problems">{rig.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
                </Notice>}
        </>
      )}
      <div className="row">
        <Button variant="ghost" busy={checking} onClick={() => onCheck(false)}>Check the rig</Button>
        {rig && rig.problems.length > 0 && (
          <Button variant="primary" busy={checking} onClick={() => onCheck(true)}>Tidy it</Button>
        )}
      </div>
    </div>
  );
}

/** The cloth a character can be dressed in, and where new cloth gets made.
 *
 *  A plain fabric - velvet, leather, cotton - is four shader numbers. A made one is a real surface
 *  with a weave in it, and the weave is what the eye reads as cloth rather than as a tinted shape.
 *  `generate/make_fabric.py` explains the split: a GPU makes one square picture and this laptop
 *  derives the relief and the roughness from it, in milliseconds, identically every time. */
function FabricPanel({value, onPick, toast}: {
  value: string; onPick: (name: string) => void; toast: (m: string, k?: "ok" | "err") => void;
}) {
  const {where} = useGpu();
  const making = where ? where.places[where.using] : null;
  const [have, setHave] = useState<Fabric[]>([]);
  const [plain, setPlain] = useState<string[]>([]);
  const [asking, setAsking] = useState("");
  const [kind, setKind] = useState("cotton");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const got = await api<{fabrics: Fabric[]; plain: string[]}>("/api/fabrics");
      setHave(got.fabrics);
      setPlain(got.plain);
    } catch { /* a missing list must not take the step down */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="rig-panel fabric-panel">
      <h3><Shirt size={15} color="var(--paint-lime)" />What the clothes are made of</h3>
      <div className="fabric-tiles">
        {plain.map(name => (
          <button key={name} type="button" className={`fabric-tile plain ${value === name ? "on" : ""}`}
                  onClick={() => onPick(name)}>
            <span className="fabric-none">{name === "garment" ? "as it comes" : name}</span>
            <b>{name}</b>
          </button>
        ))}
        {have.map(f => (
          <button key={f.name} type="button" className={`fabric-tile ${value === f.name ? "on" : ""}`}
                  onClick={() => onPick(f.name)}
                  title={`${f.kind} - seam ${f.seam?.toFixed(2)} (1.00 is perfect)`}>
            {f.swatch ? <img src={f.swatch} alt={f.name} /> : <span className="fabric-none">?</span>}
            <b>{f.name.replace(/_/g, " ")}</b>
          </button>
        ))}
      </div>

      <GpuPicker onError={m => toast(m, "err")} />

      <div className="fabric-ask">
        <input placeholder="worn indigo denim, visible twill" value={asking}
               onChange={e => setAsking(e.target.value)} />
        <Select value={kind} onChange={setKind}
                options={["denim", "knit", "velvet", "leather", "cotton", "wool", "silk", "canvas",
                          "fur"].map(k => [k, k] as [string, string])} />
        <Button variant="primary" busy={busy}
                disabled={!asking.trim() || !making?.ready}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const got = await post<{name: string}>("/api/gpu/make",
                                                           {prompt: asking, kind});
                    await load();
                    onPick(got.name);
                    toast(`${got.name} is made, and on them.`);
                    setAsking("");
                  } catch (e) { toast((e as Error).message, "err"); }
                  finally { setBusy(false); }
                }}>Make it</Button>
      </div>
      <p className="muted small">
        A square is made on the chosen machine and the weave, relief and roughness are worked out here.
        Anything with a visible join is refused rather than put on a character. A rented one takes a
        few minutes.
      </p>
    </div>
  );
}

/** The screen test: can this character do the things a scene will ask of it?
 *
 *  `core/rigging.py` asks whether the rig is sound. This asks whether the person can act - walk, run,
 *  jump, turn their head, bend, work their wrists and fingers - because finding that out in the middle
 *  of a film means rebuilding the character and re-rendering every shot it is in. */
function ScreenPanel({screen, busy, isNew, name, onRun}: {
  screen: ScreenReport | null; busy: boolean; isNew: boolean; name: string;
  onRun: (shots: boolean) => void;
}) {
  if (isNew) return null;
  const mark = (state: ScreenRow["state"]) =>
    state === "works" ? <Check size={14} color="var(--ok)" />
    : state === "rough" ? <TriangleAlert size={14} color="var(--paint-orange)" />
    : <X size={14} color="var(--err)" />;
  return (
    <div className="rig-panel screen-panel">
      <h3><Clapperboard size={15} color={screen ? (screen.approved ? "var(--ok)" : "var(--err)")
                                                : "var(--paint-yellow)"} />The screen test</h3>
      {!screen && (
        <p className="muted small">
          Every move a scene can ask for - walking, running, jumping, bending, the head, the wrists, the
          fingers - posed on this character and measured. About twenty seconds, and nothing is changed.
          An actor passes this before anybody spends a film on them.
        </p>
      )}
      {screen && <>
        <div className={`screen-verdict ${screen.approved ? "ok" : "no"}`}>
          <PersonStanding size={18} />
          <div>
            <b>{screen.approved ? `${name} is an approved actor` : `${name} is not ready`}</b>
            <span className="muted small">{screen.line}</span>
          </div>
          <span className="screen-tally">
            <i className="ok">{screen.passed}</i>
            {screen.rough > 0 && <i className="rough">{screen.rough}</i>}
            {screen.failed > 0 && <i className="no">{screen.failed}</i>}
          </span>
        </div>
        {screen.walk && screen.body && (
          <div className="move-panel">
            <h4><Footprints size={14} color="var(--paint-cyan)" />How this body moves</h4>
            <p className="muted small">{screen.walk.why}</p>
            <div className="move-facts">
              <span><b>{screen.walk.speed.toFixed(2)}</b><i>m/s walking</i></span>
              <span><b>{(screen.walk.step * 100).toFixed(0)}</b><i>cm a step</i></span>
              <span><b>{screen.walk.cadence.toFixed(2)}</b><i>steps a second</i></span>
              <span><b>{(screen.walk.gap * 200).toFixed(0)}</b><i>cm between the feet</i></span>
              <span><b>{screen.walk.sway.toFixed(2)}&times;</b><i>side-to-side roll</i></span>
              <span><b>{(screen.walk.double * 100).toFixed(0)}%</b><i>on both feet</i></span>
            </div>
            <div className="move-facts measured">
              <span><b>{screen.body.tall.toFixed(2)}</b><i>m tall</i></span>
              <span><b>{(screen.body.leg * 100).toFixed(0)}</b><i>cm of leg</i></span>
              <span><b>{screen.body.bulk.toFixed(2)}</b><i>build (1 = average)</i></span>
              <span><b>{(screen.body.head_share * 100).toFixed(0)}%</b><i>of it is head</i></span>
            </div>
            <p className="muted small">
              Measured off this body, not a stock one: speed follows the square root of leg length and the
              step follows it straight, so a small character takes shorter, busier steps instead of being
              dragged through a grown adult&apos;s stride.
            </p>
          </div>
        )}
        <ul className="screen-moves">
          {screen.rows.map(row => (
            <li key={row.move} className={row.state}>
              <span className="screen-mark">{mark(row.state)}</span>
              <span className="screen-what">
                <b>{row.title}</b>
                <em>{row.problems.length ? row.problems.join("; ") : row.why}</em>
              </span>
              <span className="screen-nums">
                {row.rough_skin != null && row.rough_skin > 0 &&
                  <i title="how much of the skin is pulled out of shape">
                    {(row.rough_skin * 100).toFixed(2)}%</i>}
                {row.slide != null && <i title="how far a planted foot drifts">
                  {(row.slide * 100).toFixed(1)} cm</i>}
              </span>
            </li>
          ))}
        </ul>
      </>}
      <div className="row">
        <Button variant="ghost" busy={busy} onClick={() => onRun(false)}>
          {screen ? "Test again" : "Run the screen test"}
        </Button>
        <Button variant="ghost" busy={busy} onClick={() => onRun(true)}>With pictures</Button>
      </div>
    </div>
  );
}

/** One value as a person reads it: a colour as a dot of that colour, an empty one as "none". */
function Swatchy({value}: {value: Json}) {
  if (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value)) {
    return <span className="swatchy"><i style={{background: value}} />{value}</span>;
  }
  if (value === null || value === undefined || value === "") return <span className="swatchy muted">none</span>;
  if (typeof value === "number") return <span className="swatchy">{Math.round(value * 100) / 100}</span>;
  if (typeof value === "object") return <span className="swatchy muted">set by hand</span>;
  return <span className="swatchy">{String(value).replace(/_/g, " ")}</span>;
}

function SliderField({name, def, range, value, onChange, middle = 0, label, onTouch}:
                     {name: string; def: ParamDef; range: readonly [number, number] | number[]; value: number;
                      onChange: (v: number) => void; middle?: number; label?: string;
                      onTouch?: (on: boolean) => void}) {
  const [lo, hi] = range as [number, number];
  // most of these sliders sit at nothing in the middle (a face is ordinary at 0); a size sits at 1, so
  // "changed" and the double-click that puts it back are both measured from wherever the middle is
  const moved = Math.abs(value - middle) > 1e-9;
  return (
    <label className={`slider-row ${moved ? "set" : ""}`} title={def.help}
           onMouseEnter={() => onTouch?.(true)} onMouseLeave={() => onTouch?.(false)}
           onFocus={() => onTouch?.(true)} onBlur={() => onTouch?.(false)}>
      <span className="slider-name">{label || title(name)}</span>
      <input type="range" min={lo} max={hi} step={0.05} value={value}
             onChange={e => onChange(Number(e.target.value))} onDoubleClick={() => onChange(middle)} />
      <span className="slider-value">
        {middle === 0 ? (moved ? (value > 0 ? "+" : "") + value.toFixed(2) : "0") : `x${value.toFixed(2)}`}
      </span>
    </label>
  );
}

function DesignField({k, def, value, onChange}: {k: string; def: ParamDef; value: Json; onChange: (v: Json) => void}) {
  const optional = !def.required && def.type === "color";
  return (
    <Field label={title(k)} hint={def.help} required={def.required}>
      {def.type === "enum" ? <Select value={value ?? def.default ?? ""} onChange={v => onChange(v || null)} options={def.values || []} />
        : def.type === "color" ? <ColorField value={value || ""} onChange={onChange} allowEmpty={optional} />
        : <input className="input" type={def.type === "number" ? "number" : "text"} value={value ?? ""}
                 onChange={e => onChange(def.type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} />}
    </Field>
  );
}
