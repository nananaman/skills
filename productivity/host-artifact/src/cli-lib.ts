export interface ReadinessDependencies {
  isHealthy(): Promise<boolean>;
  ensureService(): Promise<void>;
}

export async function ensureReady(dependencies: ReadinessDependencies): Promise<void> {
  if (await dependencies.isHealthy()) return;
  await dependencies.ensureService();
  if (!(await dependencies.isHealthy())) throw new Error("host-artifact service is unavailable after ensure");
}

export function isExpectedHealth(status: number, body: unknown): boolean {
  if (status !== 200 || typeof body !== "object" || body === null) return false;
  const value = body as Record<string, unknown>;
  return value.service === "host-artifact" && value.version === 1 && value.status === "ok";
}

export function hasReadyTailscaleListener(status: number, body: unknown): boolean {
  return isExpectedHealth(status, body)
    && (body as Record<string, unknown>).tailscaleReady === true;
}

export function buildArtifactUrl(base: string, id: string, relativePath: string): string {
  const encoded = relativePath.split("/").map(encodeURIComponent).join("/");
  return `${base}/${id}/${encoded}`;
}

export interface ArtifactWaitDependencies {
  fetchStatus(url: string): Promise<number>;
  wait(milliseconds: number): Promise<void>;
  attempts?: number;
  intervalMs?: number;
}

export async function waitForArtifact(url: string, dependencies: ArtifactWaitDependencies): Promise<boolean> {
  const attempts = dependencies.attempts ?? 10;
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const status = await dependencies.fetchStatus(url);
      if (status >= 200 && status < 300) return true;
    } catch {
      // Listener startup and interface transitions are expected to be temporarily unreachable.
    }
    if (attempt + 1 < attempts) await dependencies.wait(dependencies.intervalMs ?? 100);
  }
  return false;
}

export interface PublishedArtifact {
  id: string;
  relativePath: string;
}

export async function publishVerified<T>(operations: {
  publish(): Promise<PublishedArtifact>;
  verify(artifact: PublishedArtifact): Promise<T>;
  remove(id: string): Promise<void>;
}): Promise<{ artifact: PublishedArtifact; verification: T }> {
  const artifact = await operations.publish();
  try {
    return { artifact, verification: await operations.verify(artifact) };
  } catch (primaryError) {
    try {
      await operations.remove(artifact.id);
    } catch (cleanupError) {
      const primary = primaryError instanceof Error ? primaryError.message : String(primaryError);
      const cleanup = cleanupError instanceof Error ? cleanupError.message : String(cleanupError);
      throw new Error(`${primary}; cleanup of ${artifact.id} also failed: ${cleanup}`, { cause: primaryError });
    }
    throw primaryError;
  }
}
