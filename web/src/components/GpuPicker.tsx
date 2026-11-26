import {createContext, useCallback, useContext, useEffect, useState} from "react";
import {Cloud, Laptop} from "lucide-react";
import {api, GpuWhere, post} from "../api";
import {Button, Notice} from "./ui";

/** Where the heavy work runs: this laptop, or a rented GPU.
 *
 *  The choice is one setting for the whole studio - the server keeps it in `.gpu.json` and every job
 *  reads it - so it is held here once and shown in two places: a line in the sidebar that is always on
 *  screen, and the full pair of buttons wherever a GPU is about to be used. Two copies of the state
 *  would let the sidebar say "this laptop" while the panel beside it says "rented".
 */
const Ctx = createContext<{
  where: GpuWhere | null; use: (place: string) => Promise<void>; reload: () => void;
} | null>(null);

export function GpuProvider({children}: {children: React.ReactNode}) {
  const [where, setWhere] = useState<GpuWhere | null>(null);
  const reload = useCallback(() => {
    api<GpuWhere>("/api/gpu/where").then(setWhere).catch(() => { /* a panel must not go down with it */ });
  }, []);
  useEffect(() => { reload(); }, [reload]);
  const use = useCallback(async (place: string) => {
    setWhere(await post<GpuWhere>("/api/gpu/use", {place}));
  }, []);
  return <Ctx.Provider value={{where, use, reload}}>{children}</Ctx.Provider>;
}

export function useGpu() {
  const got = useContext(Ctx);
  if (!got) throw new Error("useGpu outside GpuProvider");
  return got;
}

export const PLACES = [
  {id: "local", label: "This laptop", icon: Laptop},
  {id: "kaggle", label: "Rented GPU", icon: Cloud},
] as const;

/** The two buttons, and a line about whichever is chosen. */
export function GpuPicker({onError}: {onError?: (m: string) => void}) {
  const {where, use} = useGpu();
  if (!where) return <p className="muted small"><span className="spinner" /> looking at what this machine has...</p>;
  const making = where.places[where.using];
  return (
    <>
      <div className="gpu-row">
        {PLACES.map(({id, label, icon: Icon}) => {
          const it = where.places[id];
          return (
            <Button key={id} variant={where.using === id ? "primary" : "ghost"} icon={<Icon size={14} />}
                    onClick={() => use(id).catch(e => onError?.((e as Error).message))}>
              {label}
              {it && !it.ready && <i className="gpu-no" title={it.how}>not ready</i>}
            </Button>
          );
        })}
      </div>
      {making && !making.ready && <Notice kind="warn">{making.why} — {making.how}</Notice>}
      {making && making.ready && <p className="muted small">{making.why}</p>}
    </>
  );
}

/** One line for the sidebar foot: which machine is chosen, and a click to swap it. */
export function GpuWhereLine() {
  const {where, use} = useGpu();
  if (!where) return null;
  const here = PLACES.find(p => p.id === where.using) ?? PLACES[0];
  const it = where.places[where.using];
  const Icon = here.icon;
  const rented = where.using === "kaggle";
  // A switch, not a button that swaps two words: the question people actually have is "is the rented
  // GPU on?", and leaving it on when nothing is being made is what quietly spends a session. Turning
  // it off only stops work being SENT there - the address is remembered for next time.
  return (
    <div className={`gpu gpu-where ${it && !it.ready ? "warn" : ""}`}
         title={`${it?.why ?? ""}\n${it?.how ?? ""}`}>
      <Icon size={12} />
      <span className="gpu-text">Making on: {here.label}</span>
      <label className="gpu-switch" title={rented
        ? "Turn the rented GPU off: work goes to this laptop instead. Its address is kept for next time."
        : "Turn the rented GPU on: heavy work is sent there instead of to this laptop."}>
        <input type="checkbox" checked={rented}
               onChange={e => use(e.target.checked ? "kaggle" : "local")
                 .catch(() => { /* the title says what is wrong */ })} />
        <span className="track" />
      </label>
    </div>
  );
}
