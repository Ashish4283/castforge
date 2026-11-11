// Small building blocks for every page (styles in styles.css).
import {ButtonHTMLAttributes, ReactNode, useEffect, useRef, useState} from "react";
import {AlertTriangle, CheckCircle2, ImagePlus, Info, X, XCircle} from "lucide-react";
import {useStore} from "../app/store";

type Btn = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger"; size?: "sm" | "lg"; icon?: ReactNode; busy?: boolean; square?: boolean;
};
export function Button({variant, size, icon, busy, square, className = "", children, disabled, ...rest}: Btn) {
  const cls = ["btn", variant, size, square && "icon", className].filter(Boolean).join(" ");
  return (
    <button type="button" className={cls} disabled={disabled || busy} {...rest}>
      {busy ? <span className="spinner" /> : icon}
      {children}
    </button>
  );
}

export function PageHead({eyebrow, title, text, actions}: {eyebrow?: ReactNode; title: ReactNode; text?: ReactNode; actions?: ReactNode}) {
  return (
    <div className="page-head">
      <div className="titles">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Card({title, text, actions, children, foot, className = "", bodyClass = ""}: {
  title?: ReactNode; text?: ReactNode; actions?: ReactNode; children?: ReactNode; foot?: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div className="grow">{title && <h2>{title}</h2>}{text && <p>{text}</p>}</div>
          {actions}
        </div>
      )}
      {children !== undefined && <div className={`card-body ${bodyClass}`}>{children}</div>}
      {foot && <div className="card-foot">{foot}</div>}
    </section>
  );
}

export function Field({label, hint, required, children, wide}: {label: ReactNode; hint?: ReactNode; required?: boolean; children: ReactNode; wide?: boolean}) {
  return (
    <div className="field" style={wide ? {gridColumn: "1 / -1"} : undefined}>
      <label>{label}{required && <span className="req">*</span>}</label>
      {children}
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Select({value, onChange, options, placeholder, className = "", ...rest}: {
  value: string; onChange: (v: string) => void; options: (string | [string, string])[]; placeholder?: string;
  className?: string; disabled?: boolean; "aria-label"?: string;
}) {
  const opts = options.map(o => (Array.isArray(o) ? o : [o, o.replace(/_/g, " ")]));
  const known = value === "" || opts.some(([v]) => v === value);
  return (
    <select className={`select ${className}`} value={value} onChange={e => onChange(e.target.value)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {!known && <option value={value}>Unrecognized: {value}</option>}
      {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

export function ColorField({value, onChange, allowEmpty}: {value: string; onChange: (v: string) => void; allowEmpty?: boolean}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const valid = /^#[0-9a-f]{6}$/i.test(value);
  return (
    <div className="color-field">
      <input type="color" value={valid ? value : "#000000"} onChange={e => onChange(e.target.value)} aria-label="colour" />
      <input className="input" value={text} placeholder={allowEmpty ? "none" : "#rrggbb"}
             onChange={e => setText(e.target.value)}
             onBlur={() => { if (text === "" && allowEmpty) onChange(""); else if (/^#?[0-9a-f]{6}$/i.test(text)) onChange("#" + text.replace("#", "").toLowerCase()); else setText(value); }} />
      {allowEmpty && value && <Button size="sm" variant="ghost" square icon={<X size={14} />} title="None" onClick={() => onChange("")} />}
    </div>
  );
}

export function Switch({checked, onChange, children}: {checked: boolean; onChange: (v: boolean) => void; children: ReactNode}) {
  return (
    <label className="switch">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span className="track" />
      {children}
    </label>
  );
}

export function Segmented<T extends string>({value, onChange, options}: {value: T; onChange: (v: T) => void; options: [T, ReactNode][]}) {
  return (
    <div className="segmented" role="tablist">
      {options.map(([v, l]) => <button key={v} type="button" className={v === value ? "on" : ""} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

export function Tabs<T extends string>({value, onChange, tabs}: {value: T; onChange: (v: T) => void; tabs: [T, ReactNode, ReactNode?][]}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([v, l, icon]) => <button key={v} type="button" className={v === value ? "on" : ""} onClick={() => onChange(v)}>{icon}{l}</button>)}
    </div>
  );
}

export function Badge({kind, children, pip}: {kind?: "ok" | "warn" | "err" | "accent"; children: ReactNode; pip?: boolean}) {
  return <span className={`badge ${kind || ""}`}>{pip && <span className="pip" />}{children}</span>;
}

export function Notice({kind, children}: {kind?: "ok" | "err" | "warn"; children: ReactNode}) {
  const Icon = kind === "ok" ? CheckCircle2 : kind === "err" ? XCircle : kind === "warn" ? AlertTriangle : Info;
  return <div className={`notice ${kind || ""}`}><Icon size={16} /><div>{children}</div></div>;
}

export function Empty({icon, title, text, action}: {icon: ReactNode; title: ReactNode; text?: ReactNode; action?: ReactNode}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export function Modal({title, text, onClose, children, foot}: {title: ReactNode; text?: ReactNode; onClose: () => void; children: ReactNode; foot?: ReactNode}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true">
        <div className="card-head">
          <div className="grow"><h2>{title}</h2>{text && <p>{text}</p>}</div>
          <Button variant="ghost" square icon={<X size={16} />} onClick={onClose} aria-label="Close" />
        </div>
        <div className="card-body">{children}</div>
        {foot && <div className="card-foot">{foot}</div>}
      </div>
    </div>
  );
}

export function Toasts() {
  const {toasts, dismiss} = useStore();
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map(t => {
        const Icon = t.kind === "ok" ? CheckCircle2 : t.kind === "err" ? XCircle : Info;
        return (
          <div key={t.id} className={`toast ${t.kind}`}>
            <Icon size={17} />
            <div className="t-text">{t.text}</div>
            <Button size="sm" variant="ghost" square icon={<X size={13} />} onClick={() => dismiss(t.id)} aria-label="Dismiss" />
          </div>
        );
      })}
    </div>
  );
}

// A picture field: choose, drop, or paste (Ctrl+V while the pointer is over it, or the Paste button).
export function PictureDrop({file, onFile, label = "Picture", hint}: {file: File | null; onFile: (f: File | null) => void; label?: string; hint?: string}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const hovered = useRef(false);
  useEffect(() => {
    if (!file) { setUrl(null); return; }
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  useEffect(() => {
    const paste = (e: ClipboardEvent) => {
      if (!hovered.current) return;
      const item = [...(e.clipboardData?.items || [])].find(i => i.kind === "file" && i.type.startsWith("image/"));
      const f = item?.getAsFile();
      if (f) { e.preventDefault(); onFile(new File([f], `pasted.${f.type === "image/jpeg" ? "jpg" : "png"}`, {type: f.type})); }
    };
    addEventListener("paste", paste);
    return () => removeEventListener("paste", paste);
  }, [onFile]);
  const fromClipboard = async () => {
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find(t => t.startsWith("image/"));
        if (type) return onFile(new File([await item.getType(type)], `pasted.${type === "image/jpeg" ? "jpg" : "png"}`, {type}));
      }
      alert("There is no picture on the clipboard. Copy an image first.");
    } catch { alert("The browser blocked reading the clipboard: point at the box and press Ctrl+V instead."); }
  };
  return (
    <div className={`drop ${over ? "over" : ""}`} tabIndex={0}
         onClick={() => input.current?.click()}
         onPointerEnter={() => (hovered.current = true)} onPointerLeave={() => (hovered.current = false)}
         onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
         onDrop={e => { e.preventDefault(); setOver(false); const f = [...e.dataTransfer.files].find(x => x.type.startsWith("image/")); if (f) onFile(f); }}>
      {url ? <img src={url} alt="" /> : <div className="d-icon"><ImagePlus size={18} /></div>}
      <div className="d-text">
        <b>{file ? file.name : label}</b>
        {hint || "Drop, paste (Ctrl+V) or click to choose"}
      </div>
      <Button size="sm" onClick={e => { e.stopPropagation(); fromClipboard(); }}>Paste</Button>
      {file && <Button size="sm" variant="ghost" square icon={<X size={14} />} onClick={e => { e.stopPropagation(); onFile(null); }} aria-label="Remove" />}
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={e => onFile(e.target.files?.[0] || null)} />
    </div>
  );
}

export async function copyText(text: string, toast: (t: string) => void, what = "Copied") {
  try { await navigator.clipboard.writeText(text); toast(`${what} to the clipboard`); }
  catch { alert(text); }
}
