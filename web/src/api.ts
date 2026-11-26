// The CastForge server API (app/server.py). Errors come back as {"error": "plain-language message"}.

export type Json = any; // scene.json and set blueprints are free-form; the server's schema checks them

export interface ParamDef {
  type: string;
  help: string;
  required: boolean;
  default?: Json;
  values?: string[];
  // the span a number lives in, from core/schema.py RANGES: every number gets a slider, not a text box
  lo?: number;
  hi?: number;
  step?: number;
  unit?: string;
}
/** A voice name taken apart, so 54 of them can be a gallery you filter and listen to. */
export interface VoiceFacts { language: string; short: string; gender: "female" | "male"; person: string }
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
  voice_facts: Record<string, VoiceFacts>;
  expressions: string[];
  postures: string[];
  voice_fx: string[];
  seats: string[];
  weather: string[];
  look_directions: string[];
  transitions: string[];
  grades: string[];
  character: Record<string, ParamDef>;
  fix_parts: string[];
  costumes: Record<string, Record<string, string>>;
  face_groups: Record<string, string[]>;      // the designer's face sliders, by heading
  body_groups: Record<string, string[]>;      // and the body ones
  slider_range: [number, number];
  slider_targets: Record<string, {plus: string[]; minus: string[]}>;   // what each slider morphs
  head_shapes: Record<string, string>;
  library: {footsteps: string[]; sfx: string[]; beds: string[]; clips: string[]};
}
export interface Character { name: string; preview: string | null; design: boolean }
/** The render holding the lock right now: the longest job there is, and the one the app never said. */
export interface Running { folder: string; name: string; text: string; alive: boolean }
/** What an episode is holding on disk, and what each sweep would free. */
export interface Space {
  total: number; spare: number; cheap: number; dear: number;
  words: {total: string; spare: string; cheap: string; dear: string};
  kinds: {group: string; name: string; back: string; bytes: number; files: number; words: string}[];
}
export interface Queued { id: string; kind: string; name: string; movie: string | null; position: number }
export interface SetInfo {
  name: string; picture: string; path: string; blueprint: Json; asset: string | null; preview: string | null;
  empty: string | null;
}
export interface PropAsset {
  name: string; make: string; asset: string | null; preview: string | null; picture: string | null; size: number[] | null;
}
export interface Movie { name: string; characters: Character[]; episodes: string[]; sets: SetInfo[]; props: PropAsset[] }
export interface Job { id: string; name: string; movie: string; kind: string; state: string; last?: string }
export interface Prompts { scene: string; character: string; help: string }
export interface Preview { name: string; glb: string; meta: string }
/** One rendered scene, as a piece of film: where it is, how long it runs, how much is said in it. */
export interface Shot {
  name: string; video: string; id?: string; seconds?: number; lines?: number; cuts?: number;
}
export interface EpisodeInfo {
  scene: string; status: string; rendering: boolean; video: string | null;
  shots: Shot[]; storyboard: string | null;
  /** photoreal clips fetched back from the GPU, beside the episode they came from */
  real: {id: string; video: string; still: string | null}[];
  /** the graded, mastered film forgefilms cut from these scenes */
  post: {video: string; captions: string | null} | null;
  downloads: {name: string; url: string}[]; previews: Preview[];
}
export interface Step { key: string; title: string; tab: string; state: "done" | "started" | "todo"; detail: string }
export interface Progress {
  movie: string; steps: Step[]; next: Step | null;
  episodes: Record<string, {scenes: number; rendered?: number; storyboard?: boolean; film?: boolean;
    current?: boolean; broken?: boolean; missing?: string[];
    /** what this episode has actually produced */
    graded?: boolean; clips?: number}>;
}
export interface BuildingTemplate {
  id: string; title: string; description: string; category: string; category_title: string; family: string;
  footprint: number[]; floors: number; height: number; wall_color: string; roof_color: string;
}
export interface BuildingAsset {
  name: string; title: string; category: string; footprint: number[]; asset: string | null; preview: string | null;
}
export interface BuildingCatalog { templates: BuildingTemplate[]; assets: BuildingAsset[] }
/** What the last rig check found (blender/rig_check.py); null when the character has never been built. */
export interface RigReport {
  bones: number; deform: number; visemes: number; vertices: number;
  unweighted: number; over_four: number; unnormalised: number; missing: string[];
  problems: string[]; verdict: string;
}

/** One move of a screen test (blender/screen_test.py; what the numbers mean: core/screening.py). */
export interface ScreenRow {
  move: string; title: string; why: string;
  state: "works" | "rough" | "failed" | "untested";
  problems: string[];
  stretch?: number | null; rough_skin?: number | null; reach?: number | null;
  moved?: number | null; slide?: number | null;
}
/** What this body is, and how its own size and build make it move (core/gait.py). */
export interface BodyShape {
  tall: number; leg: number; hips: number; head_share: number; bulk: number; childish: number;
}
export interface WalkLike {
  speed: number; step: number; cadence: number; gap: number; swing: number;
  sway: number; bob: number; double: number; guard: number; why: string;
}
/** Is this character fit to put in a film? */
export interface ScreenReport {
  approved: boolean; line: string; passed: number; rough: number; failed: number;
  rows: ScreenRow[]; height?: number; bones?: number; shots?: string | null;
  body?: BodyShape | null; walk?: WalkLike | null;
}

/** A fabric on this machine: the GPU made the colour, the laptop derived the rest. */
export interface Fabric {
  name: string; kind: string | null; scale: number | null; seam: number | null;
  source: string | null; made: string | null; swatch: string | null;
}
/** Where heavy work can go, and what to do about the place that cannot take it. */
export interface GpuPlace { ready: boolean; why: string; how: string }
export interface GpuWhere { places: Record<string, GpuPlace>; using: string }

export interface CharacterDetail {
  name: string; design: Json; photo: string | null; face: string | null;
  previews: Partial<Record<"front" | "side" | "back", string>>; log: string[];
  rig?: RigReport | null;
  screen?: ScreenReport | null;
  clips?: Partial<Record<"turntable" | "walk", string>>;
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
