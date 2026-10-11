/** Mock image list for layout prototyping. Replace with API later. */
export const ROUTES = [
  { id: "route/under-iphone", label: "under.iphone", count: 3926 },
  { id: "route/pixiv", label: "pixiv", count: 36394 },
];

export const TAGS = [
  "女性", "室内", "黒髪", "太もも", "脚", "手", "パンツ", "画角/上半身",
  "アングル/正面", "人数/1人", "種類/写真", "笑顔", "制服", "水着",
  "青髪", "赤髪", "屋外", "夜景", "R-18", "オリジナル",
];

/** Deterministic hue from string */
function hue(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

function makeThumbStyle(id, w, h) {
  const h1 = hue(id);
  const h2 = (h1 + 40) % 360;
  return {
    background: `linear-gradient(135deg, hsl(${h1} 45% 28%) 0%, hsl(${h2} 55% 18%) 100%)`,
    aspectRatio: `${w}/${h}`,
  };
}

function pickTags(seed, n = 6) {
  const out = [];
  for (let i = 0; i < TAGS.length && out.length < n; i++) {
    if (((seed * 17 + i * 13) % 7) < 3) out.push(TAGS[i]);
  }
  return out.length ? out : TAGS.slice(0, 4);
}

/** pixiv 複数ページ作品のモック定義 */
const MOCK_WORKS = [
  { work_id: "100001", title: "2024年まとめ（12p）", artist: "mock_artist", pages: 12, startIndex: 10, posted_at: "2024-01-08" },
  { work_id: "100002", title: "短編セット", artist: "mock_artist2", pages: 3, startIndex: 30, posted_at: "2024-05-22" },
  { work_id: "100003", title: "167p 相当の長編（UIテスト用20p）", artist: "mock_artist3", pages: 20, startIndex: 50, posted_at: "2023-11-03" },
];

/** pixiv 単ページ作品（ページナビなし・メタデータあり） */
const MOCK_SINGLE_PIXIV = [
  { work_id: "200001", title: "単ページイラスト", artist: "solo_artist", index: 5, posted_at: "2024-03-15" },
  { work_id: "200002", title: "ラクガキ", artist: "solo_artist2", index: 6, posted_at: "2024-06-20" },
];

function singlePixivForIndex(i) {
  return MOCK_SINGLE_PIXIV.find((w) => w.index === i) ?? null;
}

function workForIndex(i) {
  for (const w of MOCK_WORKS) {
    if (i >= w.startIndex && i < w.startIndex + w.pages) {
      return { ...w, page: i - w.startIndex };
    }
  }
  return null;
}

export const IMAGES = Array.from({ length: 120 }, (_, i) => {
  const n = String(i + 1).padStart(3, "0");
  const id = `img_mock_${n}`;
  const work = workForIndex(i);
  const singlePixiv = singlePixivForIndex(i);
  const route = work || singlePixiv || i % 5 === 0 ? "route/pixiv" : "route/under-iphone";
  const w = [800, 1200, 900, 1600, 750][i % 5];
  const h = [1200, 800, 1350, 900, 1000][i % 5];
  const pixivMeta = work || singlePixiv;
  return {
    image_id: id,
    file_name: work
      ? `${work.work_id}_p${work.page}.jpg`
      : singlePixiv
        ? `${singlePixiv.work_id}.jpg`
        : `sample_${n}_テスト画像.jpg`,
    route_tag: route,
    width: w,
    height: h,
    tags: pickTags(i + 1),
    score: i % 8 === 0 ? +(0.45 - i * 0.001).toFixed(3) : null,
    ocr_text: i % 11 === 0 ? "サンプル OCR テキスト\n2行目" : "",
    vlm_caption: i % 3 === 0
      ? "室内で撮影された写真。自然光が窓から差し込んでいる。"
      : "",
    thumbStyle: makeThumbStyle(id, w, h),
    work_id: pixivMeta?.work_id ?? null,
    work_title: pixivMeta?.title ?? null,
    work_artist: pixivMeta?.artist ?? null,
    posted_at: pixivMeta?.posted_at ?? (route === "route/pixiv" ? `2024-${String((i % 12) + 1).padStart(2, "0")}-10` : null),
    page: work?.page ?? null,
    source_url: pixivMeta ? `https://www.pixiv.net/artworks/${pixivMeta.work_id}` : null,
  };
});

export function getMockWorkPages(workId) {
  return IMAGES.filter((img) => img.work_id === workId).sort(
    (a, b) => (a.page ?? 0) - (b.page ?? 0),
  );
}

export function mockWorkContext(imageId) {
  const item = IMAGES.find((img) => img.image_id === imageId);
  if (!item?.work_id) return null;
  const pages = getMockWorkPages(item.work_id);
  const pageIndex = pages.findIndex((p) => p.image_id === imageId);
  const pageCount = pages.length;
  const multiPage = pageCount > 1;
  return {
    work_id: item.work_id,
    title: item.work_title,
    artist: item.work_artist,
    posted_at: item.posted_at,
    source_url: item.source_url,
    page: item.page,
    page_index: pageIndex >= 0 ? pageIndex : 0,
    page_count: pageCount,
    multi_page: multiPage,
    prev_image_id: multiPage && pageIndex > 0 ? pages[pageIndex - 1].image_id : null,
    next_image_id: multiPage && pageIndex < pageCount - 1 ? pages[pageIndex + 1].image_id : null,
  };
}

export const ALBUMS = [
  { id: "ref-2024", label: "参考資料 2024" },
  { id: "wip", label: "作業中" },
  { id: "favorites", label: "お気に入り" },
];
