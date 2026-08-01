import { createHash } from "node:crypto";
import { REVISION_HEADER } from "./config.js";
export const LIVE_RELOAD_MARKER = "data-host-artifact-live-reload";
export const ARTIFACT_VERSION_HEADER = REVISION_HEADER;

function script(version: string): string {
  return `<script ${LIVE_RELOAD_MARKER} data-host-artifact-version="${version}">
(() => {
  const scrollKey = \`host-artifact-scroll:\${location.pathname}\`;
  try { const value = sessionStorage.getItem(scrollKey); if (value !== null) addEventListener("load", () => { scrollTo(0, Number(value)); sessionStorage.removeItem(scrollKey); }, { once: true }); } catch {}
  const currentVersion = "${version}";
  async function checkForUpdate() {
    try {
      const response = await fetch(location.href, { method: "HEAD", cache: "no-store" });
      const nextVersion = response.headers.get("${REVISION_HEADER}");
      if (response.ok && nextVersion && nextVersion !== currentVersion) { try { sessionStorage.setItem(scrollKey, String(scrollY)); } catch {} location.reload(); }
    } catch {}
  }
  setInterval(checkForUpdate, 1500);
})();
</script>`;
}

function stripGenerated(input: string): string {
  return input.replace(/\n?<script data-host-artifact-live-reload data-host-artifact-version="(?:r-[a-f0-9]{32}|[a-f0-9]{64})">\n\(\(\) => \{\n  const scrollKey[\s\S]*?<\/script>\n?/g, "");
}

export function withLiveReload(html: string, revision?: string): string;
export function withLiveReload(html: Buffer, revision?: string): Buffer;
export function withLiveReload(html: string | Buffer, revision?: string): string | Buffer {
  const isBuffer = Buffer.isBuffer(html); const raw = isBuffer ? html.toString("latin1") : html;
  const source = stripGenerated(raw);
  const version = revision ?? createHash("sha256").update(isBuffer ? Buffer.from(source, "latin1") : source).digest("hex");
  const transformed = `${source}\n${script(version)}\n`;
  return isBuffer ? Buffer.from(transformed, "latin1") : transformed;
}
