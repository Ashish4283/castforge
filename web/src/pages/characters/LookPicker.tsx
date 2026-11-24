// Picking a look by looking at it: a row of little pictures of the thing itself, not a list of names.
import {Check, Ban} from "lucide-react";
import {Json} from "../../api";

export interface Look { value: string; asset: string; thumb: string | null; mine?: string }

/** A piece someone cut themselves (core/wardrobe.py), as the studio lists them. */
export interface Piece { id: string; name: string; base: string; role: string; says?: string }

const pretty = (v: string) => v.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());

export function LookPicker({title, looks, value, none, onPick}: {
  title: string; looks: Look[]; value: Json; none?: string; onPick: (v: string | null) => void;
}) {
  const chosen = typeof value === "string" ? value : "";
  return (
    <div className="look-row">
      <div className="look-head">{title}</div>
      <div className="looks">
        {none && (
          <button type="button" className={`look ${!chosen || chosen === "none" ? "on" : ""}`}
                  onClick={() => onPick(none === "Separates" ? "casual" : "none")} title={none}>
            <span className="look-pic empty"><Ban size={18} /></span>
            <span className="look-name">{none}</span>
          </button>
        )}
        {looks.map(l => (
          <button type="button" key={l.value} className={`look ${chosen === l.value ? "on" : ""}`}
                  onClick={() => onPick(l.value)} title={l.mine ? `${l.mine} (yours)` : pretty(l.value)}>
            <span className="look-pic">
              {l.thumb ? <img src={l.thumb} alt={pretty(l.value)} loading="lazy" />
                       : <span className="look-wait">{(l.mine || pretty(l.value)).slice(0, 2)}</span>}
              {l.mine && <i className="look-mine">yours</i>}
              {chosen === l.value && <i className="look-tick"><Check size={12} /></i>}
            </span>
            <span className="look-name">{l.mine || pretty(l.value)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Swatches({title, value, swatches, onPick}: {
  title: string; value: Json; swatches: string[]; onPick: (v: string) => void;
}) {
  const chosen = typeof value === "string" ? value.toLowerCase() : "";
  return (
    <div className="look-row">
      <div className="look-head">{title}</div>
      <div className="swatches-row">
        {swatches.map(c => (
          <button type="button" key={c} className={`swatch ${chosen === c.toLowerCase() ? "on" : ""}`}
                  style={{background: c}} title={c} onClick={() => onPick(c)}>
            {chosen === c.toLowerCase() && <Check size={13} />}
          </button>
        ))}
        <label className="swatch custom" title="Any other colour">
          <input type="color" value={typeof value === "string" && value ? value : "#808080"}
                 onChange={e => onPick(e.target.value)} />
        </label>
      </div>
    </div>
  );
}
