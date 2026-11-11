import {useEffect, useState} from "react";
import {Boxes, Download, Hammer, PlusCircle} from "lucide-react";
import {form, Json} from "../api";
import {useStore} from "../app/store";
import {useEpisode} from "../app/episode";
import {Badge, Button, Card, ColorField, Empty, Field, PageHead, PictureDrop, Select} from "../components/ui";

export function Props() {
  const {schema, current, movie, toast, reload, go} = useStore();
  const ep = useEpisode();
  const types = Object.entries(schema?.props || {}).filter(([n, p]) => n !== "picture_road" && p.size).map(([n]) => n);
  const [make, setMake] = useState("");
  const [name, setName] = useState("");
  const [size, setSize] = useState([0.5, 0.5, 0.5]);
  const [material, setMaterial] = useState("wood");
  const [color, setColor] = useState("#7a5230");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!make && types.length) pickType(types[0]); });
  if (!schema) return null;
  function pickType(t: string) {
    setMake(t);
    const d = schema!.props[t];
    if (d?.size) setSize([...d.size]);
    setMaterial(d?.material || schema!.materials[0]);
  }
  const build = async () => {
    if (!photo) return toast("Choose a reference image for this prop.", "err");
    setBusy(true);
    try {
      await form("/api/prop/build", {movie, name, make, width: String(size[0]), depth: String(size[1]), height: String(size[2]), material, color, photo});
      toast("Building the Blender prop: it appears below when ready.", "info");
      await reload(movie);
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };
  const addToScene = (n: string) => {
    if (!ep.model) return toast("Open an episode first, then add this prop to it.", "err");
    let id = "";
    ep.update(m => {
      const s = ep.scene() || m;
      if (!Array.isArray(s.props)) s.props = [];
      const base = n.replace(/[^a-z0-9_]/g, "_");
      let k = 2;
      id = base;
      while (s.props.some((p: Json) => p?.id === id)) id = `${base}_${k++}`;
      s.props.push({id, file: `${"../".repeat(ep.depth())}props/${n}/${n}.blend`, position: [0, 0], rotation: 0, scale: 1});
    });
    toast(`${n} added to ${ep.ep} as “${id}”. Save the episode to keep it.`);
    go("episodes");
  };
  const props = current?.props || [];
  return (
    <div className="page">
      <PageHead eyebrow="Assets" title="Props" text="Build an editable 3D object from a reference picture: choose the closest prop type and its real size. The picture stays beside the model as a reference." />
      <div className="stack lg">
        <Card title="Build a prop" foot={<><div className="spacer" /><Button variant="primary" icon={<Hammer size={15} />} busy={busy} onClick={build}>Build Blender prop</Button></>}>
          <div className="form-grid">
            <Field label="Name" required><input className="input" maxLength={40} value={name} onChange={e => setName(e.target.value)} placeholder="santa_radio" /></Field>
            <Field label="3D prop type"><Select value={make} onChange={pickType} options={types} /></Field>
            {["Width", "Depth", "Height"].map((d, k) => (
              <Field key={d} label={`${d} (m)`}><input className="input" type="number" min={0.01} max={50} step={0.05} value={size[k]}
                onChange={e => setSize(s => s.map((v, j) => (j === k ? Number(e.target.value) : v)))} /></Field>
            ))}
            <Field label="Material"><Select value={material} onChange={setMaterial} options={schema.materials} /></Field>
            <Field label="Base colour"><ColorField value={color} onChange={setColor} /></Field>
            <Field label="Reference image" required wide><PictureDrop file={photo} onFile={setPhoto} label="Prop photo" /></Field>
          </div>
        </Card>
        <div>
          <h3 className="section-title">My Blender props</h3>
          {props.length === 0 ? <Card><Empty icon={<Boxes />} title="No props yet" text="Build your first one above." /></Card> : (
            <div className="gallery">
              {props.map(p => (
                <div key={p.name} className="tile" style={{cursor: "default"}}>
                  <div className="thumb landscape contain">{p.preview ? <img src={p.preview} alt={p.name} /> : <span className="muted small">Build in progress…</span>}</div>
                  <div className="meta">
                    <b>{p.name}</b><small>{(p.make || "").replace(/_/g, " ")} · {(p.size || []).join(" × ")} m</small>
                    <div className="row" style={{marginTop: 8}}>
                      {p.asset ? <a className="btn sm" href={p.asset} download><Download size={14} />.blend</a> : <Badge kind="warn">Building</Badge>}
                      <Button size="sm" icon={<PlusCircle size={14} />} disabled={!p.asset || !ep.model} onClick={() => addToScene(p.name)}>Add to scene</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
