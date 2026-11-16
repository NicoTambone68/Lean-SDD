import { readFileSync } from "node:fs";
import { respond } from "../src/.build/index.js";

const input = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(respond(input)) + "\n");
