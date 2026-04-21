import { c as create_ssr_component, a as subscribe, e as each, b as escape, o as onDestroy, v as validate_component } from "../../chunks/ssr.js";
import { t as toasts } from "../../chunks/stores.js";
const css$1 = {
  code: ".toast-zone.svelte-z33arq.svelte-z33arq{position:fixed;top:72px;left:50%;transform:translateX(-50%);width:min(540px, 90vw);z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}.toast-zone.svelte-z33arq .alert.svelte-z33arq{pointer-events:all;cursor:pointer;animation:svelte-z33arq-slideIn 0.2s ease}@keyframes svelte-z33arq-slideIn{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}",
  map: `{"version":3,"file":"Toast.svelte","sources":["Toast.svelte"],"sourcesContent":["<script>\\n\\timport { toasts, removeToast } from '$lib/stores.js';\\n<\/script>\\n\\n<div class=\\"toast-zone\\">\\n\\t{#each $toasts as toast (toast.id)}\\n\\t\\t<div\\n\\t\\t\\tclass=\\"alert {toast.type === 'error' ? 'alert-error' : 'alert-info'}\\"\\n\\t\\t\\trole=\\"alert\\"\\n\\t\\t\\ton:click={() => removeToast(toast.id)}\\n\\t\\t>\\n\\t\\t\\t{toast.message}\\n\\t\\t</div>\\n\\t{/each}\\n</div>\\n\\n<style>\\n\\t.toast-zone {\\n\\t\\tposition: fixed;\\n\\t\\ttop: 72px;\\n\\t\\tleft: 50%;\\n\\t\\ttransform: translateX(-50%);\\n\\t\\twidth: min(540px, 90vw);\\n\\t\\tz-index: 9999;\\n\\t\\tdisplay: flex;\\n\\t\\tflex-direction: column;\\n\\t\\tgap: 8px;\\n\\t\\tpointer-events: none;\\n\\t}\\n\\t.toast-zone .alert {\\n\\t\\tpointer-events: all;\\n\\t\\tcursor: pointer;\\n\\t\\tanimation: slideIn 0.2s ease;\\n\\t}\\n\\t@keyframes slideIn {\\n\\t\\tfrom { opacity: 0; transform: translateY(-8px); }\\n\\t\\tto   { opacity: 1; transform: translateY(0); }\\n\\t}\\n</style>\\n"],"names":[],"mappings":"AAiBC,uCAAY,CACX,QAAQ,CAAE,KAAK,CACf,GAAG,CAAE,IAAI,CACT,IAAI,CAAE,GAAG,CACT,SAAS,CAAE,WAAW,IAAI,CAAC,CAC3B,KAAK,CAAE,IAAI,KAAK,CAAC,CAAC,IAAI,CAAC,CACvB,OAAO,CAAE,IAAI,CACb,OAAO,CAAE,IAAI,CACb,cAAc,CAAE,MAAM,CACtB,GAAG,CAAE,GAAG,CACR,cAAc,CAAE,IACjB,CACA,yBAAW,CAAC,oBAAO,CAClB,cAAc,CAAE,GAAG,CACnB,MAAM,CAAE,OAAO,CACf,SAAS,CAAE,qBAAO,CAAC,IAAI,CAAC,IACzB,CACA,WAAW,qBAAQ,CAClB,IAAK,CAAE,OAAO,CAAE,CAAC,CAAE,SAAS,CAAE,WAAW,IAAI,CAAG,CAChD,EAAK,CAAE,OAAO,CAAE,CAAC,CAAE,SAAS,CAAE,WAAW,CAAC,CAAG,CAC9C"}`
};
const Toast = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let $toasts, $$unsubscribe_toasts;
  $$unsubscribe_toasts = subscribe(toasts, (value) => $toasts = value);
  $$result.css.add(css$1);
  $$unsubscribe_toasts();
  return `<div class="toast-zone svelte-z33arq">${each($toasts, (toast) => {
    return `<div class="${"alert " + escape(toast.type === "error" ? "alert-error" : "alert-info", true) + " svelte-z33arq"}" role="alert">${escape(toast.message)} </div>`;
  })} </div>`;
});
const css = {
  code: ".inactivity-banner.svelte-a57x6f{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--color-warning, #b45309);color:#fff;padding:10px 20px;border-radius:var(--radius-lg, 8px);display:flex;align-items:center;gap:16px;z-index:8000;box-shadow:0 4px 16px rgba(0,0,0,0.4);font-size:14px}",
  map: `{"version":3,"file":"WatcherInactivity.svelte","sources":["WatcherInactivity.svelte"],"sourcesContent":["<script>\\n\\timport { onMount, onDestroy } from 'svelte';\\n\\n\\tlet warned = false;\\n\\tlet graceRemaining = 0;\\n\\tlet forceStopIn = 0;\\n\\tlet interval;\\n\\n\\tasync function poll() {\\n\\t\\ttry {\\n\\t\\t\\tconst res = await fetch('/watcher/inactivity-status', { credentials: 'same-origin' });\\n\\t\\t\\tif (!res.ok) return;\\n\\t\\t\\tconst data = await res.json();\\n\\t\\t\\twarned = !!data.warned;\\n\\t\\t\\tgraceRemaining = data.grace_remaining_seconds ?? 0;\\n\\t\\t\\tforceStopIn = data.force_stop_in_seconds ?? 0;\\n\\t\\t} catch {\\n\\t\\t\\t// ignore\\n\\t\\t}\\n\\t}\\n\\n\\tasync function keepalive() {\\n\\t\\ttry {\\n\\t\\t\\tawait fetch('/watcher/keepalive', { method: 'POST', credentials: 'same-origin' });\\n\\t\\t\\twarned = false;\\n\\t\\t} catch {\\n\\t\\t\\t// ignore\\n\\t\\t}\\n\\t}\\n\\n\\tonMount(() => {\\n\\t\\tpoll();\\n\\t\\tinterval = setInterval(poll, 30_000);\\n\\t});\\n\\n\\tonDestroy(() => clearInterval(interval));\\n<\/script>\\n\\n{#if warned}\\n\\t<div class=\\"inactivity-banner\\">\\n\\t\\t<span>\\n\\t\\t\\t⌛ Inactivité détectée — arrêt automatique dans\\n\\t\\t\\t<strong>{Math.ceil(graceRemaining / 60)} min</strong>\\n\\t\\t</span>\\n\\t\\t<button class=\\"btn btn-sm btn-primary\\" on:click={keepalive}>\\n\\t\\t\\tRester actif\\n\\t\\t</button>\\n\\t</div>\\n{/if}\\n\\n<style>\\n\\t.inactivity-banner {\\n\\t\\tposition: fixed;\\n\\t\\tbottom: 16px;\\n\\t\\tleft: 50%;\\n\\t\\ttransform: translateX(-50%);\\n\\t\\tbackground: var(--color-warning, #b45309);\\n\\t\\tcolor: #fff;\\n\\t\\tpadding: 10px 20px;\\n\\t\\tborder-radius: var(--radius-lg, 8px);\\n\\t\\tdisplay: flex;\\n\\t\\talign-items: center;\\n\\t\\tgap: 16px;\\n\\t\\tz-index: 8000;\\n\\t\\tbox-shadow: 0 4px 16px rgba(0,0,0,0.4);\\n\\t\\tfont-size: 14px;\\n\\t}\\n</style>\\n"],"names":[],"mappings":"AAmDC,gCAAmB,CAClB,QAAQ,CAAE,KAAK,CACf,MAAM,CAAE,IAAI,CACZ,IAAI,CAAE,GAAG,CACT,SAAS,CAAE,WAAW,IAAI,CAAC,CAC3B,UAAU,CAAE,IAAI,eAAe,CAAC,QAAQ,CAAC,CACzC,KAAK,CAAE,IAAI,CACX,OAAO,CAAE,IAAI,CAAC,IAAI,CAClB,aAAa,CAAE,IAAI,WAAW,CAAC,IAAI,CAAC,CACpC,OAAO,CAAE,IAAI,CACb,WAAW,CAAE,MAAM,CACnB,GAAG,CAAE,IAAI,CACT,OAAO,CAAE,IAAI,CACb,UAAU,CAAE,CAAC,CAAC,GAAG,CAAC,IAAI,CAAC,KAAK,CAAC,CAAC,CAAC,CAAC,CAAC,CAAC,GAAG,CAAC,CACtC,SAAS,CAAE,IACZ"}`
};
const WatcherInactivity = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let interval;
  onDestroy(() => clearInterval(interval));
  $$result.css.add(css);
  return `${``}`;
});
const Layout = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let pollInterval;
  onDestroy(() => clearInterval(pollInterval));
  return `${validate_component(Toast, "Toast").$$render($$result, {}, {}, {})} ${validate_component(WatcherInactivity, "WatcherInactivity").$$render($$result, {}, {}, {})} ${slots.default ? slots.default({}) : ``}`;
});
export {
  Layout as default
};
