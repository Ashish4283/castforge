// Which scene you are working on, and what it is set in - both as pictures, always on screen.
//
// Choosing a scene used to be a drop-down reading "Scene 2: to_the_truck", which tells you nothing about
// what is in it; and choosing a set meant scrolling to the bottom of the Stage and finding a field. Both
// are the two things you do most often in an episode, so both are here, above everything else: the scenes
// as a strip you click, and the sets as pictures you click or drag onto a scene.
import {useState} from "react";
import {Clapperboard, ImagePlus, Plus, Trash2} from "lucide-react";
import {Json} from "../../api";
import {useStore} from "../../app/store";
import {useEpisode} from "../../app/episode";
import {Badge, Button, Card, Guide} from "../../components/ui";

const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);

export function Scenes() {
  const {current, toast} = useStore();
  const ep = useEpisode();
  const [over, setOver] = useState<number | null>(null);
  const [adding, setAdding] = useState("");
  if (!ep.model) return null;
  const scenes: Json[] = Array.isArray(ep.model.scenes) ? ep.model.scenes : [];
  const made = (current?.sets || []).filter(s => s.blueprint);
  const prefix = "../".repeat(ep.depth());

  /** Put a built set under a scene: its picture, its depth and everything standing in it come with it. */
  const setOn = (i: number, name: string) => {
    const picked = made.find(s => s.name === name);
    if (!picked) return;
    ep.update(m => {
      const sc = Array.isArray(m.scenes) ? m.scenes[i] : m;
      sc.set_folder = `../sets/${picked.name}`;
      sc.background = `${prefix}${picked.path.replace(/^\.\.\/sets\//, "sets/")}`;
      if (!sc.set) sc.set = "3d";
    });
    toast(`Scene ${i + 1} is on the set ${picked.name}: its picture and its 3D come with it.`);
  };
  const add = () => {
    const id = (adding.trim().toLowerCase().replace(/[ -]+/g, "_") || `scene_${scenes.length + 1}`);
    if (!/^[a-z0-9_]+$/.test(id)) return toast("A scene name can use lowercase letters, numbers and _.", "err");
    if (scenes.some(s => s?.id === id)) return toast(`This episode already has a scene called ${id}.`, "err");
    ep.update(m => {
      if (!Array.isArray(m.scenes)) m.scenes = [isObj(m.scenes) ? m.scenes : {}];
      m.scenes.push({id, cast: {}, props: [], script: []});
    });
    setAdding("");
    ep.setPart(scenes.length);
    toast(`Scene ${scenes.length + 1} added. Put it on a set, then put someone in it.`);
  };
  const remove = (i: number) => {
    const name = scenes[i]?.id || `scene ${i + 1}`;
    ep.update(m => { m.scenes.splice(i, 1); });
    ep.setPart(Math.max(0, Math.min(i, scenes.length - 2)));
    toast(`${name} taken out of the cut. Save to keep that.`);
  };

  const setOf = (sc: Json) => {
    const folder = typeof sc?.set_folder === "string" ? sc.set_folder : null;
    return folder ? made.find(s => folder.endsWith(`/${s.name}`) || folder === s.name) || null : null;
  };

  return (
    <Card title={<span className="row nowrap" style={{gap: 7}}>Scenes <Guide topic="scenes" /></span>} bodyClass="tight"
          text="Click a scene to work on it. Click a set to put the scene in it, or drag the set onto the scene."
          actions={<Badge>{scenes.length || 1} {scenes.length === 1 ? "scene" : "scenes"}</Badge>}>
      <div className="scene-strip">
        {(scenes.length ? scenes : [ep.model]).map((sc, i) => {
          const on = setOf(sc);
          const mine = ep.part === i;
          return (
            <div key={(sc?.id || i) + String(i)}
                 className={`scene-card ${mine ? "on" : ""} ${over === i ? "over" : ""}`}
                 onClick={() => ep.setPart(i)}
                 onDragOver={e => { e.preventDefault(); setOver(i); }}
                 onDragLeave={() => setOver(null)}
                 onDrop={e => {
                   e.preventDefault();
                   setOver(null);
                   const name = e.dataTransfer.getData("text/castforge-set");
                   if (name) setOn(i, name);
                 }}>
              <div className="scene-frame">
                {on?.empty || on?.picture
                  ? <img src={(on.empty || on.picture)!} alt="" />
                  : <div className="scene-none"><ImagePlus size={16} /><span>no set yet</span></div>}
                <span className="scene-n">{i + 1}</span>
              </div>
              <div className="scene-what">
                <b>{sc?.id || "untitled"}</b>
                <span className="muted small">
                  {on ? on.name : "drop a set here"}
                  {Array.isArray(sc?.script) && sc.script.length ? ` · ${sc.script.length} steps` : ""}
                </span>
              </div>
              {scenes.length > 1 && (
                <button className="scene-kill" title={`Take ${sc?.id || "this scene"} out of the cut`}
                        onClick={e => { e.stopPropagation(); remove(i); }}>
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          );
        })}
        <div className="scene-add">
          <input className="input sm" value={adding} placeholder="new scene name"
                 onChange={e => setAdding(e.target.value)}
                 onKeyDown={e => { if (e.key === "Enter") add(); }} />
          <Button size="sm" icon={<Plus size={14} />} onClick={add}>Add scene</Button>
        </div>
      </div>
      <div className="set-shelf">
        <span className="muted small"><Clapperboard size={12} /> Sets you have built</span>
        {made.map(s => (
          <button key={s.name} className="set-chip" draggable
                  title={`Drag onto a scene, or click to put scene ${ep.part + 1} in ${s.name}`}
                  onDragStart={e => e.dataTransfer.setData("text/castforge-set", s.name)}
                  onClick={() => setOn(ep.part, s.name)}>
            <img src={(s.empty || s.picture)!} alt="" />
            <span>{s.name}</span>
          </button>
        ))}
        {!made.length && <span className="hint">No built sets yet. Make one on the Sets page: a picture becomes a 3D room.</span>}
      </div>
    </Card>
  );
}
