---
name: vestaboard
description: Display messages, status, row layouts, and color-tile art on a physical Vestaboard split-flap display over its Local API on the home LAN, and read what it currently shows. Use when the user asks to put, show, push, post, announce, read, inspect, clear, format, or troubleshoot content on "the board," "the Vestaboard," or "the split-flap."
---

# Vestaboard

Control the Vestaboard with the bundled client. Resolve `<skill-root>` as the
directory containing this `SKILL.md`:

```text
<skill-root>/scripts/vestaboard.py
```

Run it with `python3`. It needs only the Python standard library. The script
reads its API key from a config file outside the skill folder
(`~/.config/vestaboard/config.json` by default, or `VESTABOARD_CONFIG_DIR`).
Never print, quote, summarize, or otherwise expose the API key, the config
file's contents, or an enablement token.

Check the setup state without exposing secrets:

```bash
python3 "<skill-root>/scripts/vestaboard.py" config
```

If no key is set, tell the user to follow the setup steps in the README
(request a Local API enablement token from Vestaboard, then run `enable`).

## Interpret the request

Treat `read`, `test`, `config`, and `discover` as read-only. Treat `say`,
`rows`, `grid`, `clear`, and `enable` as changes to a physical device.

- Execute a write once when the user explicitly asks to put, show, push, post,
  announce, clear, or change something on the board.
- Do not ask for confirmation after an explicit write request.
- Do not write when the user only asks what is displayed, asks for a draft, or
  discusses a possible message.
- Keep the user's wording unless fitting the 6 by 22 display requires a small
  adjustment. Explain any material truncation or rewrite.
- Do not issue duplicate writes. The board may accept a request before its
  flaps visibly update.

## Use the CLI

Use `say` for ordinary messages. It uppercases, word-wraps, horizontally aligns,
and vertically centers text:

```bash
python3 "<skill-root>/scripts/vestaboard.py" say "STANDUP IN 5"
python3 "<skill-root>/scripts/vestaboard.py" say "DINNER IS READY" --left
```

Use `rows` for intentional row-by-row layouts. Each argument maps to one
physical row and the layout is top-anchored:

```bash
python3 "<skill-root>/scripts/vestaboard.py" rows "BUILD" "PASSED" "MAIN" --center
```

Read the current display:

```bash
python3 "<skill-root>/scripts/vestaboard.py" read
```

Clear the board:

```bash
python3 "<skill-root>/scripts/vestaboard.py" clear
```

Force discovery only when normal reachability checks fail:

```bash
python3 "<skill-root>/scripts/vestaboard.py" discover
```

## Format content

- The display has 6 rows and 22 columns.
- Prefer messages that fit in roughly six short lines.
- Use `--center` by default for `say`; use `--left` by default for `rows`.
- Use `\n` inside one `say` argument for deliberate line breaks.
- Use `{red}`, `{orange}`, `{yellow}`, `{green}`, `{blue}`, `{violet}`,
  `{white}`, or `{black}` for solid color tiles.
- Remember that letters are always white. Color tokens create separate solid
  tiles; they do not color nearby letters.
- Use `{green}{green} BUILD PASSED {green}{green}` for a simple status treatment.

For raw character codes or custom per-cell art, read
[references/layouts.md](references/layouts.md) before constructing the grid.

## Pack dense information

When the user provides a list, schedule, set of readings, or other structured
information, design an information grid instead of defaulting to one centered
item per row.

- Use `rows` with left alignment and use all six rows when there is enough data.
- Count every character, blank, and `{color}` token as one of the 22 cells.
- Fit one substantial item per row, or pair two short items on one row when both
  remain recognizable. A useful paired-row shape is
  `MON 9A MTG{blue}TUE 6P GYM`.
- Use one color tile as a compact divider. Use blue or white for a neutral
  divider. Use green, yellow, or red as a status marker only when the user or
  source actually supplies that status.
- Prefer conventional abbreviations: MON-SUN, JAN-DEC, `9A`, `5:30P`, standard
  units, `&`, `+`, and `/`. Remove low-information words such as THE, AT, ON,
  and TO when the meaning remains obvious.
- Preserve names, dates, times, quantities, order, and distinguishing words.
  Never invent a status or use an abbreviation that makes an item ambiguous.
- A heading is optional; spend that row on data when the context is already
  clear.
- Never silently omit source items. If not everything fits, reserve the last row
  for `+N MORE`, using the exact number of omitted items.
- Optimize for information per cell while keeping the display readable from
  across a room. Dense formatting should still use deliberate spaces and clear
  visual grouping.

## Handle connectivity and timing

The Local API is reachable only from the same LAN as the board. The script
tries the configured host (or `vestaboard.local`). If no host was configured
and that fails, it scans the local subnet and saves the board it finds. If a
host *was* configured and does not answer, the script never switches to a
different board on its own, because writing to the wrong physical display is
not recoverable; it reports the other boards it saw and tells the user to set
`VESTABOARD_HOST` or run `discover` deliberately. Relay that message; do not
run `discover` yourself to work around it unless the user asks.

If a command fails because the agent sandbox blocks local-network access, rerun
the same command with the normal approval for local-network access. Do not
replace the client with raw `curl`, and do not reveal the API key in an
approval request or command. If an approved command still cannot find the
board, report that the machine may not be on the home LAN or the board may be
offline.

The board generally applies one update about every 15 seconds. Do not
immediately read after a successful write and treat the old display as failure.
Only verify when the user asks; wait about 15 seconds, then read once.

## Report the result

After a successful write, summarize the displayed content. After a read,
preserve its row structure in the response. For failures, give the actionable
cause without including keys, tokens, or raw credential-bearing output.

Run `enable <TOKEN>` only when the user explicitly asks to enable the board and
provides the token. Treat the token as a secret and avoid repeating it in the
response.
