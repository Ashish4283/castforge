// App-wide state: movies, the open movie, schema, GPU and background jobs, toasts, and the hash route.
import {createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState} from "react";
import {api, BuildingCatalog, Job, Movie, Prompts, Schema, Queued} from "../api";

export type Toast = {id: number; text: string; kind: "ok" | "err" | "info"};

interface Store {
  movies: Movie[];
  movie: string;
  current: Movie | undefined;
  setMovie: (name: string) => void;
  schema: Schema | null;
  prompts: Prompts | null;
  catalog: BuildingCatalog;
  gpu: string | null;
  queue: Queued[];
  jobs: Job[];
  reload: (keep?: string) => Promise<void>;
  toasts: Toast[];
  toast: (text: string, kind?: Toast["kind"]) => void;
  dismiss: (id: number) => void;
  route: string[];
  go: (...parts: string[]) => void;
}

const Ctx = createContext<Store | null>(null);
export const useStore = () => useContext(Ctx)!;

function readRoute() {
  return (location.hash.replace(/^#\/?/, "") || "studio").split("/").map(decodeURIComponent);
}

export function StoreProvider({children}: {children: ReactNode}) {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [movie, setMovieState] = useState<string>(() => {
    try { return localStorage.getItem("cf.movie") || ""; } catch { return ""; }
  });
  const [schema, setSchema] = useState<Schema | null>(null);
  const [prompts, setPrompts] = useState<Prompts | null>(null);
  const [catalog, setCatalog] = useState<BuildingCatalog>({templates: [], assets: []});
  const [gpu, setGpu] = useState<string | null>(null);
  const [queue, setQueue] = useState<Queued[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [route, setRoute] = useState(readRoute);
  const finished = useRef("");
  const nextId = useRef(1);

  const toast = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = nextId.current++;
    setToasts(t => [...t, {id, text, kind}]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === "err" ? 9000 : 5000);
  }, []);
  const dismiss = useCallback((id: number) => setToasts(t => t.filter(x => x.id !== id)), []);

  const setMovie = useCallback((name: string) => {
    setMovieState(name);
    try { localStorage.setItem("cf.movie", name); } catch { /* private window */ }
  }, []);

  const reload = useCallback(async (keep?: string) => {
    const [list, cat] = await Promise.all([api<Movie[]>("/api/movies"), api<BuildingCatalog>("/api/library/buildings")]);
    setMovies(list);
    setCatalog(cat);
    setMovieState(cur => {
      const want = keep || cur;
      return list.some(m => m.name === want) ? want : list[0]?.name || "";
    });
  }, []);

  useEffect(() => {
    (async () => {
      const [s, p] = await Promise.all([api<Schema>("/api/schema"), api<Prompts>("/api/prompts")]);
      setSchema(s);
      setPrompts(p);
      await reload();
    })().catch(e => toast(`Could not reach the CastForge server: ${e.message}`, "err"));
  }, [reload, toast]);

  useEffect(() => {      // GPU and background builds; a finished build refreshes the movie lists
    const tick = async () => {
      try {
        const [g, j] = await Promise.all([api<{busy: string | null; queue: Queued[]}>("/api/gpu"), api<Job[]>("/api/jobs")]);
        setGpu(g.busy);
        setQueue(g.queue || []);
        setJobs(j);
        const done = j.filter(x => x.state !== "building").map(x => `${x.id}:${x.state}`).sort().join("|");
        if (done !== finished.current) {
          if (finished.current) {
            for (const x of j.filter(x => x.state !== "building" && !finished.current.includes(`${x.id}:`)))
              toast(`${x.name}: ${x.state === "done" ? "build finished" : "build failed"}`, x.state === "done" ? "ok" : "err");
          }
          finished.current = done;
          if (done) reload();
        }
      } catch { /* server restarting */ }
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => clearInterval(t);
  }, [reload, toast]);

  useEffect(() => {
    const on = () => setRoute(readRoute());
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((...parts: string[]) => {
    location.hash = "/" + parts.map(encodeURIComponent).join("/");
  }, []);

  const current = movies.find(m => m.name === movie);
  const value = useMemo(() => ({
    movies, movie, current, setMovie, schema, prompts, catalog, gpu, queue, jobs, reload, toasts, toast, dismiss, route, go,
  }), [movies, movie, current, setMovie, schema, prompts, catalog, gpu, queue, jobs, reload, toasts, toast, dismiss, route, go]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
