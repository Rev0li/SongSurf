import { c as create_ssr_component, a as subscribe, d as add_attribute, b as escape, e as each, f as add_classes, v as validate_component } from "../../chunks/ssr.js";
import { w as workerBusy, d as downloadStatus, r as recentDownloads, u as user } from "../../chunks/stores.js";
async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers ?? {} },
    credentials: "same-origin",
    ...options
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { success: false, error: text || "Réponse invalide" };
  }
  if (!response.ok) {
    throw new Error(data?.error ?? `HTTP ${response.status}`);
  }
  return data;
}
const api = {
  me() {
    return request("/api/me");
  },
  getStatus() {
    return request("/api/status");
  },
  getLibrary() {
    return request("/api/library");
  },
  extract(url) {
    return request("/api/extract", { method: "POST", body: JSON.stringify({ url }) });
  },
  download(payload) {
    return request("/api/download", { method: "POST", body: JSON.stringify(payload) });
  },
  downloadPlaylist(payload) {
    return request("/api/download-playlist", { method: "POST", body: JSON.stringify(payload) });
  },
  cancel() {
    return request("/api/cancel", { method: "POST" });
  },
  prepareZip() {
    return request("/api/prepare-zip", { method: "POST" });
  },
  moveSong(source, targetFolder) {
    return request("/api/library/move", {
      method: "POST",
      body: JSON.stringify({ source, target_folder: targetFolder })
    });
  },
  renameFolder(folderPath, newName) {
    return request("/api/library/rename-folder", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath, new_name: newName })
    });
  },
  uploadLibraryImage(file, targetFolder) {
    const form = new FormData();
    form.append("image", file);
    form.append("target_folder", targetFolder);
    return fetch("/api/library/upload-image", {
      method: "POST",
      credentials: "same-origin",
      body: form
    }).then(async (res) => {
      const text = await res.text();
      let data;
      try {
        data = text ? JSON.parse(text) : {};
      } catch {
        data = { success: false, error: text };
      }
      if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
      return data;
    });
  },
  cancelPrefetch(token) {
    return request("/api/prefetch/cancel", { method: "POST", body: JSON.stringify({ token }) });
  },
  getPrefetchCoverUrl(token) {
    return `/api/prefetch/cover?token=${encodeURIComponent(token)}&t=${Date.now()}`;
  },
  getFolderCoverUrl(folderPath) {
    return `/api/library/folder-cover?folder_path=${encodeURIComponent(folderPath)}&t=${Date.now()}`;
  }
};
function asText(value, fallback = "") {
  const v = (value ?? "").toString().trim();
  return v || fallback;
}
function primaryArtist(value) {
  const str = asText(value, "Unknown Artist");
  const parts = str.split(/\s*(?:,|;|\||&|\band\b|\bet\b|\/)\s*/i).filter(Boolean);
  return parts[0] || str;
}
function nrm(text) {
  return (text ?? "").toString().toLowerCase().trim();
}
function matchesFilter(text, query) {
  if (!query) return true;
  return nrm(text).includes(query);
}
const DownloadPanel = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let dlDisabled;
  let dlLabel;
  let $workerBusy, $$unsubscribe_workerBusy;
  $$unsubscribe_workerBusy = subscribe(workerBusy, (value) => $workerBusy = value);
  let { onDownloadQueued = () => {
  } } = $$props;
  let url = "";
  let title = "";
  let artist = "";
  let album = "";
  let playlistMode = false;
  let mp4Mode = false;
  if ($$props.onDownloadQueued === void 0 && $$bindings.onDownloadQueued && onDownloadQueued !== void 0) $$bindings.onDownloadQueued(onDownloadQueued);
  dlDisabled = true;
  dlLabel = $workerBusy ? "⏳ En attente de Worker" : "⬇️ Télécharger";
  $$unsubscribe_workerBusy();
  return ` <section class="top-analyzer-wrap"><div class="card top-analyzer-card"><h2 class="card-title" data-svelte-h="svelte-9teiro">🔗 Coller un lien YouTube Music</h2> <div class="url-group"><input type="text" class="form-input" placeholder="https://music.youtube.com/watch?v=..." autocomplete="off" ${""}${add_attribute("value", url, 0)}> <button class="btn btn-primary" ${""}>${escape("🔍 Analyser")}</button></div></div></section>  <div class="card metadata-panel"><h2 class="card-title" data-svelte-h="svelte-qxy8u2">🎛️ Panneau d&#39;analyse</h2> <div class="${["metadata-preview", "analysis-disabled"].join(" ").trim()}"><div class="metadata-layout"><div class="metadata-main"> ${`<div class="metadata-info"><div class="form-group"><label class="form-label" data-svelte-h="svelte-1djb3pk">Titre</label> <input class="form-input" placeholder="Titre" ${"disabled"}${add_attribute("value", title, 0)}></div> <div class="form-group compact-row">${`<div><label class="form-label" data-svelte-h="svelte-wdommi">Artiste</label> <input class="form-input" placeholder="Artiste" ${"disabled"}${add_attribute("value", artist, 0)}></div>`} <div${add_attribute("style", "", 0)}><label class="form-label" data-svelte-h="svelte-k1egyl">Album</label> <input class="form-input" placeholder="Album" ${"disabled"}${add_attribute("value", album, 0)}></div></div></div>`}  ${``} <div class="metadata-actions"><button class="btn btn-brand btn-block" ${dlDisabled ? "disabled" : ""}>${escape(dlLabel)}</button> <button class="btn btn-danger btn-sm" ${"disabled"}>✕ Annuler</button></div></div>  <aside class="metadata-options-column"><div class="cover-preview-box"><div class="progress-subtext" data-svelte-h="svelte-1o810us">Pochette</div> ${``} ${`<div class="cover-placeholder" data-svelte-h="svelte-6l4w68">Aperçu pochette</div>`}</div> <div class="option-card"><div class="toggle-row option-toggle-row"><div class="toggle-description" data-svelte-h="svelte-e2ncvw"><strong>🎵 Mode Playlist</strong> <small>Actif : pas de tri artiste.</small> <small>Inactif : tri Artist/Album/Titre.</small></div> <label class="toggle-switch"><input type="checkbox" ${"disabled"}${add_attribute("checked", playlistMode, 1)}> <span class="toggle-slider"></span></label></div> <div class="toggle-row option-toggle-row"><div class="toggle-description" data-svelte-h="svelte-so3bni"><strong>🎬 Mode MP4 (max 1080p)</strong></div> <label class="toggle-switch"><input type="checkbox" ${"disabled"}${add_attribute("checked", mp4Mode, 1)}> <span class="toggle-slider"></span></label></div></div></aside></div></div></div>`;
});
const ProgressZone = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let current;
  let pct;
  let total;
  let done;
  let statusLabel;
  let $workerBusy, $$unsubscribe_workerBusy;
  let $downloadStatus, $$unsubscribe_downloadStatus;
  $$unsubscribe_workerBusy = subscribe(workerBusy, (value) => $workerBusy = value);
  $$unsubscribe_downloadStatus = subscribe(downloadStatus, (value) => $downloadStatus = value);
  current = $downloadStatus.current_download?.metadata ?? {};
  pct = Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0)));
  total = Number($downloadStatus.batch_total ?? 0);
  done = Number($downloadStatus.batch_done ?? 0);
  statusLabel = $workerBusy ? current.artist ? `${primaryArtist(current.artist)} — ${asText(current.title, "…")}` : asText(current.title, "En attente…") : "En attente…";
  $$unsubscribe_workerBusy();
  $$unsubscribe_downloadStatus();
  return `${$workerBusy ? `<div class="card" id="progress-zone"><h2 class="card-title" data-svelte-h="svelte-13203s6">⏳ Téléchargement en cours</h2> <div class="progress-total"><div class="progress-total-fill" style="${"width: " + escape(pct, true) + "%"}"></div></div> <div class="progress-text"><span>${escape(statusLabel)}</span> <span>${escape(pct.toFixed(1))}%</span></div> <div class="progress-subtext">${escape(done)} / ${escape(total)} titre${escape(total > 1 ? "s" : "")}</div></div>` : ``}`;
});
const RecentDownloads = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let $recentDownloads, $$unsubscribe_recentDownloads;
  $$unsubscribe_recentDownloads = subscribe(recentDownloads, (value) => $recentDownloads = value);
  $$unsubscribe_recentDownloads();
  return `<div class="card"><h2 class="card-title" data-svelte-h="svelte-13s75lw">✅ Téléchargements récents</h2> <button class="btn btn-success btn-block" style="margin-bottom: var(--space-3)" ${""}>${escape("📥 Télécharger mon ZIP")}</button> ${$recentDownloads.length === 0 ? `<div class="empty-state" data-svelte-h="svelte-29ytji"><div class="empty-state-icon">📭</div> <p class="empty-state-text">Aucun téléchargement</p></div>` : `<div id="dl-list">${each($recentDownloads, (dl) => {
    return `<div class="dl-item"><strong>${escape(dl.artist)} — ${escape(dl.title)}</strong> ${dl.filePath ? `<div class="progress-subtext">${escape(dl.filePath)}</div>` : ``} </div>`;
  })}</div>`}</div>`;
});
const LibraryTree = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let q;
  let filteredArtists;
  let filteredPlaylists;
  let isEmpty;
  let tree = null;
  let filter = "";
  let expanded = /* @__PURE__ */ new Set();
  let selectedFolderPath = "";
  async function refresh() {
    try {
      const data = await api.getLibrary();
      tree = data;
    } catch {
      if (!tree) tree = { artists: [], playlists: [] };
    }
  }
  if ($$props.refresh === void 0 && $$bindings.refresh && refresh !== void 0) $$bindings.refresh(refresh);
  q = nrm(filter);
  filteredArtists = (tree?.artists ?? []).map((a) => ({
    ...a,
    albums: (a.albums ?? []).map((al) => ({
      ...al,
      songs: (al.songs ?? []).filter((s) => matchesFilter([a.name, al.name, s.name].join(" "), q))
    })).filter((al) => al.songs.length > 0 || matchesFilter(`${a.name} ${al.name}`, q))
  })).filter((a) => a.albums.length > 0);
  filteredPlaylists = (tree?.playlists ?? []).map((pl) => ({
    ...pl,
    songs: (pl.songs ?? []).filter((s) => matchesFilter([pl.name, s.name].join(" "), q))
  })).filter((pl) => pl.songs.length > 0 || matchesFilter(pl.name, q));
  isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;
  return ` <div class="card"><h2 class="card-title" data-svelte-h="svelte-rf7prx">📚 Bibliothèque</h2>  <div class="lib-toolbar" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center"><input class="form-input" placeholder="Rechercher…" style="flex:1;min-width:140px"${add_attribute("value", filter, 0)}> <button class="btn btn-ghost btn-sm" data-svelte-h="svelte-eg4hfn">Tout ouvrir</button> <button class="btn btn-ghost btn-sm" data-svelte-h="svelte-1a8ie0g">Tout fermer</button></div>  ${``}  ${tree === null ? `<div class="empty-state-text" data-svelte-h="svelte-13l3xgg">Chargement…</div>` : `${isEmpty ? `<div class="empty-state-text">${escape("Aucune musique dans la bibliothèque.")}</div>` : `<div class="library-tree"> ${each(filteredArtists, (artist) => {
    return `<details ${(q ? true : expanded.has(artist.path)) ? "open" : ""}${add_classes((selectedFolderPath === artist.path ? "selected-folder" : "").trim())}><summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">${escape(expanded.has(artist.path) || q ? "▾" : "▸")}</span> <span class="lib-icon" data-svelte-h="svelte-1o5ot38">🎤</span> <span class="lib-name">${escape(artist.name)}</span> <span class="lib-count">${escape(artist.albums.reduce((n, al) => n + al.songs.length, 0))}</span></span> <button class="folder-actions" data-svelte-h="svelte-ljr073">✏️</button> </div></summary> ${each(artist.albums, (album) => {
      return `<details ${(q ? true : expanded.has(album.path)) ? "open" : ""}${add_classes((selectedFolderPath === album.path ? "selected-folder" : "").trim())}><summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">${escape(expanded.has(album.path) || q ? "▾" : "▸")}</span> <span class="lib-icon" data-svelte-h="svelte-bbfjz4">💿</span> <span class="lib-name">${escape(album.name)}</span> <span class="lib-count">${escape(album.songs.length)}</span></span> <button class="folder-actions" data-svelte-h="svelte-xvz85x">✏️</button> </div></summary> ${each(album.songs, (song) => {
        return `<div class="song-item lib-song-row" draggable="true"><span class="lib-song-name">${escape(song.name)}</span> <span class="lib-drag-hint" data-svelte-h="svelte-1s2o68d">drag</span> </div>`;
      })} </details>`;
    })} </details>`;
  })}  ${each(filteredPlaylists, (pl) => {
    return `<details ${(q ? true : expanded.has(pl.path)) ? "open" : ""}${add_classes((selectedFolderPath === pl.path ? "selected-folder" : "").trim())}><summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">${escape(expanded.has(pl.path) || q ? "▾" : "▸")}</span> <span class="lib-icon" data-svelte-h="svelte-k71h4y">📁</span> <span class="lib-name">${escape(pl.name)}</span> <span class="lib-count">${escape(pl.songs.length)}</span></span> <button class="folder-actions" data-svelte-h="svelte-74ie19">✏️</button> </div></summary> ${each(pl.songs, (song) => {
      return `<div class="song-item lib-song-row" draggable="true"><span class="lib-song-name">${escape(song.name)}</span> <span class="lib-drag-hint" data-svelte-h="svelte-1s2o68d">drag</span> </div>`;
    })} </details>`;
  })}</div>`}`}</div>`;
});
const css = {
  code: ".main-grid.svelte-12a0igv{display:grid;grid-template-columns:70% 30%;gap:var(--space-6);max-width:1200px;margin:0 auto;padding:var(--space-8) var(--space-5)}@media(max-width: 1024px){.main-grid.svelte-12a0igv{grid-template-columns:1fr}.side-column.svelte-12a0igv{order:-1}}",
  map: `{"version":3,"file":"+page.svelte","sources":["+page.svelte"],"sourcesContent":["<script>\\n\\timport { user } from '$lib/stores.js';\\n\\timport DownloadPanel from '$lib/components/DownloadPanel.svelte';\\n\\timport ProgressZone from '$lib/components/ProgressZone.svelte';\\n\\timport RecentDownloads from '$lib/components/RecentDownloads.svelte';\\n\\timport LibraryTree from '$lib/components/LibraryTree.svelte';\\n\\n\\tlet libraryRef;\\n\\n\\tfunction onDownloadQueued() {\\n\\t\\tlibraryRef?.refresh();\\n\\t}\\n<\/script>\\n\\n<svelte:head>\\n\\t<title>Dashboard — SongSurf</title>\\n</svelte:head>\\n\\n<header class=\\"header\\">\\n\\t<div class=\\"header-brand\\">\\n\\t\\t<span class=\\"header-logo\\">🎵</span>\\n\\t\\t<h1 class=\\"header-title\\">SongSurf</h1>\\n\\t</div>\\n\\t<nav class=\\"header-nav\\">\\n\\t\\t{#if $user?.email}\\n\\t\\t\\t<span class=\\"badge badge-primary\\" title={$user.sub}>{$user.email}</span>\\n\\t\\t{/if}\\n\\t\\t<a href=\\"/donation\\" class=\\"btn btn-ghost btn-sm\\">Donation</a>\\n\\t</nav>\\n</header>\\n\\n<DownloadPanel onDownloadQueued={onDownloadQueued} />\\n\\n<div class=\\"main-grid\\">\\n\\t<div class=\\"main-column\\">\\n\\t\\t<ProgressZone />\\n\\t\\t<LibraryTree bind:this={libraryRef} />\\n\\t</div>\\n\\t<div class=\\"side-column\\">\\n\\t\\t<RecentDownloads />\\n\\t</div>\\n</div>\\n\\n<style>\\n\\t.main-grid {\\n\\t\\tdisplay: grid;\\n\\t\\tgrid-template-columns: 70% 30%;\\n\\t\\tgap: var(--space-6);\\n\\t\\tmax-width: 1200px;\\n\\t\\tmargin: 0 auto;\\n\\t\\tpadding: var(--space-8) var(--space-5);\\n\\t}\\n\\t@media (max-width: 1024px) {\\n\\t\\t.main-grid { grid-template-columns: 1fr; }\\n\\t\\t.side-column { order: -1; }\\n\\t}\\n</style>\\n"],"names":[],"mappings":"AA4CC,yBAAW,CACV,OAAO,CAAE,IAAI,CACb,qBAAqB,CAAE,GAAG,CAAC,GAAG,CAC9B,GAAG,CAAE,IAAI,SAAS,CAAC,CACnB,SAAS,CAAE,MAAM,CACjB,MAAM,CAAE,CAAC,CAAC,IAAI,CACd,OAAO,CAAE,IAAI,SAAS,CAAC,CAAC,IAAI,SAAS,CACtC,CACA,MAAO,YAAY,MAAM,CAAE,CAC1B,yBAAW,CAAE,qBAAqB,CAAE,GAAK,CACzC,2BAAa,CAAE,KAAK,CAAE,EAAI,CAC3B"}`
};
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let $user, $$unsubscribe_user;
  $$unsubscribe_user = subscribe(user, (value) => $user = value);
  let libraryRef;
  function onDownloadQueued() {
    libraryRef?.refresh();
  }
  $$result.css.add(css);
  let $$settled;
  let $$rendered;
  let previous_head = $$result.head;
  do {
    $$settled = true;
    $$result.head = previous_head;
    $$rendered = `${$$result.head += `<!-- HEAD_svelte-17m8xz1_START -->${$$result.title = `<title>Dashboard — SongSurf</title>`, ""}<!-- HEAD_svelte-17m8xz1_END -->`, ""} <header class="header"><div class="header-brand" data-svelte-h="svelte-1qvdzty"><span class="header-logo">🎵</span> <h1 class="header-title">SongSurf</h1></div> <nav class="header-nav">${$user?.email ? `<span class="badge badge-primary"${add_attribute("title", $user.sub, 0)}>${escape($user.email)}</span>` : ``} <a href="/donation" class="btn btn-ghost btn-sm" data-svelte-h="svelte-168f12l">Donation</a></nav></header> ${validate_component(DownloadPanel, "DownloadPanel").$$render($$result, { onDownloadQueued }, {}, {})} <div class="main-grid svelte-12a0igv"><div class="main-column">${validate_component(ProgressZone, "ProgressZone").$$render($$result, {}, {}, {})} ${validate_component(LibraryTree, "LibraryTree").$$render(
      $$result,
      { this: libraryRef },
      {
        this: ($$value) => {
          libraryRef = $$value;
          $$settled = false;
        }
      },
      {}
    )}</div> <div class="side-column svelte-12a0igv">${validate_component(RecentDownloads, "RecentDownloads").$$render($$result, {}, {}, {})}</div> </div>`;
  } while (!$$settled);
  $$unsubscribe_user();
  return $$rendered;
});
export {
  Page as default
};
