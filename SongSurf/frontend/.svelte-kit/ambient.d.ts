
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * Environment variables [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env`. Like [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private), this module cannot be imported into client-side code. This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured).
 * 
 * _Unlike_ [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private), the values exported from this module are statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * ```ts
 * import { API_KEY } from '$env/static/private';
 * ```
 * 
 * Note that all environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * 
 * ```
 * MY_FEATURE_FLAG=""
 * ```
 * 
 * You can override `.env` values from the command line like so:
 * 
 * ```bash
 * MY_FEATURE_FLAG="enabled" npm run dev
 * ```
 */
declare module '$env/static/private' {
	export const GJS_DEBUG_TOPICS: string;
	export const ZSH_CONFIG_DIR: string;
	export const MAIL: string;
	export const LANGUAGE: string;
	export const USER: string;
	export const CLAUDE_CODE_ENTRYPOINT: string;
	export const npm_config_user_agent: string;
	export const XDG_SEAT: string;
	export const GIT_EDITOR: string;
	export const STARSHIP_SHELL: string;
	export const XDG_SESSION_TYPE: string;
	export const npm_node_execpath: string;
	export const SHLVL: string;
	export const XDG_CACHE_HOME: string;
	export const npm_config_noproxy: string;
	export const HOME: string;
	export const OLDPWD: string;
	export const CYAN: string;
	export const DESKTOP_SESSION: string;
	export const TERM_PROGRAM_VERSION: string;
	export const npm_package_json: string;
	export const GIO_LAUNCHED_DESKTOP_FILE: string;
	export const GTK_MODULES: string;
	export const XDG_SEAT_PATH: string;
	export const LC_MONETARY: string;
	export const npm_config_userconfig: string;
	export const npm_config_local_prefix: string;
	export const CINNAMON_VERSION: string;
	export const DBUS_SESSION_BUS_ADDRESS: string;
	export const VISUAL: string;
	export const COLORTERM: string;
	export const GIO_LAUNCHED_DESKTOP_FILE_PID: string;
	export const COLOR: string;
	export const npm_config_metrics_registry: string;
	export const WEZTERM_EXECUTABLE: string;
	export const LOGNAME: string;
	export const _: string;
	export const npm_config_prefix: string;
	export const XDG_SESSION_CLASS: string;
	export const TERM: string;
	export const XDG_SESSION_ID: string;
	export const OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE: string;
	export const npm_config_cache: string;
	export const GNOME_DESKTOP_SESSION_ID: string;
	export const WEZTERM_CONFIG_FILE: string;
	export const DOTFILES_DIR: string;
	export const BOLD: string;
	export const DIM: string;
	export const WEZTERM_EXECUTABLE_DIR: string;
	export const npm_config_node_gyp: string;
	export const PATH: string;
	export const GDM_LANG: string;
	export const GTK3_MODULES: string;
	export const SESSION_MANAGER: string;
	export const NODE: string;
	export const npm_package_name: string;
	export const LC_ADDRESS: string;
	export const XDG_RUNTIME_DIR: string;
	export const XDG_SESSION_PATH: string;
	export const RESET: string;
	export const WHITE: string;
	export const COREPACK_ENABLE_AUTO_PIN: string;
	export const DISPLAY: string;
	export const LANG: string;
	export const LC_TELEPHONE: string;
	export const XDG_CURRENT_DESKTOP: string;
	export const HISTSIZE: string;
	export const NoDefaultCurrentDirectoryInExePath: string;
	export const TERM_PROGRAM: string;
	export const XAUTHORITY: string;
	export const XDG_SESSION_DESKTOP: string;
	export const XDG_CONFIG_HOME: string;
	export const XDG_DATA_HOME: string;
	export const LS_COLORS: string;
	export const npm_lifecycle_script: string;
	export const SSH_AUTH_SOCK: string;
	export const XDG_GREETER_DATA_DIR: string;
	export const BRIGHT_CYAN: string;
	export const STARSHIP_CONFIG: string;
	export const LC_NAME: string;
	export const SHELL: string;
	export const npm_package_version: string;
	export const npm_lifecycle_event: string;
	export const GDMSESSION: string;
	export const QT_ACCESSIBILITY: string;
	export const HELIX_RUNTIME: string;
	export const LC_MEASUREMENT: string;
	export const CLAUDECODE: string;
	export const GJS_DEBUG_OUTPUT: string;
	export const GPG_AGENT_INFO: string;
	export const LC_IDENTIFICATION: string;
	export const WEZTERM_CONFIG_DIR: string;
	export const XDG_VTNR: string;
	export const SAVEHIST: string;
	export const npm_config_globalconfig: string;
	export const npm_config_init_module: string;
	export const PWD: string;
	export const CLICOLOR: string;
	export const npm_config_globalignorefile: string;
	export const npm_execpath: string;
	export const XDG_CONFIG_DIRS: string;
	export const XDG_DATA_DIRS: string;
	export const BRIGHT_WHITE: string;
	export const CLAUDE_CODE_EXECPATH: string;
	export const npm_config_global_prefix: string;
	export const LC_NUMERIC: string;
	export const WEZTERM_UNIX_SOCKET: string;
	export const STARSHIP_SESSION_KEY: string;
	export const npm_command: string;
	export const LC_PAPER: string;
	export const WEZTERM_PANE: string;
	export const HISTFILE: string;
	export const EDITOR: string;
	export const INIT_CWD: string;
	export const NODE_ENV: string;
}

/**
 * Similar to [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private), except that it only includes environment variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`), and can therefore safely be exposed to client-side code.
 * 
 * Values are replaced statically at build time.
 * 
 * ```ts
 * import { PUBLIC_BASE_URL } from '$env/static/public';
 * ```
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to runtime environment variables, as defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`. This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured).
 * 
 * This module cannot be imported into client-side code.
 * 
 * Dynamic environment variables cannot be used during prerendering.
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * console.log(env.DEPLOYMENT_SPECIFIC_VARIABLE);
 * ```
 * 
 * > In `dev`, `$env/dynamic` always includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 */
declare module '$env/dynamic/private' {
	export const env: {
		GJS_DEBUG_TOPICS: string;
		ZSH_CONFIG_DIR: string;
		MAIL: string;
		LANGUAGE: string;
		USER: string;
		CLAUDE_CODE_ENTRYPOINT: string;
		npm_config_user_agent: string;
		XDG_SEAT: string;
		GIT_EDITOR: string;
		STARSHIP_SHELL: string;
		XDG_SESSION_TYPE: string;
		npm_node_execpath: string;
		SHLVL: string;
		XDG_CACHE_HOME: string;
		npm_config_noproxy: string;
		HOME: string;
		OLDPWD: string;
		CYAN: string;
		DESKTOP_SESSION: string;
		TERM_PROGRAM_VERSION: string;
		npm_package_json: string;
		GIO_LAUNCHED_DESKTOP_FILE: string;
		GTK_MODULES: string;
		XDG_SEAT_PATH: string;
		LC_MONETARY: string;
		npm_config_userconfig: string;
		npm_config_local_prefix: string;
		CINNAMON_VERSION: string;
		DBUS_SESSION_BUS_ADDRESS: string;
		VISUAL: string;
		COLORTERM: string;
		GIO_LAUNCHED_DESKTOP_FILE_PID: string;
		COLOR: string;
		npm_config_metrics_registry: string;
		WEZTERM_EXECUTABLE: string;
		LOGNAME: string;
		_: string;
		npm_config_prefix: string;
		XDG_SESSION_CLASS: string;
		TERM: string;
		XDG_SESSION_ID: string;
		OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE: string;
		npm_config_cache: string;
		GNOME_DESKTOP_SESSION_ID: string;
		WEZTERM_CONFIG_FILE: string;
		DOTFILES_DIR: string;
		BOLD: string;
		DIM: string;
		WEZTERM_EXECUTABLE_DIR: string;
		npm_config_node_gyp: string;
		PATH: string;
		GDM_LANG: string;
		GTK3_MODULES: string;
		SESSION_MANAGER: string;
		NODE: string;
		npm_package_name: string;
		LC_ADDRESS: string;
		XDG_RUNTIME_DIR: string;
		XDG_SESSION_PATH: string;
		RESET: string;
		WHITE: string;
		COREPACK_ENABLE_AUTO_PIN: string;
		DISPLAY: string;
		LANG: string;
		LC_TELEPHONE: string;
		XDG_CURRENT_DESKTOP: string;
		HISTSIZE: string;
		NoDefaultCurrentDirectoryInExePath: string;
		TERM_PROGRAM: string;
		XAUTHORITY: string;
		XDG_SESSION_DESKTOP: string;
		XDG_CONFIG_HOME: string;
		XDG_DATA_HOME: string;
		LS_COLORS: string;
		npm_lifecycle_script: string;
		SSH_AUTH_SOCK: string;
		XDG_GREETER_DATA_DIR: string;
		BRIGHT_CYAN: string;
		STARSHIP_CONFIG: string;
		LC_NAME: string;
		SHELL: string;
		npm_package_version: string;
		npm_lifecycle_event: string;
		GDMSESSION: string;
		QT_ACCESSIBILITY: string;
		HELIX_RUNTIME: string;
		LC_MEASUREMENT: string;
		CLAUDECODE: string;
		GJS_DEBUG_OUTPUT: string;
		GPG_AGENT_INFO: string;
		LC_IDENTIFICATION: string;
		WEZTERM_CONFIG_DIR: string;
		XDG_VTNR: string;
		SAVEHIST: string;
		npm_config_globalconfig: string;
		npm_config_init_module: string;
		PWD: string;
		CLICOLOR: string;
		npm_config_globalignorefile: string;
		npm_execpath: string;
		XDG_CONFIG_DIRS: string;
		XDG_DATA_DIRS: string;
		BRIGHT_WHITE: string;
		CLAUDE_CODE_EXECPATH: string;
		npm_config_global_prefix: string;
		LC_NUMERIC: string;
		WEZTERM_UNIX_SOCKET: string;
		STARSHIP_SESSION_KEY: string;
		npm_command: string;
		LC_PAPER: string;
		WEZTERM_PANE: string;
		HISTFILE: string;
		EDITOR: string;
		INIT_CWD: string;
		NODE_ENV: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * Similar to [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private), but only includes variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`), and can therefore safely be exposed to client-side code.
 * 
 * Note that public dynamic environment variables must all be sent from the server to the client, causing larger network requests — when possible, use `$env/static/public` instead.
 * 
 * Dynamic environment variables cannot be used during prerendering.
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.PUBLIC_DEPLOYMENT_SPECIFIC_VARIABLE);
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
