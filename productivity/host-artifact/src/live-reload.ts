import { createHash } from "node:crypto";

export const LIVE_RELOAD_MARKER = "data-host-artifact-live-reload";
export const ARTIFACT_VERSION_HEADER = "X-Host-Artifact-Version";
const SCRIPT_START = Buffer.from(`<script ${LIVE_RELOAD_MARKER} data-host-artifact-version="`);
const SCRIPT_END = Buffer.from("</script>");

function liveReloadScript(version: string): string {
  return `<script ${LIVE_RELOAD_MARKER} data-host-artifact-version="${version}">
(() => {
  const scrollKey = \`host-artifact-scroll:\${location.pathname}\`;
  let savedScroll = null;
  try {
    savedScroll = sessionStorage.getItem(scrollKey);
  } catch {
    // Storage is optional; polling remains available without scroll restoration.
  }
  if (savedScroll !== null) {
    addEventListener("load", () => {
      scrollTo(0, Number(savedScroll));
      try {
        sessionStorage.removeItem(scrollKey);
      } catch {
        // Storage is optional.
      }
    }, { once: true });
  }
  let currentVersion = "${version}";
  async function checkForUpdate() {
    try {
      const response = await fetch(location.href, { method: "HEAD", cache: "no-store" });
      if (!response.ok) return;
      const nextVersion = response.headers.get("${ARTIFACT_VERSION_HEADER}");
      if (nextVersion && nextVersion !== currentVersion) {
        try {
          sessionStorage.setItem(scrollKey, String(scrollY));
        } catch {
          // Storage is optional.
        }
        location.reload();
        return;
      }
      currentVersion = nextVersion ?? currentVersion;
    } catch {
      // Temporary listener or network failures are retried by the next interval.
    }
  }
  void checkForUpdate();
  setInterval(checkForUpdate, 1500);
})();
</script>`;
}

function withoutGeneratedScripts(html: Buffer): Buffer {
  const chunks: Buffer[] = [];
  let copyOffset = 0;
  let searchOffset = 0;
  while (true) {
    const start = html.indexOf(SCRIPT_START, searchOffset);
    if (start === -1) break;
    const closing = html.indexOf(SCRIPT_END, start + SCRIPT_START.length);
    if (closing === -1) break;
    const end = closing + SCRIPT_END.length;
    const candidate = html.subarray(start, end);
    const version = candidate
      .subarray(SCRIPT_START.length, SCRIPT_START.length + 64)
      .toString("ascii");
    const expected = Buffer.from(liveReloadScript(version));
    if (!candidate.equals(expected)) {
      searchOffset = start + 1;
      continue;
    }
    chunks.push(html.subarray(copyOffset, start));
    copyOffset = end;
    if (html[copyOffset] === 0x0a) copyOffset++;
    searchOffset = copyOffset;
  }
  chunks.push(html.subarray(copyOffset));
  return Buffer.concat(chunks);
}

export function withLiveReload(html: string): string;
export function withLiveReload(html: Buffer): Buffer;
export function withLiveReload(html: string | Buffer): string | Buffer {
  const input = Buffer.isBuffer(html) ? html : Buffer.from(html);
  const source = withoutGeneratedScripts(input);
  const version = createHash("sha256").update(source).digest("hex");
  const transformed = Buffer.concat([source, Buffer.from(`\n${liveReloadScript(version)}\n`)]);
  return Buffer.isBuffer(html) ? transformed : transformed.toString("utf8");
}
