import { REVISION_HEADER, PROTOCOL_VERSION } from "./config.js";

export interface ReadinessDependencies { isHealthy(): Promise<boolean>; ensureService(): Promise<void> }
export async function ensureReady(dependencies: ReadinessDependencies): Promise<void> {
  if (await dependencies.isHealthy()) return;
  await dependencies.ensureService();
  if (!(await dependencies.isHealthy())) throw new Error("host-artifact protocol v2 service is unavailable after ensure");
}
export function isExpectedHealth(status: number, body: unknown): boolean {
  if (status !== 200 || typeof body !== "object" || body === null) return false;
  const value = body as Record<string, unknown>;
  return value.service === "host-artifact" && value.version === PROTOCOL_VERSION && value.status === "ok";
}
export interface WorkspaceResult { segment: string; displayName: string }
export function parseWorkspaceResult(value: unknown): WorkspaceResult {
  if (typeof value !== "object" || value === null) throw new Error("malformed workspace helper response");
  const root = value as Record<string, unknown>; const workspace = root.workspace as Record<string, unknown> | undefined;
  if (root.schemaVersion !== 1 || root.status !== "ok" || !workspace || typeof workspace.segment !== "string" || typeof workspace.displayName !== "string") throw new Error("malformed workspace helper response");
  return workspace as unknown as WorkspaceResult;
}
export interface TransportResult { transport: "localhost" | "tailscale-serve"; url: string; reason?: string }
export function selectTransport(localUrl: string, inspect: unknown, verify?: unknown): TransportResult {
  if (typeof inspect !== "object" || inspect === null) return { transport: "localhost", url: localUrl, reason: "Tailscale inspection unavailable" };
  const state = inspect as Record<string, unknown>;
  if (state.schemaVersion !== 1 || state.available !== true || state.configured !== true || typeof state.origin !== "string") return { transport: "localhost", url: localUrl, ...(typeof state.reason === "string" ? { reason: state.reason } : {}) };
  if (typeof verify === "object" && verify !== null) {
    const result = verify as Record<string, unknown>;
    if (result.schemaVersion === 1 && result.verified === true && typeof result.url === "string") {
      try {
        const local = new URL(localUrl); const configured = new URL(state.origin); const verified = new URL(result.url);
        const exactPath = /^\/a\/[a-z0-9][a-z0-9-]{0,47}~[a-f0-9]{12}\/(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\/$/;
        if (configured.protocol === "https:" && configured.pathname === "/" && !configured.search && !configured.hash && !configured.username && !configured.password
          && verified.protocol === "https:" && verified.origin === configured.origin && verified.pathname === local.pathname && exactPath.test(verified.pathname)
          && !verified.search && !verified.hash && !verified.username && !verified.password) return { transport: "tailscale-serve", url: verified.href };
      } catch { /* Invalid helper URLs degrade to the already verified local route. */ }
      return { transport: "localhost", url: localUrl, reason: "remote helper returned a mismatched URL" };
    }
    return { transport: "localhost", url: localUrl, ...(typeof result.reason === "string" ? { reason: result.reason } : {}) };
  }
  return { transport: "localhost", url: localUrl, reason: "remote artifact was not verified" };
}
export async function waitForRevision(url: string, revision: string, fetcher: (input: string | URL | Request, init?: RequestInit) => Promise<Response> = fetch): Promise<boolean> {
  for (let attempt = 0; attempt < 10; attempt++) {
    try { const response = await fetcher(url, { signal: AbortSignal.timeout(1_000) }); if (response.ok && response.headers.get(REVISION_HEADER) === revision) return true; } catch {}
    if (attempt < 9) await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return false;
}
