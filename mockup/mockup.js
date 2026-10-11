import { IMAGES, TAGS, getMockWorkPages, mockWorkContext } from "./data.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  layoutPreset: "b",
  appMode: "explore",
  query: "",
  route: "all",
  viewMode: "grid",
  sort: "file_name",
  tagStates: Object.fromEntries(TAGS.map((t) => [t, 0])),
  selected: new Set(),
  activeId: null,
  detailIndex: -1,
  similarTab: "color",
  useApi: false,
  apiImages: null,
  workContext: null,
  workPages: [],
  originStack: [{ label: "開始", query: "", route: "all", scrollTop: 0 }],
  originIndex: 0,
  savedScrollTop: 0,
  retagBusy: false,
  apiTotal: null,
  apiLoadError: null,
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
  return state.viewMode === "grid" ? els.grid : els.tableWrap;
}

function tagStateLabel(s) {
  return s === 1 ? "+" : s === 2 ? "−" : "·";
}

function tagStateClass(s) {
  return s === 1 ? "include" : s === 2 ? "exclude" : "neutral";
}

function cycleTag(tag) {
  state.tagStates[tag] = (state.tagStates[tag] + 1) % 3;
  syncQueryFromTags();
  commitQueryToOrigin();
  render();
}

function tagNeedsQuotes(tag) {
  return /[\s()"']/.test(tag);
}

function formatTagQueryToken(tag, exclude) {
  const prefix = exclude ? "-tag:" : "tag:";
  if (!tagNeedsQuotes(tag)) return `${prefix}${tag}`;
  const escaped = tag.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return `${prefix}"${escaped}"`;
}

function stripTagTokensFromQuery(q) {
  return q
    .replace(/(-?)tag:(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s]+)/gi, "")
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
    if (s === 1) parts.push(formatTagQueryToken(tag, false));
    if (s === 2) parts.push(formatTagQueryToken(tag, true));
  }
  const text = queryTextOnly(state.query);
  state.query = [...parts, text].filter(Boolean).join(" ").trim();
  if (els.queryInput) els.queryInput.value = state.query;
}

function removeTagFilter(tag) {
  clearTimeout(debounceTimer);
  if (TAGS.includes(tag)) state.tagStates[tag] = 0;
  else delete state.tagStates[tag];
  syncQueryFromTags();
  commitQueryToOrigin();
  void refreshList();
}

async function refreshList() {
  if (state.useApi) await tryLoadApi();
  render();
}

function parseQueryTags(q) {
  state.tagStates = state.useApi
    ? {}
    : Object.fromEntries(TAGS.map((t) => [t, 0]));
  const re = /(-?)tag:(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^\s]+))/gi;
  let m;
  while ((m = re.exec(q)) !== null) {
    const excl = m[1] === "-";
    let tag = m[2] ?? m[3] ?? m[4] ?? "";
    tag = tag.replace(/\\"/g, '"').replace(/\\'/g, "'");
    if (!tag) continue;
    state.tagStates[tag] = excl ? 2 : 1;
  }
  state.query = q;
}

function applyQueryInput() {
  state.query = els.queryInput.value;
  parseQueryTags(state.query);
  commitQueryToOrigin();
  debouncedRender();
}

function filterByTagFromDetail(tag) {
  clearTimeout(debounceTimer);
  if (state.tagStates[tag] === 1) {
    if (TAGS.includes(tag)) state.tagStates[tag] = 0;
    else delete state.tagStates[tag];
  } else {
    state.tagStates[tag] = 1;
  }
  syncQueryFromTags();
  commitQueryToOrigin();
  if (state.layoutPreset === "b" && state.appMode === "view") exitViewMode();
  void refreshList();
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
  const sources = item?.tag_sources;
  if (sources && state.useApi) {
    const legend = document.createElement("p");
    legend.className = "detail-tag-legend";
    legend.textContent =
      "レイヤー別: d1＝構造化（種類/画角…）、Tagger＝Danbooru EN 平坦タグ。一覧の tags はこれらをマージした effective。";
    els.detailTags.appendChild(legend);
    appendTagSourceBlock(els.detailTags, "d1 — 構造化 (NS)", sources.auto_d1, {
      chipClass: "chip-ns",
      open: true,
    });
    appendTagSourceBlock(els.detailTags, "ファイル名 / pixiv (JA)", sources.filename, {
      chipClass: "chip-ja",
      open: true,
    });
    appendTagSourceBlock(els.detailTags, "Tagger — 平坦 (EN)", sources.auto_tagger, {
      chipClass: "chip-en",
      open: false,
    });
    appendTagSourceBlock(els.detailTags, "推定 JA", sources.inferred_ja, { chipClass: "chip-ja", open: false });
    appendTagSourceBlock(els.detailTags, "VLM (legacy)", sources.auto, { chipClass: "chip-legacy", open: false });
    appendTagSourceBlock(els.detailTags, "手動", sources.manual_added, { chipClass: "chip-manual", open: false });
    return;
  }
  appendTagChips(els.detailTags, item?.tags || []);
}

function appendTagSourceBlock(container, label, tags, opts = {}) {
  const list = tags || [];
  if (!list.length) return;
  const block = document.createElement("details");
  block.className = "tag-source-block";
  block.open = opts.open === true;
  const head = document.createElement("summary");
  head.className = "tag-source-label";
  head.textContent = `${label} (${list.length})`;
  block.appendChild(head);
  const row = document.createElement("div");
  row.className = "tag-editor tag-editor-sub";
  appendTagChips(row, list, opts.chipClass);
  block.appendChild(row);
  container.appendChild(block);
}

function appendTagChips(container, tags, extraClass = "") {
  for (const t of tags || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `chip neutral tag-filter ${extraClass}`.trim();
    if (state.tagStates[t] === 1) btn.classList.add("include");
    if (state.tagStates[t] === 2) btn.classList.add("exclude");
    btn.textContent = t;
    btn.title = state.tagStates[t] === 1 ? "絞り込みを解除" : "このタグで絞り込む";
    btn.addEventListener("click", () => filterByTagFromDetail(t));
    container.appendChild(btn);
  }
}

function ocrExcerpt(item) {
  const t = (item.ocr_text || "").replace(/\s+/g, " ").trim();
  if (!t) return "—";
  return t.length > 40 ? `${t.slice(0, 40)}…` : t;
}

function listTagsPreview(item, max = 4) {
  const tags = item?.tags || [];
  if (!tags.length) return "—";
  const { ns, flat } = partitionEffectiveTags(tags);
  const parts = [];
  if (ns.length) {
    const head = ns.slice(0, Math.min(3, max));
    const nsRest = ns.length - head.length;
    parts.push(`NS: ${head.join(" · ")}${nsRest > 0 ? ` +${nsRest}` : ""}`);
  }
  if (flat.length) {
    const flatMax = ns.length ? Math.max(2, max - 1) : max;
    const head = flat.slice(0, flatMax);
    const flatRest = flat.length - head.length;
    parts.push(`${head.join(", ")}${flatRest > 0 ? ` +${flatRest}` : ""}`);
  }
  return parts.join(" │ ") || "—";
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
  $$(".route-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.route === state.route);
  });
  void (async () => {
    if (state.useApi) await tryLoadApi();
    render();
    requestAnimationFrame(() => {
      listScrollEl().scrollTop = entry.scrollTop;
    });
  })();
}

function pushSimilarReflux(imageId) {
  const scrollTop = listScrollEl()?.scrollTop ?? 0;
  state.originStack = state.originStack.slice(0, state.originIndex + 1);
  state.originStack.push({
    label: originLabel(state.query),
    query: state.query,
    route: state.route,
    scrollTop,
  });
  state.query = `similar_to:${imageId}`;
  state.originIndex = state.originStack.length;
  state.originStack.push({
    label: originLabel(state.query),
    query: state.query,
    route: state.route,
    scrollTop: 0,
  });
  if (state.originStack.length > 6) {
    state.originStack = state.originStack.slice(-5);
    state.originIndex = state.originStack.length - 1;
  }
  els.queryInput.value = state.query;
  render();
}

function appendThumbPlaceholder(el, item, mode) {
  const ph = document.createElement("div");
  if (mode === "table") {
    ph.className = "table-thumb-ph";
    ph.style.background = item.thumbStyle?.background || "#2a3140";
  } else {
    ph.className = "thumb-placeholder";
    if (item.thumbStyle?.background) ph.style.background = item.thumbStyle.background;
  }
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

function renderGrid(list) {
  resetThumbObserver(els.grid);
  els.grid.innerHTML = "";
  for (const item of list) {
    const card = document.createElement("article");
    card.className = "image-card";
    if (state.selected.has(item.image_id)) card.classList.add("selected");
    if (item.image_id === state.activeId) card.classList.add("active");
    card.dataset.id = item.image_id;
    const check = document.createElement("span");
    check.className = "check";
    check.textContent = "✓";
    card.appendChild(check);
    const thumbWrap = document.createElement("div");
    thumbWrap.className = "thumb-wrap";
    renderThumb(thumbWrap, item);
    card.appendChild(thumbWrap);
    if (item.score != null) {
      const sc = document.createElement("span");
      sc.className = "score";
      sc.textContent = item.score.toFixed(3);
      card.appendChild(sc);
    }
    card.addEventListener("click", (e) => onCardClick(item, e));
    els.grid.appendChild(card);
  }
}

function renderTable(list) {
  resetThumbObserver(els.tableWrap);
  els.tableBody.innerHTML = "";
  for (const item of list) {
    const tr = document.createElement("tr");
    if (item.image_id === state.activeId) tr.classList.add("active");
    tr.innerHTML = `
      <td class="col-thumb"><div class="table-thumb-cell"></div></td>
      <td class="col-filename">${item.file_name}</td>
      <td class="col-tags" title="${(item.tags || []).join(", ")}">${listTagsPreview(item)}</td>
      <td class="col-ocr">${ocrExcerpt(item)}</td>
      <td class="col-score">${item.score?.toFixed(3) ?? "—"}</td>
    `;
    renderThumb(tr.querySelector(".table-thumb-cell"), item, "table");
    tr.addEventListener("click", () => openDetail(item.image_id, list));
    els.tableBody.appendChild(tr);
  }
}

function renderTagList() {
  const filter = els.tagFilter.value.toLowerCase();
  els.tagList.innerHTML = "";
  if (state.useApi) {
    const hint = document.createElement("p");
    hint.className = "api-tag-hint";
    hint.textContent =
      "API モード: tag:名前（空白・括弧ありは tag:\"black hair\"）。詳細チップは自動で引用。";
    els.tagList.appendChild(hint);
    return;
  }
  for (const tag of TAGS) {
    if (filter && !tag.toLowerCase().includes(filter)) continue;
    const s = state.tagStates[tag];
    const row = document.createElement("div");
    row.className = "tag-item";
    const count = IMAGES.filter((i) => i.tags.includes(tag)).length;
    row.innerHTML = `
      <button type="button" class="tag-cycle ${tagStateClass(s)}" title="未選択→含む→除外">${tagStateLabel(s)}</button>
      <span>${tag}</span>
      <span class="tag-count">${count}</span>
    `;
    row.querySelector(".tag-cycle").addEventListener("click", () => cycleTag(tag));
    els.tagList.appendChild(row);
  }
}

function renderChips() {
  els.chipRow.innerHTML = "";
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 0) continue;
    const chip = document.createElement("span");
    chip.className = `chip ${s === 1 ? "include" : "exclude"}`;
    chip.append(document.createTextNode(s === 2 ? `−${tag} ` : `${tag} `));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "x";
    btn.textContent = "×";
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      removeTagFilter(tag);
    });
    chip.append(btn);
    els.chipRow.appendChild(chip);
  }
  const showNote =
    /similar_to:/.test(state.query) ||
    (state.useApi && Object.values(state.tagStates).some((s) => s !== 0));
  els.queryNote.classList.toggle("visible", showNote);
  if (state.useApi) {
    els.queryNote.textContent = state.apiLoadError
      ? `⚠ API: ${state.apiLoadError}`
      : "API: フィルタはサーバ検索。チップはクエリと同期（Enter で再検索）。";
  }
}

function enterViewMode() {
  if (state.layoutPreset !== "b") return;
  state.savedScrollTop = listScrollEl()?.scrollTop ?? 0;
  state.appMode = "view";
  applyShellClasses();
}

function exitViewMode() {
  if (state.layoutPreset !== "b") return;
  state.appMode = "explore";
  applyShellClasses();
  requestAnimationFrame(() => {
    listScrollEl().scrollTop = state.savedScrollTop;
  });
}

function openDetail(id, list) {
  state.activeId = id;
  const fresh = list ?? filteredImages();
  state.detailIndex = fresh.findIndex((i) => i.image_id === id);
  if (state.layoutPreset === "b") enterViewMode();
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

function renderDetailMeta(item) {
  els.detailMeta.innerHTML = `
    <dt>ID</dt><dd>${item.image_id}</dd>
    <dt>ファイル</dt><dd>${item.file_name}</dd>
    <dt>ルート</dt><dd>${routeLabel(item.route_tag)}</dd>
  `;
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
    els.detailTags.innerHTML = '<p class="detail-tag-legend">タグ（source 別）を読み込み中…</p>';
  } else {
    renderDetailTags(item);
  }
  syncRetagButton();
  renderDetailMeta(item);
  els.similarStrip.innerHTML = "";
  const sim = (state.useApi ? list : IMAGES).filter((i) => i.image_id !== item.image_id).slice(0, 8);
  for (const s of sim) {
    const m = document.createElement("button");
    m.type = "button";
    m.className = "mini";
    Object.assign(m.style, s.thumbStyle || { background: "#444", width: "56px", height: "56px" });
    if (s.thumb_url) {
      m.style.background = `center/cover url(${s.thumb_url})`;
    }
    m.title = "詳細へ";
    m.addEventListener("click", () => openDetail(s.image_id, filteredImages()));
    els.similarStrip.appendChild(m);
  }
  els.btnSimilarReflux.disabled = false;
  els.btnSimilarReflux.dataset.imageId = item.image_id;
}

function renderListOnly(list) {
  $$(".image-card").forEach((c) => c.classList.toggle("active", c.dataset.id === state.activeId));
  $$(".image-table tbody tr").forEach((tr, i) => {
    const id = list[i]?.image_id;
    tr.classList.toggle("active", id === state.activeId);
  });
}

function onCardClick(item, e) {
  const list = filteredImages();
  if (e.shiftKey) {
    if (state.selected.has(item.image_id)) state.selected.delete(item.image_id);
    else state.selected.add(item.image_id);
    renderBulkBar();
    renderGrid(list);
    return;
  }
  openDetail(item.image_id, list);
}

function renderBulkBar() {
  const n = state.selected.size;
  els.bulkBar.classList.toggle("visible", n > 0);
  els.bulkCount.textContent = `${n} 件選択`;
}

function applyShellClasses() {
  els.app.classList.remove("layout-a", "layout-b", "mode-explore", "mode-view");
  els.app.classList.add(state.layoutPreset === "b" ? "layout-b" : "layout-a");
  els.app.classList.add(state.appMode === "view" ? "mode-view" : "mode-explore");
  els.layoutBadge.textContent = state.layoutPreset === "b" ? "案 B" : "案 A";
  els.modeBadge.textContent = state.appMode === "view" ? "閲覧" : "探索";
  els.navHint.textContent =
    state.layoutPreset === "b"
      ? "クリック → 閲覧モード · Esc → 探索へ"
      : "クリック → 右ペイン · Shift+クリック → 複数選択";
  els.btnBackExplore.hidden = !(state.layoutPreset === "b" && state.appMode === "view");
}

function applyLayoutVars() {
  document.documentElement.style.setProperty("--sidebar-w", `${$("#lab-sidebar-w").value}px`);
  document.documentElement.style.setProperty("--detail-w", `${$("#lab-detail-w").value}px`);
  document.documentElement.style.setProperty("--grid-cols", $("#lab-cols").value);
}

function render() {
  const list = filteredImages();
  if (state.useApi && state.apiTotal != null) {
    const shown = list.length.toLocaleString();
    const total = state.apiTotal.toLocaleString();
    els.resultCount.textContent =
      state.apiTotal > list.length ? `${shown} / ${total} 件` : `${total} 件`;
  } else {
    els.resultCount.textContent = `${list.length.toLocaleString()} 件`;
  }
  renderBreadcrumb();
  renderChips();
  renderTagList();
  if (state.viewMode === "grid") {
    els.grid.hidden = false;
    els.tableWrap.hidden = true;
    renderGrid(list);
  } else {
    els.grid.hidden = true;
    els.tableWrap.hidden = false;
    renderTable(list);
  }
  if (state.activeId) {
    syncDetailChrome(list);
  } else if (state.layoutPreset === "a" && state.appMode === "explore") {
    els.detailEmpty.hidden = false;
    els.detailContent.hidden = true;
  }
  renderBulkBar();
  syncLoadMoreButton();
  applyShellClasses();
  applyLayoutVars();
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
  const qText = queryTextOnly(state.query.replace(/similar_to:\S+/g, "").trim());
  params.set("q", qText);
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 1) params.append("include_tag", tag);
    if (s === 2) params.append("exclude_tag", tag);
  }
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
    els.btnLoadMore.textContent = `さらに読み込み (+${Math.min(rest, state.apiPageLimit)})`;
  }
}

function formatRouteStack(label, row) {
  if (!row) return "";
  return `${label}: tagger ${row.with_auto_tagger}/${row.active} · d1 ${row.with_auto_d1}/${row.active}`;
}

function renderIndexStatusPanel() {
  if (!els.labIndexBody) return;
  if (state.indexStatusError) {
    els.labIndexBody.textContent = `⚠ ${state.indexStatusError}`;
    return;
  }
  const d = state.indexStatus;
  if (!d) {
    els.labIndexBody.textContent = "「更新」で /api/index/status を取得";
    return;
  }
  const ts = d.tag_stack || {};
  const by = d.tag_stack_by_route || {};
  const lines = [
    `画像 ${d.images_active?.toLocaleString()} · CLIP ${d.embedded?.toLocaleString()}`,
    `tagger ${ts.with_auto_tagger?.toLocaleString()}/${ts.images_active?.toLocaleString()} · d1 ${ts.with_auto_d1?.toLocaleString()}/${ts.images_active?.toLocaleString()}`,
    formatRouteStack("pixiv", by["route/pixiv"]),
    formatRouteStack("under", by["route/under-iphone"]),
    `キュー tagger ${ts.jobs_pending?.tagger_tag ?? 0} · VLM ${ts.jobs_pending?.vlm_tag ?? 0}`,
  ].filter(Boolean);
  els.labIndexBody.textContent = lines.join("\n");
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
  debounceTimer = setTimeout(async () => {
    if (state.useApi) await tryLoadApi();
    render();
  }, 280);
}

function bindEvents() {
  els.queryInput.addEventListener("input", applyQueryInput);
  els.queryInput.addEventListener("search", applyQueryInput);
  els.queryInput.addEventListener("change", applyQueryInput);
  els.queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyQueryInput();
  });

  $$(".route-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".route-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.route = btn.dataset.route;
      commitQueryToOrigin();
      debouncedRender();
    });
  });

  $$(".view-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".view-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.viewMode = btn.dataset.view;
      render();
    });
  });

  els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    render();
  });

  els.detailPrev.addEventListener("click", () => navDetail(-1));
  els.detailNext.addEventListener("click", () => navDetail(1));
  els.btnRetag?.addEventListener("click", () => void retagActiveImage());
  els.workPrev.addEventListener("click", () => navWork(-1));
  els.workNext.addEventListener("click", () => navWork(1));
  els.btnBackExplore.addEventListener("click", () => {
    exitViewMode();
  });
  els.btnSimilarReflux.addEventListener("click", () => {
    const id = els.btnSimilarReflux.dataset.imageId;
    if (id) {
      if (state.layoutPreset === "b") exitViewMode();
      pushSimilarReflux(id);
    }
  });

  $$(".similar-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".similar-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.similarTab = btn.dataset.tab;
    });
  });

  $("#lab-preset").addEventListener("change", (e) => {
    state.layoutPreset = e.target.value;
    state.appMode = "explore";
    render();
  });

  $("#lab-cols").addEventListener("input", () => {
    $("#lab-cols-val").textContent = $("#lab-cols").value;
    applyLayoutVars();
  });
  $("#lab-sidebar-w").addEventListener("input", () => {
    $("#lab-sidebar-w-val").textContent = `${$("#lab-sidebar-w").value}px`;
    applyLayoutVars();
  });
  $("#lab-detail-w").addEventListener("input", () => {
    $("#lab-detail-w-val").textContent = `${$("#lab-detail-w").value}px`;
    applyLayoutVars();
  });
  $("#lab-table-thumb").addEventListener("input", () => {
    const size = $("#lab-table-thumb").value;
    $("#lab-table-thumb-val").textContent = `${size}px`;
    document.documentElement.style.setProperty("--table-thumb-size", `${size}px`);
  });
  $("#lab-api").addEventListener("change", async (e) => {
    state.useApi = e.target.checked;
    parseQueryTags(state.query);
    await tryLoadApi();
    if (state.useApi) await refreshIndexStatus();
    render();
  });

  els.btnLoadMore?.addEventListener("click", async () => {
    await tryLoadApi({ append: true });
    render();
  });

  els.labIndexRefresh?.addEventListener("click", () => refreshIndexStatus());

  els.tagFilter.addEventListener("input", () => renderTagList());
  els.labToggle.addEventListener("click", () => els.lab.classList.toggle("collapsed"));

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
      if (state.layoutPreset === "b" && state.appMode === "view") {
        exitViewMode();
        return;
      }
      if (state.activeId && state.layoutPreset === "a") {
        state.activeId = null;
        state.detailIndex = -1;
        render();
      }
      return;
    }
    if (state.activeId == null) return;
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

function init() {
  els.app = $("#app");
  els.grid = $("#image-grid");
  els.tableWrap = $("#table-wrap");
  els.tableBody = $("#table-body");
  els.queryInput = $("#query-input");
  els.chipRow = $("#chip-row");
  els.queryNote = $("#query-note");
  els.breadcrumb = $("#breadcrumb");
  els.tagList = $("#tag-list");
  els.tagFilter = $("#tag-filter");
  els.resultCount = $("#result-count");
  els.sortSelect = $("#sort-select");
  els.navHint = $("#nav-hint");
  els.detail = $("#detail-pane");
  els.detailEmpty = $("#detail-empty");
  els.detailContent = $("#detail-content");
  els.detailImage = $("#detail-image");
  els.detailPos = $("#detail-pos");
  els.detailPrev = $("#detail-prev");
  els.detailNext = $("#detail-next");
  els.detailTitle = $("#detail-title");
  els.detailSubline = $("#detail-subline");
  els.detailContext = $("#detail-context");
  els.detailPageSlot = $("#detail-page-slot");
  els.workPos = $("#work-pos");
  els.workPrev = $("#work-prev");
  els.workNext = $("#work-next");
  els.pageStrip = $("#page-strip");
  els.detailTags = $("#detail-tags");
  els.detailMeta = $("#detail-meta");
  els.btnRetag = $("#btn-retag");
  els.similarStrip = $("#similar-strip");
  els.btnSimilarReflux = $("#btn-similar-reflux");
  els.bulkBar = $("#bulk-bar");
  els.bulkCount = $("#bulk-count");
  els.modeBadge = $("#mode-badge");
  els.layoutBadge = $("#layout-badge");
  els.btnBackExplore = $("#btn-back-explore");
  els.lab = $("#mockup-lab");
  els.labToggle = $("#lab-toggle");
  els.btnLoadMore = $("#btn-load-more");
  els.labIndexBody = $("#lab-index-body");
  els.labIndexRefresh = $("#lab-index-refresh");

  bindEvents();
  void refreshIndexStatus();
  render();
}

init();
