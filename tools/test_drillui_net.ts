#!/usr/bin/env bun
/**
 * Unit test for the client-locality classifier (tools/drillui_net.ts).
 *
 * The REMOTE branch is the one that matters — a remote browser must NOT be told
 * host-open/edit are available, because those act on the SERVER's screen. It
 * cannot be exercised by connecting from this machine (every source address here
 * is our own), so it is tested directly against the pure function.
 *
 *   bun tools/test_drillui_net.ts
 */
import { isLocalClient, lanAddresses } from "./drillui_net.ts";

let fails = 0;
const ok = (name: string, cond: boolean, extra = "") => {
  console.log(`  [${cond ? "ok" : "FAIL"}] ${name}${extra ? "  — " + extra : ""}`);
  if (!cond) fails++;
};

const own = new Set(["192.168.178.67"]);          // pretend THIS box is .67

// --- LOCAL: the browser is on the same machine as the bridge -----------------
ok("127.0.0.1 is local",            isLocalClient("127.0.0.1", own));
ok("127.0.1.1 is local (the /etc/hosts hostname address)",
                                    isLocalClient("127.0.1.1", own));
ok("whole 127/8 is local",          isLocalClient("127.99.4.2", own));
ok("::1 is local",                  isLocalClient("::1", own));
ok("IPv4-mapped ::ffff:127.0.0.1 is local",
                                    isLocalClient("::ffff:127.0.0.1", own));
ok("our OWN lan ip is local (beelink:8787 typed ON beelink)",
                                    isLocalClient("192.168.178.67", own));
ok("IPv4-mapped own lan ip is local",
                                    isLocalClient("::ffff:192.168.178.67", own));

// --- REMOTE: another device on the LAN — the case that was silently broken ---
ok("another LAN host is REMOTE",   !isLocalClient("192.168.178.42", own),
   "a laptop/phone: host-open would open a window on the server");
ok("a different subnet is REMOTE", !isLocalClient("10.0.0.5", own));
ok("a public address is REMOTE",   !isLocalClient("93.184.216.34", own));

// --- unknown -> REMOTE (safe default: never spawn invisible server windows) --
ok("null is REMOTE",               !isLocalClient(null, own));
ok("undefined is REMOTE",          !isLocalClient(undefined, own));
ok("empty string is REMOTE",       !isLocalClient("", own));

// --- default `own` reads the real interfaces --------------------------------
const real = lanAddresses();
ok("lanAddresses() returns non-loopback IPv4s", Array.isArray(real)
   && real.every((a) => /^\d+\.\d+\.\d+\.\d+$/.test(a) && !a.startsWith("127.")),
   real.join(", ") || "(none)");
if (real.length) {
  ok("this machine's own ip classifies local with the default set",
     isLocalClient(real[0]), real[0]);
}

console.log(fails ? `\n${fails} FAILURE(S)` : "\nAll drillui_net checks passed.");
process.exit(fails ? 1 : 0);
