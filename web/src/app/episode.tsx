// The open episode: its live scene.json model (edited in place, then saved), the active scene part, and the
// render status polled from the server. Episodes, Props, Library and the 3D editor all edit this one model.
import {createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState} from "react";
import {api, EpisodeInfo, Json, post, q} from "../api";
import {useStore} from "./store";

interface EpisodeStore {
  ep: string | null;
  model: Json | null;
  rev: number;
  part: number;
  setPart: (i: number) => void;
  info: EpisodeInfo | null;
  dirty: boolean;
  error: string | null;
  open: (ep: string) => Promise<void>;
  update: (fn: (model: Json) => void) => void;
  replace: (model: Json, clean?: boolean) => void;
  save: () => Promise<void>;
  scene: () => Json | null;
  cast: () => Record<string, Json>;
  castEntry: (name: string) => Json;
  characterPath: (name: string) => string;
  depth: () => number;
}

const Ctx = createContext<EpisodeStore | null>(null);
export const useEpisode = () => useContext(Ctx)!;

const isObj = (v: Json) => v && typeof v === "object" && !Array.isArray(v);

export function EpisodeProvider({children}: {children: ReactNode}) {
  const {movie, current} = useStore();
  const [ep, setEp] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  const [part, setPartState] = useState(0);
  const [info, setInfo] = useState<EpisodeInfo | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const model = useRef<Json | null>(null);
  const epRef = useRef<string | null>(null);

  const scene = useCallback(() => {
    const m = model.current;
    if (!m) return null;
    return Array.isArray(m.scenes) ? m.scenes[part] ?? null : m;
  }, [part]);

  const open = useCallback(async (name: string) => {
    epRef.current = name;
    setEp(name);
    setError(null);
    try {
      const e = await api<EpisodeInfo>(`/api/episode?${q({movie, episode: name})}`);
      if (epRef.current !== name) return;
      model.current = JSON.parse(e.scene);
      setInfo(e);
      setPartState(0);
      setDirty(false);
      setRev(r => r + 1);
      try { localStorage.setItem("cf.episode." + movie, name); } catch { /* ignore */ }
    } catch (e) {
      model.current = null;
      setInfo(null);
      setError(`Could not load this episode: ${(e as Error).message}`);
      setRev(r => r + 1);
    }
  }, [movie]);

  // a new movie: open its last-used episode
  useEffect(() => {
    if (!current) return;
    if (epRef.current && current.episodes.includes(epRef.current)) return;
    let last: string | null = null;
    try { last = localStorage.getItem("cf.episode." + current.name); } catch { /* ignore */ }
    const pick = current.episodes.includes(last || "") ? last! : current.episodes[0];
    model.current = null;
    epRef.current = null;
    setEp(null);
    setInfo(null);
    if (pick) open(pick);
  }, [current, open]);

  useEffect(() => {      // render status, video and 3D previews (never the model: that is being edited)
    if (!ep) return;
    const t = setInterval(async () => {
      try {
        const e = await api<EpisodeInfo>(`/api/episode?${q({movie, episode: ep})}`);
        if (epRef.current === ep) setInfo(e);
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(t);
  }, [ep, movie]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [dirty]);

  const update = useCallback((fn: (m: Json) => void) => {
    if (!model.current) return;
    fn(model.current);
    setDirty(true);
    setRev(r => r + 1);
  }, []);
  const replace = useCallback((m: Json, clean = false) => {     // clean: the server already has this version
    model.current = m;
    setPartState(p => (Array.isArray(m.scenes) ? Math.min(p, Math.max(0, m.scenes.length - 1)) : 0));
    setDirty(!clean);
    setRev(r => r + 1);
  }, []);
  const save = useCallback(async () => {
    if (!model.current || !ep) throw new Error("Open an episode before saving.");
    await post("/api/episode/save", {movie, episode: ep, scene: JSON.stringify(model.current, null, 1)});
    setDirty(false);
  }, [ep, movie]);

  const cast = useCallback(() => {
    const m = model.current;
    const root = isObj(m?.cast) ? m.cast : {};
    const local = Array.isArray(m?.scenes) && isObj(scene()?.cast) ? scene().cast : {};
    return {...root, ...local};
  }, [scene]);
  const castEntry = useCallback((name: string) => {
    const m = model.current;
    if (Array.isArray(m.scenes)) {
      const s = scene();
      s.cast = isObj(s.cast) ? s.cast : {};
      s.cast[name] = s.cast[name] || {};
      return s.cast[name];
    }
    m.cast = m.cast || {};
    m.cast[name] = m.cast[name] || {};
    return m.cast[name];
  }, [scene]);
  const depth = useCallback(() => (ep ? ep.split("/").length : 1), [ep]);
  const characterPath = useCallback((name: string) => `${"../".repeat(depth())}characters/${name}.blend`, [depth]);

  const value = useMemo<EpisodeStore>(() => ({
    ep, model: model.current, rev, part, setPart: (i: number) => { setPartState(i); setRev(r => r + 1); },
    info, dirty, error, open, update, replace, save, scene, cast, castEntry, characterPath, depth,
  }), [ep, rev, part, info, dirty, error, open, update, replace, save, scene, cast, castEntry, characterPath, depth]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function parsePoint(value: string): [number, number] {
  const p = value.split(/[,\s]+/).filter(Boolean).map(Number);
  if (p.length !== 2 || p.some(n => !Number.isFinite(n))) throw new Error("Enter two coordinates, for example -1.2, 0.5.");
  return [p[0], p[1]];
}
