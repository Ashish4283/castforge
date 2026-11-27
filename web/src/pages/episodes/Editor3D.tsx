// The 3D scene editor: see the scene, scrub or play, click a step on the timeline, drag where people start and
// walk to. Edits go straight into the open scene (Save, then Build 3D preview to see the new movement).
import {useEffect, useRef, useState} from "react";
import {Aperture, Armchair, Box, Camera, Hammer, Pause, Play, Plus, RotateCcw, Save, Trash2, Undo2,
  UserPlus, Users, View, Zap} from "lucide-react";
import {Json, post} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, Guide, Notice, Select} from "../../components/ui";
import {NavPad} from "../../components/controls";
import {ACTION_GLYPHS, GLYPHS, words} from "../../components/glyphs";
import {Actor, NewProp, PutSomeoneIn} from "./SceneSetup";
import {Cam, Meta, SceneViewer} from "./viewer";

type Edit = {kind: "start" | "to" | "prop"; who: string; n?: number; prev: Json};

// The handful you reach for while looking at the shot. Everything else, with all its settings,
// is on the Script tab - this is not a second copy of it.
const QUICK: [string, string][] = [
  ["walk", "walk to a spot on the floor"],
  ["say", "speak a line"],
  ["look", "turn head and eyes"],
  ["face", "turn the body"],
  ["gesture", "a hand or head gesture"],
  ["emote", "change the face"],
];

export function Editor3D() {
  const {movie, toast, schema} = useStore();
  const ep = useEpisode();
  const host = useRef<HTMLDivElement>(null);
  const viewer = useRef<SceneViewer | null>(null);
  const scrub = useRef<HTMLInputElement>(null);
  const time = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const undo = useRef<Edit[]>([]);
  const epRef = useRef(ep);
  epRef.current = ep;
  const [meta, setMeta] = useState<Meta | null>(null);
  const [playing, setPlaying] = useState(false);
  const [note, setNote] = useState("");
  const [sel, setSel] = useState<{who: string | null; n?: number}>({who: null});
  const [undoCount, setUndoCount] = useState(0);
  const [building, setBuilding] = useState(false);
  const [part, setPart] = useState("head");
  const [lens, setLens] = useState(false);
  const [shot, setShot] = useState<Cam | null>(null);
  const [turn, setTurn] = useState<[number, number, number]>([0, 0, 0]);
  const [hold, setHold] = useState(0.6);

  const preview = ep.info?.previews?.[ep.part] || ep.info?.previews?.[0] || null;
  const cast = ep.model ? Object.keys(ep.cast()) : [];
  const addStep = (what: string, who: string) => {
    const def = schema?.actions?.[what];
    ep.update(() => {
      const sc = ep.scene();
      if (!Array.isArray(sc.script)) sc.script = [];
      const step: Json = {do: what};
      if (def?.who) step.who = who;
      for (const [k, p_] of Object.entries(def?.params || {})) {
        if (p_ && typeof p_ === "object" && "default" in p_) step[k] = (p_ as Json).default;
      }
      sc.script.push(step);
    });
    setNote(`${who} will ${words(what)}. Set where or what on the Script tab, then Build 3D preview to watch it.`);
  };

  useEffect(() => {
    const e = () => epRef.current;
    const live = (who: string) => {
      const s = e().scene(), top = e().model?.cast?.[who];
      return (Array.isArray(e().model?.scenes) ? s?.cast?.[who] : null) || top || {};
    };
    const v = new SceneViewer(host.current!, {
      start: who => live(who).position || viewer.current?.meta?.cast?.[who]?.start || [0, 0],
      script: () => (Array.isArray(e().scene()?.script) ? e().scene().script : []),
      props: () => (Array.isArray(e().scene()?.props) ? e().scene().props : []),
      seat: who => live(who).sit,
      frame: (f, m) => {
        if (scrub.current) { scrub.current.max = String(m.frames); scrub.current.value = String(Math.round(f)); }
        const t = (f - 1) / m.fps, line = (m.lines || []).find(l => l.start <= t && t <= l.end);
        if (time.current) time.current.textContent = `${t.toFixed(1)} s · frame ${Math.round(f)}` + (line ? ` · ${line.who}: “${line.text}”` : "");
        if (head.current) head.current.style.left = `${(f - 1) / Math.max(1, m.frames - 1) * 100}%`;
        setShot(prev => {
          const now = viewer.current?.shotAt(f) || null;
          return now?.n === prev?.n ? prev : now;       // only when the cut actually changes
        });
      },
      note: setNote,
      select: (who, n) => setSel({who, n}),
      playing: setPlaying,
      drop: (kind, who, n, spot) => {
        const key = kind === "start" ? "position" : "to";
        e().update(() => {
          const target = kind === "start" ? e().castEntry(who) : e().scene().script[n!];
          undo.current.push({kind, who, n, prev: target[key]});
          target[key] = spot;
        });
        setUndoCount(undo.current.length);
        setNote(`${who} ${kind === "start" ? "now starts at" : "now walks to"} [${spot.join(", ")}]. Save, then Build 3D preview to see the new movement.`);
      },
      dropProp: (id, spot, fromSet) => {
        e().update(m => {
          const sc = e().scene();
          if (!Array.isArray(sc.props)) sc.props = [];
          let prop = sc.props.find((x: Json) => x?.id === id);
          undo.current.push({kind: "prop", who: id, prev: prop ? prop.position : undefined});
          if (!prop) { prop = {id}; sc.props.push(prop); }        // a set object: the scene moves it in place
          prop.position = spot;
          void m;
        });
        setUndoCount(undo.current.length);
        setNote(`${id} moved to [${spot.join(", ")}]${fromSet ? " (it came with the set; this scene now places it)" : ""}. Save, then Build 3D preview.`);
      },
    });
    viewer.current = v;
    (window as Json).cf3d = {loaded: () => !!v.meta, frame: () => v.frame, screenOf: (who: string) => v.screenOf(who)};
    return () => { v.dispose(); viewer.current = null; };
  }, []);

  useEffect(() => {
    const v = viewer.current;
    if (!v) return;
    v.load(preview).then(() => setMeta(v.meta)).catch(err => setNote(`Could not load the 3D preview: ${err.message}`));
  }, [preview?.glb]);      // reload only when the preview file itself changes

  useEffect(() => { viewer.current?.redraw(); }, [ep.rev]);
  useEffect(() => {              // light the editor the way the scene's mood will light the render
    const sc = ep.scene() || {};
    const look = (schema as Json)?.lights?.[sc.lighting as string] || null;
    viewer.current?.setLook(look, sc.weather);
  }, [ep.rev, schema]);
  useEffect(() => { viewer.current?.previewFix(sel.who, part, turn); }, [sel.who, part, turn]);

  const doUndo = () => {
    const u = undo.current.pop();
    if (!u) return;
    ep.update(() => {
      if (u.kind === "prop") {
        const props: Json[] = ep.scene().props || [];
        const at = props.findIndex((x: Json) => x?.id === u.who);
        if (at < 0) return;
        if (u.prev === undefined) {                 // it was only ever in the set: take the override away again
          if (Object.keys(props[at]).length <= 2) props.splice(at, 1);
          else delete props[at].position;
        } else props[at].position = u.prev;
        return;
      }
      const target = u.kind === "start" ? ep.castEntry(u.who) : ep.scene().script[u.n!];
      const key = u.kind === "start" ? "position" : "to";
      if (u.prev === undefined) delete target[key]; else target[key] = u.prev;
    });
    setUndoCount(undo.current.length);
    setNote("Undone.");
  };
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !(e.target as HTMLElement).closest("input, textarea, select") && undo.current.length) {
        e.preventDefault();
        doUndo();
      }
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  });

  const fixes: Json[] = Array.isArray(ep.model?.fixes) ? ep.model.fixes : [];
  const at = () => Math.round(((viewer.current?.frame ?? 1) - 1) / (meta?.fps || 24) * 100) / 100;
  const addFix = () => {
    if (!sel.who) return toast("Click the character you want to fix first.", "err");
    if (!turn.some(v => v)) return toast("Turn one of the three dials before adding the fix.", "err");
    ep.update(m => {
      if (!Array.isArray(m.fixes)) m.fixes = [];
      m.fixes.push({who: sel.who, part, at: at(), seconds: hold, rotate: turn.map(v => Math.round(v))});
    });
    setTurn([0, 0, 0]);
    setNote(`Fix added: ${sel.who}'s ${part.replace(/_/g, " ")} at ${at()} s. Save, then Build 3D preview (or render) to see it.`);
  };
  const removeFix = (i: number) => {
    ep.update(m => { m.fixes.splice(i, 1); if (!m.fixes.length) delete m.fixes; });
    setNote("Fix removed.");
  };

  const build = async () => {
    setBuilding(true);
    try {
      await ep.save();
      await post("/api/episode/preview3d", {movie, episode: ep.ep});
      toast("Building the 3D preview (about 20 seconds per scene)…", "info");
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBuilding(false); }
  };
  const save = async () => {
    try { await ep.save(); toast("Saved. Build 3D preview to see the new movement."); }
    catch (e) { toast((e as Error).message, "err"); }
  };
  const clickStep = (s: Meta["steps"][number]) => {
    viewer.current?.seek(s.f0);
    viewer.current?.select(s.who || null);
    setSel({who: s.who || null, n: s.n});
    const st = (ep.scene()?.script || [])[s.n] || {};
    const detail = Object.entries(st).filter(([k]) => !["who", "do"].includes(k)).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
    setNote(`Step ${s.n + 1}: ${s.who ? s.who + " " : ""}${s.do}${detail ? " (" + detail + ")" : ""}. Change its details in the Script tab.`);
  };

  const script: Json[] = Array.isArray(ep.scene()?.script) ? ep.scene().script : [];
  const lanes = meta ? [...Object.keys(meta.cast), null] : [];
  const span = meta ? Math.max(1, meta.frames - 1) : 1;
  return (
    <Card title={<span className="row nowrap" style={{gap: 7}}>3D scene editor <Guide topic="editor3d" /></span>} text="Orbit with the mouse, scrub or play, click a step. Drag the discs (where people start), rings (where they walk to) and squares (props, including the ones that came with the set)."
          actions={<div className="row nowrap">
            <Button icon={<Undo2 size={15} />} disabled={!undoCount} onClick={doUndo} title="Undo (Ctrl+Z)">Undo</Button>
            <Button icon={<Save size={15} />} disabled={!ep.dirty} onClick={save}>Save</Button>
            <Button variant="primary" icon={<Hammer size={15} />} busy={building} onClick={build} title="Builds the scene without rendering: about 20 seconds per scene">Build 3D preview</Button>
          </div>}>
      <div className="editor-split">
      <div className="editor-main">
      <div className="viewport" ref={host}>
        {!preview && (
          // A render makes the FILM. The editor needs a different, much cheaper thing - the scene as a
          // 3D file - and nothing said so, which left people pressing Render and finding an empty
          // viewport. So the button that fixes it is here, where they are looking.
          <div className="vp-empty">
            <div className="stack" style={{justifyItems: "center", gap: 10, maxWidth: 440, textAlign: "center"}}>
              <Box size={34} />
              <b style={{color: "var(--text)"}}>This scene has not been built in 3D yet</b>
              <span>
                Rendering makes the film; this makes the scene you can walk around. It takes about
                twenty seconds a scene and renders nothing, so it is cheap to redo whenever you move
                someone.
              </span>
              <Button variant="primary" icon={<Hammer size={15} />} busy={building} onClick={build}>
                Build 3D preview
              </Button>
              <span className="muted small">
                Then you can drag where people start and where they walk to, scrub the timeline, and
                look through the lens the render will use.
              </span>
            </div>
          </div>
        )}
        {preview && (
          <div className="vp-tools">
            <Button size="sm" variant={lens ? "primary" : undefined} icon={<Aperture size={14} />}
                    disabled={!meta?.cameras?.length}
                    title={meta?.cameras?.length ? "See the shot the render will see"
                                                 : "Build the 3D preview again to get the camera track"}
                    onClick={() => setLens(viewer.current?.lens(!lens) ?? false)}>
              {lens ? "Through the lens" : "Fly around"}
            </Button>
            {!lens && <Button size="sm" icon={<Camera size={14} />} onClick={() => viewer.current?.frameCamera(false)}>Front</Button>}
            {!lens && <Button size="sm" icon={<View size={14} />} onClick={() => viewer.current?.frameCamera(true)}>Top</Button>}
          </div>
        )}
        {preview && !lens && (
          <div className="vp-nav">
            <NavPad onOrbit={(x, y) => viewer.current?.orbit(x, y)} onZoom={d => viewer.current?.zoom(d)}
                    onReset={top => viewer.current?.frameCamera(top)} />
          </div>
        )}
        {preview && lens && shot && (
          <div className="vp-shot">
            <b>{words(shot.kind)}</b>
            {!!shot.on.length && <span>on {shot.on.join(" + ")}</span>}
            <span>{shot.lens} mm</span>
            {shot.move !== "static" && <span>{words(shot.move)}</span>}
          </div>
        )}
        {preview && <div className="vp-time" ref={time} />}
      </div>
      <div className="transport">
        <Button square variant="primary" icon={playing ? <Pause size={16} /> : <Play size={16} />} disabled={!meta} onClick={() => viewer.current?.toggle()} aria-label={playing ? "Pause" : "Play"} />
        <input ref={scrub} className="scrub" type="range" min={1} max={meta?.frames || 1} defaultValue={1} disabled={!meta}
               onInput={e => viewer.current?.seek(Number((e.target as HTMLInputElement).value))} aria-label="Timeline" />
      </div>
      {meta?.cameras?.length ? (
        <div className="shot-strip">
          <span className="muted small">the cut</span>
          {meta.cameras.map(c => (
            <button key={c.n} type="button" className={`shot-chip ${shot?.n === c.n ? "on" : ""}`}
                    title={`${words(c.kind)}${c.on.length ? " on " + c.on.join(" + ") : ""} · ${c.lens} mm · `
                           + `${words(c.move)} · ${((c.f0 - 1) / (meta.fps || 24)).toFixed(1)}s`}
                    onClick={() => { viewer.current?.seek(c.f0); setLens(viewer.current?.lens(true) ?? false); }}>
              <span>{GLYPHS[c.kind] || "\u{1F3A5}"}</span>
              <b>{words(c.kind)}</b>
              {!!c.on.length && <small>{c.on.join("+")}</small>}
              {c.move !== "static" && <em>{GLYPHS[c.move] || ""}</em>}
            </button>
          ))}
        </div>
      ) : null}
      {meta && (
        <div className="lanes">
          {lanes.map(w => {
            const color = w ? viewer.current?.colorOf(w) : "var(--line-2)";
            return (
              <div key={w || "scene"} className="lane">
                <span className="who" style={{color: w ? color : "var(--text-3)"}}>{w || "scene"}</span>
                <div className="track" onClick={e => {
                  if ((e.target as HTMLElement).closest(".blk")) return;
                  const r = e.currentTarget.getBoundingClientRect();
                  viewer.current?.seek(1 + (e.clientX - r.left) / r.width * (meta.frames - 1));
                }}>
                  {meta.steps.filter(s => (s.who || null) === w).map(s => {
                    const st = script[s.n] || {}, what = st.clip || st.text || st.target || st.shot || st.sfx || "";
                    return (
                      <button key={s.n} className={`blk ${sel.n === s.n ? "on" : ""}`} onClick={() => clickStep(s)}
                              style={{left: `${(s.f0 - 1) / span * 100}%`, width: `${Math.max(0.6, (s.f1 - s.f0) / span * 100)}%`, borderColor: color}}
                              title={`${s.do} ${what}`.trim() + ` · ${((s.f0 - 1) / meta.fps).toFixed(1)}–${((s.f1 - 1) / meta.fps).toFixed(1)} s`}>{s.do}</button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          <div className="heads"><div className="playhead" ref={head} /></div>
        </div>
      )}
      <div className="fixes">
        <div className="row nowrap" style={{marginBottom: 10}}>
          <h4 className="section-title" style={{margin: 0}}>Pose fixes</h4>
          <Badge>{fixes.length}</Badge>
          <span className="muted small" style={{flex: 1, minWidth: 0}}>
            For when the render gets a pose slightly wrong: click the person in the view, scrub to the
            moment, pick the body part, then turn it. <b>Nod</b> is up and down, <b>tip</b> is side to
            side, <b>turn</b> is left and right. The fix is kept in the scene and re-applied every render.
          </span>
        </div>
        <div className="row nowrap" style={{flexWrap: "wrap"}}>
          <Badge kind={sel.who ? "accent" : undefined}>{sel.who || "no one selected"}</Badge>
          <Select className="sm" value={part} onChange={setPart} options={schema?.fix_parts || ["head"]} aria-label="Body part" />
          <span className="muted small">at {at()} s</span>
          {(["x", "y", "z"] as const).map((axis, i) => (
            <label key={axis} className={`slider axis ${axis}`} style={{width: 180}}
                   title={`${axis.toUpperCase()}: ${["nod up and down", "tip side to side",
                                                     "turn left and right"][i]}`}>
              {["nod", "tip", "turn"][i]}
              <input type="range" min={-60} max={60} step={1} value={turn[i]}
                     onChange={e => setTurn(t => t.map((v, k) => (k === i ? Number(e.target.value) : v)) as [number, number, number])} />
              <span>{turn[i]}°</span>
            </label>
          ))}
          <label className="slider" style={{width: 150}}>hold
            <input type="range" min={0} max={3} step={0.1} value={hold} onChange={e => setHold(Number(e.target.value))} />
            <span>{hold.toFixed(1)}s</span>
          </label>
          <Button size="sm" variant="ghost" square icon={<RotateCcw size={14} />} aria-label="Reset dials"
                  disabled={!turn.some(v => v)} onClick={() => setTurn([0, 0, 0])} />
          <Button size="sm" variant="primary" icon={<Plus size={14} />} onClick={addFix}>Add fix</Button>
        </div>
        {fixes.length > 0 && (
          <div className="fix-list">
            {fixes.map((f, i) => (
              <div key={i} className="fix-row">
                <button className="fix-go" onClick={() => viewer.current?.seek(1 + Number(f.at || 0) * (meta?.fps || 24))}>
                  <b>{f.who}</b> {String(f.part).replace(/_/g, " ")}
                  <span className="muted"> at {f.at}s · {(f.rotate || []).join(", ")}°</span>
                </button>
                <Button size="sm" variant="ghost" square icon={<Trash2 size={14} />} aria-label="Remove fix"
                        onClick={() => removeFix(i)} />
              </div>
            ))}
          </div>
        )}
      </div>
      {note && <div style={{marginTop: 12}}><Notice>{note}</Notice></div>}
      </div>
      {/* Everything you need to put something in the scene and check it, beside the thing you are
          checking it in. Going to another tab to add a person, coming back, and losing the camera
          angle you had is not a workflow. */}
      <aside className="editor-dock">
        <section>
          <h4 className="section-title"><UserPlus size={13} /> Put someone in</h4>
          <PutSomeoneIn size={42} onAdded={who => { setSel({who}); viewer.current?.select(who); }} />
        </section>
        {!!cast.length && (
          <section>
            <h4 className="section-title"><Users size={13} /> In this scene</h4>
            <div className="row nowrap wrap" style={{gap: 5}}>
              {cast.map(who => (
                <button key={who} type="button" className={`tag ${sel.who === who ? "on" : ""}`}
                        style={{borderColor: viewer.current?.colorOf(who)}}
                        onClick={() => { setSel({who}); viewer.current?.select(who); }}>
                  <span className="dot" style={{background: viewer.current?.colorOf(who)}} />{who}
                </button>
              ))}
            </div>
          </section>
        )}
        {sel.who && (
          <section className="dock-panel">
            <Actor name={sel.who} />
          </section>
        )}
        {sel.who && (
          <section>
            <h4 className="section-title"><Zap size={13} /> Make {sel.who} do something</h4>
            <div className="dock-acts">
              {QUICK.map(([what, says]) => (
                <button key={what} type="button" className="act" title={says}
                        onClick={() => addStep(what, sel.who!)}>
                  <span className="act-glyph">{ACTION_GLYPHS[what] || "✨"}</span>
                  <b>{words(what)}</b>
                  <small>{says}</small>
                </button>
              ))}
            </div>
            <p className="hint">Added at the end of the scene. The Script tab has every action and all
              their settings; these are the ones you reach for while looking at the shot.</p>
          </section>
        )}
        <section>
          <h4 className="section-title"><Armchair size={13} /> Put a prop in</h4>
          <NewProp onMade={() => setNote("Prop added. Drag its square on the floor, or in the Stage tab.")} />
        </section>
      </aside>
      </div>
    </Card>
  );
}
