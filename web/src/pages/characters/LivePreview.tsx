// The live body beside the sliders: it changes as you drag, so nothing has to be agreed to unseen.
// It shows the SHAPE only - hair, beard, clothes and skin come from a build - and says so.
import {useEffect, useRef, useState} from "react";
import {Loader2, Maximize2, Move3d, RefreshCw} from "lucide-react";
import {api, Json, Schema} from "../../api";
import {Button, Segmented} from "../../components/ui";
import {BodyView, Kit, RING_SPIN, RING_TIP} from "./bodyview";

const get = (d: Json, key: string) => key.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), d);

/** Which morph targets a design asks for: the browser's half of core/appearance.targets_for. */
export function targetsFor(design: Json, schema: Schema): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, pair] of Object.entries(schema.slider_targets || {})) {
    const raw = Number(get(design, key) || 0);
    if (!raw) continue;
    const value = Math.max(-1, Math.min(1, raw));
    for (const name of value > 0 ? pair.plus : pair.minus) out[name] = (out[name] || 0) + Math.abs(value);
  }
  const shape = get(design, "face.head_shape") as string;
  const target = schema.head_shapes?.[shape];
  if (target) out[target] = Math.max(out[target] || 0, 1);
  return out;
}

export function LivePreview({design, schema, focus}: {design: Json; schema: Schema; focus: "whole" | "face" | "body"}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<BodyView | null>(null);
  const [state, setState] = useState<"off" | "making" | "ready" | "failed">("off");
  const [note, setNote] = useState("");
  const [rings, setRings] = useState(true);
  // the body underneath the sliders: only these three change it, so only these three fetch a new one
  const shape = [get(design, "gender") || "female", get(design, "age") || 30,
                 get(design, "build") || "average", get(design, "height_cm") || 170].join("|");

  useEffect(() => {                       // one viewer for the life of the panel
    if (!canvas.current) return;
    view.current = new BodyView(canvas.current);
    const onResize = () => view.current?.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); view.current?.dispose(); view.current = null; };
  }, []);

  useEffect(() => {                       // a different body: fetch its kit (made once, then kept)
    let dropped = false;
    (async () => {
      setState("making");
      setNote("");
      try {
        const [gender, age, build, height] = shape.split("|");
        const where = await api<{json: string; bin: string; made: boolean}>(
          `/api/character/preview-kit?gender=${gender}&age=${age}&build=${build}&height_cm=${height}`);
        const [kit, bin] = await Promise.all([
          fetch(where.json).then(r => r.json() as Promise<Kit>),
          fetch(where.bin).then(r => r.arrayBuffer()),
        ]);
        if (dropped) return;
        await view.current?.load(kit, bin);
        view.current?.apply(targetsFor(design, schema));
        view.current?.resize();
        setState("ready");
      } catch (e) {
        if (!dropped) { setState("failed"); setNote((e as Error).message); }
      }
    })();
    return () => { dropped = true; };
  }, [shape]);                            // eslint-disable-line react-hooks/exhaustive-deps

  const asked = JSON.stringify(targetsFor(design, schema));
  useEffect(() => {                       // every slider move lands here: a few hundred adds, no server
    if (state === "ready") view.current?.apply(JSON.parse(asked));
  }, [asked, state]);

  useEffect(() => { view.current?.frame(focus); }, [focus]);
  useEffect(() => { view.current?.showRings(rings); }, [rings]);

  return (
    <div className="live-preview">
      <div className="live-stage">
        <canvas ref={canvas} />
        {state !== "ready" && (
          <div className="live-cover">
            {state === "failed"
              ? <div className="stack" style={{justifyItems: "center", gap: 6, padding: 16, textAlign: "center"}}>
                  <b>The live body is not available</b>
                  <span className="muted small">{note || "it could not be made"}</span>
                  <Button variant="ghost" icon={<RefreshCw size={14} />} onClick={() => setState("off")}>Try again</Button>
                </div>
              : <div className="stack" style={{justifyItems: "center", gap: 8}}>
                  <Loader2 size={22} className="spin" />
                  <b>Shaping the body…</b>
                  <span className="muted small">about eight seconds, once per age, sex and build</span>
                </div>}
          </div>
        )}
        {state === "ready" && (
          <div className="live-hint">
            <span><i style={{background: RING_SPIN}} />turn</span>
            <span><i style={{background: RING_TIP}} />tip</span>
            <span className="muted">drag anywhere · wheel to zoom · double-click to fit</span>
          </div>
        )}
      </div>
      <div className="live-bar">
        <Segmented value="" onChange={v => view.current?.turnTo(v as "front")}
                   options={[["front", "Front"], ["three_quarter", "3/4"], ["side", "Side"], ["back", "Back"]]} />
        <span className="spacer" />
        <Button variant="ghost" icon={<Move3d size={14} />} onClick={() => setRings(r => !r)}
                title="Show or hide the rings">{rings ? "Rings on" : "Rings off"}</Button>
        <Button variant="ghost" icon={<Maximize2 size={14} />} onClick={() => view.current?.frame("whole")}>Fit</Button>
      </div>
      <p className="live-note muted small">
        The shape as it will be built. Hair, beard, clothes and skin are added by the build.
      </p>
    </div>
  );
}
