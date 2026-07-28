import os from "node:os";
import path from "node:path";

export const DEFAULT_PORT = 9417;
export const DEFAULT_PUBLISH_ROOT = path.join(os.homedir(), ".local", "share", "host-artifact", "public");
export const HEALTH_PATH = "/.well-known/host-artifact/health";
export type Exposure = "local" | "tailscale";
export const ARTIFACT_ID_PATTERN = /^(local|tailscale)(-live)?-[a-f0-9]{32}$/;
