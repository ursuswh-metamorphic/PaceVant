// Run the pinned Foundry binary on the current OS/CPU, falling back to PATH.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
const [tool, ...args] = process.argv.slice(2);
if (!["forge", "anvil"].includes(tool)) throw new Error("Expected forge or anvil");
const os = process.platform === "win32" ? "win32" : process.platform === "darwin" ? "darwin" : "linux";
const arch = process.arch === "arm64" ? "arm64" : "amd64";
const binary = resolve(`node_modules/@foundry-rs/${tool}-${os}-${arch}/bin/${tool}${os === "win32" ? ".exe" : ""}`);
const result = spawnSync(existsSync(binary) ? binary : tool, args, { stdio: "inherit" });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
