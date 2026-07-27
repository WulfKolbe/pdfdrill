/**
 * drillui_net.ts — where is the client, relative to the bridge?
 *
 * The single fact everything file-related depends on. Two worlds:
 *
 *   LOCAL   the browser runs on the SAME machine as the bridge (localhost, or
 *           `beelink:8787` typed on beelink itself). The server's screen IS the
 *           user's screen and the server's filesystem IS the user's filesystem,
 *           so host-open (xdg-open) and the host editor (gummi) are meaningful.
 *
 *   REMOTE  the browser runs on another device (laptop/phone via beelink:8787).
 *           Spawning a browser or an editor on the bridge opens a window on the
 *           SERVER, which the user never sees — the "I clicked and nothing
 *           happened" case. Only HTTP artifact URLs work; a local path or a
 *           `file://` URL is meaningless (it addresses the CLIENT's own disk).
 *
 * Kept in its own module (no side effects, no server) so it is directly unit
 * testable — the remote branch is the one that matters and it cannot be
 * exercised by connecting from this machine, where every source address is ours.
 */
import { networkInterfaces } from "node:os";

/** This machine's non-loopback IPv4 addresses — what to type on another device
 *  when the bridge binds 0.0.0.0 (`localhost` there would be that device). */
export function lanAddresses(): string[] {
  const out: string[] = [];
  for (const addrs of Object.values(networkInterfaces())) {
    for (const a of addrs ?? []) {
      if (a.family === "IPv4" && !a.internal) out.push(a.address);
    }
  }
  return out;
}

/**
 * True when `ip` belongs to THIS machine: loopback, or one of our own interface
 * addresses — a browser on beelink reaching `beelink:8787` shows up with the LAN
 * ip as its source, not 127.0.0.1, so own-address membership is required.
 *
 * An unknown/absent address is treated as REMOTE: the safe default, since the
 * consequence of guessing "local" is spawning invisible windows on the server.
 */
export function isLocalClient(
  ip: string | null | undefined,
  own: Set<string> | Iterable<string> = lanAddresses(),
): boolean {
  if (!ip) return false;
  const a = String(ip).trim().replace(/^::ffff:/i, "");   // unwrap IPv4-mapped IPv6
  if (a === "::1" || a === "0.0.0.0" || a === "localhost") return true;
  if (/^127\./.test(a)) return true;                      // whole 127/8 loopback block
  const set = own instanceof Set ? own : new Set(own);
  return set.has(a);
}
