// The CastForge server API (app/server.py). Errors come back as {"error": "plain-language message"}.

export type Json = any; // scene.json and set blueprints are free-form; the server's schema checks them

export interface ParamDef {
  type: string;
  help: string;
  required: boolean;
  default?: Json;
  values?: string[];
}
export interface ActionDef {
  help: string;
  who?: boolean;
  params: Record<string, ParamDef>;
}
export interface Schema {
  actions: Record<string, ActionDef>;
  scene: Record<string, ParamDef>;
  finish: Record<string, ParamDef>;
  props: Record<string, {size: number[] | null; material: string; blocks: boolean; help: string}>;
  materials: string[];
  voices: Record<string, string>;
  expressions: string[];
  postures: string[];
  voice_fx: string[];
  seats: string[];
  character: Record<string, ParamDef>;
  costumes: Record<string, Record<string, string>>;
  library: {footsteps: string[]; sfx: string[]; beds: string[]; clips: string[]};
}
export interface Character { name: string; preview: string | null; design: boolean }
export interface SetInfo {
  name: string; picture: string; path: string; blueprint: Json; asset: string | null; preview: string | null;
}
export interface PropAsset {
  name: string; make: string; asset: string | null; preview: string | null; picture: string | null; size: number[] | null;
}
export interface Movie { name: string; characters: Character[]; episodes: string[]; sets: SetInfo[]; props: PropAsset[] }
export interface Job { id: string; name: string; movie: string; kind: string; state: string; last?: string }
export interface Prompts { scene: string; character: string; help: string }
export interface Preview { name: string; glb: string; meta: string }
export interface EpisodeInfo {
  scene: string; status: string; rendering: boolean; video: string | null;
  shots: {name: string; video: string}[]; storyboard: string | null;
  downloads: {name: string; url: string}[]; previews: Preview[];
}
export interface Step { key: string; title: string; tab: string; state: "done" | "started" | "todo"; detail: string }
export interface Progress {
  movie: string; steps: Step[]; next: Step | null;
  episodes: Record<string, {scenes: number; rendered?: number; storyboard?: boolean; film?: boolean;
    current?: boolean; broken?: boolean; missing?: string[]}>;
}
export interface BuildingTemplate {
  id: string; title: string; description: string; category: string; category_title: string; family: string;
  footprint: number[]; floors: number; height: number; wall_color: string; roof_color: string;
}
export interface BuildingAsset {
  name: string; title: string; category: string; footprint: number[]; asset: string | null; preview: string | null;
}
export interface BuildingCatalog { templates: BuildingTemplate[]; assets: BuildingAsset[] }
export interface CharacterDetail {
  name: string; design: Json; photo: string | null; face: string | null;
  previews: Partial<Record<"front" | "side" | "back", string>>; log: string[];
}

export async function api<T = Json>(url: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j as T;
}
export const post = <T = Json>(url: string, body: Json) =>
  api<T>(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
export const form = <T = Json>(url: string, data: Record<string, string | Blob | null | undefined>) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(data)) if (v != null) f.append(k, v);
  return api<T>(url, {method: "POST", body: f});
};
export const q = (params: Record<string, string>) => new URLSearchParams(params).toString();
export const label = (key: string) => key.replace(/[._]/g, " ");
