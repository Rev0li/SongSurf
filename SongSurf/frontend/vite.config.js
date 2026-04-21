import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		port: 5173,
		proxy: {
			// In dev, proxy API and static assets to SongSurf running directly (DEV_MODE=true)
			'/api': { target: 'http://localhost:8081', changeOrigin: true },
			'/watcher': { target: 'http://localhost:8080', changeOrigin: true },
			'/static': { target: 'http://localhost:8081', changeOrigin: true },
		},
	},
});
