export interface Listener {
  close(): Promise<void>;
}

export type ListenerFactory = (host: string) => Promise<Listener>;

export class ListenerReconciler {
  private readonly listeners = new Map<string, Listener>();
  constructor(private readonly start: ListenerFactory) {}

  async reconcile(tailscaleAddress: string | undefined): Promise<void> {
    const desired = new Set(["127.0.0.1", ...(tailscaleAddress ? [tailscaleAddress] : [])]);
    for (const [host, listener] of this.listeners) {
      if (!desired.has(host)) {
        await listener.close();
        this.listeners.delete(host);
      }
    }
    for (const host of desired) {
      if (!this.listeners.has(host)) this.listeners.set(host, await this.start(host));
    }
  }
}
