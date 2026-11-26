import {useEffect, useRef, useState} from "react";
import {Boxes, Building2, ChevronsLeft, ChevronsRight, ChevronsUpDown, Clapperboard, Film, Image, Layers,
  LayoutDashboard, LifeBuoy, Plus, Users, X} from "lucide-react";
import {post} from "../api";
import {useStore} from "../app/store";
import {GpuWhereLine} from "../components/GpuPicker";

export const PAGES = [
  {id: "studio", label: "Overview", icon: LayoutDashboard, group: "Produce"},
  {id: "episodes", label: "Episodes", icon: Clapperboard, group: "Produce"},
  {id: "characters", label: "Characters", icon: Users, group: "Assets"},
  {id: "sets", label: "Sets", icon: Image, group: "Assets"},
  {id: "props", label: "Props", icon: Boxes, group: "Assets"},
  {id: "library", label: "City library", icon: Building2, group: "Assets"},
  {id: "suite", label: "Suite", icon: Layers, group: "Support"},
  {id: "help", label: "Help", icon: LifeBuoy, group: "Support"},
] as const;

export function Sidebar({collapsed, onCollapse}: {collapsed: boolean; onCollapse: (v: boolean) => void}) {
  const {movies, movie, current, setMovie, reload, route, go, gpu, queue, running, building, jobs, toast} = useStore();
  const [menu, setMenu] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setMenu(false); };
    addEventListener("mousedown", close);
    return () => removeEventListener("mousedown", close);
  }, [menu]);
  const counts: Record<string, number | undefined> = {
    episodes: current?.episodes.length, characters: current?.characters.length, sets: current?.sets.length,
    props: current?.props.length,
  };
  const buildingJobs = jobs.filter(j => j.state === "building");
  const buildingNow = building;
  const newMovie = async () => {
    setMenu(false);
    const n = prompt("Movie name (letters, numbers, _):");
    if (!n) return;
    try {
      const r = await post<{movie: string}>("/api/movie/new", {name: n});
      await reload(r.movie);
      setMovie(r.movie);
      toast(`Movie ${r.movie} created`);
    } catch (e) { toast((e as Error).message, "err"); }
  };
  let group = "";
  return (
    <aside className="side">
      <div className="brand">
        <div className="mark"><Film size={16} color="#fff" /></div>
        <div className="word">CastForge <span>Studio</span></div>
        <button className="btn ghost sm icon collapse" onClick={() => onCollapse(true)} title="Collapse sidebar"><ChevronsLeft size={15} /></button>
      </div>
      <div ref={box} style={{position: "relative"}}>
        <button className="movie-switch" onClick={() => (collapsed ? onCollapse(false) : setMenu(m => !m))} title={movie}>
          <span className="ms-icon">{(movie || "?").slice(0, 2)}</span>
          <span className="ms-text"><small>Movie</small><b>{movie || "No movie"}</b></span>
          {!collapsed && <ChevronsUpDown size={14} className="muted" />}
        </button>
        {menu && (
          <div className="card" style={{position: "absolute", left: 12, right: 12, top: "calc(100% + 4px)", zIndex: 20, padding: 6}}>
            {movies.map(m => (
              <button key={m.name} className={`nav-item ${m.name === movie ? "on" : ""}`} onClick={() => { setMovie(m.name); setMenu(false); }}>
                <Film size={15} /><span className="nav-label">{m.name}</span>
                <span className="count">{m.episodes.length} ep</span>
              </button>
            ))}
            <div style={{borderTop: "1px solid var(--line)", margin: "6px 0"}} />
            <button className="nav-item" onClick={newMovie}><Plus size={15} /><span className="nav-label">New movie</span></button>
          </div>
        )}
      </div>
      <nav className="nav">
        {PAGES.map(p => {
          const head = p.group !== group ? (group = p.group) : null;
          const Icon = p.icon;
          return (
            <div key={p.id}>
              {head && <div className="nav-group-title">{head}</div>}
              <button className={`nav-item ${route[0] === p.id ? "on" : ""}`} onClick={() => go(p.id)} title={p.label}>
                <Icon size={17} />
                <span className="nav-label">{p.label}</span>
                {counts[p.id] != null && <span className="count">{counts[p.id]}</span>}
              </button>
            </div>
          );
        })}
      </nav>
      <div className="side-foot">
        {running?.alive && (
          <div className="gpu busy" title={`${running.folder}
${running.text}`}>
            <span className="spinner" style={{width: 10, height: 10}} />
            <span className="gpu-text">Rendering {running.name}: {running.text.replace(/^rendering,?\s*/i, "")}</span>
          </div>
        )}
        {!!buildingNow && (
          <div className="gpu busy" title={buildingNow}>
            <span className="spinner" style={{width: 10, height: 10}} />
            <span className="gpu-text">{buildingNow}</span>
          </div>
        )}
        {buildingJobs.length > 0 && (
          <div className="gpu busy" title={buildingJobs.map(j => `${j.name}: ${j.last || "building"}`).join("\n")}>
            <span className="spinner" style={{width: 10, height: 10}} />
            <span className="gpu-text">Building {buildingJobs.map(j => j.name).join(", ")}</span>
          </div>
        )}
        {queue.map(q => (
          <div key={q.id} className="gpu" title={`${q.name} starts on its own when the GPU is free`}>
            <span className="dot" />
            <span className="gpu-text">{q.position}. waiting: {q.name}</span>
            <button className="btn ghost sm" title="Take it out of the queue"
                    onClick={async () => {
                      try { await post("/api/gpu/cancel", {id: q.id}); toast(`${q.name} taken out of the queue`); }
                      catch (e) { toast((e as Error).message, "err"); }
                    }}><X size={13} /></button>
          </div>
        ))}
        <GpuWhereLine />
        <div className={`gpu ${gpu ? "busy" : ""}`} title={gpu ? `GPU busy: ${gpu}` : "GPU free"}>
          <span className="dot" />
          <span className="gpu-text">{gpu ? `GPU: ${gpu}` : "GPU free"}</span>
        </div>
        {collapsed && <button className="btn ghost sm" onClick={() => onCollapse(false)} title="Expand sidebar"><ChevronsRight size={15} /></button>}
      </div>
    </aside>
  );
}
