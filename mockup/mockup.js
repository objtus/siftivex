import { ALBUMS, IMAGES, ROUTES, TAGS, getMockWorkPages, mockWorkContext } from "./data.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  query: "",
  route: "all",
  viewMode: "grid",
  sort: "file_name",
  tagStates: Object.fromEntries(TAGS.map((t) => [t, 0])), // 0 neutral 1 include 2 exclude
  selected: new Set(),
  selectMode: false,
  activeId: null,
  detailIndex: 0,
  similarTab: "color",
  layout: "wide-right", // wide-right | wide-bottom | narrow
  useApi: false,
  apiImages: null,
  workContext: null,
  workPages: [],
  detailOverride: null,
};

const els = {};

function tagStateLabel(s) {
  return s === 1 ? "+" : s === 2 ? "−" : "·";
}

function tagStateClass(s) {
  return s === 1 ? "include" : s === 2 ? "exclude" : "neutral";
}

function cycleTag(tag) {
  state.tagStates[tag] = (state.tagStates[tag] + 1) % 3;
  syncQueryFromTags();
  render();
}

function syncQueryFromTags() {
  const parts = [];
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 1) parts.push(`tag:${tag}`);
    if (s === 2) parts.push(`-tag:${tag}`);
  }
  const text = state.query.replace(/(?:^-?tag:[^\s]+\s*)+/g, "").trim();
  state.query = [...parts, text].filter(Boolean).join(" ");
}

function parseQueryTags(q) {
  for (const tag of TAGS) state.tagStates[tag] = 0;
  const re = /(-?)tag:([^\s]+)/g;
  let m;
  let text = q;
  while ((m = re.exec(q)) !== null) {
    const excl = m[1] === "-";
    const tag = m[2];
    if (TAGS.includes(tag)) state.tagStates[tag] = excl ? 2 : 1;
    text = text.replace(m[0], "");
  }
  state.query = q;
  return text.trim();
}

function filteredImages() {
  const src = state.useApi && state.apiImages ? state.apiImages : IMAGES;
  let list = [...src];
  if (state.route !== "all") {
    list = list.filter((i) => i.route_tag === state.route);
  }
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 1) list = list.filter((i) => i.tags.includes(tag));
    if (s === 2) list = list.filter((i) => !i.tags.includes(tag));
  }
  const text = parseQueryTags(state.query);
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

function activeChips() {
  const chips = [];
  for (const [tag, s] of Object.entries(state.tagStates)) {
    if (s === 0) continue;
    chips.push({ type: s === 1 ? "include" : "exclude", label: tag, tag });
  }
  return chips;
}

function renderThumb(el, item, mode = "grid") {
  if (mode === "table") {
    el.className = "table-thumb-cell";
  }
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
    const style = item.thumbStyle || {};
    ph.style.background = style.background || "#2a3140";
  } else {
    ph.className = "thumb-placeholder";
    Object.assign(ph.style, item.thumbStyle || {});
    ph.style.aspectRatio = "1";
  }
  el.appendChild(ph);
}

function renderGrid(list) {
  const grid = els.grid;
  grid.innerHTML = "";
  grid.classList.toggle("select-mode", state.selectMode);
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
    renderThumb(thumbWrap, item);
    card.appendChild(thumbWrap);

    if (item.score != null) {
      const sc = document.createElement("span");
      sc.className = "score";
      sc.textContent = item.score.toFixed(3);
      card.appendChild(sc);
    }

    card.addEventListener("click", (e) => onCardClick(item, e));
    grid.appendChild(card);
  }
}

function renderTable(list) {
  const tbody = els.tableBody;
  tbody.innerHTML = "";
  for (const item of list) {
    const tr = document.createElement("tr");
    if (item.image_id === state.activeId) tr.classList.add("active");
    tr.innerHTML = `
      <td class="col-thumb"><div class="table-thumb-cell"></div></td>
      <td class="col-filename">${item.file_name}</td>
      <td class="col-tags">${item.tags.slice(0, 6).join(", ")}</td>
      <td class="col-route">${item.route_tag?.split("/").pop() ?? ""}</td>
      <td class="col-score">${item.score?.toFixed(3) ?? "—"}</td>
    `;
    renderThumb(tr.querySelector(".table-thumb-cell"), item, "table");
    tr.addEventListener("click", () => openDetail(item.image_id, list));
    tbody.appendChild(tr);
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
  els.chipRow.innerHTML = '<span class="chip-row-label">条件</span>';
  for (const c of activeChips()) {
    const chip = document.createElement("span");
    chip.className = `chip ${c.type}`;
    chip.innerHTML = `${c.type === "exclude" ? "−" : ""}${c.label} <button type="button" class="x" aria-label="解除">×</button>`;
    chip.querySelector(".x").addEventListener("click", () => {
      state.tagStates[c.tag] = 0;
      syncQueryFromTags();
      render();
    });
    els.chipRow.appendChild(chip);
  }
  els.queryNote.classList.toggle("visible", /\([^)]+\)/.test(state.query));
}

function openDetail(id, list) {
  state.activeId = id;
  state.detailIndex = list.findIndex((i) => i.image_id === id);
  state.detailOverride = null;
  if (state.layout === "narrow") {
    els.detail.classList.add("mobile-open");
  }
  renderDetail(list);
  renderListOnly(list);
}

async function fetchWorkContext(imageId) {
  if (!state.useApi) return mockWorkContext(imageId);
  try {
    const res = await fetch(`/api/images/${encodeURIComponent(imageId)}`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.work ?? null;
  } catch {
    return null;
  }
}

function pageThumbUrl(p) {
  if (p.thumb_url) return p.thumb_url;
  if (p.has_thumbnail && p.image_id) {
    return `/api/images/${p.image_id}/thumbnail`;
  }
  return null;
}

async function fetchWorkPages(workId) {
  if (!state.useApi) {
    return getMockWorkPages(workId).map((p) => ({
      image_id: p.image_id,
      page: p.page,
      file_name: p.file_name,
      thumbStyle: p.thumbStyle,
      thumb_url: p.thumb_url,
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
  if (state.detailOverride) return state.detailOverride;
  const fromList = state.detailIndex >= 0 ? list[state.detailIndex] : null;
  if (fromList && fromList.image_id === state.activeId) return fromList;
  const local = IMAGES.find((i) => i.image_id === state.activeId);
  if (local) return local;
  const fromApi = state.apiImages?.find((i) => i.image_id === state.activeId);
  if (fromApi) return fromApi;
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
      Object.assign(ph.style, p.thumbStyle || { background: "#333", width: "52px", height: "52px" });
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

async function loadWorkPanel(item) {
  if (!item) {
    els.workPanel.hidden = true;
    state.workContext = null;
    state.workPages = [];
    return;
  }
  state.workContext = await fetchWorkContext(item.image_id);
  if (!state.workContext) {
    els.workPanel.hidden = true;
    state.workPages = [];
    return;
  }

  els.workPanel.hidden = false;
  els.workTitle.textContent = state.workContext.title || `作品 ${state.workContext.work_id}`;
  els.workArtist.textContent = state.workContext.artist || "";
  if (state.workContext.source_url) {
    els.workLink.href = state.workContext.source_url;
    els.workLink.style.display = "";
  } else {
    els.workLink.style.display = "none";
  }

  const pageLabel = state.workContext.page ?? state.workContext.page_index;
  els.workPos.textContent = `p${pageLabel} / ${state.workContext.page_count}`;
  els.workPrev.disabled = !state.workContext.prev_image_id;
  els.workNext.disabled = !state.workContext.next_image_id;

  state.workPages = await fetchWorkPages(state.workContext.work_id);
  renderPageStrip(item.image_id, state.workPages);
}

function navWorkPage(imageId) {
  const list = filteredImages();
  state.activeId = imageId;
  state.detailIndex = list.findIndex((i) => i.image_id === imageId);
  state.detailOverride = null;
  renderDetail(list);
  renderListOnly(list);
}

function navWork(delta) {
  if (!state.workContext) return;
  const target = delta < 0 ? state.workContext.prev_image_id : state.workContext.next_image_id;
  if (target) navWorkPage(target);
}

function closeDetailMobile() {
  els.detail.classList.remove("mobile-open");
  state.activeId = null;
  render();
}

function renderDetail(list) {
  void (async () => {
    const item = await resolveDetailItem(list);
    if (!item) {
      els.detailEmpty.style.display = "flex";
      els.detailContent.style.display = "none";
      els.workPanel.hidden = true;
      return;
    }
    els.detailEmpty.style.display = "none";
    els.detailContent.style.display = "flex";
    els.detailContent.style.flexDirection = "column";
    els.detailContent.style.flex = "1";
    els.detailContent.style.minHeight = "0";

    const listPos = state.detailIndex >= 0 ? `${state.detailIndex + 1} / ${list.length}` : "—";
    els.detailPos.textContent = listPos;

    els.detailImage.innerHTML = "";
    if (item.thumb_url || item.preview_url) {
      const img = document.createElement("img");
      img.src = item.preview_url || item.thumb_url;
      img.alt = item.file_name;
      els.detailImage.appendChild(img);
    } else {
      const ph = document.createElement("div");
      ph.className = "detail-ph";
      Object.assign(ph.style, item.thumbStyle || { minWidth: "200px", minHeight: "280px" });
      els.detailImage.appendChild(ph);
    }

    els.detailTags.innerHTML = (item.tags || [])
      .map((t) => `<span class="chip neutral">${t}</span>`)
      .join("");
    els.detailMeta.innerHTML = `
      <dt>ID</dt><dd>${item.image_id}</dd>
      <dt>ファイル</dt><dd>${item.file_name}</dd>
      <dt>ルート</dt><dd>${item.route_tag ?? "—"}</dd>
      <dt>サイズ</dt><dd>${item.width ?? "?"}×${item.height ?? "?"}</dd>
    `;
    els.detailCaption.textContent = item.vlm_caption || "（キャプションなし）";
    els.detailOcr.value = item.ocr_text || "";

    els.similarStrip.innerHTML = "";
    const sim = list.filter((i) => i.image_id !== item.image_id).slice(0, 8);
    for (const s of sim) {
      const m = document.createElement("div");
      m.className = "mini";
      Object.assign(m.style, s.thumbStyle || {});
      m.title = s.file_name;
      m.addEventListener("click", () => openDetail(s.image_id, list));
      els.similarStrip.appendChild(m);
    }

    await loadWorkPanel(item);
  })();
}

function renderListOnly(list) {
  $$(".image-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === state.activeId);
  });
}

function onCardClick(item, e) {
  const list = filteredImages();
  if (state.selectMode || e.shiftKey) {
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

function applyLayout() {
  const app = els.app;
  app.classList.remove("narrow", "detail-bottom");
  els.main.classList.remove("no-sidebar", "no-detail", "detail-bottom-layout");

  const showSidebar = $("#lab-sidebar").checked;
  const showDetail = $("#lab-detail").checked;
  const layout = $("#lab-layout").value;

  if (layout === "narrow") {
    app.classList.add("narrow");
    state.layout = "narrow";
  } else {
    state.layout = layout === "wide-bottom" ? "wide-bottom" : "wide-right";
    if (layout === "wide-bottom") {
      app.classList.add("detail-bottom");
      els.main.classList.add("detail-bottom-layout");
    }
  }

  if (!showSidebar) els.main.classList.add("no-sidebar");
  if (!showDetail) els.main.classList.add("no-detail");

  document.documentElement.style.setProperty("--sidebar-w", `${$("#lab-sidebar-w").value}px`);
  document.documentElement.style.setProperty("--detail-w", `${$("#lab-detail-w").value}px`);
  document.documentElement.style.setProperty("--grid-cols", $("#lab-cols").value);

  const w = $("#lab-width").value;
  if (layout === "custom") {
    app.style.maxWidth = `${w}px`;
    app.style.margin = "0 auto";
    app.style.borderLeft = "1px solid var(--border)";
    app.style.borderRight = "1px solid var(--border)";
  } else {
    app.style.maxWidth = "";
    app.style.margin = "";
    app.style.border = "";
  }
}

function render() {
  const list = filteredImages();
  els.resultCount.textContent = `${list.length.toLocaleString()} 件`;
  renderChips();
  renderTagList();
  if (state.viewMode === "grid") {
    els.grid.style.display = "grid";
    els.tableWrap.style.display = "none";
    renderGrid(list);
  } else {
    els.grid.style.display = "none";
    els.tableWrap.style.display = "block";
    renderTable(list);
  }
  if (state.activeId) {
    const idx = list.findIndex((i) => i.image_id === state.activeId);
    if (idx >= 0) {
      state.detailIndex = idx;
      renderDetail(list);
    }
  } else if (state.layout !== "narrow") {
    els.detailEmpty.style.display = "flex";
    els.detailContent.style.display = "none";
  }
  renderBulkBar();
  applyLayout();
}

async function tryLoadApi() {
  if (!state.useApi) return;
  try {
    const params = new URLSearchParams({ limit: "60", q: state.query });
    if (state.route !== "all") params.set("route_tag", state.route);
    const res = await fetch(`/api/images?${params}`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    state.apiImages = data.items.map((item) => ({
      ...item,
      thumb_url: `/api/images/${item.image_id}/thumbnail`,
      preview_url: `/api/images/${item.image_id}/preview`,
      vlm_caption: "",
      ocr_text: "",
    }));
  } catch (err) {
    console.warn("API fallback to mock:", err);
    state.apiImages = null;
    state.useApi = false;
    $("#lab-api").checked = false;
  }
}

function bindEvents() {
  els.queryInput.addEventListener("input", () => {
    state.query = els.queryInput.value;
    parseQueryTags(state.query);
    debouncedRender();
  });

  $$(".route-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".route-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.route = btn.dataset.route;
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
  els.detailClose.addEventListener("click", closeDetailMobile);

  $$(".similar-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".similar-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.similarTab = btn.dataset.tab;
    });
  });

  els.filterToggle.addEventListener("click", () => els.bottomSheet.classList.add("open"));
  els.sheetClose.addEventListener("click", () => els.bottomSheet.classList.remove("open"));
  els.sheetBackdrop.addEventListener("click", () => els.bottomSheet.classList.remove("open"));

  $("#lab-layout").addEventListener("change", render);
  $("#lab-sidebar").addEventListener("change", render);
  $("#lab-detail").addEventListener("change", render);
  $("#lab-cols").addEventListener("input", () => {
    $("#lab-cols-val").textContent = $("#lab-cols").value;
    render();
  });
  $("#lab-sidebar-w").addEventListener("input", () => {
    $("#lab-sidebar-w-val").textContent = `${$("#lab-sidebar-w").value}px`;
    render();
  });
  $("#lab-detail-w").addEventListener("input", () => {
    $("#lab-detail-w-val").textContent = `${$("#lab-detail-w").value}px`;
    render();
  });
  $("#lab-width").addEventListener("input", () => {
    $("#lab-width-val").textContent = `${$("#lab-width").value}px`;
    render();
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

  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (e.key === "/") {
      e.preventDefault();
      els.queryInput.focus();
    }
    if (state.activeId == null) return;
    if (e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault();
      navWork(e.key === "ArrowLeft" ? -1 : 1);
      return;
    }
    if (e.key === "ArrowLeft") navDetail(-1);
    if (e.key === "ArrowRight") navDetail(1);
    if (e.key === "Escape") {
      if (state.layout === "narrow") closeDetailMobile();
      else {
        state.activeId = null;
        render();
      }
    }
  });
}

function navDetail(delta) {
  const list = filteredImages();
  if (!list.length) return;
  state.detailIndex = Math.max(0, Math.min(list.length - 1, state.detailIndex + delta));
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
  }, 300);
}

function init() {
  els.app = $("#app");
  els.grid = $("#image-grid");
  els.tableWrap = $("#table-wrap");
  els.tableBody = $("#table-body");
  els.queryInput = $("#query-input");
  els.chipRow = $("#chip-row");
  els.queryNote = $("#query-note");
  els.tagList = $("#tag-list");
  els.tagFilter = $("#tag-filter");
  els.resultCount = $("#result-count");
  els.sortSelect = $("#sort-select");
  els.detail = $("#detail-pane");
  els.detailEmpty = $("#detail-empty");
  els.detailContent = $("#detail-content");
  els.detailImage = $("#detail-image");
  els.detailPos = $("#detail-pos");
  els.detailPrev = $("#detail-prev");
  els.detailNext = $("#detail-next");
  els.detailClose = $("#detail-close");
  els.workPanel = $("#work-panel");
  els.workTitle = $("#work-title");
  els.workArtist = $("#work-artist");
  els.workLink = $("#work-link");
  els.workPos = $("#work-pos");
  els.workPrev = $("#work-prev");
  els.workNext = $("#work-next");
  els.pageStrip = $("#page-strip");
  els.detailTags = $("#detail-tags");
  els.detailMeta = $("#detail-meta");
  els.detailCaption = $("#detail-caption");
  els.detailOcr = $("#detail-ocr");
  els.similarStrip = $("#similar-strip");
  els.bulkBar = $("#bulk-bar");
  els.bulkCount = $("#bulk-count");
  els.filterToggle = $("#filter-toggle");
  els.bottomSheet = $("#bottom-sheet");
  els.sheetClose = $("#sheet-close");
  els.sheetBackdrop = $("#sheet-backdrop");
  els.lab = $("#mockup-lab");
  els.labToggle = $("#lab-toggle");

  bindEvents();
  els.queryInput.value = state.query;
  render();
}

init();
