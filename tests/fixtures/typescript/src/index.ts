export interface Request {
  version: 1;
  value: number;
}

export interface Response {
  version: 1;
  result: number;
}

export function respond(input: unknown): Response {
  if (
    typeof input !== "object" ||
    input === null ||
    !("version" in input) ||
    input.version !== 1 ||
    !("value" in input) ||
    typeof input.value !== "number" ||
    !Number.isSafeInteger(input.value) ||
    !Number.isSafeInteger(input.value + 1)
  ) {
    throw new Error("Invalid versioned request");
  }
  return { version: 1, result: input.value + 1 };
}
