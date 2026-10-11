import { IMAGES, ROUTES, TAGS, getMockWorkPages, mockWorkContext } from "./data.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const PREFS_KEY = "siftivex.mockup.prefs";
const TAG_BRIDGE_DRAFT_KEY = "siftivex.mockup.tagBridge.draft";
const BRIDGE_SOURCES = ["filename", "auto_tagger", "auto_d1", "inferred_ja", "manual_added"];
const GRID_LAYOUTS = ["justified", "masonry", "square", "table"];

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
  } catch {
    return {};
  }
}

const prefs = {
  theme: "auto",
  gridLayout: "justified",
  thumbSize: 170,
  sort: "file_name",
  /** null = auto-detect on load */
  useApi: null,
  ...loadPrefs(),
};

function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable */
  }
}

const state = {
  /** False until init() has decided between API and mock data. */
  ready: false,
  appMode: "explore",
  query: "",
  route: "all",
  gridLayout: GRID_LAYOUTS.includes(prefs.gridLayout) ? prefs.gridLayout : "justified",
  thumbSize: Number(prefs.thumbSize) || 170,
  sort: prefs.sort || "file_name",
  tagStates: Object.fromEntries(TAGS.map((t) => [t, 0])),
  activeId: null,
  detailIndex: -1,
  useApi: false,
  apiImages: null,
  workContext: null,
  workPages: [],
  originStack: [{ label: "開始", query: "", route: "all", scrollTop: 0 }],
  originIndex: 0,
  savedScrollTop: 0,
  retagBusy: false,
  tagEditMode: false,
  tagEditBusy: false,
  apiTotal: null,
  apiLoadError: null,
  tagBridge: { entries: [], dirty: false, serverUpdatedAt: null },
  tagBridgeMemberLabels: {},
  /** Include/exclude keys that use tag:= (no bridge expansion). */
  tagStateLiteral: new Set(),
  apiPageLimit: 200,
  apiLoadingMore: false,
  indexStatus: null,
  indexStatusError: null,
};

const els = {};

const RETRY_DELAYS_MS = [400, 1200];
const DETAIL_SETTLE_MS = 120;
const CACHE_LIMIT = 400;

let detailSettleTimer = null;
/** Last list position shown in detail; work pages outside the list navigate relative to it. */
let lastListIndex = -1;
let wheelNavRaf = null;
let wheelNavSteps = 0;
/** @type {Map<string, Promise<object|null>>} */
const detailFetchInflight = new Map();
/** @type {Map<string, object>} */
const detailDataCache = new Map();
/** @type {Map<string, object[]>} */
const workPagesCache = new Map();
/** @type {Map<string, Promise<HTMLImageElement|null>>} */
const imageLoadCache = new Map();
/** @type {Map<string, HTMLImageElement>} decoded elements, inserted as-is so display never refetches */
const loadedImages = new Map();

function isActiveDetail(imageId) {
  return !!imageId && state.activeId === imageId;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function cachePut(map, key, value) {
  map.delete(key);
  map.set(key, value);
  if (map.size > CACHE_LIMIT) map.delete(map.keys().next().value);
}

/** Returns parsed JSON, `null` for 404, throws after retries on network / 5xx errors. */
async function fetchJsonRetry(url) {
  let lastErr = null;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    if (attempt > 0) await sleep(RETRY_DELAYS_MS[attempt - 1]);
    try {
      const res = await fetch(url);
      if (res.status === 404) return null;
      if (res.ok) return await res.json();
      lastErr = new Error(`${res.status} ${res.statusText}`);
      if (res.status < 500) break;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr ?? new Error("fetch failed");
}

function withRetryParam(src, attempt) {
  return `${src}${src.includes("?") ? "&" : "?"}r=${attempt}`;
}

function loadImageOnce(src) {
  return new Promise((resolve) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => resolve(img.naturalWidth > 0 ? img : null);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** Resolves to a fully loaded <img> (original URL or a retry variant), or null. */
function loadImage(src) {
  const hit = imageLoadCache.get(src);
  if (hit) return hit;
  const p = (async () => {
    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
      if (attempt > 0) await sleep(RETRY_DELAYS_MS[attempt - 1]);
      const img = await loadImageOnce(attempt === 0 ? src : withRetryParam(src, attempt));
      if (img) {
        cachePut(loadedImages, src, img);
        return img;
      }
    }
    return null;
  })();
  cachePut(imageLoadCache, src, p);
  p.then((img) => {
    if (!img) imageLoadCache.delete(src);
  });
  return p;
}

// List thumbnails: only near-viewport images, at most THUMB_CONCURRENCY in flight.
// A cold-cache burst of ~200 requests through SSH port forwarding drops connections.
const THUMB_CONCURRENCY = 6;
const THUMB_RETRY_MS = [500, 1500, 4000];
const thumbQueue = [];
let thumbActive = 0;
let thumbGen = 0;
let thumbObserver = null;
/** @type {WeakMap<HTMLImageElement, {src: string, onGiveUp: () => void}>} */
const thumbJobs = new WeakMap();

function queueThumb(img, attempt = 0) {
  thumbQueue.push({ img, attempt });
  pumpThumbQueue();
}

function pumpThumbQueue() {
  while (thumbActive < THUMB_CONCURRENCY && thumbQueue.length) {
    const { img, attempt } = thumbQueue.shift();
    const job = thumbJobs.get(img);
    if (!job || !img.isConnected) continue;
    thumbActive += 1;
    const gen = thumbGen;
    const finish = (ok) => {
      img.onload = null;
      img.onerror = null;
      if (gen !== thumbGen) return;
      thumbActive -= 1;
      if (!ok && img.isConnected) {
        if (attempt < THUMB_RETRY_MS.length) {
          setTimeout(() => queueThumb(img, attempt + 1), THUMB_RETRY_MS[attempt]);
        } else {
          job.onGiveUp();
        }
      }
      pumpThumbQueue();
    };
    img.onload = () => finish(true);
    img.onerror = () => finish(false);
    img.src = attempt ? withRetryParam(job.src, attempt) : job.src;
  }
}

function resetThumbObserver(root) {
  thumbObserver?.disconnect();
  thumbQueue.length = 0;
  thumbActive = 0;
  thumbGen += 1;
  thumbObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        thumbObserver.unobserve(entry.target);
        queueThumb(entry.target);
      }
    },
    { root, rootMargin: "400px 0px" },
  );
}

function observeThumb(img, src, onGiveUp) {
  thumbJobs.set(img, { src, onGiveUp });
  thumbObserver.observe(img);
}

/** Retry a DOM <img> a few times before giving up (transient proxy / tunnel failures). */
function attachImgRetry(img, src, onGiveUp) {
  let attempt = 0;
  img.addEventListener("error", () => {
    if (attempt >= RETRY_DELAYS_MS.length) {
      onGiveUp();
      return;
    }
    const delay = RETRY_DELAYS_MS[attempt];
    attempt += 1;
    setTimeout(() => {
      if (img.isConnected) img.src = withRetryParam(src, attempt);
    }, delay);
  });
}

function listScrollEl() {
  return els.listScroll;
}

function svgIcon(id) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#${id}`);
  svg.appendChild(use);
  return svg;
}

/** s: 0 = none, 1 = include, 2 = exclude */
function setTagFilter(tag, s) {
  clearTimeout(debounceTimer);
  if (s === 0) {
    if (TAGS.includes(tag) && !state.useApi) state.tagStates[tag] = 0;
    else delete state.tagStates[tag];
    state.tagStateLiteral.delete(tag);
  } else {
    state.tagStates[tag] = s;
  }
  syncQueryFromTags();
  commitQueryToOrigin();
  if (state.appMode === "view") exitViewMode();
  void refreshList();
}

function toggleTagFilter(tag, exclude) {
  const want = exclude ? 2 : 1;
  setTagFilter(tag, state.tagStates[tag] === want ? 0 : want);
}

function tagNeedsQuotes(tag) {
  return /[\s()"']/.test(tag);
}

function formatTagQueryToken(tag, exclude, { strict = false } = {}) {
  let prefix = exclude ? "-tag:" : "tag:";
  if (strict) prefix += "=";
  if (!tagNeedsQuotes(tag)) return `${prefix}${tag}`;
  const escaped = tag.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return `${prefix}"${escaped}"`;
}

function bridgeLabelForMember(source, tag) {
  return state.tagBridgeMemberLabels[`${source}\0${tag}`] || null;
}

function bridgeLabelForFlatTag(tag) {
  for (const entry of state.tagBridge.entries) {
    const label = (entry.label || "").trim();
    if (!label) continue;
    for (const m of entry.members || []) {
      if ((m.tag || "").trim() === tag) return label;
    }
  }
  return null;
}

/** Filter key for UI clicks: bridge members map to representative label. */
function filterKeyForTagClick(tag, source) {
  const label = source != null ? bridgeLabelForMember(source, tag) : bridgeLabelForFlatTag(tag);
  return label || tag;
}

/** 0 / 1 / 2 — includes bridge-expanded active filters on member chips. */
function tagFilterState(tag, source = null) {
  for (const [key, s] of Object.entries(state.tagStates)) {
    if (s === 0) continue;
    if (state.tagStateLiteral.has(key)) {
      if (key === tag) return s;
      continue;
    }
    if (key === tag) return s;
  }
  for (const [key, s] of Object.entries(state.tagStates)) {
    if (s === 0 || state.tagStateLiteral.has(key)) continue;
    const entry = state.tagBridge.entries.find((e) => (e.label || "").trim() === key);
    if (!entry) continue;
    for (const m of entry.members || []) {
      if ((m.tag || "").trim() !== tag) continue;
      if (source != null && m.source !== source) continue;
      return s;
    }
  }
  return 0;
}

function toggleTagFilterFromUi(tag, source, exclude) {
  const key = filterKeyForTagClick(tag, source);
  toggleTagFilter(key, exclude);
}

function stripTagTokensFromQuery(q) {
  return q
    .replace(/(-?)tag:(=?)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s]+)/gi, "")
    .replace(/similar_to:\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function queryTextOnly(q) {
  return stripTagTokensFromQuery(q);
}

function syncQueryFromTags() {
  const parts = [];
  for (const [tag, s] of Object.entries(state.tagStates)) {
    const strict = state.tagStateLiteral.has(tag);
    if (s === 1) parts.push(formatTagQueryToken(tag, false, { strict }));
    if (s === 2) parts.push(formatTagQueryToken(tag, true, { strict }));
  }
  const text = queryTextOnly(state.query);
  state.query = [...parts, text].filter(Boolean).join(" ").trim();
  if (els.queryInput) els.queryInput.value = state.query;
}

function clearTagFilters() {
  clearTimeout(debounceTimer);
  for (const tag of Object.keys(state.tagStates)) {
    if (TAGS.includes(tag) && !state.useApi) state.tagStates[tag] = 0;
    else delete state.tagStates[tag];
  }
  state.tagStateLiteral.clear();
  syncQueryFromTags();
  commitQueryToOrigin();
  void refreshList();
}

/** CLIP 検索時は API の score 順を使う（デフォルトのファイル名ソートで順序が崩れるのを防ぐ）。 */
function syncSortForNlQuery() {
  if (!state.useApi) return;
  const text = queryTextOnly(state.query.trim());
  if (text) {
    if (state.sort !== "score") {
      if (state._sortBeforeNl == null) state._sortBeforeNl = state.sort;
      state.sort = "score";
      prefs.sort = "score";
      savePrefs();
    }
  } else if (state._sortBeforeNl != null) {
    state.sort = state._sortBeforeNl;
    prefs.sort = state.sort;
    state._sortBeforeNl = null;
    savePrefs();
  }
  if (els.sortSelect) els.sortSelect.value = state.sort;
}

/** New result set: reload from the API (if connected) and start at the top. */
async function refreshList() {
  syncSortForNlQuery();
  if (state.useApi) await tryLoadApi();
  facetShowAll = false;
  els.listScroll.scrollTop = 0;
  render();
}

function parseQueryTags(q) {
  state.tagStates = state.useApi
    ? {}
    : Object.fromEntries(TAGS.map((t) => [t, 0]));
  state.tagStateLiteral = new Set();
  const re = /(-?)tag:(=?)("((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^\s]+))/gi;
  let m;
  while ((m = re.exec(q)) !== null) {
    const excl = m[1] === "-";
    const strict = m[2] === "=";
    let tag = m[3] ?? m[4] ?? m[5] ?? "";
    tag = tag.replace(/\\"/g, '"').replace(/\\'/g, "'");
    if (!tag) continue;
    state.tagStates[tag] = excl ? 2 : 1;
    if (strict && !excl) state.tagStateLiteral.add(tag);
  }
  state.query = q;
}

function applyQueryInput() {
  if (els.queryInput.value === state.query) return;
  state.query = els.queryInput.value;
  parseQueryTags(state.query);
  debouncedRender();
}

function syncRetagButton() {
  if (!els.btnRetag) return;
  const show = false;
  els.btnRetag.hidden = !show;
  els.btnRetag.disabled = !show || state.retagBusy;
  els.btnRetag.textContent = state.retagBusy ? "再タグ中…" : "再タグ";
}

function patchApiImageItem(data) {
  if (!state.apiImages) return;
  const idx = state.apiImages.findIndex((i) => i.image_id === data.image_id);
  const patch = {
    tags: data.tags ?? [],
    tag_sources: data.tag_sources,
    vlm_caption: data.vlm_caption ?? "",
    prompt_revision: data.prompt_revision,
  };
  if (idx >= 0) {
    state.apiImages[idx] = { ...state.apiImages[idx], ...patch };
  }
}

function activeDetailItem() {
  if (!state.activeId) return null;
  return state.apiImages?.find((i) => i.image_id === state.activeId) ?? null;
}

function setTagEditMsg(msg, isError = false) {
  if (!els.tagEditMsg) return;
  const show = !!msg;
  els.tagEditMsg.hidden = !show;
  els.tagEditMsg.textContent = msg || "";
  els.tagEditMsg.classList.toggle("ok", show && !isError);
}

function syncTagEditChrome() {
  const on = state.useApi && state.appMode === "view";
  if (els.tagEditToggleWrap) els.tagEditToggleWrap.hidden = !on;
  if (els.tagEditAddRow) els.tagEditAddRow.hidden = !on || !state.tagEditMode;
  if (els.tagEditToggle) {
    els.tagEditToggle.checked = state.tagEditMode;
    els.tagEditToggle.disabled = state.tagEditBusy;
  }
  if (els.tagEditInput) els.tagEditInput.disabled = state.tagEditBusy;
  if (els.tagEditAddBtn) els.tagEditAddBtn.disabled = state.tagEditBusy;
}

async function patchImageTags(body) {
  if (!state.useApi || !state.activeId || state.tagEditBusy) return;
  state.tagEditBusy = true;
  syncTagEditChrome();
  setTagEditMsg("");
  try {
    const res = await fetch(`/api/images/${encodeURIComponent(state.activeId)}/tags`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        add: body.add || [],
        remove: body.remove || [],
        restore: body.restore || [],
      }),
    });
    if (!res.ok) throw new Error(await readApiError(res));
    const data = await res.json();
    patchApiImageItem(data);
    renderDetailTags(data);
    renderListOnly();
    if (state.gridLayout === "table") render(filteredImages());
  } catch (err) {
    setTagEditMsg(err.message || String(err), true);
  } finally {
    state.tagEditBusy = false;
    syncTagEditChrome();
  }
}

function submitTagEditAdd() {
  const raw = els.tagEditInput?.value?.trim();
  if (!raw) return;
  if (els.tagEditInput) els.tagEditInput.value = "";
  void patchImageTags({ add: [raw] });
}

async function readApiError(res) {
  const raw = await res.text();
  try {
    const data = JSON.parse(raw);
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg ?? JSON.stringify(d)).join("; ");
  } catch {
    /* plain text */
  }
  return raw || res.statusText;
}

async function retagActiveImage() {
  if (!state.useApi || !state.activeId || state.retagBusy) return;
  state.retagBusy = true;
  syncRetagButton();
  try {
    const res = await fetch(`/api/images/${encodeURIComponent(state.activeId)}/retag`, {
      method: "POST",
    });
    if (!res.ok) {
      const detail = await readApiError(res);
      window.alert(`再タグに失敗しました (${res.status})\n\n${detail}`);
      return;
    }
    const data = await res.json();
    patchApiImageItem(data);
    detailDataCache.delete(data.image_id);
    const list = filteredImages();
    renderDetail(list);
    renderListOnly(list);
    if (els.btnRetag) {
      const think = data.thinking_enabled
        ? data.reasoning_chars > 0
          ? `think ${data.reasoning_chars}字`
          : "think 0字?"
        : "think off";
      const rev = data.prompt_revision ? ` · ${data.prompt_revision}` : "";
      els.btnRetag.textContent = `完了 (${think}${rev})`;
      setTimeout(() => syncRetagButton(), 4000);
    }
  } catch (err) {
    console.warn("retag failed:", err);
    window.alert(`再タグに失敗しました: ${err}`);
  } finally {
    state.retagBusy = false;
    syncRetagButton();
  }
}

const NAMESPACE_TAG_RE = /^(種類|画角|アングル|光の方向|人数)\//;

function partitionEffectiveTags(tags) {
  const ns = [];
  const flat = [];
  for (const t of tags || []) {
    if (NAMESPACE_TAG_RE.test(t)) ns.push(t);
    else flat.push(t);
  }
  return { ns, flat };
}

function renderDetailTags(item) {
  els.detailTags.innerHTML = "";
  syncTagEditChrome();
  const editMode = state.useApi && state.tagEditMode;
  const sources = item?.tag_sources;
  if (sources && state.useApi) {
    const layers = [
      ["構造化", "d1 が判定した種類・画角・アングルなど", sources.auto_d1, "src-d1", true, "auto_d1"],
      ["ファイル名・pixiv", "ファイル名や pixiv のタグ", sources.filename, "src-ja", true, "filename"],
      ["Tagger", "画像認識モデルによる英語タグ", sources.auto_tagger, "src-en", false, "auto_tagger"],
      ["推定（日本語）", "", sources.inferred_ja, "src-ja", false, "inferred_ja"],
      ["VLM（旧）", "", sources.auto, "src-en", false, null],
      ["手動", "手動で追加したタグ", sources.manual_added, "src-en", true, "manual_added"],
    ];
    for (const [label, hint, tags, cls, open, chipSource] of layers) {
      appendTagSourceBlock(els.detailTags, label, tags, { cls, open, hint, chipSource, editMode });
    }
    appendHiddenTagsBlock(els.detailTags, sources.manual_removed || [], editMode);
    if (!els.detailTags.childElementCount) {
      els.detailTags.innerHTML = '<p class="detail-tag-legend">タグはまだありません</p>';
    }
    return;
  }
  const row = document.createElement("div");
  row.className = "tag-editor";
  appendTagChips(row, item?.tags || [], { editMode: false });
  els.detailTags.appendChild(row);
}

function appendHiddenTagsBlock(container, removed, editMode) {
  if (!editMode || !removed?.length) return;
  const block = document.createElement("details");
  block.className = "tag-source-block src-en";
  block.open = false;
  const head = document.createElement("summary");
  const dot = document.createElement("span");
  dot.className = "src-dot";
  const name = document.createElement("span");
  name.textContent = "非表示にしたタグ";
  const count = document.createElement("span");
  count.className = "src-count";
  count.textContent = String(removed.length);
  head.append(dot, name, count);
  block.appendChild(head);
  const list = document.createElement("div");
  list.className = "tag-hidden-list";
  for (const t of removed) {
    const row = document.createElement("div");
    row.className = "tag-hidden-row";
    const label = document.createElement("span");
    label.textContent = t;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-ghost";
    btn.textContent = "表示に戻す";
    btn.addEventListener("click", () => void patchImageTags({ restore: [t] }));
    row.append(label, btn);
    list.appendChild(row);
  }
  block.appendChild(list);
  container.appendChild(block);
}

function appendTagSourceBlock(
  container,
  label,
  tags,
  { cls = "", open = false, hint = "", chipSource = null, editMode = false } = {},
) {
  const list = tags || [];
  if (!list.length) return;
  const block = document.createElement("details");
  block.className = `tag-source-block ${cls}`.trim();
  block.open = open;
  const head = document.createElement("summary");
  if (hint) head.title = hint;
  const dot = document.createElement("span");
  dot.className = "src-dot";
  const name = document.createElement("span");
  name.textContent = label;
  const count = document.createElement("span");
  count.className = "src-count";
  count.textContent = String(list.length);
  head.append(dot, name, count);
  block.appendChild(head);
  const row = document.createElement("div");
  row.className = "tag-editor";
  appendTagChips(row, list, { source: chipSource, editMode });
  block.appendChild(row);
  container.appendChild(block);
}

function chipDisplayText(tag, source) {
  if (!source) return tag;
  const label = state.tagBridgeMemberLabels[`${source}\0${tag}`];
  return label ? `${tag}（${label}）` : tag;
}

function appendTagChips(container, tags, { source = null, editMode = false } = {}) {
  for (const t of tags || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tag-chip";
    if (editMode) {
      btn.classList.add("tag-chip-edit");
      btn.textContent = chipDisplayText(t, source);
      btn.title = "クリックで非表示";
      btn.addEventListener("click", () => void patchImageTags({ remove: [t] }));
    } else {
      const fs = tagFilterState(t, source);
      if (fs === 1) btn.classList.add("include");
      if (fs === 2) btn.classList.add("exclude");
      btn.textContent = chipDisplayText(t, source);
      btn.title = "クリックで絞り込み / Shift+クリックで除外";
      btn.addEventListener("click", (e) => toggleTagFilterFromUi(t, source, e.shiftKey));
    }
    container.appendChild(btn);
  }
}

function listTagsPreview(item, max = 8) {
  const tags = item?.tags || [];
  if (!tags.length) return "—";
  const { ns, flat } = partitionEffectiveTags(tags);
  const ordered = [...ns.map((t) => t.split("/").pop()), ...flat];
  const head = ordered.slice(0, max).join(", ");
  return ordered.length > max ? `${head} ほか ${ordered.length - max}` : head;
}

function filteredImages() {
  const src = state.useApi && state.apiImages ? state.apiImages : IMAGES;
  let list = [...src];

  if (state.useApi) {
    list.sort((a, b) => {
      if (state.sort === "score") return (b.score ?? 0) - (a.score ?? 0);
      if (state.sort === "tags") return (b.tags?.length ?? 0) - (a.tags?.length ?? 0);
      return a.file_name.localeCompare(b.file_name);
    });
    return list;
  }

  if (state.route !== "all") list = list.filter((i) => i.route_tag === state.route);

  const sim = state.query.match(/similar_to:(\S+)/);
  if (sim && !state.useApi) {
    const base = IMAGES.find((i) => i.image_id === sim[1]) || list[0];
    list = list.filter((i) => i.image_id !== sim[1]).slice(0, 40);
    if (base) list.unshift(base);
    list.forEach((i, idx) => {
      i.score = +(0.4 - idx * 0.004).toFixed(3);
    });
    return list;
  }

  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 1) list = list.filter((i) => i.tags.includes(tag));
    if (s === 2) list = list.filter((i) => !i.tags.includes(tag));
  }
  const text = queryTextOnly(state.query);
  if (text && !state.useApi) {
    const lower = text.toLowerCase();
    list = list.filter(
      (i) =>
        i.file_name.toLowerCase().includes(lower) ||
        i.tags.some((t) => t.includes(text)) ||
        (i.vlm_caption && i.vlm_caption.includes(text)),
    );
    list.forEach((i, idx) => {
      i.score = +(0.42 - idx * 0.003).toFixed(3);
    });
  }
  list.sort((a, b) => {
    if (state.sort === "score") return (b.score ?? 0) - (a.score ?? 0);
    if (state.sort === "tags") return b.tags.length - a.tags.length;
    return a.file_name.localeCompare(b.file_name);
  });
  return list;
}

function originLabel(query) {
  if (!query) return "開始";
  if (query.startsWith("similar_to:")) return `類似 ${query.slice(11, 22)}…`;
  return query.length > 18 ? `${query.slice(0, 18)}…` : query;
}

function commitQueryToOrigin() {
  const cur = state.originStack[state.originIndex];
  if (cur && cur.query === state.query && cur.route === state.route) return;
  state.originStack = state.originStack.slice(0, state.originIndex + 1);
  state.originStack.push({
    label: originLabel(state.query),
    query: state.query,
    route: state.route,
    scrollTop: listScrollEl()?.scrollTop ?? 0,
  });
  if (state.originStack.length > 5) state.originStack.shift();
  else state.originIndex += 1;
}

function renderBreadcrumb() {
  els.breadcrumb.innerHTML = "";
  els.breadcrumb.hidden = state.originStack.length < 2;
  state.originStack.forEach((entry, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "origin-sep";
      sep.textContent = "›";
      els.breadcrumb.appendChild(sep);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = entry.label;
    btn.title = entry.query || "（空）";
    btn.classList.toggle("active", idx === state.originIndex);
    btn.addEventListener("click", () => jumpToOrigin(idx));
    els.breadcrumb.appendChild(btn);
  });
}

function jumpToOrigin(idx) {
  const entry = state.originStack[idx];
  if (!entry) return;
  state.originIndex = idx;
  state.query = entry.query;
  state.route = entry.route;
  els.queryInput.value = state.query;
  parseQueryTags(state.query);
  void (async () => {
    if (state.useApi) await tryLoadApi();
    render();
    requestAnimationFrame(() => {
      listScrollEl().scrollTop = entry.scrollTop;
    });
  })();
}

function appendThumbPlaceholder(el, item, mode) {
  const ph = document.createElement("div");
  ph.className = mode === "table" ? "table-thumb-ph" : "thumb-placeholder";
  if (item.thumbStyle?.background) ph.style.background = item.thumbStyle.background;
  ph.title = item.has_thumbnail === false ? "サムネ未生成" : "読み込み失敗";
  el.appendChild(ph);
}

function renderThumb(el, item, mode = "grid") {
  if (mode === "table") el.className = "table-thumb-cell";
  if (item.thumb_url) {
    const img = document.createElement("img");
    img.className = mode === "table" ? "table-thumb" : "thumb";
    img.alt = "";
    img.title = item.file_name;
    el.appendChild(img);
    observeThumb(img, item.thumb_url, () => {
      img.remove();
      appendThumbPlaceholder(el, item, mode);
    });
    return;
  }
  appendThumbPlaceholder(el, item, mode);
}

function itemAspect(item) {
  const w = Number(item.width);
  const h = Number(item.height);
  const a = w > 0 && h > 0 ? w / h : 0.75;
  return Math.min(3, Math.max(0.33, a));
}

function createCard(item) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "image-card";
  card.dataset.id = item.image_id;
  card.setAttribute("aria-label", item.file_name);
  if (item.image_id === state.activeId) card.classList.add("active");
  renderThumb(card, item);
  card.addEventListener("click", () => openDetail(item.image_id, filteredImages()));
  return card;
}

let lastGridWidth = 0;

function gridContentWidth() {
  return els.grid.clientWidth || els.listScroll.clientWidth - 8;
}

function layoutJustified(list, width) {
  const gap = parseFloat(getComputedStyle(els.grid).columnGap) || 4;
  const target = state.thumbSize;
  let row = [];
  let aspectSum = 0;
  const flush = (isLast) => {
    const rowEl = document.createElement("div");
    rowEl.className = "jrow";
    const fullHeight = (width - gap * (row.length - 1)) / aspectSum;
    const h = isLast ? Math.min(target, fullHeight) : fullHeight;
    for (const item of row) {
      const card = createCard(item);
      const a = itemAspect(item);
      card.style.height = `${h}px`;
      card.style.flex = isLast ? `0 0 ${a * h}px` : `${a} 1 0`;
      rowEl.appendChild(card);
    }
    els.grid.appendChild(rowEl);
    row = [];
    aspectSum = 0;
  };
  for (const item of list) {
    row.push(item);
    aspectSum += itemAspect(item);
    if (aspectSum * target + gap * (row.length - 1) >= width) flush(false);
  }
  if (row.length) flush(true);
}

function layoutMasonry(list, width) {
  const gap = parseFloat(getComputedStyle(els.grid).columnGap) || 4;
  const cols = Math.max(1, Math.floor((width + gap) / (state.thumbSize + gap)));
  const colWidth = (width - gap * (cols - 1)) / cols;
  const colEls = [];
  const heights = new Array(cols).fill(0);
  for (let i = 0; i < cols; i += 1) {
    const col = document.createElement("div");
    col.className = "mcol";
    els.grid.appendChild(col);
    colEls.push(col);
  }
  for (const item of list) {
    const c = heights.indexOf(Math.min(...heights));
    const a = itemAspect(item);
    const card = createCard(item);
    card.style.aspectRatio = String(a);
    colEls[c].appendChild(card);
    heights[c] += colWidth / a + gap;
  }
}

function renderGrid(list) {
  resetThumbObserver(els.listScroll);
  els.grid.innerHTML = "";
  els.grid.className = `image-grid layout-${state.gridLayout}`;
  const width = gridContentWidth();
  lastGridWidth = width;
  if (state.gridLayout === "justified" && width > 0) layoutJustified(list, width);
  else if (state.gridLayout === "masonry" && width > 0) layoutMasonry(list, width);
  else for (const item of list) els.grid.appendChild(createCard(item));
}

function tableCell(className, text, title) {
  const td = document.createElement("td");
  td.className = className;
  td.textContent = text;
  if (title) td.title = title;
  return td;
}

function renderTable(list) {
  resetThumbObserver(els.listScroll);
  els.tableBody.innerHTML = "";
  for (const item of list) {
    const tr = document.createElement("tr");
    tr.dataset.id = item.image_id;
    if (item.image_id === state.activeId) tr.classList.add("active");
    const thumbTd = document.createElement("td");
    thumbTd.className = "col-thumb";
    const cell = document.createElement("div");
    thumbTd.appendChild(cell);
    renderThumb(cell, item, "table");
    tr.append(
      thumbTd,
      tableCell("col-filename", item.file_name, item.file_name),
      tableCell("col-route", routeLabel(item.route_tag)),
      tableCell("col-dims", item.width && item.height ? `${item.width}×${item.height}` : "—"),
      tableCell("col-tags", listTagsPreview(item), (item.tags || []).join(", ")),
      tableCell("col-score", item.score != null ? item.score.toFixed(3) : "—"),
    );
    tr.addEventListener("click", () => openDetail(item.image_id, filteredImages()));
    els.tableBody.appendChild(tr);
  }
}

function routeOptions() {
  const by = state.indexStatus?.tag_stack_by_route ?? {};
  const total = state.useApi ? state.indexStatus?.images_active : IMAGES.length;
  return [
    { id: "all", label: "すべて", count: total },
    ...ROUTES.map((r) => ({
      id: r.id,
      label: r.label,
      count: state.useApi ? by[r.id]?.active : IMAGES.filter((i) => i.route_tag === r.id).length,
    })),
  ];
}

function renderRoutes() {
  els.routeList.innerHTML = "";
  for (const r of routeOptions()) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "route-item";
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", String(state.route === r.id));
    const name = document.createElement("span");
    name.className = "route-name";
    name.textContent = r.label;
    const count = document.createElement("span");
    count.className = "route-count";
    count.textContent = r.count != null ? r.count.toLocaleString() : "";
    btn.append(name, count);
    btn.addEventListener("click", () => {
      if (state.route === r.id) return;
      state.route = r.id;
      commitQueryToOrigin();
      closeOverlays();
      void refreshList();
    });
    els.routeList.appendChild(btn);
  }
}

const FACET_TOP = 40;
let facetShowAll = false;

function computeFacets(list) {
  const counts = new Map();
  for (const item of list) {
    for (const t of item.tags || []) counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s !== 0 && !counts.has(tag)) counts.set(tag, 0);
  }
  const groups = new Map();
  const flat = [];
  for (const [tag, count] of counts) {
    const m = tag.match(NAMESPACE_TAG_RE);
    if (m) {
      if (!groups.has(m[1])) groups.set(m[1], []);
      groups.get(m[1]).push({ tag, label: tag.slice(m[0].length), count });
    } else {
      flat.push({ tag, label: tag, count });
    }
  }
  const byCount = (a, b) => b.count - a.count || a.label.localeCompare(b.label);
  for (const rows of groups.values()) rows.sort(byCount);
  flat.sort(byCount);
  return { groups, flat };
}

function facetRow(row, max) {
  const s = tagFilterState(row.tag, null);
  const el = document.createElement("div");
  el.className = `facet-row${s === 1 ? " include" : s === 2 ? " exclude" : ""}`;
  el.style.setProperty("--p", `${max ? Math.round((row.count / max) * 100) : 0}%`);
  const name = document.createElement("button");
  name.type = "button";
  name.className = "facet-name";
  name.textContent = row.label;
  name.title = `${row.tag}（クリックで絞り込み / Shift+クリックで除外）`;
  el.addEventListener("click", (e) => {
    if (e.target.closest(".facet-x")) return;
    toggleTagFilterFromUi(row.tag, null, e.shiftKey);
  });
  const count = document.createElement("span");
  count.className = "facet-count";
  count.textContent = String(row.count);
  const x = document.createElement("button");
  x.type = "button";
  x.className = "facet-x";
  x.setAttribute("aria-label", `${row.tag} を除外`);
  x.title = "除外";
  x.textContent = "−";
  x.addEventListener("click", () => toggleTagFilterFromUi(row.tag, null, true));
  el.append(name, count, x);
  return el;
}

function renderFacets(list = filteredImages()) {
  const filter = els.tagFilter.value.trim().toLowerCase();
  const { groups, flat } = computeFacets(list);
  const max = list.length;
  els.facetBasis.textContent = list.length ? `${list.length.toLocaleString()} 件から集計` : "";
  els.tagList.innerHTML = "";
  const match = (r) => !filter || r.tag.toLowerCase().includes(filter);

  for (const [ns, rows] of groups) {
    const shown = rows.filter(match);
    if (!shown.length) continue;
    const g = document.createElement("div");
    g.className = "facet-group";
    const title = document.createElement("h3");
    title.className = "facet-group-title";
    title.textContent = ns;
    g.appendChild(title);
    for (const r of shown) g.appendChild(facetRow(r, max));
    els.tagList.appendChild(g);
  }

  const flatShown = flat.filter(match);
  if (flatShown.length) {
    const g = document.createElement("div");
    g.className = "facet-group";
    if (groups.size) {
      const title = document.createElement("h3");
      title.className = "facet-group-title";
      title.textContent = "タグ";
      g.appendChild(title);
    }
    const limit = filter || facetShowAll ? flatShown.length : FACET_TOP;
    for (const r of flatShown.slice(0, limit)) g.appendChild(facetRow(r, max));
    if (flatShown.length > limit) {
      const more = document.createElement("button");
      more.type = "button";
      more.className = "link-btn facet-more";
      more.textContent = `残り ${flatShown.length - limit} 件を表示`;
      more.addEventListener("click", () => {
        facetShowAll = true;
        renderFacets();
      });
      g.appendChild(more);
    }
    els.tagList.appendChild(g);
  }

  if (!els.tagList.childElementCount) {
    const p = document.createElement("p");
    p.className = "facet-empty";
    p.textContent = filter ? "一致するタグはありません" : "表示中の結果にタグがありません";
    els.tagList.appendChild(p);
  }
}

function renderChips() {
  els.chipRow.innerHTML = "";
  let n = 0;
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 0) continue;
    n += 1;
    const chip = document.createElement("span");
    chip.className = `filter-chip${s === 2 ? " exclude" : ""}`;
    chip.title = s === 2 ? `${tag} を除外中` : `${tag} を含む`;
    const text = document.createElement("span");
    text.className = "chip-text";
    text.textContent = formatTagQueryToken(tag, s === 2, {
      strict: state.tagStateLiteral.has(tag),
    });
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "x";
    btn.setAttribute("aria-label", `${tag} の絞り込みを解除`);
    btn.appendChild(svgIcon("i-close"));
    btn.addEventListener("click", () => setTagFilter(tag, 0));
    chip.append(text, btn);
    els.chipRow.appendChild(chip);
  }
  els.activeFilters.dataset.empty = String(n === 0);
  els.queryError.hidden = !state.apiLoadError;
  els.queryError.textContent = state.apiLoadError
    ? `検索に失敗しました（${state.apiLoadError}）。API サーバーが起動しているか確認してください。`
    : "";
}

function enterViewMode() {
  if (state.appMode === "view") return;
  state.savedScrollTop = listScrollEl()?.scrollTop ?? 0;
  state.appMode = "view";
  history.pushState({ siftivexView: true }, "");
  applyShellClasses();
}

function exitViewMode({ fromHistory = false } = {}) {
  state.tagEditMode = false;
  setTagEditMsg("");
  if (state.appMode !== "view") return;
  state.appMode = "explore";
  applyShellClasses();
  if (!fromHistory && history.state?.siftivexView) history.back();
  requestAnimationFrame(() => {
    listScrollEl().scrollTop = state.savedScrollTop;
    const active = state.activeId
      ? els.listScroll.querySelector(`[data-id="${CSS.escape(state.activeId)}"]`)
      : null;
    active?.scrollIntoView({ block: "nearest" });
    if (active?.matches("button")) active.focus({ preventScroll: true });
  });
}

function openDetail(id, list) {
  state.activeId = id;
  const fresh = list ?? filteredImages();
  state.detailIndex = fresh.findIndex((i) => i.image_id === id);
  enterViewMode();
  renderDetail(fresh);
  renderListOnly(fresh);
}

function pageThumbUrl(p) {
  if (p.thumb_url) return p.thumb_url;
  if (p.has_thumbnail && p.image_id) return `/api/images/${p.image_id}/thumbnail`;
  return null;
}

async function fetchWorkContext(imageId, item = null) {
  if (!state.useApi) return mockWorkContext(imageId);

  let data = item;
  if (data?.metadata == null && data?.work == null) {
    data = await fetchApiImageDetailCached(imageId);
    if (!data) return null;
  }

  const meta = data.metadata ?? null;
  const work = data.work ?? null;

  if (work) {
    const pageCount = work.page_count ?? 1;
    return {
      ...work,
      title: work.title ?? meta?.title ?? null,
      artist: work.artist ?? meta?.artist ?? null,
      posted_at: work.posted_at ?? meta?.posted_at ?? null,
      source_url: work.source_url ?? meta?.source_url ?? null,
      work_id: work.work_id ?? meta?.work_id ?? null,
      multi_page: pageCount > 1,
    };
  }

  if (meta) {
    return {
      ...meta,
      page_count: 1,
      multi_page: false,
    };
  }

  return null;
}

/** Merge image + work context into display fields (route-agnostic). */
function readDisplayMeta(item, workCtx) {
  const meta = item.metadata ?? {};
  return {
    title: workCtx?.title ?? meta.title ?? item.work_title ?? item.title ?? null,
    artist: workCtx?.artist ?? meta.artist ?? item.work_artist ?? item.artist ?? null,
    posted_at: workCtx?.posted_at ?? meta.posted_at ?? item.posted_at ?? null,
    source_url: workCtx?.source_url ?? meta.source_url ?? item.source_url ?? null,
    work_id: workCtx?.work_id ?? meta.work_id ?? item.work_id ?? null,
  };
}

function contextTitle(item, displayMeta) {
  return displayMeta.title || item.file_name;
}

function sourceLinkLabel(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "link";
  }
}

function routeLabel(route) {
  if (!route) return "—";
  return route.startsWith("route/") ? route.slice(6) : route;
}

function renderSubline(item, displayMeta) {
  els.detailSubline.innerHTML = "";
  const entries = [];
  if (displayMeta.artist) entries.push({ kind: "text", text: displayMeta.artist });
  if (displayMeta.posted_at) entries.push({ kind: "text", text: displayMeta.posted_at, dim: true });
  if (displayMeta.source_url) {
    entries.push({
      kind: "link",
      href: displayMeta.source_url,
      text: sourceLinkLabel(displayMeta.source_url),
    });
  }
  if (entries.length === 0 && item.width && item.height) {
    entries.push({ kind: "text", text: `${item.width}×${item.height}`, dim: true });
  }
  for (const entry of entries) {
    if (entry.kind === "link") {
      const a = document.createElement("a");
      a.href = entry.href;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = entry.text;
      a.appendChild(svgIcon("i-external"));
      els.detailSubline.appendChild(a);
    } else {
      const span = document.createElement("span");
      if (entry.dim) span.className = "dim";
      span.textContent = entry.text;
      els.detailSubline.appendChild(span);
    }
  }
}

async function fetchWorkPages(workId) {
  if (!state.useApi) {
    return getMockWorkPages(workId).map((p) => ({
      ...p,
      thumb_url: p.thumb_url ?? null,
    }));
  }
  const key = String(workId);
  const cached = workPagesCache.get(key);
  if (cached) return cached;
  const data = await fetchJsonRetry(`/api/works/${encodeURIComponent(workId)}/pages?limit=500`);
  const pages = (data?.items ?? []).map((p) => ({
    ...p,
    thumb_url: p.has_thumbnail ? `/api/images/${p.image_id}/thumbnail` : null,
  }));
  cachePut(workPagesCache, key, pages);
  return pages;
}

async function fetchApiImageDetail(imageId) {
  const data = await fetchJsonRetry(`/api/images/${encodeURIComponent(imageId)}`);
  if (!data) return null;
  return {
    ...data,
    thumb_url: data.has_thumbnail ? `/api/images/${data.image_id}/thumbnail` : null,
    preview_url: data.has_preview ? `/api/images/${data.image_id}/preview` : null,
  };
}

function fetchApiImageDetailCached(imageId) {
  const done = detailDataCache.get(imageId);
  if (done) return Promise.resolve(done);
  const existing = detailFetchInflight.get(imageId);
  if (existing) return existing;
  const p = fetchApiImageDetail(imageId)
    .then((data) => {
      if (data) cachePut(detailDataCache, imageId, data);
      return data;
    })
    .finally(() => {
      detailFetchInflight.delete(imageId);
    });
  detailFetchInflight.set(imageId, p);
  return p;
}

function fillDl(dl, rows) {
  dl.innerHTML = "";
  for (const [label, value] of rows) {
    if (value == null || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
  }
}

function renderDetailMeta(item) {
  fillDl(els.detailMeta, [
    ["ファイル", item.file_name],
    ["ルート", routeLabel(item.route_tag)],
    ["寸法", item.width && item.height ? `${item.width} × ${item.height}` : null],
    ["ID", item.image_id],
  ]);
}

function renderDetailTagsError() {
  els.detailTags.innerHTML = "";
  const p = document.createElement("p");
  p.className = "detail-tag-legend";
  p.textContent = "タグの読み込みに失敗しました（API / ネットワーク） ";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn-ghost";
  btn.textContent = "再試行";
  btn.addEventListener("click", () => renderDetail(filteredImages()));
  p.appendChild(btn);
  els.detailTags.appendChild(p);
}

function resolveDetailItemSync(list) {
  const fromList = state.detailIndex >= 0 ? list[state.detailIndex] : null;
  if (fromList?.image_id === state.activeId) return fromList;
  if (!state.useApi) return IMAGES.find((i) => i.image_id === state.activeId) ?? null;
  return state.apiImages?.find((i) => i.image_id === state.activeId) ?? null;
}

function bestDetailSrcs(item) {
  if (!item?.image_id) return { preview: null, thumb: null };
  const preview =
    item.preview_url ??
    (item.has_preview ? `/api/images/${item.image_id}/preview` : null);
  const thumb =
    item.thumb_url ??
    (item.has_thumbnail ? `/api/images/${item.image_id}/thumbnail` : null);
  return { preview, thumb };
}

function detailImageSrc(item) {
  const { preview, thumb } = bestDetailSrcs(item);
  return preview || thumb || null;
}

function createDetailPlaceholder(item, message = "") {
  const ph = document.createElement("div");
  ph.className = "detail-ph";
  Object.assign(ph.style, item.thumbStyle || { minHeight: "240px" });
  if (message) {
    const msg = document.createElement("span");
    msg.className = "detail-ph-msg";
    msg.textContent = message;
    ph.appendChild(msg);
  }
  return ph;
}

/** `kind`: thumb | preview | failed | none — which image is currently shown for `imageId`. */
function shownDetailImage() {
  return {
    imageId: els.detailImage.dataset.imageId || null,
    kind: els.detailImage.dataset.kind || null,
  };
}

function markDetailImage(imageId, kind) {
  els.detailImage.dataset.imageId = imageId;
  els.detailImage.dataset.kind = kind;
  els.detailImage.classList.remove("is-stale");
}

function showDetailImg(item, loadedImg, kind) {
  const shown = shownDetailImage();
  if (kind === "thumb" && shown.imageId === item.image_id && shown.kind === "preview") return;
  loadedImg.alt = "";
  loadedImg.title = item.file_name;
  if (els.detailImage.firstChild !== loadedImg || els.detailImage.childNodes.length !== 1) {
    els.detailImage.replaceChildren(loadedImg);
  }
  markDetailImage(item.image_id, kind);
}

function showDetailFailure(item, message) {
  const ph = createDetailPlaceholder(item, message);
  ph.addEventListener("click", () => {
    if (isActiveDetail(item.image_id)) void updateDetailImage(item);
  });
  els.detailImage.replaceChildren(ph);
  markDetailImage(item.image_id, "failed");
}

function showCachedThumbNow(item) {
  const { thumb } = bestDetailSrcs(item);
  const img = thumb ? loadedImages.get(thumb) : null;
  if (!img) return false;
  showDetailImg(item, img, "thumb");
  return true;
}

async function updateDetailImage(item, { withPreview = true } = {}) {
  const imageId = item?.image_id;
  if (!isActiveDetail(imageId)) return;

  const { preview, thumb } = bestDetailSrcs(item);
  if (!preview && !thumb) {
    els.detailImage.replaceChildren(createDetailPlaceholder(item, "サムネ／プレビュー未生成"));
    markDetailImage(imageId, "none");
    return;
  }

  const shown = shownDetailImage();
  if (shown.imageId === imageId && shown.kind === "preview") return;
  if (shown.imageId !== imageId) els.detailImage.classList.add("is-stale");

  const wantPreview = withPreview && preview && preview !== thumb;
  const previewP = wantPreview ? loadImage(preview) : null;
  if (thumb) {
    const img = await loadImage(thumb);
    if (!isActiveDetail(imageId)) return;
    if (img) showDetailImg(item, img, "thumb");
  }
  const previewLoad = previewP ?? (!thumb && preview ? loadImage(preview) : null);
  if (previewLoad) {
    const img = await previewLoad;
    if (!isActiveDetail(imageId)) return;
    if (img) {
      showDetailImg(item, img, "preview");
      return;
    }
  }
  if (!withPreview && wantPreview) return;
  if (shownDetailImage().imageId !== imageId) {
    showDetailFailure(item, `${item.file_name} を読み込めませんでした（クリックで再試行）`);
  }
}

function prefetchDetailNeighbors(list) {
  if (!list.length || state.detailIndex < 0) return;
  const n = list.length;
  for (const delta of [1, -1, 2, -2]) {
    const { preview, thumb } = bestDetailSrcs(list[(state.detailIndex + delta + n) % n]);
    if (thumb) void loadImage(thumb);
    if (Math.abs(delta) === 1 && preview && preview !== thumb) void loadImage(preview);
  }
}

function renderPageStrip(activeId, pages, workId) {
  els.pageStrip.innerHTML = "";
  els.pageStrip.dataset.workId = String(workId ?? "");
  for (const p of pages) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `page-strip-item${p.image_id === activeId ? " active" : ""}`;
    btn.dataset.id = p.image_id;
    btn.title = p.file_name || `p${p.page ?? "?"}`;
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = p.page != null ? `p${p.page}` : "?";
    const thumbUrl = pageThumbUrl(p);
    const appendPh = () => {
      const ph = document.createElement("span");
      ph.className = "ph";
      Object.assign(ph.style, p.thumbStyle || { background: "#333" });
      btn.insertBefore(ph, label);
    };
    btn.appendChild(label);
    if (thumbUrl) {
      const img = document.createElement("img");
      img.alt = "";
      attachImgRetry(img, thumbUrl, () => {
        img.remove();
        appendPh();
      });
      img.src = thumbUrl;
      btn.insertBefore(img, label);
    } else {
      appendPh();
    }
    btn.addEventListener("click", () => navWorkPage(p.image_id));
    els.pageStrip.appendChild(btn);
  }
  scrollPageStripToActive();
}

function scrollPageStripToActive() {
  requestAnimationFrame(() => {
    els.pageStrip.querySelector(".active")?.scrollIntoView({ inline: "center", block: "nearest" });
  });
}

/** Strip already shows this image's work: move the highlight without rebuilding. */
function highlightPageStrip(imageId) {
  const btn = els.pageStrip.querySelector(`.page-strip-item[data-id="${CSS.escape(imageId)}"]`);
  if (!btn) return false;
  els.pageStrip.querySelectorAll(".page-strip-item.active").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  scrollPageStripToActive();
  return true;
}

function beginDetailContext(item) {
  els.detailContext.classList.remove("is-error");
  if (highlightPageStrip(item.image_id)) return;
  els.detailContext.classList.add("is-loading");
  els.detailTitle.textContent = item.file_name || "…";
  els.detailSubline.innerHTML = "";
}

function clearPageStrip() {
  els.pageStrip.innerHTML = "";
  els.pageStrip.dataset.workId = "";
  els.workPos.textContent = "—";
  els.workPrev.disabled = true;
  els.workNext.disabled = true;
  els.detailPageSlot.classList.remove("has-pages");
}

async function renderDetailContext(item, attempt = 0) {
  const imageId = item.image_id;
  if (!isActiveDetail(imageId)) return;

  let workCtx = null;
  let pages = null;
  try {
    workCtx = await fetchWorkContext(imageId, item);
    if (workCtx?.multi_page && workCtx.work_id != null) pages = await fetchWorkPages(workCtx.work_id);
  } catch {
    if (!isActiveDetail(imageId)) return;
    if (attempt < 2) {
      setTimeout(() => void renderDetailContext(item, attempt + 1), 1500 * (attempt + 1));
      return;
    }
    els.detailContext.classList.remove("is-loading");
    els.detailContext.classList.add("is-error");
    els.detailSubline.textContent = "作品情報を読み込めませんでした（← → で再試行）";
    return;
  }
  if (!isActiveDetail(imageId)) return;

  const displayMeta = readDisplayMeta(item, workCtx);
  state.workContext = workCtx?.multi_page ? workCtx : null;
  els.detailTitle.textContent = contextTitle(item, displayMeta);
  renderSubline(item, displayMeta);

  if (workCtx?.multi_page) {
    const pageLabel = workCtx.page ?? workCtx.page_index ?? 0;
    els.workPos.textContent = `p${pageLabel} / ${workCtx.page_count}`;
    els.workPrev.disabled = !workCtx.prev_image_id;
    els.workNext.disabled = !workCtx.next_image_id;
    els.detailPageSlot.classList.add("has-pages");
    const sameWork = els.pageStrip.dataset.workId === String(workCtx.work_id);
    if (!(sameWork && highlightPageStrip(imageId))) {
      renderPageStrip(imageId, pages ?? [], workCtx.work_id);
    }
  } else {
    clearPageStrip();
  }
  els.detailContext.classList.remove("is-loading", "is-error");
}

function navWorkPage(imageId) {
  state.activeId = imageId;
  const list = filteredImages();
  state.detailIndex = list.findIndex((i) => i.image_id === imageId);
  renderDetail(list);
  renderListOnly(list);
}

function navWork(delta) {
  if (!state.workContext) return;
  const target = delta < 0 ? state.workContext.prev_image_id : state.workContext.next_image_id;
  if (target) navWorkPage(target);
}

/**
 * Detail pipeline: render list data synchronously, then after navigation settles
 * (DETAIL_SETTLE_MS without another step) fetch detail JSON, preview and work context.
 * Every async step re-checks `state.activeId`, so late responses are dropped.
 */
function renderDetail(list) {
  const imageId = state.activeId;
  if (!imageId) {
    els.detailEmpty.hidden = false;
    els.detailContent.hidden = true;
    state.workContext = null;
    return;
  }
  const fromList = resolveDetailItemSync(list);
  const cached = detailDataCache.get(imageId);
  const base = cached
    ? { ...fromList, ...cached }
    : fromList ??
      (state.useApi ? { image_id: imageId, file_name: "…", route_tag: null, tags: [] } : null);
  if (!base) {
    els.detailEmpty.hidden = false;
    els.detailContent.hidden = true;
    state.workContext = null;
    return;
  }

  if (state.detailIndex >= 0) lastListIndex = state.detailIndex;
  renderDetailBody(list, base);
  beginDetailContext(base);
  if (!showCachedThumbNow(base)) void updateDetailImage(base, { withPreview: false });

  clearTimeout(detailSettleTimer);
  detailSettleTimer = setTimeout(() => {
    detailSettleTimer = null;
    if (isActiveDetail(imageId)) void settleDetail(imageId, base, list);
  }, DETAIL_SETTLE_MS);
}

async function settleDetail(imageId, base, list) {
  const baseHasMedia = !!detailImageSrc(base);
  if (baseHasMedia || !state.useApi) {
    void updateDetailImage(base).then(() => {
      if (isActiveDetail(imageId)) prefetchDetailNeighbors(list);
    });
  }
  if (!state.useApi) {
    void renderDetailContext(base);
    return;
  }

  let full;
  try {
    full = await fetchApiImageDetailCached(imageId);
  } catch {
    full = undefined;
  }
  if (!isActiveDetail(imageId)) return;

  if (full) {
    patchApiImageItem(full);
    if (full.tag_sources) renderDetailTags(full);
    else renderDetailTagsError();
    renderDetailMeta(full);
    if (!baseHasMedia) void updateDetailImage(full);
    void renderDetailContext(full);
    return;
  }
  renderDetailTagsError();
  if (!baseHasMedia) showDetailFailure(base, "詳細を読み込めませんでした（クリックで再試行）");
  void renderDetailContext(base);
}

function syncDetailChrome(list) {
  if (!state.activeId) return;
  const idx = list.findIndex((i) => i.image_id === state.activeId);
  if (idx >= 0) state.detailIndex = idx;
  renderListOnly(list);
  els.detailPos.textContent = idx >= 0 ? `${idx + 1} / ${list.length}` : "—";
  if (detailSettleTimer != null) return;
  const shown = shownDetailImage();
  if (shown.imageId !== state.activeId || shown.kind === "failed") renderDetail(list);
}

function renderDetailBody(list, item) {
  els.detailEmpty.hidden = true;
  els.detailContent.hidden = false;
  els.detailPos.textContent =
    state.detailIndex >= 0 ? `${state.detailIndex + 1} / ${list.length}` : "—";

  els.detailTags.innerHTML = "";
  if (state.useApi && !item.tag_sources) {
    els.detailTags.innerHTML = '<p class="detail-tag-legend">タグを読み込み中…</p>';
  } else {
    renderDetailTags(item);
  }
  syncRetagButton();
  renderDetailMeta(item);
}

function renderListOnly() {
  els.listScroll.querySelectorAll("[data-id].active").forEach((el) => el.classList.remove("active"));
  if (!state.activeId) return;
  els.listScroll
    .querySelectorAll(`[data-id="${CSS.escape(state.activeId)}"]`)
    .forEach((el) => el.classList.add("active"));
}

function applyShellClasses() {
  els.app.classList.toggle("mode-view", state.appMode === "view");
  els.app.classList.toggle("mode-explore", state.appMode !== "view");
}

function renderCount(list) {
  els.resultCount.innerHTML = "";
  const shown = document.createTextNode(`${list.length.toLocaleString()} 件`);
  els.resultCount.appendChild(shown);
  if (state.useApi && state.apiTotal != null && state.apiTotal > list.length) {
    const total = document.createElement("span");
    total.className = "count-total";
    total.textContent = ` / ${state.apiTotal.toLocaleString()}`;
    els.resultCount.appendChild(total);
  }
}

function renderListEmpty(list) {
  const empty = list.length === 0;
  els.listEmpty.hidden = !empty;
  if (!empty) return;
  els.listEmpty.innerHTML = "";
  const p = document.createElement("p");
  const hasFilters = Object.values(state.tagStates).some((s) => s !== 0) || queryTextOnly(state.query);
  p.textContent = state.apiLoadError
    ? "検索結果を取得できませんでした。"
    : hasFilters
      ? "条件に合う画像はありません。"
      : "画像がありません。";
  els.listEmpty.appendChild(p);
  if (hasFilters) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn";
    btn.textContent = "絞り込みを解除";
    btn.addEventListener("click", () => {
      els.queryInput.value = "";
      state.query = "";
      clearTagFilters();
    });
    els.listEmpty.appendChild(btn);
  }
}

function renderList(list) {
  const scrollTop = els.listScroll.scrollTop;
  const isTable = state.gridLayout === "table";
  els.grid.hidden = isTable;
  els.tableWrap.hidden = !isTable;
  if (isTable) {
    els.grid.innerHTML = "";
    renderTable(list);
  } else {
    els.tableBody.innerHTML = "";
    renderGrid(list);
  }
  els.listScroll.scrollTop = scrollTop;
}

function render() {
  if (!state.ready) return;
  const list = filteredImages();
  renderCount(list);
  renderBreadcrumb();
  renderRoutes();
  renderChips();
  renderFacets(list);
  renderList(list);
  renderListEmpty(list);
  if (state.activeId) syncDetailChrome(list);
  syncLoadMoreButton();
  syncToolbarControls();
  applyShellClasses();
}

function mapApiImageItems(items) {
  return (items || []).map((item) => ({
    ...item,
    thumb_url: item.has_thumbnail ? `/api/images/${item.image_id}/thumbnail` : null,
    preview_url: item.has_preview ? `/api/images/${item.image_id}/preview` : null,
    ocr_text: "",
  }));
}

function buildSearchParams(offset) {
  const params = new URLSearchParams({
    limit: String(state.apiPageLimit),
    offset: String(offset),
  });
  params.set("q", state.query.replace(/similar_to:\S+/g, "").trim());
  if (state.route !== "all") params.set("route_tag", state.route);
  return params;
}

async function tryLoadApi({ append = false } = {}) {
  if (!state.useApi) return;
  if (append && state.apiLoadingMore) return;
  state.apiLoadError = null;
  if (append) state.apiLoadingMore = true;
  else if (els.btnLoadMore) els.btnLoadMore.disabled = true;
  const offset = append ? (state.apiImages?.length ?? 0) : 0;
  try {
    const res = await fetch(`/api/images?${buildSearchParams(offset)}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    state.apiTotal = data.total ?? data.items?.length ?? 0;
    const mapped = mapApiImageItems(data.items);
    if (append && state.apiImages) state.apiImages = [...state.apiImages, ...mapped];
    else state.apiImages = mapped;
  } catch (err) {
    console.warn("API load failed:", err);
    state.apiLoadError = err.message || String(err);
    if (!append) {
      state.apiImages = [];
      state.apiTotal = 0;
    }
  } finally {
    state.apiLoadingMore = false;
    if (els.btnLoadMore) els.btnLoadMore.disabled = false;
    syncLoadMoreButton();
  }
}

function syncLoadMoreButton() {
  if (!els.btnLoadMore) return;
  const show =
    state.useApi &&
    state.apiImages &&
    state.apiTotal != null &&
    state.apiImages.length < state.apiTotal;
  els.btnLoadMore.hidden = !show;
  if (show) {
    const rest = state.apiTotal - state.apiImages.length;
    els.btnLoadMore.textContent = state.apiLoadingMore
      ? "読み込み中…"
      : `さらに読み込む（残り ${rest.toLocaleString()} 件）`;
  }
}

function ratio(done, total) {
  if (done == null || !total) return null;
  return `${done.toLocaleString()} / ${total.toLocaleString()}`;
}

function renderIndexStatusPanel() {
  if (!els.labIndexBody) return;
  if (state.indexStatusError) {
    fillDl(els.labIndexBody, [["状態", `取得できません（${state.indexStatusError}）`]]);
    return;
  }
  const d = state.indexStatus;
  if (!d) {
    fillDl(els.labIndexBody, [["状態", "API に接続すると表示します"]]);
    return;
  }
  const ts = d.tag_stack || {};
  const by = d.tag_stack_by_route || {};
  const rows = [
    ["画像", d.images_active?.toLocaleString()],
    ["CLIP 埋め込み", ratio(d.embedded, d.images_active)],
    ["Tagger", ratio(ts.with_auto_tagger, ts.images_active)],
    ["d1", ratio(ts.with_auto_d1, ts.images_active)],
  ];
  for (const r of ROUTES) {
    const row = by[r.id];
    if (row) rows.push([`${r.label}（d1）`, ratio(row.with_auto_d1, row.active)]);
  }
  const pending = (ts.jobs_pending?.tagger_tag ?? 0) + (ts.jobs_pending?.vlm_tag ?? 0);
  rows.push(["処理待ち", pending ? `${pending.toLocaleString()} 件` : "なし"]);
  fillDl(els.labIndexBody, rows);
}

async function refreshIndexStatus() {
  state.indexStatusError = null;
  try {
    const res = await fetch("/api/index/status");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    state.indexStatus = await res.json();
  } catch (err) {
    state.indexStatus = null;
    state.indexStatusError = err.message || String(err);
  }
  renderIndexStatusPanel();
  renderRoutes();
}

function navDetailBySteps(steps) {
  if (!steps) return;
  const list = filteredImages();
  const start = state.detailIndex >= 0 ? state.detailIndex : lastListIndex;
  if (!list.length || start < 0) return;
  const n = list.length;
  state.detailIndex = (((start + steps) % n) + n) % n;
  state.activeId = list[state.detailIndex].image_id;
  renderDetail(list);
  renderListOnly(list);
}

function navDetail(delta) {
  navDetailBySteps(delta > 0 ? 1 : -1);
}

function flushWheelNav() {
  wheelNavRaf = null;
  const steps = wheelNavSteps;
  wheelNavSteps = 0;
  if (steps) navDetailBySteps(steps);
}

function queueWheelNav(delta) {
  wheelNavSteps += delta > 0 ? 1 : -1;
  if (wheelNavRaf != null) return;
  wheelNavRaf = requestAnimationFrame(flushWheelNav);
}

let debounceTimer;
function debouncedRender() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    commitQueryToOrigin();
    void refreshList();
  }, 280);
}

function bindEvents() {
  els.queryInput.addEventListener("input", applyQueryInput);
  els.queryInput.addEventListener("search", applyQueryInput);
  els.queryInput.addEventListener("change", applyQueryInput);
  els.queryInput.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    clearTimeout(debounceTimer);
    state.query = els.queryInput.value;
    parseQueryTags(state.query);
    commitQueryToOrigin();
    void refreshList();
  });

  els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    prefs.sort = state.sort;
    savePrefs();
    render();
  });

  $$("#layout-seg button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.gridLayout = btn.dataset.layout;
      prefs.gridLayout = state.gridLayout;
      savePrefs();
      renderList(filteredImages());
      syncToolbarControls();
    });
  });

  els.thumbSize.addEventListener("input", () => {
    state.thumbSize = Number(els.thumbSize.value);
    document.documentElement.style.setProperty("--thumb", `${state.thumbSize}px`);
    scheduleRelayout(true);
  });
  els.thumbSize.addEventListener("change", () => {
    prefs.thumbSize = state.thumbSize;
    savePrefs();
  });

  els.detailPrev.addEventListener("click", () => navDetail(-1));
  els.detailNext.addEventListener("click", () => navDetail(1));
  els.workPrev.addEventListener("click", () => navWork(-1));
  els.workNext.addEventListener("click", () => navWork(1));
  els.btnBackExplore.addEventListener("click", () => exitViewMode());

  els.tagEditToggle?.addEventListener("change", () => {
    state.tagEditMode = !!els.tagEditToggle.checked;
    syncTagEditChrome();
    setTagEditMsg("");
    const item = activeDetailItem();
    if (item?.tag_sources) renderDetailTags(item);
    else if (state.activeId && state.useApi) {
      void fetchApiImageDetailCached(state.activeId).then((full) => {
        if (full?.tag_sources && isActiveDetail(state.activeId)) renderDetailTags(full);
      });
    }
  });
  els.tagEditAddBtn?.addEventListener("click", () => submitTagEditAdd());
  els.tagEditInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitTagEditAdd();
    }
  });
  $$(".edge-nav").forEach((btn) => {
    btn.addEventListener("click", () => navDetail(Number(btn.dataset.nav)));
  });
  els.btnInfo.addEventListener("click", () => {
    const hidden = els.app.classList.toggle("info-hidden");
    els.btnInfo.setAttribute("aria-expanded", String(!hidden));
  });
  bindSwipe(els.viewerStage);

  els.btnClearFilters.addEventListener("click", () => clearTagFilters());

  els.btnFilters.addEventListener("click", () => openOverlay("filters"));
  els.btnSettings.addEventListener("click", () => openOverlay("settings"));
  els.scrim.addEventListener("click", () => closeOverlays());
  $$("[data-close]").forEach((btn) => btn.addEventListener("click", () => closeOverlays()));

  $$("#theme-seg button").forEach((btn) => {
    btn.addEventListener("click", () => {
      prefs.theme = btn.dataset.themeChoice;
      savePrefs();
      applyTheme();
    });
  });
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => applyTheme());

  els.setApi.addEventListener("change", () => {
    prefs.useApi = els.setApi.checked;
    savePrefs();
    void setApiEnabled(els.setApi.checked);
  });

  els.btnLoadMore.addEventListener("click", () => void loadMore());
  new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) void loadMore();
    },
    { root: els.listScroll, rootMargin: "1200px 0px" },
  ).observe(els.loadSentinel);

  els.labIndexRefresh.addEventListener("click", () => refreshIndexStatus());

  els.tagFilter.addEventListener("input", () => renderFacets());

  new ResizeObserver(() => scheduleRelayout(false)).observe(els.listScroll);
  window.addEventListener("popstate", () => {
    if (state.appMode === "view") exitViewMode({ fromHistory: true });
  });

  els.detailImage.addEventListener(
    "wheel",
    (e) => {
      if (!state.activeId) return;
      e.preventDefault();
      queueWheelNav(e.deltaY > 0 ? 1 : -1);
    },
    { passive: false },
  );

  document.addEventListener("keydown", (e) => {
    const isTextEntry =
      e.target.matches("textarea, select, input") &&
      !e.target.matches('input[type="checkbox"], input[type="radio"], input[type="range"], input[type="button"]');
    if (isTextEntry) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (e.key === "/") {
      e.preventDefault();
      els.queryInput.focus();
    }
    if (e.key === "Escape") {
      if (openOverlayName) {
        closeOverlays();
        return;
      }
      if (state.tagEditMode) {
        state.tagEditMode = false;
        syncTagEditChrome();
        const item = activeDetailItem();
        if (item?.tag_sources) renderDetailTags(item);
        return;
      }
      if (state.appMode === "view") exitViewMode();
      return;
    }
    if (state.appMode !== "view" || state.activeId == null) return;
    if (e.key === "[" || (e.key === "ArrowLeft" && e.shiftKey)) {
      e.preventDefault();
      navWork(-1);
      return;
    }
    if (e.key === "]" || (e.key === "ArrowRight" && e.shiftKey)) {
      e.preventDefault();
      navWork(1);
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      navDetail(-1);
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      navDetail(+1);
    }
  });
}

/* ── Tag bridge (draft localStorage + server push) ── */

function loadBridgeDraftFromStorage() {
  try {
    const raw = JSON.parse(localStorage.getItem(TAG_BRIDGE_DRAFT_KEY) || "null");
    if (!raw?.entries) return;
    state.tagBridge.entries = raw.entries;
    state.tagBridge.dirty = !!raw.dirty;
    state.tagBridge.serverUpdatedAt = raw.serverUpdatedAt ?? null;
    applyBridgeMemberLabels();
  } catch {
    /* ignore */
  }
}

function persistBridgeDraft() {
  try {
    localStorage.setItem(
      TAG_BRIDGE_DRAFT_KEY,
      JSON.stringify({
        entries: state.tagBridge.entries,
        dirty: state.tagBridge.dirty,
        serverUpdatedAt: state.tagBridge.serverUpdatedAt,
      }),
    );
  } catch {
    /* ignore */
  }
}

function applyBridgeMemberLabels() {
  state.tagBridgeMemberLabels = {};
  for (const entry of state.tagBridge.entries) {
    const label = (entry.label || "").trim();
    if (!label) continue;
    for (const m of entry.members || []) {
      if (m.source && m.tag) state.tagBridgeMemberLabels[`${m.source}\0${m.tag}`] = label;
    }
  }
}

function setBridgeStatus(msg, isError = false) {
  if (!els.tagBridgeStatus) return;
  els.tagBridgeStatus.textContent = msg || "";
  els.tagBridgeStatus.classList.toggle("error", isError);
  els.tagBridgeStatus.classList.toggle("ok", !!msg && !isError);
}

function markBridgeDirty() {
  state.tagBridge.dirty = true;
  persistBridgeDraft();
  if (els.tagBridgeDirty) els.tagBridgeDirty.hidden = false;
}

function syncBridgeDirtyUi() {
  if (els.tagBridgeDirty) els.tagBridgeDirty.hidden = !state.tagBridge.dirty;
}

function buildBridgeMemberRow(entry, member, memberIdx) {
  const row = document.createElement("div");
  row.className = "bridge-member-row";
  const sel = document.createElement("select");
  sel.className = "select";
  for (const s of BRIDGE_SOURCES) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    if (member.source === s) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.addEventListener("change", () => {
    member.source = sel.value;
    markBridgeDirty();
    applyBridgeMemberLabels();
  });
  const tagIn = document.createElement("input");
  tagIn.type = "text";
  tagIn.className = "field";
  tagIn.placeholder = "タグ名";
  tagIn.value = member.tag || "";
  tagIn.addEventListener("input", () => {
    member.tag = tagIn.value;
    markBridgeDirty();
    applyBridgeMemberLabels();
  });
  const rm = document.createElement("button");
  rm.type = "button";
  rm.className = "icon-btn";
  rm.setAttribute("aria-label", "メンバーを削除");
  rm.textContent = "×";
  rm.addEventListener("click", () => {
    entry.members.splice(memberIdx, 1);
    markBridgeDirty();
    renderTagBridgeSettings();
  });
  row.append(sel, tagIn, rm);
  return row;
}

function buildBridgeEntryEl(entry, entryIdx) {
  const wrap = document.createElement("div");
  wrap.className = "bridge-entry";
  const labelIn = document.createElement("input");
  labelIn.type = "text";
  labelIn.className = "field";
  labelIn.placeholder = "代表ラベル（例: 制服）";
  labelIn.value = entry.label || "";
  labelIn.addEventListener("input", () => {
    entry.label = labelIn.value;
    markBridgeDirty();
    applyBridgeMemberLabels();
  });
  const memWrap = document.createElement("div");
  memWrap.className = "bridge-members";
  for (let mi = 0; mi < (entry.members || []).length; mi += 1) {
    memWrap.appendChild(buildBridgeMemberRow(entry, entry.members[mi], mi));
  }
  const addMem = document.createElement("button");
  addMem.type = "button";
  addMem.className = "link-btn";
  addMem.textContent = "メンバーを追加";
  addMem.addEventListener("click", () => {
    if (!entry.members) entry.members = [];
    entry.members.push({ source: "auto_tagger", tag: "" });
    markBridgeDirty();
    renderTagBridgeSettings();
  });
  const del = document.createElement("button");
  del.type = "button";
  del.className = "link-btn";
  del.textContent = "エントリを削除";
  del.addEventListener("click", () => {
    state.tagBridge.entries.splice(entryIdx, 1);
    markBridgeDirty();
    applyBridgeMemberLabels();
    renderTagBridgeSettings();
  });
  wrap.append(labelIn, memWrap, addMem, del);
  return wrap;
}

function renderTagBridgeSettings() {
  if (!els.tagBridgeList) return;
  syncBridgeDirtyUi();
  els.tagBridgeList.innerHTML = "";
  if (!state.tagBridge.entries.length) {
    const p = document.createElement("p");
    p.className = "set-note";
    p.textContent = "エントリがありません。";
    els.tagBridgeList.appendChild(p);
    return;
  }
  state.tagBridge.entries.forEach((entry, idx) => {
    if (!entry.members) entry.members = [];
    els.tagBridgeList.appendChild(buildBridgeEntryEl(entry, idx));
  });
}

async function fetchTagBridgeFromServer({ force = false } = {}) {
  if (!state.useApi) return;
  if (state.tagBridge.dirty && !force) return;
  try {
    const res = await fetch("/api/settings/tag-bridge");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    state.tagBridge.entries = (data.entries || []).map((e) => ({
      label: e.label,
      members: (e.members || []).map((m) => ({ source: m.source, tag: m.tag })),
    }));
    state.tagBridge.serverUpdatedAt = data.updated_at ?? null;
    state.tagBridge.dirty = false;
    persistBridgeDraft();
    applyBridgeMemberLabels();
    renderTagBridgeSettings();
    setBridgeStatus(state.tagBridge.serverUpdatedAt ? `サーバー版 ${state.tagBridge.serverUpdatedAt}` : "");
  } catch (err) {
    setBridgeStatus(`読込失敗: ${err.message}`, true);
  }
}

async function pushTagBridgeToServer() {
  if (!state.useApi) {
    setBridgeStatus("API 未接続のため保存できません。", true);
    return;
  }
  const entries = state.tagBridge.entries
    .map((e) => ({
      label: (e.label || "").trim(),
      members: (e.members || [])
        .map((m) => ({ source: m.source, tag: (m.tag || "").trim() }))
        .filter((m) => m.tag),
    }))
    .filter((e) => e.label && e.members.length);
  els.tagBridgePush.disabled = true;
  setBridgeStatus("保存中…");
  try {
    const res = await fetch("/api/settings/tag-bridge", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version: 1, entries }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    state.tagBridge.entries = (data.entries || entries).map((e) => ({
      label: e.label,
      members: (e.members || []).map((m) => ({ source: m.source, tag: m.tag })),
    }));
    state.tagBridge.serverUpdatedAt = data.updated_at ?? null;
    state.tagBridge.dirty = false;
    persistBridgeDraft();
    applyBridgeMemberLabels();
    renderTagBridgeSettings();
    setBridgeStatus("サーバーに保存しました。");
    if (state.activeId) renderDetail(filteredImages());
    void refreshList();
  } catch (err) {
    setBridgeStatus(`保存失敗: ${err.message}`, true);
  } finally {
    els.tagBridgePush.disabled = false;
  }
}

function discardTagBridgeDraft() {
  if (state.tagBridge.dirty && !window.confirm("未保存の変更を破棄してサーバーから読み直しますか？")) return;
  void fetchTagBridgeFromServer({ force: true });
}

function exportTagBridgeJson() {
  const blob = new Blob(
    [
      JSON.stringify(
        { version: 1, updated_at: state.tagBridge.serverUpdatedAt, entries: state.tagBridge.entries },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "tag_bridge.json";
  a.click();
  URL.revokeObjectURL(a.href);
}

function importTagBridgeJson(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      state.tagBridge.entries = (data.entries || []).map((e) => ({
        label: e.label,
        members: (e.members || []).map((m) => ({ source: m.source, tag: m.tag })),
      }));
      markBridgeDirty();
      applyBridgeMemberLabels();
      renderTagBridgeSettings();
      setBridgeStatus("インポートしました。サーバーに保存で反映。");
    } catch {
      setBridgeStatus("JSON の形式が正しくありません。", true);
    }
  };
  reader.readAsText(file);
}

function bindTagBridgeEvents() {
  els.tagBridgeAdd?.addEventListener("click", () => {
    state.tagBridge.entries.push({
      label: "",
      members: [{ source: "auto_tagger", tag: "" }],
    });
    markBridgeDirty();
    renderTagBridgeSettings();
  });
  els.tagBridgePush?.addEventListener("click", () => void pushTagBridgeToServer());
  els.tagBridgeDiscard?.addEventListener("click", () => discardTagBridgeDraft());
  els.tagBridgeExport?.addEventListener("click", () => exportTagBridgeJson());
  els.tagBridgeImport?.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (f) importTagBridgeJson(f);
    e.target.value = "";
  });
}

/* ── Overlays (filter drawer on compact screens, settings) ── */

let openOverlayName = null;
let overlayReturnFocus = null;

function openOverlay(name) {
  closeOverlays({ restoreFocus: false });
  openOverlayName = name;
  overlayReturnFocus = document.activeElement;
  els.scrim.hidden = false;
  if (name === "settings") {
    els.settings.classList.add("open");
    els.settings.setAttribute("aria-hidden", "false");
    els.btnSettings.setAttribute("aria-expanded", "true");
    if (state.useApi) {
      void refreshIndexStatus();
      void fetchTagBridgeFromServer();
    }
    renderTagBridgeSettings();
    els.settings.querySelector("button, input")?.focus();
  } else {
    els.app.classList.add("filters-open");
    els.btnFilters.setAttribute("aria-expanded", "true");
    els.filterPane.querySelector("button, input")?.focus();
  }
}

function closeOverlays({ restoreFocus = true } = {}) {
  if (!openOverlayName) return;
  openOverlayName = null;
  els.scrim.hidden = true;
  els.settings.classList.remove("open");
  els.settings.setAttribute("aria-hidden", "true");
  els.btnSettings.setAttribute("aria-expanded", "false");
  els.app.classList.remove("filters-open");
  els.btnFilters.setAttribute("aria-expanded", "false");
  if (restoreFocus && overlayReturnFocus?.isConnected) overlayReturnFocus.focus();
  overlayReturnFocus = null;
}

/* ── Preferences: theme, toolbar ── */

function applyTheme() {
  const choice = prefs.theme || "auto";
  const resolved =
    choice === "auto"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : choice;
  document.documentElement.dataset.theme = resolved;
  $$("#theme-seg button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.themeChoice === choice)),
  );
}

function syncToolbarControls() {
  els.sortSelect.value = state.sort;
  els.thumbSize.value = String(state.thumbSize);
  els.thumbSize.disabled = state.gridLayout === "table";
  $$("#layout-seg button").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.layout === state.gridLayout)),
  );
}

let relayoutRaf = null;

/** Re-flow the grid when its width changes (or the size slider moves). */
function scheduleRelayout(force) {
  if (relayoutRaf != null) return;
  relayoutRaf = requestAnimationFrame(() => {
    relayoutRaf = null;
    if (!state.ready || state.gridLayout === "table" || state.appMode === "view") return;
    const width = gridContentWidth();
    if (width <= 0) return;
    if (!force && Math.abs(width - lastGridWidth) < 1) return;
    if (!force && state.gridLayout === "square") {
      lastGridWidth = width;
      return;
    }
    renderList(filteredImages());
  });
}

async function loadMore() {
  if (!state.useApi || state.apiLoadingMore || els.btnLoadMore.hidden) return;
  syncLoadMoreButton();
  const p = tryLoadApi({ append: true });
  syncLoadMoreButton();
  await p;
  render();
}

async function setApiEnabled(on) {
  state.useApi = on;
  els.setApi.checked = on;
  state.activeId = null;
  state.detailIndex = -1;
  if (state.appMode === "view") exitViewMode();
  parseQueryTags(state.query);
  if (on) {
    await tryLoadApi();
    await refreshIndexStatus();
    await fetchTagBridgeFromServer();
  } else {
    state.apiImages = null;
    state.apiTotal = null;
    state.apiLoadError = null;
  }
  syncApiStatus();
  render();
}

function syncApiStatus() {
  const el = els.apiStatus;
  el.classList.remove("ok", "error");
  if (!state.useApi) {
    el.textContent = "未接続のときはサンプルデータを表示します。";
    return;
  }
  if (state.apiLoadError) {
    el.classList.add("error");
    el.textContent = `接続できません（${state.apiLoadError}）。make api-dev で API を起動してください。`;
    return;
  }
  el.classList.add("ok");
  el.textContent = `接続中。全 ${state.indexStatus?.images_active?.toLocaleString() ?? "—"} 枚。`;
}

/** Horizontal swipe on touch devices steps through the list. */
function bindSwipe(el) {
  let start = null;
  el.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return;
    start = { x: e.clientX, y: e.clientY, t: e.timeStamp };
  });
  el.addEventListener("pointerup", (e) => {
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    const quick = e.timeStamp - start.t < 600;
    start = null;
    if (quick && Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) navDetail(dx < 0 ? 1 : -1);
  });
  el.addEventListener("pointercancel", () => {
    start = null;
  });
}

async function detectApi() {
  try {
    const res = await fetch("/api/index/status");
    if (!res.ok) return false;
    state.indexStatus = await res.json();
    return true;
  } catch {
    return false;
  }
}

async function init() {
  const ids = {
    app: "app",
    grid: "image-grid",
    tableWrap: "table-wrap",
    tableBody: "table-body",
    listScroll: "list-scroll",
    listEmpty: "list-empty",
    loadSentinel: "load-sentinel",
    queryInput: "query-input",
    chipRow: "chip-row",
    queryError: "query-error",
    activeFilters: "active-filters",
    btnClearFilters: "btn-clear-filters",
    breadcrumb: "breadcrumb",
    routeList: "route-list",
    tagList: "tag-list",
    tagFilter: "tag-filter",
    facetBasis: "facet-basis",
    filterPane: "filter-pane",
    resultCount: "result-count",
    sortSelect: "sort-select",
    thumbSize: "thumb-size",
    detailEmpty: "detail-empty",
    detailContent: "detail-content",
    detailImage: "detail-image",
    viewerStage: "viewer-stage",
    detailPos: "detail-pos",
    detailPrev: "detail-prev",
    detailNext: "detail-next",
    detailTitle: "detail-title",
    detailSubline: "detail-subline",
    detailContext: "detail-context",
    detailPageSlot: "detail-page-slot",
    workPos: "work-pos",
    workPrev: "work-prev",
    workNext: "work-next",
    pageStrip: "page-strip",
    detailTags: "detail-tags",
    tagEditToggleWrap: "tag-edit-toggle-wrap",
    tagEditToggle: "tag-edit-toggle",
    tagEditMsg: "tag-edit-msg",
    tagEditAddRow: "tag-edit-add-row",
    tagEditInput: "tag-edit-input",
    tagEditAddBtn: "tag-edit-add-btn",
    detailMeta: "detail-meta",
    btnBackExplore: "btn-back-explore",
    btnInfo: "btn-info",
    btnLoadMore: "btn-load-more",
    btnFilters: "btn-filters",
    btnSettings: "btn-settings",
    scrim: "scrim",
    settings: "settings",
    setApi: "set-api",
    apiStatus: "api-status",
    labIndexBody: "lab-index-body",
    labIndexRefresh: "lab-index-refresh",
    tagBridgeList: "tag-bridge-list",
    tagBridgeDirty: "tag-bridge-dirty",
    tagBridgePush: "tag-bridge-push",
    tagBridgeAdd: "tag-bridge-add",
    tagBridgeDiscard: "tag-bridge-discard",
    tagBridgeExport: "tag-bridge-export",
    tagBridgeImport: "tag-bridge-import",
    tagBridgeStatus: "tag-bridge-status",
  };
  for (const [key, id] of Object.entries(ids)) els[key] = document.getElementById(id);

  loadBridgeDraftFromStorage();
  renderTagBridgeSettings();
  bindTagBridgeEvents();

  applyTheme();
  document.documentElement.style.setProperty("--thumb", `${state.thumbSize}px`);
  bindEvents();

  const wantApi = prefs.useApi ?? (await detectApi());
  if (wantApi) {
    await setApiEnabled(true);
  } else {
    syncApiStatus();
    renderIndexStatusPanel();
  }
  state.ready = true;
  els.app.removeAttribute("aria-busy");
  render();
}

void init();
