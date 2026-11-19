// Opt in only to public READS; the test starts isolated loopback Anvil for every write.
import { spawnSync } from "node:child_process";
const result = spawnSync("uv", ["run", "--directory", "apps/execution-plane", "--locked",
  "python", "-m", "pytest", "tests/test_lfj_fuji_fork.py", "-q", "-s", ...process.argv.slice(2)], {
  stdio: "inherit", env: { ...process.env, PACEVANT_LFJ_FORK: "1" },
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
