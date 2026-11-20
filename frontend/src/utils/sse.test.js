import { describe, expect, it } from "vitest";

import { createSseParser } from "./sse";

function parseAll(chunks) {
  const events = [];
  const parser = createSseParser((name, data) => events.push([name, data]));
  for (const chunk of chunks) parser.push(chunk);
  return events;
}

describe("Server-Sent Events parser", () => {
  it("reads named events with JSON data", () => {
    expect(parseAll(['event: token\ndata: {"text":"Hi"}\n\nevent: done\ndata: {}\n\n'])).toEqual([
      ["token", '{"text":"Hi"}'],
      ["done", "{}"],
    ]);
  });

  it("copes with events split anywhere across network chunks", () => {
    const stream = 'event: token\ndata: {"text":"a"}\n\nevent: token\r\ndata: {"text":"b"}\r\n\r\n';
    const whole = parseAll([stream]);
    for (let i = 0; i <= stream.length; i += 1) {
      expect(parseAll([stream.slice(0, i), stream.slice(i)])).toEqual(whole);
    }
    expect(whole).toEqual([
      ["token", '{"text":"a"}'],
      ["token", '{"text":"b"}'],
    ]);
  });

  it("joins multi-line data, ignores comments and waits for the blank line", () => {
    expect(parseAll([": keep-alive\n\ndata: one\ndata: two\n\n", "event: x\ndata: unfinished\n"])).toEqual([
      ["message", "one\ntwo"],
    ]);
  });
});
