import os from "node:os";
import path from "node:path";

export const DEFAULT_PORT = 9417;
export const DEFAULT_PUBLISH_ROOT = path.join(os.homedir(), ".local", "share", "host-artifact", "public");
export const HEALTH_PATH = "/.well-known/host-artifact/health";
export const PROTOCOL_VERSION = 2;
export const ARTIFACT_NAME_PATTERN = /^(?!.*--)[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
export const WORKSPACE_PATTERN = /^[a-z0-9][a-z0-9-]{0,47}~[a-f0-9]{12}$/;
export const REVISION_PATTERN = /^r-[a-f0-9]{32}$/;
export const REVISION_HEADER = "X-Host-Artifact-Revision";

export function artifactRoute(workspace: string, name: string): string {
  return `/a/${workspace}/${name}/`;
}
