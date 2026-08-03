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
import { isLocalClient, lanAddresses, isPrivateOrigin } from "./drillui_net.ts";

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

// ---------------------------------------------------------------------------
// Private-origin rule for CORS on /artifact.
//
// Dragging a tiddlers.json from drillui into a TiddlyWiki served on ANOTHER
// port makes the wiki FETCH the artifact, which is cross-origin. Without a CORS
// header the browser blocks it, so the one-gesture import of a whole tiddler
// array only works for drag flavours that carry the bytes directly.
//
// Echoing ANY Origin would let any website the user visits read their drill
// artifacts from a bridge that binds 0.0.0.0, so the public branch is the one
// that matters here — same reasoning as the REMOTE branch above.
// ---------------------------------------------------------------------------
const owns = new Set(["192.168.178.67"]);

ok("localhost origin is private", isPrivateOrigin("http://localhost:8080", owns));
ok("loopback origin is private", isPrivateOrigin("http://127.0.0.1:8080", owns));
ok("bare LAN hostname is private", isPrivateOrigin("http://beelink:8080", owns));
ok(".local hostname is private", isPrivateOrigin("http://beelink.local:8080", owns));
ok("our own ip is private", isPrivateOrigin("http://192.168.178.67:8080", owns));
ok("RFC1918 10/8 is private", isPrivateOrigin("http://10.0.0.4:8080", owns));
ok("RFC1918 172.16/12 is private", isPrivateOrigin("http://172.16.3.9:8080", owns));

ok("public FQDN is REFUSED", !isPrivateOrigin("https://evil.example.com", owns));
ok("tiddlywiki.com is REFUSED", !isPrivateOrigin("https://tiddlywiki.com", owns));
ok("public ip is REFUSED", !isPrivateOrigin("http://8.8.8.8", owns));
ok("172.32 (outside 172.16/12) is REFUSED", !isPrivateOrigin("http://172.32.0.1", owns));
ok("empty origin is REFUSED", !isPrivateOrigin("", owns));
ok("garbage origin is REFUSED", !isPrivateOrigin("not a url", owns));

console.log(fails ? `\n${fails} FAILURE(S)` : "\nAll drillui_net checks passed.");
process.exit(fails ? 1 : 0);
