import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontendRoot, "..");
const workspaceProto = resolve(root, "proto", "v1", "agent_events.proto");
const proto = existsSync(workspaceProto)
  ? workspaceProto
  : "/proto/v1/agent_events.proto";
const out = resolve(frontendRoot, "src", "proto");

mkdirSync(out, { recursive: true });
execFileSync("protoc", [
  `-I${resolve(proto, "..")}`,
  `--js_out=import_style=commonjs,binary:${out}`,
  `--grpc-web_out=import_style=commonjs,mode=grpcwebtext:${out}`,
  proto,
], { stdio: "inherit" });
