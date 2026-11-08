const $ = s => document.querySelector(s);
let data = [], prompts = {}, formSchema = null, buildingCatalog = {templates: [], assets: []};
let activeLibraryCategory = "buildings";
let curEp = null, poll = null, sceneModel = null, activeSceneIndex = null, advancedDirty = false;

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j;
}
const post = (url, body) => api(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
const movie = () => $("#movie").value;
function msg(el, text, ok) { el.textContent = text; el.className = "msg " + (ok ? "ok" : "err"); }
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); const t = btn.textContent; btn.textContent = "Copied"; setTimeout(() => btn.textContent = t, 1500); }
  catch { alert(text); }
}

async function load(keep) {
  data = await api("/api/movies");
  buildingCatalog = await api("/api/library/buildings");
  const sel = $("#movie"), cur = keep || sel.value || (localStorage.getItem("cf.movie") || "");
  sel.innerHTML = data.map(m => `<option value="${esc(m.name)}">${esc(m.name)}</option>`).join("");
  if (data.some(m => m.name === cur)) sel.value = cur;
  render();
}
function render() {
  const m = data.find(x => x.name === movie()); if (!m) return;
  try { localStorage.setItem("cf.movie", m.name); } catch {}
  $("#chars").innerHTML = m.characters.map(c => `<div class="char">${c.preview ? `<img src="${c.preview}" alt="">` : `<div class="ph">no preview</div>`}<div class="n">${esc(c.name)}</div></div>`).join("") || `<p class="muted">No characters yet.</p>`;
  $("#eps").innerHTML = m.episodes.map(e => `<button class="b${e === curEp ? " on" : ""}" data-ep="${esc(e)}">${esc(e)}</button>`).join("") || `<p class="muted">No episodes yet.</p>`;
  renderSets(m.sets);
  renderPropAssets(m.props || []);
  renderBuildingLibrary();
}
function setBlueprint(set) {
  if (!set.blueprint || typeof set.blueprint !== "object") set.blueprint = {description: "", props: []};
  if (!Array.isArray(set.blueprint.props)) set.blueprint.props = [];
  return set.blueprint;
}
function renderSets(sets) {
  const types = Object.entries(formSchema?.props || {}).filter(([name]) => name !== "picture_road");
  const optionMarkup = (selected, items) => items.map(([value, label]) =>
    `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
  $("#sets").innerHTML = sets.map(set => {
    const blueprint = setBlueprint(set);
    const objects = blueprint.props.map((prop, index) => {
      const def = formSchema?.props?.[prop.make] || {};
      const size = prop.size || def.size || [1, 1, 1];
      const rect = prop.picture_rect;
      const doorTargets = sets.filter(candidate => candidate.name !== set.name)
        .map(candidate => [candidate.name, candidate.name]);
      const linkOptions = [["", "No linked set"], ...doorTargets];
      return `<div class="set-object" data-set-object="${index}">
        <div class="row"><input aria-label="Object id" data-set-field="id" value="${esc(prop.id || "")}" title="Unique object id">
          <select aria-label="Object type" data-set-field="make">${optionMarkup(prop.make, types.map(([name, value]) => [name, `${name.replaceAll("_", " ")}${value.size ? ` (${value.size.join(" × ")} m)` : ""}`]))}</select>
          <button class="b" type="button" data-set-action="remove">Remove</button></div>
        <div class="row"><label>Width (m)<input type="number" min="0.01" step="0.05" data-set-size="0" value="${esc(size[0])}"></label>
          <label>Depth (m)<input type="number" min="0.01" step="0.05" data-set-size="1" value="${esc(size[1])}"></label>
          <label>Height (m)<input type="number" min="0.01" step="0.05" data-set-size="2" value="${esc(size[2])}"></label></div>
        ${prop.make === "door" ? `<label>Show this set outside the door<select data-set-field="outside_set">${optionMarkup(prop.outside_set || "", linkOptions)}</select></label>` : ""}
        <div class="row"><button class="b" type="button" data-set-action="draw">${rect ? "Redraw region" : "Mark image region"}</button>
          ${rect ? `<button class="b" type="button" data-set-action="clear-region">Clear region</button>` : ""}
          <label>Rotation (°)<input type="number" step="5" data-set-field="rotation" value="${esc(prop.rotation ?? 0)}"></label></div>
        <div class="row"><label>Position X (m)<input type="number" step="0.1" data-set-position="0" value="${esc((prop.position || [0, 0])[0])}"></label>
          <label>Position Y (m)<input type="number" step="0.1" data-set-position="1" value="${esc((prop.position || [0, 0])[1])}"></label></div>
        <small class="muted">${esc(def.help || "Mark the image region to align this 3D object with the set picture.")}</small>
      </div>`;
    }).join("");
    const marks = blueprint.props.map(prop => {
      if (!Array.isArray(prop.picture_rect) || prop.picture_rect.length !== 4) return "";
      const [left, top, right, bottom] = prop.picture_rect.map(value => Math.max(0, Math.min(1, value)) * 100);
      return `<div class="set-mark" style="left:${left}%;top:${top}%;width:${right - left}%;height:${bottom - top}%"><span>${esc(prop.id || prop.make)}</span></div>`;
    }).join("");
    return `<article class="set-card" data-set-card="${esc(set.name)}">
      <div class="set-stage" data-set-stage><img src="${esc(set.picture)}" alt="${esc(set.name)} reference set"><div class="set-overlays">${marks}</div></div>
      <h3>${esc(set.name)}</h3><div class="muted"><code>${esc(set.path)}</code></div>
      <label class="field-title" for="set-description-${esc(set.name)}">Set notes (stored with this blueprint)</label>
      <input id="set-description-${esc(set.name)}" class="set-description" data-set-description maxlength="2000" value="${esc(blueprint.description || "")}" placeholder="Optional notes; these do not change the generated geometry">
      <div class="editor-list">${objects || `<p class="muted">No 3D details marked yet. Add one, then mark the matching area in the image.</p>`}</div>
      <div class="row"><select data-set-new-type aria-label="New 3D object type">${optionMarkup(types[0]?.[0], types.map(([name]) => [name, name.replaceAll("_", " ")]))}</select>
        <button class="b" type="button" data-set-action="add">Add set detail</button></div>
      <div class="row set-actions"><button class="b" type="button" data-set-action="save">Save details</button>
        <button class="b p" type="button" data-set-action="build">Build 3D set</button>
        ${set.asset ? `<a class="b" href="${esc(set.asset)}" download>Download .blend</a>` : ""}</div>
      ${set.preview ? `<figure class="set-preview"><img src="${esc(set.preview)}" alt="${esc(set.name)} 3D build preview"><figcaption class="muted">Generated 3D preview</figcaption></figure>` : ""}
      <p class="muted set-hint" data-set-status>${set.asset ? `3D asset ready: <a href="${esc(set.asset)}" download>Download set.blend</a>` : "The build creates a reusable asset and leaves your movie scenes unchanged."}</p>
    </article>`;
  }).join("") || `<p class="muted">No sets yet. Add a background image under <code>movies/&lt;movie&gt;/sets/&lt;set&gt;/</code> to start.</p>`;
}
function renderPropAssets(props) {
  $("#propAssets").innerHTML = props.map(prop => `<article class="set-card">
    ${prop.preview ? `<img src="${esc(prop.preview)}" alt="${esc(prop.name)} Blender preview">` :
      `<div class="ph">No preview yet</div>`}
    <h3>${esc(prop.name)}</h3>
    <div class="muted">${esc((prop.make || "").replaceAll("_", " "))} · ${esc((prop.size || []).join(" × "))} m</div>
    ${prop.picture ? `<details style="margin-top:8px"><summary>Reference image</summary><img src="${esc(prop.picture)}" alt="${esc(prop.name)} reference"></details>` : ""}
    <div class="row set-actions">
      ${prop.asset ? `<a class="b" href="${esc(prop.asset)}" download>Download .blend</a>` : `<span class="muted">Build in progress…</span>`}
      <button class="b" type="button" data-add-prop-asset="${esc(prop.name)}"${!sceneModel ? " disabled" : ""}>Add to open scene</button>
    </div>
  </article>`).join("") || `<p class="muted">No prop assets yet. Upload a reference image above to build your first one.</p>`;
}
function renderBuildingLibrary() {
  const templates = buildingCatalog.templates || [];
  const categories = [...new Map(templates.map(template =>
    [template.category, template.category_title])).entries()];
  if (!categories.some(([category]) => category === activeLibraryCategory)) {
    activeLibraryCategory = categories[0]?.[0] || "";
  }
  $("#libraryCategories").innerHTML = categories.map(([category, title]) =>
    `<button class="b${category === activeLibraryCategory ? " p" : ""}" type="button" data-library-category="${esc(category)}">${esc(title)}</button>`).join("");
  const visibleTemplates = templates.filter(template => template.category === activeLibraryCategory);
  const current = templates.find(template => template.id === $("#buildingTemplate").value);
  const selected = current?.category === activeLibraryCategory ? current.id : visibleTemplates[0]?.id || "";
  $("#buildingTemplate").innerHTML = visibleTemplates.map(template =>
    `<option value="${esc(template.id)}">${esc(template.title)}</option>`).join("");
  if (visibleTemplates.some(template => template.id === selected)) $("#buildingTemplate").value = selected;
  if (selected && (!current || current.category !== activeLibraryCategory || !$("#buildingName").value)) {
    setBuildingTemplate(selected);
  }
  $("#buildingTemplates").innerHTML = visibleTemplates.map(template => `<article class="set-card">
    <h3>${esc(template.title)}</h3>
    <p class="muted">${esc(template.description)}</p>
    <p class="muted">Starter size ${esc(template.footprint.join(" × "))} m${template.family === "building" ? ` · ${esc(template.floors)} floor${template.floors === 1 ? "" : "s"}` : ` · ${esc(template.height)} m high`}</p>
    <button class="b" type="button" data-select-building="${esc(template.id)}">Customize this design</button>
  </article>`).join("") || `<p class="muted">No starter designs are available in this category.</p>`;
  const visibleAssets = (buildingCatalog.assets || []).filter(asset => asset.category === activeLibraryCategory);
  $("#buildingAssets").innerHTML = visibleAssets.map(asset => `<article class="set-card">
    ${asset.preview ? `<img src="${esc(asset.preview)}" alt="${esc(asset.name)} building preview">` :
      `<div class="ph">Build in progress…</div>`}
    <h3>${esc(asset.name)}</h3>
    <p class="muted">${esc(asset.title)} · ${esc((asset.footprint || []).join(" × "))} m</p>
    <div class="row set-actions">
      ${asset.asset ? `<a class="b" href="${esc(asset.asset)}" download>Download .blend</a>` : ""}
      <button class="b" type="button" data-add-building="${esc(asset.name)}" data-add-building-category="${esc(asset.category)}"${!sceneModel || !asset.asset ? " disabled" : ""}>Add to open scene</button>
    </div>
  </article>`).join("") || `<p class="muted">Your shared building library is empty. Choose a starter design above to create the first asset.</p>`;
}
function setBuildingTemplate(id) {
  const template = buildingCatalog.templates.find(item => item.id === id);
  if (!template) return;
  activeLibraryCategory = template.category;
  $("#buildingTemplate").value = id;
  $("#buildingName").value = id;
  $("#buildingWidth").value = template.footprint[0];
  $("#buildingDepth").value = template.footprint[1];
  $("#buildingFloors").value = template.floors;
  $("#buildingHeight").value = template.height;
  $("#buildingFloorsField").classList.toggle("hidden", template.family !== "building");
  $("#buildingHeightField").classList.toggle("hidden", template.family === "building");
  $("#buildingWallColor").value = template.wall_color;
  $("#buildingRoofColor").value = template.roof_color;
}
async function buildLibraryBuilding() {
  const button = $("#buildLibraryBuilding");
  button.disabled = true;
  try {
    const result = await post("/api/library/building", {
      template: $("#buildingTemplate").value,
      name: $("#buildingName").value,
      width: Number($("#buildingWidth").value),
      depth: Number($("#buildingDepth").value),
      floors: Number($("#buildingFloors").value),
      height: Number($("#buildingHeight").value),
      wall_color: $("#buildingWallColor").value,
      roof_color: $("#buildingRoofColor").value,
    });
    msg($("#libraryMsg"), `Asset build started (job ${result.job}). It will appear in your shared library when ready.`, true);
    await load(movie());
  } catch (error) {
    msg($("#libraryMsg"), error.message);
  } finally {
    button.disabled = false;
  }
}
function addBuildingAssetToScene(name, category) {
  if (!sceneModel) {
    msg($("#libraryMsg"), "Open an episode scene first, then add a building.");
    return;
  }
  const part = activeScene();
  if (!part) {
    msg($("#libraryMsg"), "The current episode has no active scene.");
    return;
  }
  if (part.props == null) part.props = [];
  if (!Array.isArray(part.props)) {
    msg($("#libraryMsg"), "The current scene's props field must be a list before adding a building.");
    return;
  }
  const asset = buildingCatalog.assets.find(item => item.name === name && item.category === category);
  if (!asset?.asset) {
    msg($("#libraryMsg"), `The Blender asset for ${name} is not ready yet.`);
    return;
  }
  const baseId = `library_${category}_${name}`;
  let id = baseId, index = 2;
  while (part.props.some(item => item?.id === id)) id = `${baseId}_${index++}`;
  const sceneDepth = curEp?.split("/").length || 1;
  const file = `${"../".repeat(sceneDepth + 2)}library/${asset.category}/${name}/${name}.blend`;
  part.props.push({id, file, position: [0, 0], rotation: 0, scale: 1});
  refreshSceneJson();
  renderPropsEditor();
  msg($("#libraryMsg"), `${name} added to the open scene. Save scene changes to keep it.`, true);
  activateTab("episodes");
}
function setForCard(card) {
  const currentMovie = data.find(entry => entry.name === movie());
  return currentMovie?.sets.find(entry => entry.name === card.dataset.setCard);
}
function setProp(card, objectElement) {
  const set = setForCard(card);
  return set && setBlueprint(set).props[Number(objectElement.dataset.setObject)];
}
function updateSetField(target) {
  const card = target.closest("[data-set-card]");
  if (!card) return;
  const set = setForCard(card);
  const blueprint = set && setBlueprint(set);
  if (!blueprint) return;
  if (target.hasAttribute("data-set-description")) {
    blueprint.description = target.value;
    return;
  }
  const objectElement = target.closest("[data-set-object]");
  if (!objectElement) return;
  const prop = setProp(card, objectElement);
  if (!prop) return;
  if (target.dataset.setField === "make") {
    prop.make = target.value;
    prop.size = [...(formSchema.props[target.value]?.size || [1, 1, 1])];
    if (target.value !== "door") delete prop.outside_set;
    render();
  } else if (target.dataset.setField === "id") {
    prop.id = target.value;
  } else if (target.dataset.setField === "outside_set") {
    if (target.value) prop.outside_set = target.value;
    else delete prop.outside_set;
  } else if (target.dataset.setField === "rotation") {
    prop.rotation = Number(target.value);
  } else if (target.dataset.setSize !== undefined) {
    prop.size = prop.size || [...(formSchema.props[prop.make]?.size || [1, 1, 1])];
    prop.size[Number(target.dataset.setSize)] = Number(target.value);
  } else if (target.dataset.setPosition !== undefined) {
    prop.position = prop.position || [0, 0];
    prop.position[Number(target.dataset.setPosition)] = Number(target.value);
  }
}
async function saveSet(card, build) {
  const set = setForCard(card);
  if (!set) return;
  const button = card.querySelector(`[data-set-action="${build ? "build" : "save"}"]`);
  const status = card.querySelector("[data-set-status]");
  button.disabled = true;
  status.textContent = build ? "Building the 3D set… this may take a few minutes the first time." : "Saving details…";
  status.className = "muted set-hint";
  try {
    const result = await post(build ? "/api/set/build" : "/api/set/blueprint",
      {movie: movie(), set: set.name, blueprint: setBlueprint(set)});
    set.blueprint = result.blueprint;
    status.textContent = build ? `Build started (${result.job}). Follow progress in Jobs; your scene files are unchanged.` : "Set details saved.";
    status.className = "msg ok set-hint";
  } catch (error) {
    status.textContent = error.message;
    status.className = "msg err set-hint";
  } finally {
    button.disabled = false;
  }
}
let activeSetDraw = null;
function setImagePoint(stage, event) {
  const bounds = stage.getBoundingClientRect();
  return {x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))};
}
function refreshSceneJson() {
  if (sceneModel) {
    $("#scene").value = JSON.stringify(sceneModel, null, 1);
    advancedDirty = false;
  }
}
function activeScene() {
  return Array.isArray(sceneModel?.scenes) ? sceneModel.scenes[activeSceneIndex] : sceneModel;
}
function optionsMarkup(values, selected, labels = {}) {
  const keys = Array.isArray(values) ? values : Object.keys(values || {});
  const known = Array.isArray(selected) ? selected.every(value => keys.includes(value)) : (!selected || keys.some(value => String(value) === String(selected)));
  const unknown = !known && !Array.isArray(selected) ? `<option value="${esc(selected)}" selected>Unrecognized: ${esc(selected)}</option>` : "";
  return unknown + keys.map(value => `<option value="${esc(value)}"${Array.isArray(selected) ? (selected.includes(value) ? " selected" : "") : (String(value) === String(selected) ? " selected" : "")}>${esc(labels[value] || value.replaceAll("_", " "))}</option>`).join("");
}
function fieldMarkup(key, definition, value, group) {
  const id = `${group}-${key}`;
  const help = definition.help ? `<small>${esc(definition.help)}</small>` : "";
  let control;
  if (definition.type === "bool") {
    control = `<label class="check-field"><input type="checkbox" data-setting="${group}.${key}"${value ? " checked" : ""}> ${esc(key.replaceAll("_", " "))}</label>`;
    return `<div class="field">${control}${help}</div>`;
  }
  if (definition.type === "enum") {
    control = `<select id="${id}" data-setting="${group}.${key}">${optionsMarkup(definition.values, value ?? definition.default ?? "")}</select>`;
  } else if (definition.type === "weather") {
    const weather = typeof value === "string" ? {type: value} : (value || {});
    control = `<select id="${id}" data-weather-type="${group}.${key}"><option value="">None</option>${optionsMarkup(["snow", "rain"], weather.type)}</select>
      <div class="row"><label class="muted">Amount <input type="number" min="0" max="1" step="0.1" data-weather-prop="amount" data-weather-key="${group}.${key}" value="${esc(weather.amount ?? 0.5)}"></label>
      <label class="muted">Wind <input type="number" min="-1" max="1" step="0.1" data-weather-prop="wind" data-weather-key="${group}.${key}" value="${esc(weather.wind ?? 0.2)}"></label>
      <label class="muted">Fog <input type="number" min="0" max="1" step="0.1" data-weather-prop="fog" data-weather-key="${group}.${key}" value="${esc(weather.fog ?? 0)}"></label></div>`;
  } else if (definition.type === "voice") {
    control = `<select id="${id}" data-setting="${group}.${key}"><option value="">Choose voice</option>${optionsMarkup(Object.keys(formSchema.voices), value)}</select>`;
  } else if (definition.type === "bed" || definition.type === "sfx") {
    const list = formSchema.library[definition.type === "bed" ? "beds" : "sfx"] || [];
    control = `<input id="${id}" data-setting="${group}.${key}" list="${id}-options" value="${esc(value ?? "")}" placeholder="Choose a library name or enter a file path">
      <datalist id="${id}-options">${optionsMarkup(list, value)}</datalist>`;
  } else if (definition.type === "image") {
    const depth = curEp?.split("/").length || 1;
    const prefix = "../".repeat(depth);
    const sets = data.find(item => item.name === movie())?.sets || [];
    const paths = sets.map(set => `${prefix}${set.path.replace(/^\.\.\/sets\//, "sets/")}`);
    control = `<input id="${id}" data-setting="${group}.${key}" list="${id}-options" value="${esc(value ?? "")}" placeholder="Choose a set image path">
      <datalist id="${id}-options">${optionsMarkup(paths, value)}</datalist>`;
  } else if (definition.type === "number") {
    control = `<input id="${id}" type="number" step="any" data-setting="${group}.${key}" value="${esc(value ?? definition.default ?? "")}">`;
  } else {
    control = `<input id="${id}" data-setting="${group}.${key}" value="${esc(value ?? definition.default ?? "")}" placeholder="${esc(definition.help || "")}">`;
  }
  return `<div class="field"><label for="${id}">${esc(key.replaceAll("_", " "))}${definition.required ? " *" : ""}</label>${control}${help}</div>`;
}
function sceneFormValue(key, definition) {
  const part = activeScene() || {};
  return part[key] ?? sceneModel?.[key] ?? definition.default ?? "";
}
function renderSceneForms() {
  const panel = $("#sceneForms");
  panel.classList.toggle("hidden", !sceneModel);
  $("#actionEditor").closest(".studio-panel").classList.toggle("hidden", !sceneModel);
  if (!sceneModel || !formSchema) return;
  $("#sceneSettings").innerHTML = Object.entries(formSchema.scene)
    .map(([key, def]) => fieldMarkup(key, def, sceneFormValue(key, def), "scene")).join("");
  $("#finishSettings").innerHTML = Object.entries(formSchema.finish)
    .map(([key, def]) => fieldMarkup(key, def, sceneFormValue(key, def), "finish")).join("");
  $("#quality").value = sceneFormValue("quality", formSchema.scene.quality) || "blocking";
  const title = sceneModel.title;
  $("#titleText").value = typeof title === "string" ? title : (title?.text || "");
  $("#titleSubtitle").value = typeof title === "object" ? (title.subtitle || "") : "";
  $("#creditsLines").value = Array.isArray(sceneModel.credits?.lines) ? sceneModel.credits.lines.join("\n") : "";
  renderCastEditor();
  if (Array.isArray(sceneModel.scenes) && !activeScene()) {
    $("#propsEditor").innerHTML = `<p class="muted">Add a scene before placing props.</p>`;
    $("#actionEditor").innerHTML = `<p class="muted">Add a scene before adding actions.</p>`;
    return;
  }
  renderPropsEditor();
  renderActionEditor();
}
function sceneCast() {
  const root = sceneModel?.cast && typeof sceneModel.cast === "object" && !Array.isArray(sceneModel.cast) ? sceneModel.cast : {};
  const localValue = Array.isArray(sceneModel?.scenes) ? activeScene()?.cast : {};
  const local = localValue && typeof localValue === "object" && !Array.isArray(localValue) ? localValue : {};
  return {...root, ...local};
}
function renderCastEditor() {
  if (!sceneModel) return;
  const cast = sceneCast();
  const available = data.find(item => item.name === movie())?.characters || [];
  $("#castToAdd").innerHTML = `<option value="">Choose a character</option>` +
    available.filter(item => !cast[item.name]).map(item => `<option value="${esc(item.name)}">${esc(item.name)}</option>`).join("");
  $("#addCast").disabled = available.every(item => cast[item.name]);
  const localValue = Array.isArray(sceneModel.scenes) ? activeScene()?.cast : cast;
  const localCast = localValue && typeof localValue === "object" && !Array.isArray(localValue) ? localValue : {};
  const seats = (activeScene()?.props || []).filter(prop => prop && formSchema.seats.includes(prop.make));
  $("#castEditor").innerHTML = Object.entries(cast).map(([name, entry]) => {
    entry = entry && typeof entry === "object" ? entry : {};
    const position = Array.isArray(entry.position) ? entry.position : [0, 0];
    const editable = Object.prototype.hasOwnProperty.call(localCast, name);
    return `<div class="editor-item"><div class="row"><strong>${esc(name)}</strong><span class="muted">${editable ? "In this scene" : "Episode cast"}</span><div class="spacer"></div>
      ${editable ? `<button class="b" data-remove-cast="${esc(name)}">Remove</button>` : ""}</div>
      <div class="row" style="margin-top:8px">
        <label class="muted">Position x,y <input data-cast-name="${esc(name)}" data-cast-field="position" value="${esc(position.join(", "))}" aria-label="${esc(name)} position"></label>
        <label class="muted">Facing (degrees) <input data-cast-name="${esc(name)}" data-cast-field="facing" type="number" step="1" value="${esc(entry.facing === "camera" || entry.facing == null ? "" : entry.facing)}" placeholder="Camera" aria-label="${esc(name)} facing"></label>
        <label class="muted">Expression <select data-cast-name="${esc(name)}" data-cast-field="expression"><option value="">Default</option>${optionsMarkup(formSchema.expressions, entry.expression)}</select></label>
        <label class="muted">Posture <select data-cast-name="${esc(name)}" data-cast-field="posture"><option value="">Default</option>${optionsMarkup(formSchema.postures, entry.posture)}</select></label>
        <label class="muted">Voice <select data-cast-name="${esc(name)}" data-cast-field="voice"><option value="">No voice</option>${optionsMarkup(Object.keys(formSchema.voices), entry.voice)}</select></label>
        <label class="muted">Voice effect <select data-cast-name="${esc(name)}" data-cast-field="voice_fx"><option value="">Default</option>${optionsMarkup(formSchema.voice_fx, entry.voice_fx)}</select></label>
        <label class="muted">Start seated <select data-cast-name="${esc(name)}" data-cast-field="sit"><option value="">Standing</option>${optionsMarkup(seats.map(prop => prop.id), entry.sit)}</select></label>
      </div></div>`;
  }).join("") || `<p class="muted">Add a character to stage the scene.</p>`;
}
function renderPropsEditor() {
  if (!sceneModel) return;
  const part = activeScene() || sceneModel;
  if (!Array.isArray(part.props)) {
    $("#propsEditor").innerHTML = `<p class="muted">Props must be a list. Use the advanced editor to repair this scene.</p>`;
    return;
  }
  const kinds = Object.keys(formSchema.props).filter(name => formSchema.props[name].size);
  const previousKind = $("#propType").value;
  const selectedKind = kinds.includes(previousKind) ? previousKind : (kinds.includes("chair") ? "chair" : kinds[0]);
  $("#propType").innerHTML = optionsMarkup(kinds, selectedKind);
  if (!previousKind) setDefaultPropSize();
  const previousMaterial = $("#propMaterial").value;
  const defaultMaterial = formSchema.props[selectedKind]?.material;
  $("#propMaterial").innerHTML = optionsMarkup(formSchema.materials, formSchema.materials.includes(previousMaterial) ? previousMaterial : defaultMaterial);
  $("#propsEditor").innerHTML = part.props.map((prop, index) => {
    if (!prop || typeof prop !== "object" || Array.isArray(prop)) {
      return `<div class="editor-item">Invalid prop at position ${index + 1}; repair it in the advanced editor.</div>`;
    }
    const position = Array.isArray(prop.position) ? prop.position : [0, 0];
    const defaultSize = formSchema.props[prop.make]?.size;
    const size = Array.isArray(prop.size) ? prop.size : (defaultSize || (formSchema.props[prop.make] ? null : [0.5, 0.5, 0.5]));
    const materials = formSchema.materials;
    const material = materials.includes(prop.material) ? prop.material : (formSchema.props[prop.make]?.material || "");
    return `<div class="editor-item"><div class="row"><strong>${esc(prop.id || `Prop ${index + 1}`)}</strong><span class="muted">${esc(prop.file ? "Blender model" : (prop.make || "box"))}</span><div class="spacer"></div><button class="b" data-remove-prop="${index}">Remove</button></div>
      <div class="row" style="margin-top:8px"><label class="muted">Position x,y <input data-prop-index="${index}" data-prop-field="position" value="${esc(position.join(", "))}" aria-label="${esc(prop.id || "prop")} position"></label>
      <label class="muted">Rotation <input data-prop-index="${index}" data-prop-field="rotation" type="number" step="1" value="${esc(prop.rotation ?? 0)}" aria-label="${esc(prop.id || "prop")} rotation"></label>
      ${prop.file ? `<label class="muted">Scale <input data-prop-index="${index}" data-prop-field="scale" type="number" min="0.01" step="0.05" value="${esc(prop.scale ?? 1)}" aria-label="${esc(prop.id || "prop")} scale"></label>` : ""}
      ${size ? size.map((value, dimension) => `<label class="muted">${["Width", "Depth", "Height"][dimension]} <input data-prop-index="${index}" data-prop-field="size" data-prop-size-index="${dimension}" type="number" min="0.01" step="0.05" value="${esc(value)}" aria-label="${esc(prop.id || "prop")} ${["width", "depth", "height"][dimension]}"></label>`).join("") : ""}
      <label class="muted">Material <select data-prop-index="${index}" data-prop-field="material"><option value="">Default</option>${optionsMarkup(materials, material)}</select></label>
      <label class="muted">Color <input data-prop-index="${index}" data-prop-field="color" type="color" value="${esc(prop.color || "#7a5230")}" aria-label="${esc(prop.id || "prop")} color"></label></div></div>`;
  }).join("") || `<p class="muted">Add a prop to build it into this scene.</p>`;
}
function actionInput(name, definition, value, index) {
  const key = `data-action-field="${esc(name)}" data-action-index="${index}"`;
  const val = value == null ? "" : (Array.isArray(value) ? value.join(", ") : value);
  if (definition.type === "enum") return `<select ${key}>${optionsMarkup(definition.values, value ?? definition.default ?? "")}</select>`;
  if (definition.type === "bool") return `<label class="check-field"><input type="checkbox" ${key}${value ? " checked" : ""}> ${esc(name)}</label>`;
  if (definition.type === "voice") return `<select ${key}><option value="">Choose voice</option>${optionsMarkup(Object.keys(formSchema.voices), value)}</select>`;
  if (definition.type === "cast_list") return `<select multiple ${key} aria-label="${esc(name)}">${optionsMarkup(Object.keys(sceneCast()), value || [])}</select>`;
  if (definition.type === "door" || definition.type === "seat") {
    const types = definition.type === "door" ? ["door"] : formSchema.seats;
    const props = (activeScene()?.props || []).filter(prop => types.includes(prop.make)).map(prop => prop.id);
    return `<select ${key}><option value="">Choose prop</option>${optionsMarkup(props, value)}</select>`;
  }
  if (definition.type === "bed" || definition.type === "sfx") {
    const list = formSchema.library[definition.type === "bed" ? "beds" : "sfx"] || [];
    return `<input ${key} list="action-${index}-${name}-options" value="${esc(val)}" placeholder="${esc(definition.help)}"><datalist id="action-${index}-${name}-options">${optionsMarkup(list, value)}</datalist>`;
  }
  const inputType = definition.type === "number" ? 'type="number" step="any"' : "";
  return `<input ${key} ${inputType} value="${esc(val)}" placeholder="${esc(definition.help)}">`;
}
function renderActionEditor() {
  if (!sceneModel || !formSchema) return;
  const part = activeScene() || sceneModel;
  if (!Array.isArray(part.script)) {
    $("#actionEditor").innerHTML = `<p class="muted">Actions must be a list. Use the advanced editor to repair this scene.</p>`;
    return;
  }
  const cast = sceneCast();
  const actions = Object.entries(formSchema.actions).filter(([name]) => !["say", "think"].includes(name));
  $("#actionType").innerHTML = optionsMarkup(actions.map(([name]) => name), $("#actionType").value || "walk",
    Object.fromEntries(actions.map(([name, spec]) => [name, `${name.replaceAll("_", " ")} — ${spec.help}`])));
  $("#actionEditor").innerHTML = part.script.map((step, index) => {
    if (!step || typeof step !== "object" || Array.isArray(step)) {
      return `<div class="editor-item">Invalid action at position ${index + 1}; repair it in the advanced editor.</div>`;
    }
    if (["say", "think"].includes(step.do)) return "";
    const spec = formSchema.actions[step.do];
    if (!spec) return `<div class="editor-item">Unknown action <strong>${esc(step.do)}</strong> <button class="b" data-remove-action="${index}">Remove</button></div>`;
    const who = spec.who ? `<select data-action-field="who" data-action-index="${index}" aria-label="Character">${optionsMarkup(Object.keys(cast), step.who)}</select>` : "";
    const params = Object.entries(spec.params).map(([key, def]) =>
      `<label class="field"><span>${esc(key.replaceAll("_", " "))}${def.required ? " *" : ""}</span>${actionInput(key, def, step[key], index)}<small>${esc(def.help || "")}</small></label>`).join("");
    return `<div class="editor-item"><div class="row"><strong>Action ${index + 1}</strong>
      <select data-action-kind="${index}" aria-label="Action type">${optionsMarkup(actions.map(([name]) => name), step.do,
        Object.fromEntries(actions.map(([name, item]) => [name, name.replaceAll("_", " ")])))}</select>
      ${who}<div class="spacer"></div><button class="b" data-remove-action="${index}">Remove</button></div>
      <div class="row action-form">${params}</div></div>`;
  }).join("") || `<p class="muted">No extra actions yet. Add a walk, gesture, camera direction or sound cue.</p>`;
}
function parsePoint(value) {
  const pieces = value.split(/[,\s]+/).filter(Boolean).map(Number);
  if (pieces.length !== 2 || pieces.some(number => !Number.isFinite(number))) {
    throw new Error("Enter two coordinates, for example -1.2, 0.5.");
  }
  return pieces;
}
function setDefaultPropSize() {
  const size = formSchema.props[$("#propType").value]?.size;
  if (!size) {
    $("#propWidth").value = $("#propDepth").value = $("#propHeight").value = "";
    return;
  }
  [$("#propWidth").value, $("#propDepth").value, $("#propHeight").value] = size;
}
function setDefaultAssetPropSize() {
  const definition = formSchema.props[$("#assetPropType").value];
  if (!definition?.size) return;
  [$("#assetPropWidth").value, $("#assetPropDepth").value, $("#assetPropHeight").value] = definition.size;
  $("#assetPropMaterial").value = definition.material || formSchema.materials[0];
}
function setupPropAssetForm() {
  const types = Object.entries(formSchema.props).filter(([name, prop]) => name !== "picture_road" && prop.size);
  $("#assetPropType").innerHTML = types.map(([name]) =>
    `<option value="${esc(name)}">${esc(name.replaceAll("_", " "))}</option>`).join("");
  $("#assetPropMaterial").innerHTML = optionsMarkup(formSchema.materials, "wood");
  setDefaultAssetPropSize();
}
async function buildPropFromImage() {
  const form = $("#propAssetMsg");
  const photo = $("#assetPropPhoto").files[0];
  if (!photo) return msg(form, "Choose a reference image for this prop.");
  const payload = new FormData();
  payload.append("movie", movie());
  payload.append("name", $("#assetPropName").value);
  payload.append("make", $("#assetPropType").value);
  payload.append("width", $("#assetPropWidth").value);
  payload.append("depth", $("#assetPropDepth").value);
  payload.append("height", $("#assetPropHeight").value);
  payload.append("material", $("#assetPropMaterial").value);
  payload.append("color", $("#assetPropColor").value);
  payload.append("photo", photo);
  $("#buildPropAsset").disabled = true;
  try {
    const result = await api("/api/prop/build", {method: "POST", body: payload});
    msg(form, `Building Blender prop. Follow progress below (job ${result.job}).`, true);
    await load(movie());
  } catch (error) {
    msg(form, error.message);
  } finally {
    $("#buildPropAsset").disabled = false;
  }
}
function addPropAssetToScene(name) {
  if (!sceneModel) {
    msg($("#propAssetMsg"), "Open an episode scene first, then add this prop to it.");
    return;
  }
  const part = activeScene();
  if (!part) {
    msg($("#propAssetMsg"), "The current scene must have a props list before adding a model.");
    return;
  }
  if (part.props == null) part.props = [];
  if (!Array.isArray(part.props)) {
    msg($("#propAssetMsg"), "The current scene's props field must be a list before adding a model.");
    return;
  }
  const prop = data.find(entry => entry.name === movie())?.props?.find(entry => entry.name === name);
  if (!prop?.asset) {
    msg($("#propAssetMsg"), `The Blender asset for ${name} is not ready yet.`);
    return;
  }
  const baseId = name.replace(/[^a-z0-9_]/g, "_");
  let id = baseId, index = 2;
  while (part.props.some(item => item?.id === id)) id = `${baseId}_${index++}`;
  const depth = curEp?.split("/").length || 1;
  const file = `${"../".repeat(depth)}props/${name}/${name}.blend`;
  part.props.push({id, file, position: [0, 0], rotation: 0, scale: 1});
  refreshSceneJson();
  renderPropsEditor();
  msg($("#propAssetMsg"), `${name} added to the open scene. Save scene changes to keep it.`, true);
  activateTab("episodes");
}
function setSceneSetting(group, key, value) {
  const target = activeScene() || sceneModel;
  if (value === "" || value == null) delete target[key];
  else target[key] = value;
}
function castEntryForEdit(name) {
  if (Array.isArray(sceneModel.scenes)) {
    const part = activeScene() || sceneModel;
    if (!part.cast) part.cast = {};
    if (!part.cast[name]) part.cast[name] = {};
    return part.cast[name];
  }
  if (!sceneModel.cast) sceneModel.cast = {};
  return sceneModel.cast[name];
}
function renderAllSceneForms() {
  renderSceneForms();
  renderDialogue();
}
function characterPath(name) {
  const depth = curEp.split("/").length;
  return `${"../".repeat(depth)}characters/${name}.blend`;
}
function actionDefinition(step) {
  return formSchema.actions[step.do];
}
function readActionValue(input, definition) {
  if (definition.type === "bool") return input.checked;
  if (definition.type === "cast_list") return [...input.selectedOptions].map(option => option.value);
  if (definition.type === "number") {
    if (input.value === "") return null;
    const number = Number(input.value);
    if (!Number.isFinite(number)) throw new Error("Enter a valid number.");
    return number;
  }
  if (input.value === "") return null;
  if (definition.type === "point" || ((definition.type === "target" || definition.type === "look") && /^[\d.+-]/.test(input.value.trim()))) {
    return parsePoint(input.value);
  }
  return input.value;
}
function renderDialogue() {
  if (!sceneModel) return;
  const isEpisode = Array.isArray(sceneModel.scenes);
  const part = activeScene();
  renderSceneForms();
  $("#scenePartRow").classList.toggle("hidden", !isEpisode);
  if (!part) {
    $("#dialogueLines").innerHTML = `<p class="muted">This episode has no scenes yet.</p>`;
    return;
  }
  if (isEpisode) {
    $("#scenePart").innerHTML = sceneModel.scenes.map((item, index) =>
      `<option value="${index}"${index === activeSceneIndex ? " selected" : ""}>${esc(item.id || `Scene ${index + 1}`)}</option>`
    ).join("");
  }
  const cast = {...(sceneModel.cast || {}), ...(part.cast || {})};
  const speakers = Object.keys(cast);
  $("#newSpeaker").innerHTML = speakers.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
  $("#newSpeaker").disabled = speakers.length === 0;
  const script = Array.isArray(part.script) ? part.script : [];
  const lines = script.map((step, index) => ({step, index}))
    .filter(({step}) => step && typeof step === "object" && ["say", "think"].includes(step.do));
  const lineParams = ["expression", "fx", "speed", "pause"];
  $("#dialogueLines").innerHTML = lines.map(({step, index}) => `
    <div class="card" style="margin:10px 0" data-dialogue="${index}">
      <div class="row">
        <strong>Line ${index + 1}</strong>
        <select data-field="who" aria-label="Speaker">${speakers.map(name => `<option value="${esc(name)}"${name === step.who ? " selected" : ""}>${esc(name)}</option>`).join("")}</select>
        <select data-field="do" aria-label="Line type"><option value="say"${step.do === "say" ? " selected" : ""}>Speak aloud</option><option value="think"${step.do === "think" ? " selected" : ""}>Inner thought</option></select>
        <div class="spacer"></div><button class="b" data-remove="${index}">Remove line</button>
      </div>
      <textarea data-field="text" rows="2" aria-label="Dialogue text" placeholder="Enter the exact words">${esc(step.text || "")}</textarea>
      <div class="form-grid">${lineParams.map(key => {
        const definition = formSchema.actions[step.do].params[key];
        const value = step[key] ?? definition.default ?? "";
        const input = definition.type === "enum"
          ? `<select data-dialogue-param="${key}" data-dialogue-index="${index}"><option value="">Default</option>${optionsMarkup(definition.values, value)}</select>`
          : `<input type="number" step="any" data-dialogue-param="${key}" data-dialogue-index="${index}" value="${esc(value)}">`;
        return `<label class="field"><span>${esc(key.replaceAll("_", " "))}</span>${input}<small>${esc(definition.help)}</small></label>`;
      }).join("")}</div>
      <div class="row">
        <span class="muted">${step.audio ? `Voice file attached: ${esc(step.audio)}` : "Draft voice (Kokoro), unless you upload a performance."}</span>
        <button class="b" type="button" data-hear="${index}">Hear it</button>
        <button class="b" type="button" data-pick-voice="${index}">Choose WAV performance</button>
        <input type="file" data-voice="${index}" accept=".wav,audio/wav" hidden>
      </div>
      ${step.audio && step.audio.startsWith("voices/") ? `<audio controls preload="none" style="width:100%;margin-top:8px" src="/media/${[movie(), curEp, step.audio].join("/").split("/").map(encodeURIComponent).join("/")}"></audio>` : ""}
    </div>`).join("") || `<p class="muted">No dialogue yet. Add a line below to start.</p>`;
}
async function saveScene() {
  if (!sceneModel) throw new Error("Open a scene before saving.");
  if (advancedDirty) {
    try { sceneModel = JSON.parse($("#scene").value); }
    catch (e) { throw new Error("Scene JSON is invalid: " + e.message); }
    if (Array.isArray(sceneModel.scenes)) {
      activeSceneIndex = Math.min(activeSceneIndex ?? 0, sceneModel.scenes.length - 1);
    } else activeSceneIndex = null;
  }
  refreshSceneJson();
  await post("/api/episode/save", {movie: movie(), episode: curEp, scene: $("#scene").value});
  renderDialogue();
}
async function openEp(ep) {
  clearInterval(poll);
  curEp = ep; render();
  $("#epTitle").textContent = ep; $("#checkOut").classList.add("hidden"); $("#epMsg").textContent = "";
  try {
    const e = await api(`/api/episode?movie=${encodeURIComponent(movie())}&episode=${encodeURIComponent(ep)}`);
    sceneModel = JSON.parse(e.scene);
    activeSceneIndex = Array.isArray(sceneModel.scenes) ? 0 : null;
    refreshSceneJson(); renderDialogue(); showEp(e); startPoll();
    try { localStorage.setItem("cf.episode." + movie(), ep); } catch {}
  } catch (e) {
    sceneModel = null;
    activeSceneIndex = null;
    $("#scene").value = "";
    renderSceneForms();
    msg($("#epMsg"), "Could not load scene: " + e.message);
  }
}
function clearEpisode() {
  clearInterval(poll);
  $("#epTitle").textContent = "Choose a scene";
  $("#scene").value = "";
  sceneModel = null;
  activeSceneIndex = null;
  $("#dialogueLines").innerHTML = "";
  $("#status").textContent = "";
  $("#barFill").style.width = "0";
  $("#render").disabled = true;
  const video = $("#video");
  video.pause();
  video.removeAttribute("src");
  delete video.dataset.src;
  video.classList.add("hidden");
  $("#noVideo").classList.remove("hidden");
  $("#shots").innerHTML = "";
  $("#checkOut").classList.add("hidden");
  $("#epMsg").textContent = "";
  renderSceneForms();
}
async function renderStudio() {
  if (!movie()) return;
  let p;
  try { p = await api(`/api/movie/progress?movie=${encodeURIComponent(movie())}`); } catch (e) { $("#studioNext").textContent = e.message; return; }
  const next = p.next;
  $("#studioNext").innerHTML = next
    ? `<div><div class="muted">Next step</div><strong>${esc(next.title)}</strong> <span class="muted">${esc(next.detail)}</span></div><button class="b p" data-go="${next.tab}">Go to ${esc(next.title)}</button>`
    : `<div><div class="muted">All steps done</div><strong>${esc(p.movie)}</strong> <span class="muted">every film is rendered and up to date</span></div>`;
  $("#studioSteps").innerHTML = p.steps.map((s, i) =>
    `<li class="${s.state}" data-go="${s.tab}"><span class="n">${s.state === "done" ? "✓" : i + 1}</span><b>${esc(s.title)}</b><small>${esc(s.detail)}</small></li>`).join("");
  const film = e => e.broken ? "scene.json is broken" : !e.film ? "not made" : e.current ? "up to date" : "changed since render";
  $("#studioEps").innerHTML = Object.entries(p.episodes).map(([n, e]) =>
    `<tr><td>${esc(n)}${(e.missing || []).length ? `<div class="warn">missing: ${esc(e.missing.join(", "))}</div>` : ""}</td><td>${e.scenes}</td>
     <td>${e.rendered ?? 0} / ${e.scenes}</td><td>${e.storyboard ? "yes" : "—"}</td><td class="${e.current ? "ok" : ""}">${film(e)}</td>
     <td><button class="b" data-ep="${esc(n)}">Open</button></td></tr>`).join("") || `<tr><td colspan="6" class="muted">No episodes yet.</td></tr>`;
}
function activateTab(name) {
  if (name === "studio") renderStudio();
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll("main > section").forEach(s => s.classList.toggle("hidden", s.id !== "tab-" + name));
}
async function openMovieScene() {
  const m = data.find(x => x.name === movie());
  curEp = null;
  clearEpisode();
  render();
  renderStudio();
  if (!m || !m.episodes.length) return;
  let ep = null;
  try { ep = localStorage.getItem("cf.episode." + m.name); } catch {}
  await openEp(m.episodes.includes(ep) ? ep : m.episodes[0]);
}
function showEp(e) {
  $("#status").textContent = e.status;
  const m = /(\d+)\/(\d+) frames/.exec(e.status), sc = /scene (\d+)\/(\d+)/.exec(e.status);
  let pct = e.status.startsWith("finished") ? 100 : 0;
  if (m) { const f = (+m[1]) / Math.max(+m[2], 1); pct = sc ? ((+sc[1] - 1 + f) / (+sc[2])) * 100 : f * 100; }
  $("#barFill").style.width = pct + "%";
  $("#render").disabled = e.rendering;
  const v = $("#video");
  if (e.video) { if (v.dataset.src !== e.video) { v.src = e.video; v.dataset.src = e.video; } v.classList.remove("hidden"); $("#noVideo").classList.add("hidden"); }
  else { v.classList.add("hidden"); $("#noVideo").classList.remove("hidden"); }
  $("#shots").innerHTML = e.shots.map(s => `<div><div class="muted">${esc(s.name)}</div><video src="${s.video}" controls preload="metadata"></video></div>`).join("")
    + (e.storyboard ? `<div style="grid-column:1/-1"><div class="muted">Storyboard</div><a href="${e.storyboard}" target="_blank"><img src="${e.storyboard}" alt="Storyboard" style="width:100%;border-radius:8px"></a></div>` : "")
    + ((e.downloads || []).length ? `<div style="grid-column:1/-1" class="row">${e.downloads.map(d => `<a class="b" href="${d.url}" download>${esc(d.name)}</a>`).join("")}</div>` : "");
}
function startPoll() {
  clearInterval(poll);
  poll = setInterval(async () => {
    if (!curEp) return;
    try { showEp(await api(`/api/episode?movie=${encodeURIComponent(movie())}&episode=${encodeURIComponent(curEp)}`)); } catch {}
  }, 3000);
}
setInterval(async () => {
  try {
    const g = await api("/api/gpu"); const el = $("#gpu");
    el.textContent = g.busy ? "GPU busy: " + g.busy : "GPU free"; el.className = g.busy ? "busy" : "";
    const jobs = await api("/api/jobs");
    const box = $("#jobs");
    if (jobs.length) { box.classList.remove("hidden"); box.textContent = jobs.map(j => `${j.name}: ${j.state}${j.last ? "  — " + j.last : ""}`).join("\n"); }
    const propJobs = jobs.filter(job => job.kind === "prop");
    const propJobBox = $("#propJobs");
    if (propJobs.length) {
      propJobBox.classList.remove("hidden");
      propJobBox.textContent = propJobs.map(job => `${job.name}: ${job.state}${job.last ? "  — " + job.last : ""}`).join("\n");
    }
    const libraryJobs = jobs.filter(job => job.kind === "library");
    const libraryJobBox = $("#libraryJobs");
    if (libraryJobs.length) {
      libraryJobBox.classList.remove("hidden");
      libraryJobBox.textContent = libraryJobs.map(job => `${job.name}: ${job.state}${job.last ? "  — " + job.last : ""}`).join("\n");
    } else {
      libraryJobBox.classList.add("hidden");
    }
    const finishedJobs = jobs.filter(job => job.state !== "building").map(job => `${job.id}:${job.state}`).sort().join("|");
    if (finishedJobs !== window._finishedJobs) {
      window._finishedJobs = finishedJobs;
      if (finishedJobs) load(movie());
    }
  } catch {}
}, 3000);

document.querySelectorAll("nav button").forEach(b => b.onclick = () => activateTab(b.dataset.tab));
$("#tab-studio").addEventListener("click", async e => {
  const go = e.target.closest("[data-go]"), ep = e.target.closest("[data-ep]");
  if (ep) { activateTab("episodes"); await openEp(ep.dataset.ep); }
  else if (go) activateTab(go.dataset.go);
});
$("#sets").addEventListener("input", e => { if (e.target.tagName !== "SELECT") updateSetField(e.target); });
$("#sets").addEventListener("change", e => { if (e.target.tagName === "SELECT") updateSetField(e.target); });
$("#sets").addEventListener("click", e => {
  const action = e.target.closest("[data-set-action]");
  if (!action) return;
  const card = action.closest("[data-set-card]");
  const set = setForCard(card);
  if (!set) return;
  const blueprint = setBlueprint(set);
  const objectElement = action.closest("[data-set-object]");
  const index = objectElement ? Number(objectElement.dataset.setObject) : -1;
  if (action.dataset.setAction === "add") {
    const type = card.querySelector("[data-set-new-type]").value;
    const definition = formSchema.props[type];
    const baseId = type.replace(/[^a-z0-9_]/g, "_");
    let number = blueprint.props.filter(prop => prop.id?.startsWith(baseId + "_")).length + 1;
    let id = `${baseId}_${number}`;
    while (blueprint.props.some(prop => prop.id === id)) id = `${baseId}_${++number}`;
    blueprint.props.push({id, make: type, position: [0, 0], rotation: 0, size: [...(definition.size || [1, 1, 1]) ]});
    render();
  } else if (action.dataset.setAction === "remove") {
    blueprint.props.splice(index, 1);
    render();
  } else if (action.dataset.setAction === "draw") {
    card.dataset.drawIndex = String(index);
    card.querySelector("[data-set-stage]").classList.add("drawing");
    card.querySelector("[data-set-status]").textContent = "Drag across the reference image to mark the object's region.";
    card.querySelector("[data-set-status]").className = "muted set-hint";
  } else if (action.dataset.setAction === "clear-region") {
    delete blueprint.props[index].picture_rect;
    render();
  } else if (action.dataset.setAction === "save") {
    saveSet(card, false);
  } else if (action.dataset.setAction === "build") {
    saveSet(card, true);
  }
});
$("#sets").addEventListener("pointerdown", e => {
  const stage = e.target.closest("[data-set-stage]");
  const card = stage?.closest("[data-set-card]");
  if (!stage || !card || card.dataset.drawIndex === undefined) return;
  e.preventDefault();
  const start = setImagePoint(stage, e);
  const draft = document.createElement("div");
  draft.className = "set-mark";
  stage.querySelector(".set-overlays").append(draft);
  stage.classList.add("drawing");
  activeSetDraw = {stage, card, draft, start, pointerId: e.pointerId, index: Number(card.dataset.drawIndex)};
  stage.setPointerCapture(e.pointerId);
});
document.addEventListener("pointermove", e => {
  if (!activeSetDraw || e.pointerId !== activeSetDraw.pointerId) return;
  const point = setImagePoint(activeSetDraw.stage, e);
  const left = Math.min(point.x, activeSetDraw.start.x) * 100;
  const top = Math.min(point.y, activeSetDraw.start.y) * 100;
  activeSetDraw.draft.style.left = `${left}%`;
  activeSetDraw.draft.style.top = `${top}%`;
  activeSetDraw.draft.style.width = `${Math.abs(point.x - activeSetDraw.start.x) * 100}%`;
  activeSetDraw.draft.style.height = `${Math.abs(point.y - activeSetDraw.start.y) * 100}%`;
});
document.addEventListener("pointerup", e => {
  if (!activeSetDraw || e.pointerId !== activeSetDraw.pointerId) return;
  const draw = activeSetDraw;
  const end = setImagePoint(draw.stage, e);
  const rect = [Math.min(end.x, draw.start.x), Math.min(end.y, draw.start.y),
    Math.max(end.x, draw.start.x), Math.max(end.y, draw.start.y)];
  const set = setForCard(draw.card);
  if (set && rect[2] - rect[0] >= 0.01 && rect[3] - rect[1] >= 0.01) {
    setBlueprint(set).props[draw.index].picture_rect = rect;
  }
  activeSetDraw = null;
  delete draw.card.dataset.drawIndex;
  draw.stage.classList.remove("drawing");
  render();
});
$("#propAssets").addEventListener("click", e => {
  const button = e.target.closest("[data-add-prop-asset]");
  if (button) addPropAssetToScene(button.dataset.addPropAsset);
});
$("#buildingTemplates").addEventListener("click", e => {
  const button = e.target.closest("[data-select-building]");
  if (button) setBuildingTemplate(button.dataset.selectBuilding);
});
$("#libraryCategories").addEventListener("click", e => {
  const button = e.target.closest("[data-library-category]");
  if (!button) return;
  activeLibraryCategory = button.dataset.libraryCategory;
  renderBuildingLibrary();
});
$("#buildingTemplate").onchange = e => setBuildingTemplate(e.target.value);
$("#buildLibraryBuilding").onclick = buildLibraryBuilding;
$("#buildingAssets").addEventListener("click", e => {
  const button = e.target.closest("[data-add-building]");
  if (button) addBuildingAssetToScene(button.dataset.addBuilding, button.dataset.addBuildingCategory);
});
$("#assetPropType").onchange = setDefaultAssetPropSize;
$("#buildPropAsset").onclick = buildPropFromImage;
document.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => {
  document.querySelectorAll("[data-mode]").forEach(x => x.classList.toggle("p", x === b));
  $("#mode-design").classList.toggle("hidden", b.dataset.mode !== "design");
  $("#mode-photo").classList.toggle("hidden", b.dataset.mode !== "photo");
});
$("#movie").onchange = openMovieScene;
$("#openMovie").onclick = openMovieScene;
$("#eps").onclick = e => { const b = e.target.closest("[data-ep]"); if (b) openEp(b.dataset.ep); };
$("#advancedScene").ontoggle = () => { if ($("#advancedScene").open && !advancedDirty) refreshSceneJson(); };
$("#scene").oninput = () => { advancedDirty = true; };
$("#sceneForms").onchange = e => {
  const setting = e.target.dataset.setting;
  const weatherType = e.target.dataset.weatherType;
  const weatherKey = e.target.dataset.weatherKey;
  if (setting) {
    const [group, key] = setting.split(".");
    const definition = formSchema[group][key];
    let value = definition.type === "bool" ? e.target.checked : e.target.value;
    if (definition.type === "number") value = value === "" ? null : Number(value);
    setSceneSetting(group, key, value);
    refreshSceneJson();
  } else if (weatherType) {
    const [group, key] = weatherType.split(".");
    if (!e.target.value) setSceneSetting(group, key, null);
    else {
      const current = sceneFormValue(key, formSchema[group][key]);
      const weather = typeof current === "string" ? {type: current} : {...(current || {})};
      weather.type = e.target.value;
      setSceneSetting(group, key, weather);
    }
    refreshSceneJson();
  } else if (weatherKey) {
    const [group, key] = weatherKey.split(".");
    const current = sceneFormValue(key, formSchema[group][key]);
    const weather = typeof current === "string" ? {type: current} : {...(current || {})};
    weather[e.target.dataset.weatherProp] = Number(e.target.value);
    if (weather.type) setSceneSetting(group, key, weather);
    refreshSceneJson();
  }
  const castName = e.target.dataset.castName;
  if (castName) {
    const field = e.target.dataset.castField, entry = castEntryForEdit(castName);
    try {
      if (field === "position") entry.position = parsePoint(e.target.value);
      else if (field === "facing") entry.facing = e.target.value === "" ? "camera" : Number(e.target.value);
      else if (e.target.value === "") delete entry[field];
      else entry[field] = e.target.value;
      refreshSceneJson(); renderDialogue();
    } catch (error) {
      msg($("#epMsg"), error.message);
      renderCastEditor();
    }
  }
  const propIndex = e.target.dataset.propIndex;
  if (propIndex !== undefined) {
    const prop = activeScene().props[Number(propIndex)];
    try {
      const field = e.target.dataset.propField;
      if (field === "position") prop.position = parsePoint(e.target.value);
      else if (field === "rotation") prop.rotation = Number(e.target.value);
      else if (field === "size") {
        const dimension = Number(e.target.dataset.propSizeIndex), value = Number(e.target.value);
        if (!Number.isFinite(value) || value <= 0) throw new Error("Prop dimensions must be greater than zero.");
        const defaults = formSchema.props[prop.make]?.size || [0.5, 0.5, 0.5];
        prop.size = [...(Array.isArray(prop.size) ? prop.size : defaults)];
        prop.size[dimension] = value;
      } else if (field === "material" || field === "color") {
        if (e.target.value) prop[field] = e.target.value;
        else delete prop[field];
      }
      refreshSceneJson();
    } catch (error) {
      msg($("#epMsg"), error.message);
      renderPropsEditor();
    }
  }
  if (e.target.id === "titleText" || e.target.id === "titleSubtitle") {
    const text = $("#titleText").value.trim(), subtitle = $("#titleSubtitle").value.trim();
    if (!text && !subtitle) delete sceneModel.title;
    else sceneModel.title = {text, subtitle};
    refreshSceneJson();
  }
  if (e.target.id === "creditsLines") {
    const lines = e.target.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (!lines.length) delete sceneModel.credits;
    else sceneModel.credits = {...(sceneModel.credits || {}), lines};
    refreshSceneJson();
  }
  if (e.target.id === "propType") {
    setDefaultPropSize();
    $("#propMaterial").value = formSchema.props[e.target.value]?.material || "";
  }
};
$("#quality").onchange = () => {
  setSceneSetting("scene", "quality", $("#quality").value);
  refreshSceneJson();
};
$("#addCast").onclick = () => {
  if (!sceneModel || !$("#castToAdd").value) return;
  const name = $("#castToAdd").value, path = characterPath(name);
  if (Array.isArray(sceneModel.scenes)) {
    if (!sceneModel.cast) sceneModel.cast = {};
    if (!sceneModel.cast[name]) sceneModel.cast[name] = {character: path};
    const part = activeScene();
    if (!part.cast) part.cast = {};
    part.cast[name] = {...(part.cast[name] || {}), position: [0, 0]};
  } else {
    if (!sceneModel.cast) sceneModel.cast = {};
    sceneModel.cast[name] = {character: path, position: [0, 0]};
  }
  refreshSceneJson(); renderDialogue();
};
$("#addProp").onclick = () => {
  if (!sceneModel) return;
  const part = activeScene() || sceneModel;
  if (!Array.isArray(part.props)) part.props = [];
  const make = $("#propType").value;
  const id = $("#propId").value.trim().toLowerCase().replace(/[ -]+/g, "_") || `${make}_${part.props.length + 1}`;
  if (!/^[a-z0-9_]+$/.test(id)) return msg($("#epMsg"), "Prop names can use lowercase letters, numbers and underscores.");
  if (part.props.some(prop => prop.id === id)) return msg($("#epMsg"), `A prop named "${id}" already exists in this scene.`);
  const definition = formSchema.props[make];
  const prop = {id, make, position: [Number($("#propX").value) || 0, Number($("#propY").value) || 0]};
  if (definition.size) {
    const size = [$("#propWidth").value, $("#propDepth").value, $("#propHeight").value].map(Number);
    if (size.some(value => !Number.isFinite(value) || value <= 0)) return msg($("#epMsg"), "Prop width, depth and height must be greater than zero.");
    prop.size = size;
  }
  if ($("#propMaterial").value) prop.material = $("#propMaterial").value;
  if ($("#propColor").value) prop.color = $("#propColor").value;
  part.props.push(prop);
  $("#propId").value = "";
  refreshSceneJson(); renderDialogue();
};
$("#propsEditor").onclick = e => {
  const button = e.target.closest("[data-remove-prop]");
  if (!button) return;
  activeScene().props.splice(Number(button.dataset.removeProp), 1);
  refreshSceneJson(); renderDialogue();
};
$("#castEditor").onclick = e => {
  const button = e.target.closest("[data-remove-cast]");
  if (!button) return;
  const name = button.dataset.removeCast;
  if (Array.isArray(sceneModel.scenes)) delete activeScene().cast[name];
  else delete sceneModel.cast[name];
  refreshSceneJson(); renderDialogue();
};
$("#addAction").onclick = () => {
  if (!sceneModel) return;
  const part = activeScene() || sceneModel, name = $("#actionType").value;
  if (!Array.isArray(part.script)) part.script = [];
  const definition = formSchema.actions[name], action = {do: name};
  if (definition.who) action.who = Object.keys(sceneCast())[0] || "";
  for (const [key, param] of Object.entries(definition.params)) {
    if (Object.prototype.hasOwnProperty.call(param, "default")) action[key] = param.default;
  }
  part.script.push(action);
  refreshSceneJson(); renderDialogue();
};
$("#actionEditor").onchange = e => {
  const kindIndex = e.target.dataset.actionKind;
  if (kindIndex !== undefined) {
    const index = Number(kindIndex), current = activeScene().script[index], name = e.target.value;
    const replacement = {do: name};
    if (formSchema.actions[name].who) replacement.who = current.who || Object.keys(sceneCast())[0] || "";
    activeScene().script[index] = replacement;
    refreshSceneJson(); renderDialogue();
    return;
  }
  const indexValue = e.target.dataset.actionIndex, field = e.target.dataset.actionField;
  if (indexValue === undefined || !field) return;
  const index = Number(indexValue), step = activeScene().script[index];
  if (field === "who") {
    step.who = e.target.value;
  } else {
    const definition = formSchema.actions[step.do]?.params[field];
    if (!definition) return;
    try {
      const value = readActionValue(e.target, definition);
      if (value === null) delete step[field];
      else step[field] = value;
      msg($("#epMsg"), "", true);
    } catch (error) {
      msg($("#epMsg"), error.message);
    }
  }
  refreshSceneJson();
};
$("#actionEditor").onclick = e => {
  const button = e.target.closest("[data-remove-action]");
  if (!button) return;
  activeScene().script.splice(Number(button.dataset.removeAction), 1);
  refreshSceneJson(); renderDialogue();
};
$("#dialogueLines").onchange = async e => {
  const param = e.target.dataset.dialogueParam;
  const paramCard = e.target.closest("[data-dialogue]");
  if (param && paramCard && sceneModel) {
    const step = activeScene().script[Number(paramCard.dataset.dialogue)];
    const definition = formSchema.actions[step.do].params[param];
    if (e.target.value === "") delete step[param];
    else if (definition.type === "number") {
      const value = Number(e.target.value);
      if (!Number.isFinite(value)) return msg($("#epMsg"), "Enter a valid number.");
      step[param] = value;
    } else step[param] = e.target.value;
    refreshSceneJson();
    return;
  }
  const field = e.target.dataset.field, card = e.target.closest("[data-dialogue]");
  if (field && card && sceneModel) {
    const step = activeScene().script[Number(card.dataset.dialogue)];
    step[field] = e.target.value;
    if (field === "text") delete step.audio;
    refreshSceneJson(); renderDialogue();
  }
  const upload = e.target.closest("[data-voice]");
  if (upload && upload.files[0]) {
    const file = upload.files[0];
    const index = Number(upload.dataset.voice);
    try {
      await saveScene();
      const form = new FormData();
      form.append("movie", movie()); form.append("episode", curEp);
      form.append("step", String(index)); form.append("text", activeScene().script[index].text || "");
      if (Array.isArray(sceneModel.scenes)) form.append("scene_index", String(activeSceneIndex));
      form.append("file", file);
      const result = await api("/api/episode/voice", {method: "POST", body: form});
      sceneModel = JSON.parse(result.scene); refreshSceneJson(); renderDialogue();
      msg($("#epMsg"), "Voice performance uploaded and linked to this line.", true);
    } catch (err) { msg($("#epMsg"), err.message); }
  }
};
$("#dialogueLines").onclick = e => {
  const pick = e.target.closest("[data-pick-voice]");
  if (pick) {
    $("#dialogueLines").querySelector(`[data-voice="${pick.dataset.pickVoice}"]`).click();
    return;
  }
  const remove = e.target.closest("[data-remove]");
  if (!remove || !sceneModel) return;
  activeScene().script.splice(Number(remove.dataset.remove), 1);
  refreshSceneJson(); renderDialogue();
};
$("#scenePart").onchange = e => {
  activeSceneIndex = Number(e.target.value);
  renderDialogue();
};
$("#dialogueLines").oninput = e => {
  const field = e.target.dataset.field, card = e.target.closest("[data-dialogue]");
  if (field === "text" && card && sceneModel) {
    const step = activeScene().script[Number(card.dataset.dialogue)];
    step.text = e.target.value;
    delete step.audio;
    refreshSceneJson();
  }
};
$("#addDialogue").onclick = () => {
  if (!sceneModel) return msg($("#epMsg"), "Open a scene first.");
  const who = $("#newSpeaker").value, text = $("#newDialogueText").value.trim();
  if (!who) return msg($("#epMsg"), "Add a character to the scene before adding dialogue.");
  if (!text) return msg($("#epMsg"), "Enter the words for this line.");
  const part = activeScene();
  if (!Array.isArray(part.script)) part.script = [];
  part.script.push({who, do: $("#newDialogueType").value, text});
  $("#newDialogueText").value = "";
  refreshSceneJson(); renderDialogue();
};
$("#newMovie").onclick = async () => {
  const n = prompt("Movie name (letters, numbers, _):"); if (!n) return;
  try { const r = await post("/api/movie/new", {name: n}); await load(r.movie); } catch (e) { alert(e.message); }
};
$("#addEp").onclick = async () => {
  try { await post("/api/episode/new", {movie: movie(), episode: $("#newEp").value}); const n = $("#newEp").value.toLowerCase().replace(/[ -]/g, "_"); $("#newEp").value = ""; await load(movie()); openEp(n); }
  catch (e) { alert(e.message); }
};
$("#save").onclick = async () => {
  try { await saveScene(); msg($("#epMsg"), "Saved.", true); }
  catch (e) { msg($("#epMsg"), e.message); }
};
$("#check").onclick = async () => {
  try {
    await saveScene();
    const r = await post("/api/episode/check", {movie: movie(), episode: curEp});
    const o = $("#checkOut"); o.textContent = r.output; o.classList.remove("hidden");
    msg($("#epMsg"), r.ok ? "Looks good." : "Problems found (see below).", r.ok);
  } catch (e) { msg($("#epMsg"), e.message); }
};
$("#storyboard").onclick = async () => {
  try {
    await saveScene();
    await post("/api/episode/storyboard", {movie: movie(), episode: curEp});
    msg($("#epMsg"), "Making the storyboard (about a minute per scene)…", true);
  } catch (e) { msg($("#epMsg"), e.message); }
};
$("#stop").onclick = async () => {
  try { const r = await post("/api/episode/stop", {movie: movie(), episode: curEp}); msg($("#epMsg"), r.output, true); }
  catch (e) { msg($("#epMsg"), e.message); }
};
$("#finish").onclick = async () => {
  try {
    await saveScene();
    msg($("#epMsg"), "Finishing: titles, transitions, subtitles and sound…", true);
    await post("/api/episode/finish", {movie: movie(), episode: curEp});
    msg($("#epMsg"), "Finished. The video and downloads below are updated.", true);
  } catch (e) { msg($("#epMsg"), e.message); }
};
async function hearLine(text, voice, fx, btn) {
  const label = btn.textContent;
  btn.disabled = true; btn.textContent = "Speaking…";
  try {
    const r = await fetch("/api/voice/preview", {method: "POST", headers: {"Content-Type": "application/json"},
                                                body: JSON.stringify({text, voice, fx})});
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    new Audio(URL.createObjectURL(await r.blob())).play();
  } catch (e) { msg($("#epMsg"), e.message); }
  finally { btn.disabled = false; btn.textContent = label; }
}
$("#dialogueLines").addEventListener("click", e => {
  const b = e.target.closest("[data-hear]");
  if (!b || !sceneModel) return;
  const step = activeScene().script[Number(b.dataset.hear)];
  const cast = {...(sceneModel.cast || {}), ...(activeScene().cast || {})};
  const voice = (cast[step.who] || {}).voice || (sceneModel.narrator || {}).voice;
  hearLine(step.text || "", voice, step.fx, b);
});
$("#render").onclick = async () => {
  try {
    await saveScene();
    const r = await post("/api/episode/render", {movie: movie(), episode: curEp, quality: $("#quality").value});
    msg($("#epMsg"), "Rendering in the background. You can close this page; it keeps going.", true);
  } catch (e) { msg($("#epMsg"), e.message); }
};
$("#copyScenePrompt").onclick = e => copy(prompts.scene, e.target);
$("#copyCharPrompt").onclick = e => copy(prompts.character, e.target);
$("#buildDesign").onclick = async () => {
  try { await post("/api/character/design", {movie: movie(), name: $("#dName").value, design: $("#dJson").value}); msg($("#charMsg"), "Building (about a minute)…", true); }
  catch (e) { msg($("#charMsg"), e.message); }
};
$("#buildPhoto").onclick = async () => {
  const f = new FormData();
  f.append("movie", movie()); f.append("name", $("#pName").value); f.append("gender", $("#pGender").value);
  f.append("age", $("#pAge").value); f.append("height_cm", $("#pHeight").value);
  if (!$("#pPhoto").files[0]) return msg($("#charMsg"), "Choose a body photo.");
  f.append("photo", $("#pPhoto").files[0]); if ($("#pFace").files[0]) f.append("face_photo", $("#pFace").files[0]);
  try { await api("/api/character/photo", {method: "POST", body: f}); msg($("#charMsg"), "Building (about a minute)…", true); }
  catch (e) { msg($("#charMsg"), e.message); }
};

(async () => {
  formSchema = await api("/api/schema");
  setupPropAssetForm();
  prompts = await api("/api/prompts");
  $("#helpText").textContent = prompts.help;
  await load();
  await openMovieScene();
})();
