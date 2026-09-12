# Vestaboard Skill

An agent skill that lets Claude Code, Codex, or any skill-aware AI agent put
messages on your [Vestaboard](https://www.vestaboard.com) split-flap display
and read what it currently shows. It talks to the board directly over the
**Local API** on your home network, so nothing goes through the cloud.

Ask your agent things like:

- "Put DINNER AT 6 on the board"
- "Show this week's schedule on the Vestaboard"
- "What's on the board right now?"
- "Clear the board"

The skill knows the board is 6 rows by 22 columns, how to word-wrap and center
text, how to use the colored tiles, and how to pack a list or schedule into a
readable grid.

## Supported boards

This skill was built and tested against the original **Vestaboard** (the
Flagship, 6 rows x 22 columns). It has not been tested with the **Vestaboard
Note** or **Note Array**. Adapting it should be straightforward if those boards
speak the same Local API: the grid size lives in one place in
`scripts/vestaboard.py` (`ROWS, COLS`), and the rest of the client is
geometry-agnostic. If you get it working on a Note, a pull request is welcome.

## What you need

- A Vestaboard (Flagship, 6 x 22) that is paired and online.
- The **Local API** enabled on your board. Request it at
  <https://www.vestaboard.com/local-api>. Vestaboard emails the board owner an
  *enablement token*.
- A computer on the **same Wi-Fi / LAN** as the board. The Local API is not
  reachable from the internet or from a cloud VM.
- Python 3.9 or newer. No extra packages are required.

## Install the skill

Copy the `vestaboard/` folder to wherever your agent looks for skills:

| Agent | Location |
| --- | --- |
| Claude Code (personal, all projects) | `~/.claude/skills/vestaboard/` |
| Claude Code (one project) | `<project>/.claude/skills/vestaboard/` |
| Codex CLI | `~/.codex/skills/vestaboard/` |

For example, for Claude Code:

```bash
git clone https://github.com/erictfree/vestaboard-skill.git
cp -R vestaboard-skill/vestaboard ~/.claude/skills/vestaboard
```

Restart the agent (or start a new session) so it picks up the new skill.

## One-time board setup

The API key is **not** stored inside the skill folder. It goes in
`~/.config/vestaboard/config.json`, which the script creates for you with
owner-only permissions.

1. Request the Local API at <https://www.vestaboard.com/local-api> and wait for
   the enablement token email.

2. From a computer on the same network as the board, exchange the token for a
   permanent API key. This also saves the key to the config file:

   ```bash
   python3 ~/.claude/skills/vestaboard/scripts/vestaboard.py enable PASTE_TOKEN_HERE
   ```

   The script finds the board at `vestaboard.local`. If your network does not
   resolve that name, give it the board's IP address instead:

   ```bash
   VESTABOARD_HOST=192.168.1.50 python3 ~/.claude/skills/vestaboard/scripts/vestaboard.py enable PASTE_TOKEN_HERE
   ```

3. Check it works:

   ```bash
   python3 ~/.claude/skills/vestaboard/scripts/vestaboard.py test
   python3 ~/.claude/skills/vestaboard/scripts/vestaboard.py say "HELLO"
   ```

That's it. Now ask your agent to put something on the board.

Run the enablement step yourself in a terminal rather than pasting the token
into a chat with the agent. The token and the key are secrets.

### Already have a Local API key?

If you enabled the Local API some other way and already have a key, create the
config file by hand. Copy `vestaboard/scripts/config.example.json` to
`~/.config/vestaboard/config.json`, fill in the key, and lock it down:

```bash
mkdir -p ~/.config/vestaboard && chmod 700 ~/.config/vestaboard
cp vestaboard/scripts/config.example.json ~/.config/vestaboard/config.json
chmod 600 ~/.config/vestaboard/config.json
```

The `host` field can be `vestaboard.local` or the board's IP address.

## Command reference

All commands are subcommands of `scripts/vestaboard.py`:

| Command | What it does |
| --- | --- |
| `enable <TOKEN>` | One-time: exchange an enablement token for an API key and save it |
| `config` | Show where the config lives and whether a key is set (never prints the key) |
| `test` / `read` | Read and print the board's current contents |
| `say "TEXT"` | Show text, word-wrapped and centered. `--left` / `--right` to align |
| `rows "R1" "R2" ...` | One argument per row, top-anchored, no wrapping |
| `grid <JSON or file or ->` | Write a raw 6 x 22 grid of tile codes (see `references/layouts.md`) |
| `clear` | Blank the board |
| `discover` | Scan the local network for the board and save its IP |

Color tiles go inline in text as `{red}`, `{orange}`, `{yellow}`, `{green}`,
`{blue}`, `{violet}`, `{white}`, `{black}`. Letters are always white on black;
a color token is its own solid tile.

## Configuration

`config.json` has two fields:

```json
{
  "host": "vestaboard.local",
  "key": "YOUR_LOCAL_API_KEY"
}
```

Environment variables override the file when set:

| Variable | Purpose |
| --- | --- |
| `VESTABOARD_CONFIG_DIR` | Use a different directory for `config.json` |
| `VESTABOARD_LOCAL_API_KEY` | Supply the key without a config file |
| `VESTABOARD_HOST` | Board hostname or IP (default `vestaboard.local`) |
| `VESTABOARD_PORT` | Local API port (default `7000`) |

**More than one board?** Give each its own config directory and pick one with
`VESTABOARD_CONFIG_DIR` when you run the script.

## Troubleshooting

- **"Could not reach the board."** Make sure the computer is on the same
  network as the Vestaboard, then run `discover`. The script scans your local
  subnet and saves the board's IP. If the agent runs commands in a sandbox
  that blocks local-network access, approve local network access for the
  command when it asks.
- **"HTTP 401" or "HTTP 403".** The key was rejected. If the board was
  replaced or factory-reset, it needs a fresh enablement token. Request one
  at <https://www.vestaboard.com/local-api> and run `enable` again.
- **"No API key."** Run the one-time setup above, or set
  `VESTABOARD_LOCAL_API_KEY`.
- **The board didn't change.** The board applies roughly one update every
  15 seconds and may accept a request before the flaps move. Wait, then `read`.
- **Something on port 7000 answers but isn't the board.** macOS AirPlay also
  uses port 7000. The script ignores it during discovery.

## Files

```
vestaboard/
  SKILL.md                     instructions the agent reads
  scripts/vestaboard.py        Local API client and CLI (stdlib only)
  scripts/config.example.json  template for ~/.config/vestaboard/config.json
  references/layouts.md        tile codes and raw-grid layouts
  agents/openai.yaml           Codex skill metadata
```

## Privacy and safety

- The skill never includes keys. `config.json` lives outside the skill folder
  and is created with `600` permissions.
- The agent is instructed never to print the key or token, and never to write
  to the board unless you explicitly ask it to.
- All traffic stays on your LAN.

## License

MIT. Created by Eric Freeman. See [LICENSE](LICENSE).
