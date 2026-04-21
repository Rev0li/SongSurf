export const manifest = (() => {
function __memo(fn) {
	let value;
	return () => value ??= (value = fn());
}

return {
	appDir: "_app",
	appPath: "_app",
	assets: new Set([]),
	mimeTypes: {},
	_: {
		client: {"start":"_app/immutable/entry/start.CjKZUn8h.js","app":"_app/immutable/entry/app.B78dqjwM.js","imports":["_app/immutable/entry/start.CjKZUn8h.js","_app/immutable/chunks/entry.B0gxsClL.js","_app/immutable/chunks/scheduler.ciK3WxRx.js","_app/immutable/chunks/index.OV4-fCl-.js","_app/immutable/entry/app.B78dqjwM.js","_app/immutable/chunks/scheduler.ciK3WxRx.js","_app/immutable/chunks/index.CWH-mSnn.js"],"stylesheets":[],"fonts":[],"uses_env_dynamic_public":false},
		nodes: [
			__memo(() => import('./nodes/0.js')),
			__memo(() => import('./nodes/1.js')),
			__memo(() => import('./nodes/2.js')),
			__memo(() => import('./nodes/3.js'))
		],
		routes: [
			{
				id: "/",
				pattern: /^\/$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 2 },
				endpoint: null
			},
			{
				id: "/donation",
				pattern: /^\/donation\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 3 },
				endpoint: null
			}
		],
		matchers: async () => {
			
			return {  };
		},
		server_assets: {}
	}
}
})();
