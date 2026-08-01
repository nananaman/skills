import { createArtifactApp } from "./app.js";
import { DEFAULT_PORT, DEFAULT_PUBLISH_ROOT } from "./config.js";
function argument(name: string, fallback: string): string { const index = process.argv.indexOf(name); return index >= 0 && process.argv[index + 1] ? process.argv[index + 1]! : fallback; }
const port = Number(argument("--port", String(DEFAULT_PORT)));
const root = argument("--publish-root", DEFAULT_PUBLISH_ROOT);
Bun.serve({ fetch: createArtifactApp({ root }).fetch, hostname: "127.0.0.1", port });
