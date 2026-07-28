import assert from "node:assert/strict";
import test from "node:test";
import { ListenerReconciler, type Listener } from "../src/listeners.js";

test("reconciliation always keeps loopback and adds the detected Tailscale address", async () => {
  // Arrange
  const started: string[] = [];
  const factory = async (host: string): Promise<Listener> => {
    started.push(host);
    return { close: async () => undefined };
  };
  const reconciler = new ListenerReconciler(factory);

  // Act
  await reconciler.reconcile("100.64.0.9");

  // Assert
  assert.deepEqual(started, ["127.0.0.1", "100.64.0.9"]);
});

test("address change closes the old Tailscale listener and starts the new one", async () => {
  // Arrange
  const closed: string[] = [];
  const factory = async (host: string): Promise<Listener> => ({
    close: async () => { closed.push(host); },
  });
  const reconciler = new ListenerReconciler(factory);
  await reconciler.reconcile("100.64.0.9");

  // Act
  await reconciler.reconcile("100.64.0.10");

  // Assert
  assert.deepEqual(closed, ["100.64.0.9"]);
});

test("Tailscale disappearance closes only its listener", async () => {
  // Arrange
  const closed: string[] = [];
  const factory = async (host: string): Promise<Listener> => ({
    close: async () => { closed.push(host); },
  });
  const reconciler = new ListenerReconciler(factory);
  await reconciler.reconcile("100.64.0.9");

  // Act
  await reconciler.reconcile(undefined);

  // Assert
  assert.deepEqual(closed, ["100.64.0.9"]);
});
