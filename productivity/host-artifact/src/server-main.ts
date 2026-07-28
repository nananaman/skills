import { createArtifactApp } from "./app.js";
import { DEFAULT_PORT, DEFAULT_PUBLISH_ROOT } from "./config.js";
import { ListenerReconciler } from "./listeners.js";
import { detectTailscaleIPv4 } from "./tailscale.js";

function argument(name: string, fallback: string): string {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1]! : fallback;
}

const port = Number(argument("--port", String(DEFAULT_PORT)));
const root = argument("--publish-root", DEFAULT_PUBLISH_ROOT);
let tailscaleReady = false;
const localApp = createArtifactApp({
  root,
  exposure: "local",
  tailscaleReady: () => tailscaleReady,
});
const tailscaleApp = createArtifactApp({ root, exposure: "tailscale" });
const reconciler = new ListenerReconciler(async (hostname) => {
  const app = hostname === "127.0.0.1" ? localApp : tailscaleApp;
  const server = Bun.serve({ fetch: app.fetch, hostname, port });
  if (hostname !== "127.0.0.1") tailscaleReady = true;
  return {
    close: async () => {
      await server.stop(true);
      if (hostname !== "127.0.0.1") tailscaleReady = false;
    },
  };
});

await reconciler.reconcile(undefined);

async function reconcileRemote(): Promise<void> {
  try {
    await reconciler.reconcile(detectTailscaleIPv4());
  } catch (error) {
    console.error("host-artifact Tailscale listener reconciliation failed", error);
  } finally {
    setTimeout(reconcileRemote, 15_000).unref();
  }
}

void reconcileRemote();
