

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/donation/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/3.BtUJAEKs.js","_app/immutable/chunks/scheduler.ciK3WxRx.js","_app/immutable/chunks/index.CWH-mSnn.js","_app/immutable/chunks/stores.BAaZsHgm.js","_app/immutable/chunks/index.OV4-fCl-.js"];
export const stylesheets = ["_app/immutable/assets/3.Bf9iNmJ6.css"];
export const fonts = [];
