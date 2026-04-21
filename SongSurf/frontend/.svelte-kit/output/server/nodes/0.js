import * as universal from '../entries/pages/_layout.js';

export const index = 0;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/_layout.svelte.js')).default;
export { universal };
export const universal_id = "src/routes/+layout.js";
export const imports = ["_app/immutable/nodes/0.eknYXFM5.js","_app/immutable/chunks/scheduler.ciK3WxRx.js","_app/immutable/chunks/index.CWH-mSnn.js","_app/immutable/chunks/utils.C6iSAHHS.js","_app/immutable/chunks/stores.BAaZsHgm.js","_app/immutable/chunks/index.OV4-fCl-.js"];
export const stylesheets = ["_app/immutable/assets/0.DxPEvexp.css"];
export const fonts = [];
