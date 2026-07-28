import os from "node:os";
import { isIPv4 } from "node:net";

type InterfaceAddress = { address: string; family: string | number; internal: boolean };
type Interfaces = Record<string, readonly InterfaceAddress[] | undefined>;
export type InterfaceProvider = () => Interfaces;

function isCgnat(address: string): boolean {
  if (!isIPv4(address)) return false;
  const [first, second] = address.split(".").map(Number);
  return first === 100 && second !== undefined && second >= 64 && second <= 127;
}

export function detectTailscaleIPv4(
  getInterfaces: InterfaceProvider = () => os.networkInterfaces() as Interfaces,
): string | undefined {
  for (const [name, addresses] of Object.entries(getInterfaces())) {
    if (!/^(tailscale|utun)/i.test(name)) continue;
    for (const address of addresses ?? []) {
      if (address.family === "IPv4" && !address.internal && isCgnat(address.address)) return address.address;
    }
  }
  return undefined;
}
