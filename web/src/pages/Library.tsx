import {useEffect, useMemo, useState} from "react";
import {Building2, Download, Hammer, PlusCircle} from "lucide-react";
import {BuildingTemplate, Json, post} from "../api";
import {useStore} from "../app/store";
import {useEpisode} from "../app/episode";
import {Badge, Button, Card, ColorField, Empty, Field, PageHead, Segmented, Select} from "../components/ui";

export function Library() {
  const {catalog, movie, toast, reload, go} = useStore();
  const ep = useEpisode();
  const categories = useMemo(() => [...new Map(catalog.templates.map(t => [t.category, t.category_title])).entries()], [catalog]);
  const [cat, setCat] = useState("");
  const [tpl, setTpl] = useState<BuildingTemplate | null>(null);
  const [f, setF] = useState<Json>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!cat && categories.length) setCat(categories[0][0]); }, [categories, cat]);
  const shown = catalog.templates.filter(t => t.category === cat);
  const choose = (t: BuildingTemplate) => {
    setTpl(t);
    setCat(t.category);
    setF({name: t.id, width: t.footprint[0], depth: t.footprint[1], floors: t.floors, height: t.height, wall_color: t.wall_color, roof_color: t.roof_color});
  };
  useEffect(() => { if (shown.length && (!tpl || tpl.category !== cat)) choose(shown[0]); });   // keep a design chosen in this category
  const build = async () => {
    if (!tpl) return;
    setBusy(true);
    try {
      const r = await post<{job: string}>("/api/library/building", {template: tpl.id, ...f});
      toast(`Building ${f.name}: it appears in your library when ready (job ${r.job}).`, "info");
      await reload(movie);
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  };
  const addToScene = (name: string, category: string) => {
    if (!ep.model) return toast("Open an episode first, then add a building.", "err");
    ep.update(m => {
      const s = ep.scene() || m;
      if (!Array.isArray(s.props)) s.props = [];
      const base = `library_${category}_${name}`;
      let id = base, k = 2;
      while (s.props.some((p: Json) => p?.id === id)) id = `${base}_${k++}`;
      s.props.push({id, file: `${"../".repeat(ep.depth() + 2)}library/${category}/${name}/${name}.blend`, position: [0, 0], rotation: 0, scale: 1});
    });
    toast(`${name} added to ${ep.ep}. Save the episode to keep it.`);
    go("episodes");
  };
  const assets = catalog.assets.filter(a => a.category === cat);
  return (
    <div className="page">
      <PageHead eyebrow="Assets" title="City library" text="Reusable buildings, streets, trees and vehicles. Build one once, then use it in any movie. These are procedural starter assets, not finished film sets." />
      <div className="stack lg">
        {categories.length > 0 && <Segmented value={cat} onChange={setCat} options={categories.map(([c, t]) => [c, t] as [string, string])} />}
        <div className="grid-2" style={{alignItems: "start"}}>
          <Card title="Starter designs" bodyClass="tight">
            <div className="item-list">
              {shown.map(t => (
                <button key={t.id} className="item" onClick={() => choose(t)}
                        style={{textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit", borderColor: tpl?.id === t.id ? "var(--accent-line)" : undefined, background: tpl?.id === t.id ? "var(--accent-soft)" : undefined}}>
                  <div className="item-body">
                    <b>{t.title}</b>
                    <div className="muted small">{t.description}</div>
                    <div className="muted small">{t.footprint.join(" × ")} m{t.family === "building" ? ` · ${t.floors} floor${t.floors === 1 ? "" : "s"}` : ` · ${t.height} m high`}</div>
                  </div>
                </button>
              ))}
              {!shown.length && <Empty icon={<Building2 />} title="No designs in this category" />}
            </div>
          </Card>
          {tpl && (
            <Card title={`Customize: ${tpl.title}`} foot={<><div className="spacer" /><Button variant="primary" icon={<Hammer size={15} />} busy={busy} onClick={build}>Build and save to library</Button></>}>
              <div className="form-grid">
                <Field label="Design"><Select value={tpl.id} onChange={id => choose(catalog.templates.find(t => t.id === id)!)} options={shown.map(t => [t.id, t.title] as [string, string])} /></Field>
                <Field label="Library name"><input className="input" maxLength={40} value={f.name || ""} onChange={e => setF({...f, name: e.target.value})} /></Field>
                <Field label="Width (m)"><input className="input" type="number" step={0.5} value={f.width} onChange={e => setF({...f, width: Number(e.target.value)})} /></Field>
                <Field label="Depth (m)"><input className="input" type="number" step={0.5} value={f.depth} onChange={e => setF({...f, depth: Number(e.target.value)})} /></Field>
                {tpl.family === "building"
                  ? <Field label="Floors"><input className="input" type="number" min={1} max={10} value={f.floors} onChange={e => setF({...f, floors: Number(e.target.value)})} /></Field>
                  : <Field label="Height (m)"><input className="input" type="number" step={0.1} value={f.height} onChange={e => setF({...f, height: Number(e.target.value)})} /></Field>}
                <Field label="Wall colour"><ColorField value={f.wall_color || "#cccccc"} onChange={v => setF({...f, wall_color: v})} /></Field>
                <Field label="Roof colour"><ColorField value={f.roof_color || "#555555"} onChange={v => setF({...f, roof_color: v})} /></Field>
              </div>
            </Card>
          )}
        </div>
        <div>
          <h3 className="section-title">My reusable assets</h3>
          {assets.length === 0 ? <Card><Empty icon={<Building2 />} title="Nothing built in this category yet" text="Choose a starter design above to make the first one." /></Card> : (
            <div className="gallery">
              {assets.map(a => (
                <div key={a.name} className="tile" style={{cursor: "default"}}>
                  <div className="thumb landscape">{a.preview ? <img src={a.preview} alt={a.name} /> : <span className="muted small">Build in progress…</span>}</div>
                  <div className="meta">
                    <b>{a.name}</b><small>{a.title} · {(a.footprint || []).join(" × ")} m</small>
                    <div className="row" style={{marginTop: 8}}>
                      {a.asset ? <a className="btn sm" href={a.asset} download><Download size={14} />.blend</a> : <Badge kind="warn">Building</Badge>}
                      <Button size="sm" icon={<PlusCircle size={14} />} disabled={!a.asset || !ep.model} onClick={() => addToScene(a.name, a.category)}>Add to scene</Button>
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
