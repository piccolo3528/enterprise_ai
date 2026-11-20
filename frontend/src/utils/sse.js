/**
 * An incremental Server-Sent Events parser for the stream our backend sends (M13).
 *
 * Network chunks can end anywhere, even mid-line, so text is buffered until a line is complete.
 * An event is a group of lines ended by a blank line: `event: <name>` names it, `data: ...` lines
 * are joined with "\n", and lines starting with ":" are comments (keep-alives). Lines may end with
 * "\n" or "\r\n". Calls `onEvent(name, data)` for each complete event.
 */
export function createSseParser(onEvent) {
  let buffer = "";
  let name = "message";
  let data = [];

  function handleLine(line) {
    if (line === "") {
      if (data.length > 0) onEvent(name, data.join("\n"));
      name = "message";
      data = [];
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }

  return {
    push(text) {
      buffer += text;
      let end;
      while ((end = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, end).replace(/\r$/, "");
        buffer = buffer.slice(end + 1);
        handleLine(line);
      }
    },
  };
}
