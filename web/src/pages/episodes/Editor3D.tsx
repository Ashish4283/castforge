// The 3D scene editor: see the scene, scrub or play, click a step on the timeline, drag where people start and
// walk to. Edits go straight into the open scene (Save, then Build 3D preview to see the new movement).
import {useEffect, useRef, useState} from "react";
import {Box, Camera, Hammer, Pause, Play, Save, Undo2, View} from "lucide-react";
import {Json, post} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Button, Card, Notice} from "../../components/ui";
import {Meta, SceneViewer} from "./viewer";

type Edit = {kind: "start" | "to"; who: string; n?: number; prev: Json};

export function Editor3D() {
  const {movie, toast} = useStore();
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

  const preview = ep.info?.previews?.[ep.part] || ep.info?.previews?.[0] || null;

  useEffect(() => {
    const e = () => epRef.current;
    const live = (who: string) => {
      const s = e().scene(), top = e().model?.cast?.[who];
      return (Array.isArray(e().model?.scenes) ? s?.cast?.[who] : null) || top || {};
    };
    const v = new SceneViewer(host.current!, {
      start: who => live(who).position || viewer.current?.meta?.cast?.[who]?.start || [0, 0],
      script: () => (Array.isArray(e().scene()?.script) ? e().scene().script : []),
      seat: who => live(who).sit,
      frame: (f, m) => {
        if (scrub.current) { scrub.current.max = String(m.frames); scrub.current.value = String(Math.round(f)); }
        const t = (f - 1) / m.fps, line = (m.lines || []).find(l => l.start <= t && t <= l.end);
        if (time.current) time.current.textContent = `${t.toFixed(1)} s · frame ${Math.round(f)}` + (line ? ` · ${line.who}: “${line.text}”` : "");
        if (head.current) head.current.style.left = `${(f - 1) / Math.max(1, m.frames - 1) * 100}%`;
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

  const doUndo = () => {
    const u = undo.current.pop();
    if (!u) return;
    ep.update(() => {
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
    <Card title="3D scene editor" text="Orbit with the mouse, scrub or play, click a step. Drag the discs (where people start) and rings (where they walk to)."
          actions={<div className="row nowrap">
            <Button icon={<Undo2 size={15} />} disabled={!undoCount} onClick={doUndo} title="Undo (Ctrl+Z)">Undo</Button>
            <Button icon={<Save size={15} />} disabled={!ep.dirty} onClick={save}>Save</Button>
            <Button variant="primary" icon={<Hammer size={15} />} busy={building} onClick={build} title="Builds the scene without rendering: about 20 seconds per scene">Build 3D preview</Button>
          </div>}>
      <div className="viewport" ref={host}>
        {!preview && (
          <div className="vp-empty">
            <div className="stack" style={{justifyItems: "center"}}>
              <Box size={34} />
              <b style={{color: "var(--text)"}}>No 3D preview yet</b>
              <span>Press Build 3D preview: about 20 seconds per scene, and it renders nothing.</span>
            </div>
          </div>
        )}
        {preview && (
          <div className="vp-tools">
            <Button size="sm" icon={<Camera size={14} />} onClick={() => viewer.current?.frameCamera(false)}>Front</Button>
            <Button size="sm" icon={<View size={14} />} onClick={() => viewer.current?.frameCamera(true)}>Top</Button>
          </div>
        )}
        {preview && <div className="vp-time" ref={time} />}
      </div>
      <div className="transport">
        <Button square variant="primary" icon={playing ? <Pause size={16} /> : <Play size={16} />} disabled={!meta} onClick={() => viewer.current?.toggle()} aria-label={playing ? "Pause" : "Play"} />
        <input ref={scrub} className="scrub" type="range" min={1} max={meta?.frames || 1} defaultValue={1} disabled={!meta}
               onInput={e => viewer.current?.seek(Number((e.target as HTMLInputElement).value))} aria-label="Timeline" />
      </div>
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
      {note && <div style={{marginTop: 12}}><Notice>{note}</Notice></div>}
    </Card>
  );
}
