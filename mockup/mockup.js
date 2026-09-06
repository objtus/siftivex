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
};

const els = {};

let detailRenderGen = 0;
let detailContextTimer = null;
const detailImageCache = new Map();

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

function queryTextOnly(q) {
  return q
    .replace(/-?tag:[^\s]+/g, "")
    .replace(/similar_to:\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function syncQueryFromTags() {
  const parts = [];
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 1) parts.push(`tag:${tag}`);
    if (s === 2) parts.push(`-tag:${tag}`);
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
  state.tagStates = Object.fromEntries(TAGS.map((t) => [t, 0]));
  const re = /(-?)tag:([^\s]+)/g;
  let m;
  while ((m = re.exec(q)) !== null) {
    const excl = m[1] === "-";
    const tag = m[2];
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

function renderDetailTags(tags) {
  els.detailTags.innerHTML = "";
  for (const t of tags || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip neutral tag-filter";
    if (state.tagStates[t] === 1) btn.classList.add("include");
    if (state.tagStates[t] === 2) btn.classList.add("exclude");
    btn.textContent = t;
    btn.title = state.tagStates[t] === 1 ? "絞り込みを解除" : "このタグで絞り込む";
    btn.addEventListener("click", () => filterByTagFromDetail(t));
    els.detailTags.appendChild(btn);
  }
}

function ocrExcerpt(item) {
  const t = (item.ocr_text || "").replace(/\s+/g, " ").trim();
  if (!t) return "—";
  return t.length > 40 ? `${t.slice(0, 40)}…` : t;
}

function filteredImages() {
  const src = state.useApi && state.apiImages ? state.apiImages : IMAGES;
  let list = [...src];
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

function renderThumb(el, item, mode = "grid") {
  if (mode === "table") el.className = "table-thumb-cell";
  if (item.thumb_url) {
    const img = document.createElement("img");
    img.className = mode === "table" ? "table-thumb" : "thumb";
    img.src = item.thumb_url;
    img.alt = item.file_name;
    img.loading = "lazy";
    el.appendChild(img);
    return;
  }
  const ph = document.createElement("div");
  if (mode === "table") {
    ph.className = "table-thumb-ph";
    ph.style.background = item.thumbStyle?.background || "#2a3140";
  } else {
    ph.className = "thumb-placeholder";
    if (item.thumbStyle?.background) ph.style.background = item.thumbStyle.background;
  }
  el.appendChild(ph);
}

function renderGrid(list) {
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
  els.tableBody.innerHTML = "";
  for (const item of list) {
    const tr = document.createElement("tr");
    if (item.image_id === state.activeId) tr.classList.add("active");
    tr.innerHTML = `
      <td class="col-thumb"><div class="table-thumb-cell"></div></td>
      <td class="col-filename">${item.file_name}</td>
      <td class="col-tags">${item.tags.slice(0, 5).join(", ")}</td>
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
  els.queryNote.classList.toggle("visible", /similar_to:/.test(state.query));
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
  state.detailIndex = list.findIndex((i) => i.image_id === id);
  if (state.layoutPreset === "b") enterViewMode();
  renderDetail(list);
  renderListOnly(list);
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
    try {
      const res = await fetch(`/api/images/${encodeURIComponent(imageId)}`);
      if (!res.ok) return null;
      data = await res.json();
    } catch {
      return null;
    }
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
  try {
    const res = await fetch(`/api/works/${encodeURIComponent(workId)}/pages?limit=500`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.items ?? []).map((p) => ({
      ...p,
      thumb_url: p.has_thumbnail ? `/api/images/${p.image_id}/thumbnail` : null,
    }));
  } catch {
    return [];
  }
}

async function resolveDetailItem(list) {
  const sync = resolveDetailItemSync(list);
  if (sync) return sync;

  if (!state.useApi || !state.activeId) return null;
  try {
    const res = await fetch(`/api/images/${encodeURIComponent(state.activeId)}`);
    if (!res.ok) return null;
    const data = await res.json();
    return {
      ...data,
      thumb_url: data.has_thumbnail ? `/api/images/${data.image_id}/thumbnail` : null,
      preview_url: data.has_preview ? `/api/images/${data.image_id}/preview` : null,
    };
  } catch {
    return null;
  }
}

function resolveDetailItemSync(list) {
  const fromList = state.detailIndex >= 0 ? list[state.detailIndex] : null;
  if (fromList?.image_id === state.activeId) return fromList;
  if (!state.useApi) return IMAGES.find((i) => i.image_id === state.activeId) ?? null;
  return state.apiImages?.find((i) => i.image_id === state.activeId) ?? null;
}

function detailImageSrc(item) {
  return item?.preview_url || item?.thumb_url || null;
}

async function preloadDetailImage(src) {
  if (!src) return null;
  const cached = detailImageCache.get(src);
  if (cached?.complete) return cached;
  const img = cached ?? new Image();
  img.decoding = "async";
  img.src = src;
  if (detailImageCache.size >= 64) {
    detailImageCache.delete(detailImageCache.keys().next().value);
  }
  detailImageCache.set(src, img);
  try {
    await img.decode();
  } catch {
    if (!img.complete) {
      await new Promise((resolve) => {
        img.onload = () => resolve();
        img.onerror = () => resolve();
      });
    }
  }
  return img;
}

function createDetailPlaceholder(item) {
  const ph = document.createElement("div");
  ph.className = "detail-ph";
  Object.assign(ph.style, item.thumbStyle || { minHeight: "240px" });
  return ph;
}

function applyDetailImageSrc(src, alt) {
  const absoluteSrc = new URL(src, location.href).href;
  let img = els.detailImage.querySelector("img");
  if (!img) {
    img = document.createElement("img");
    els.detailImage.replaceChildren(img);
  }
  img.alt = alt;
  if (img.src !== absoluteSrc) img.src = src;
}

async function updateDetailImage(item, gen) {
  const src = detailImageSrc(item);
  if (!src) {
    if (gen !== detailRenderGen) return;
    els.detailImage.replaceChildren(createDetailPlaceholder(item));
    return;
  }

  const cached = detailImageCache.get(src);
  if (cached?.complete) {
    if (gen !== detailRenderGen) return;
    applyDetailImageSrc(src, item.file_name);
    return;
  }

  await preloadDetailImage(src);
  if (gen !== detailRenderGen) return;
  applyDetailImageSrc(src, item.file_name);
}

function prefetchDetailNeighbors(list) {
  if (!list.length || state.detailIndex < 0) return;
  const n = list.length;
  for (const delta of [-1, 1]) {
    const idx = (state.detailIndex + delta + n) % n;
    const src = detailImageSrc(list[idx]);
    if (src) preloadDetailImage(src).catch(() => {});
  }
}

function scheduleDetailContext(item, gen) {
  clearTimeout(detailContextTimer);
  detailContextTimer = setTimeout(() => {
    if (gen !== detailRenderGen) return;
    void renderDetailContext(item);
  }, 150);
}

function renderPageStrip(activeId, pages) {
  els.pageStrip.innerHTML = "";
  for (const p of pages) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `page-strip-item${p.image_id === activeId ? " active" : ""}`;
    btn.title = p.file_name || `p${p.page ?? "?"}`;
    const thumbUrl = pageThumbUrl(p);
    if (thumbUrl) {
      const img = document.createElement("img");
      img.src = thumbUrl;
      img.alt = btn.title;
      img.loading = "lazy";
      btn.appendChild(img);
    } else {
      const ph = document.createElement("span");
      ph.className = "ph";
      Object.assign(ph.style, p.thumbStyle || { background: "#333" });
      btn.appendChild(ph);
    }
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = p.page != null ? `p${p.page}` : "?";
    btn.appendChild(label);
    btn.addEventListener("click", () => navWorkPage(p.image_id));
    els.pageStrip.appendChild(btn);
  }
  requestAnimationFrame(() => {
    els.pageStrip.querySelector(".active")?.scrollIntoView({ inline: "center", block: "nearest" });
  });
}

async function renderDetailContext(item) {
  const workCtx = await fetchWorkContext(item.image_id, item);
  const displayMeta = readDisplayMeta(item, workCtx);
  state.workContext = workCtx?.multi_page ? workCtx : null;

  els.detailTitle.textContent = contextTitle(item, displayMeta);
  renderSubline(item, displayMeta);

  const multiPage = !!workCtx?.multi_page;
  els.detailPageSlot.classList.toggle("has-pages", multiPage);

  if (multiPage) {
    const pageLabel = workCtx.page ?? workCtx.page_index ?? 0;
    els.workPos.textContent = `p${pageLabel} / ${workCtx.page_count}`;
    els.workPrev.disabled = !workCtx.prev_image_id;
    els.workNext.disabled = !workCtx.next_image_id;
    const pages = await fetchWorkPages(workCtx.work_id);
    renderPageStrip(item.image_id, pages);
  } else {
    els.workPos.textContent = "—";
    els.workPrev.disabled = true;
    els.workNext.disabled = true;
    els.pageStrip.innerHTML = "";
  }
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

function renderDetail(list) {
  const gen = ++detailRenderGen;
  const item = resolveDetailItemSync(list);

  if (!item) {
    void (async () => {
      const fetched = await resolveDetailItem(list);
      if (gen !== detailRenderGen) return;
      if (!fetched) {
        els.detailEmpty.hidden = false;
        els.detailContent.hidden = true;
        state.workContext = null;
        return;
      }
      renderDetailBody(list, fetched, gen);
    })();
    return;
  }

  renderDetailBody(list, item, gen);
}

function renderDetailBody(list, item, gen) {
  els.detailEmpty.hidden = true;
  els.detailContent.hidden = false;
  els.detailPos.textContent =
    state.detailIndex >= 0 ? `${state.detailIndex + 1} / ${list.length}` : "—";

  void updateDetailImage(item, gen);
  prefetchDetailNeighbors(list);

  els.detailTags.innerHTML = "";
  renderDetailTags(item.tags || []);
  els.detailMeta.innerHTML = `
    <dt>ID</dt><dd>${item.image_id}</dd>
    <dt>ファイル</dt><dd>${item.file_name}</dd>
    <dt>ルート</dt><dd>${routeLabel(item.route_tag)}</dd>
  `;
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
    m.addEventListener("click", () => openDetail(s.image_id, list));
    els.similarStrip.appendChild(m);
  }
  els.btnSimilarReflux.disabled = false;
  els.btnSimilarReflux.dataset.imageId = item.image_id;

  scheduleDetailContext(item, gen);

  if (!item.metadata && state.useApi) {
    void (async () => {
      const full = await resolveDetailItem(list);
      if (gen !== detailRenderGen || !full) return;
      scheduleDetailContext(full, gen);
    })();
  }
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
  els.resultCount.textContent = `${list.length.toLocaleString()} 件`;
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
    const idx = list.findIndex((i) => i.image_id === state.activeId);
    if (idx >= 0) state.detailIndex = idx;
    renderDetail(list);
  } else if (state.layoutPreset === "a" && state.appMode === "explore") {
    els.detailEmpty.hidden = false;
    els.detailContent.hidden = true;
  }
  renderBulkBar();
  applyShellClasses();
  applyLayoutVars();
}

async function tryLoadApi() {
  if (!state.useApi) return;
  try {
    const params = new URLSearchParams({ limit: "80", q: state.query.replace(/similar_to:\S+/g, "").trim() });
    if (state.route !== "all") params.set("route_tag", state.route);
    const res = await fetch(`/api/images?${params}`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    state.apiImages = data.items.map((item) => ({
      ...item,
      thumb_url: `/api/images/${item.image_id}/thumbnail`,
      preview_url: `/api/images/${item.image_id}/preview`,
      ocr_text: "",
    }));
  } catch (err) {
    console.warn("API fallback:", err);
    state.apiImages = null;
    state.useApi = false;
    $("#lab-api").checked = false;
  }
}

function navDetail(delta) {
  const list = filteredImages();
  if (!list.length || state.detailIndex < 0) return;
  const n = list.length;
  state.detailIndex = ((state.detailIndex + delta) % n + n) % n;
  state.activeId = list[state.detailIndex].image_id;
  renderDetail(list);
  renderListOnly(list);
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
    await tryLoadApi();
    render();
  });

  els.tagFilter.addEventListener("input", render);
  els.labToggle.addEventListener("click", () => els.lab.classList.toggle("collapsed"));

  els.detailImage.addEventListener(
    "wheel",
    (e) => {
      if (!state.activeId) return;
      e.preventDefault();
      navDetail(e.deltaY > 0 ? 1 : -1);
    },
    { passive: false },
  );

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) {
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
  els.detailPageSlot = $("#detail-page-slot");
  els.workPos = $("#work-pos");
  els.workPrev = $("#work-prev");
  els.workNext = $("#work-next");
  els.pageStrip = $("#page-strip");
  els.detailTags = $("#detail-tags");
  els.detailMeta = $("#detail-meta");
  els.similarStrip = $("#similar-strip");
  els.btnSimilarReflux = $("#btn-similar-reflux");
  els.bulkBar = $("#bulk-bar");
  els.bulkCount = $("#bulk-count");
  els.modeBadge = $("#mode-badge");
  els.layoutBadge = $("#layout-badge");
  els.btnBackExplore = $("#btn-back-explore");
  els.lab = $("#mockup-lab");
  els.labToggle = $("#lab-toggle");

  bindEvents();
  render();
}

init();
