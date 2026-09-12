"""
Vestaboard Local API client (single board, Python standard library only).

Talks directly to a Vestaboard on your LAN, no cloud round-trip:
    http://vestaboard.local:7000/local-api/message

One-time setup:
  1. Request a Local API *enablement token* at
     https://www.vestaboard.com/local-api (the board owner is emailed a token).
     The board must be paired and online.
  2. Exchange the token ONCE for a permanent API key:
         python3 vestaboard.py enable <TOKEN>
     The key is provisioned onto the board itself and saved to the config file.
  3. Verify:
         python3 vestaboard.py test

Configuration lives in `config.json` inside the config directory, which is
resolved in this order:
  - the directory named by VESTABOARD_CONFIG_DIR
  - the directory containing this script, if a config.json is already there
  - ~/.config/vestaboard  (default; keeps the key out of the shareable skill)

Environment overrides: VESTABOARD_LOCAL_API_KEY, VESTABOARD_HOST, VESTABOARD_PORT.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import error, request

PORT = int(os.environ.get("VESTABOARD_PORT", "7000"))
ROWS, COLS = 6, 22  # Flagship board geometry
DEFAULT_HOST = "vestaboard.local"  # mDNS name, when the network supports it


# --- errors ------------------------------------------------------------------

class VestaboardError(Exception):
    """Base class for errors raised by this client."""


class BoardUnreachable(VestaboardError):
    """The board could not be contacted on the network."""


class BoardHTTPError(VestaboardError):
    """The board answered with an HTTP error status."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status} from the board: {body.strip()[:200]}")
        self.status = status
        self.body = body


# --- configuration -----------------------------------------------------------

def _config_dir() -> Path:
    env = os.environ.get("VESTABOARD_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "config.json").exists():
        return script_dir
    return Path.home() / ".config" / "vestaboard"


CONFIG_DIR = _config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Return the saved config, or {} when there is none yet."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError as e:
            raise VestaboardError(f"{CONFIG_FILE} is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise VestaboardError(f"{CONFIG_FILE} must contain a JSON object.")
        return data
    return {}


def save_config(cfg: dict) -> None:
    """Write the config with owner-only permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")
    CONFIG_FILE.chmod(0o600)


def load_key() -> str | None:
    env = os.environ.get("VESTABOARD_LOCAL_API_KEY")
    if env:
        return env.strip()
    key = load_config().get("key")
    return key.strip() if isinstance(key, str) and key.strip() else None


def load_host() -> str:
    env = os.environ.get("VESTABOARD_HOST")
    if env:
        return env.strip()
    host = load_config().get("host")
    if isinstance(host, str) and host.strip():
        return host.strip()
    return DEFAULT_HOST


# --- character map -----------------------------------------------------------

CHAR_TO_CODE = {
    " ": 0,
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8, "I": 9,
    "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15, "P": 16, "Q": 17,
    "R": 18, "S": 19, "T": 20, "U": 21, "V": 22, "W": 23, "X": 24, "Y": 25,
    "Z": 26,
    "1": 27, "2": 28, "3": 29, "4": 30, "5": 31, "6": 32, "7": 33, "8": 34,
    "9": 35, "0": 36,
    "!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42, "-": 44, "+": 46,
    "&": 47, "=": 48, ";": 49, ":": 50, "'": 52, '"': 53, "%": 54, ",": 55,
    ".": 56, "/": 59, "?": 60, "°": 62,
}
CODE_TO_CHAR = {code: ch for ch, code in CHAR_TO_CODE.items()}

# Named color tiles, usable in text as {red}, {blue}, etc. (see encode_text).
COLORS = {
    "red": 63, "orange": 64, "yellow": 65, "green": 66, "blue": 67,
    "violet": 68, "purple": 68, "white": 69, "black": 70, "filled": 71,
    "blank": 0,
}
CODE_TO_COLOR_LETTER = {
    63: "R", 64: "O", 65: "Y", 66: "G", 67: "B", 68: "V", 69: "W", 70: "K",
    71: "#",
}


# --- encoding helpers --------------------------------------------------------

def encode_char(ch: str) -> int:
    """Map a single character to its Vestaboard code (unknown -> blank)."""
    return CHAR_TO_CODE.get(ch.upper(), 0)


def encode_text(text: str, align: str = "center") -> list[list[int]]:
    """
    Encode a string into a well-formatted 6x22 grid of character codes.

    - Word-wraps long text across rows at word boundaries.
    - A single word longer than 22 cells is hard-split across rows.
    - An explicit "\\n" forces a line break.
    - The block of lines is centered vertically; each line is aligned
      horizontally per `align` ("center", "left", or "right").
    - Color tiles embed with braces: "{red}{red} HI {blue}{blue}".
    - Text is upper-cased (the board has no lowercase tiles).
    - Text needing more than 6 rows is truncated to 6 with a stderr warning.
    """
    lines = _wrap_to_lines(text)
    if len(lines) > ROWS:
        print(
            f"warning: text needs {len(lines)} rows but the board has {ROWS}; "
            f"showing the first {ROWS}.",
            file=sys.stderr,
        )
        lines = lines[:ROWS]

    grid: list[list[int]] = []
    top_pad = (ROWS - len(lines)) // 2
    for r in range(ROWS):
        line_idx = r - top_pad
        if 0 <= line_idx < len(lines):
            grid.append(_align_row(lines[line_idx][:COLS], align))
        else:
            grid.append([0] * COLS)
    return grid


def encode_rows(lines: list[str], align: str = "left") -> list[list[int]]:
    """
    Put each string on its OWN row (no word-wrap), top-anchored.
    Each line is encoded, truncated to 22 cells, and aligned. Up to 6 lines;
    extras are dropped with a stderr warning. Supports {color} tokens per line.
    """
    if len(lines) > ROWS:
        print(f"warning: {len(lines)} lines given but the board has {ROWS} rows; "
              f"showing the first {ROWS}.", file=sys.stderr)
    grid: list[list[int]] = []
    for r in range(ROWS):
        codes = _tokenize_line(lines[r])[:COLS] if r < len(lines) else []
        grid.append(_align_row(codes, align))
    return grid


def _align_row(codes: list[int], align: str) -> list[int]:
    pad = COLS - len(codes)
    if align == "left":
        left = 0
    elif align == "right":
        left = pad
    else:  # center
        left = pad // 2
    return [0] * left + codes + [0] * (pad - left)


def _wrap_to_lines(text: str) -> list[list[int]]:
    """Word-wrap `text` into a list of code-rows, each at most COLS wide."""
    lines: list[list[int]] = []
    for para in text.split("\n"):
        words = [w for w in para.split(" ") if w != ""]
        if not words:
            lines.append([])  # preserve blank line
            continue
        cur: list[int] = []
        for word in words:
            codes = _tokenize_line(word)
            # hard-split a word that can't fit on a row by itself
            chunks = [codes[i:i + COLS] for i in range(0, len(codes), COLS)]
            for chunk in chunks:
                if not cur:
                    cur = chunk[:]
                elif len(cur) + 1 + len(chunk) <= COLS:
                    cur += [0] + chunk  # single blank between words
                else:
                    lines.append(cur)
                    cur = chunk[:]
        lines.append(cur)
    return lines


def _tokenize_line(line: str) -> list[int]:
    """Turn one line of text (with optional {color} tokens) into codes."""
    codes: list[int] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "{":
            end = line.find("}", i)
            if end != -1:
                token = line[i + 1:end].strip().lower()
                if token in COLORS:
                    codes.append(COLORS[token])
                    i = end + 1
                    continue
        codes.append(encode_char(ch))
        i += 1
    return codes


def decode_grid(grid: list[list[int]]) -> str:
    """Render a 6x22 grid back to readable text (color tiles as one letter)."""
    out_rows = []
    for row in grid:
        chars = []
        for code in row:
            if code in CODE_TO_CHAR:
                chars.append(CODE_TO_CHAR[code])
            elif code in CODE_TO_COLOR_LETTER:
                chars.append(CODE_TO_COLOR_LETTER[code])
            else:
                chars.append("?")
        out_rows.append("".join(chars).rstrip())
    return "\n".join(out_rows)


def _validate_grid(grid: object) -> None:
    ok = (
        isinstance(grid, list)
        and len(grid) == ROWS
        and all(isinstance(row, list) and len(row) == COLS for row in grid)
        and all(isinstance(c, int) and 0 <= c <= 71 for row in grid for c in row)
    )
    if not ok:
        raise ValueError(f"Grid must be {ROWS} rows of {COLS} integer codes (0-71).")


# --- HTTP --------------------------------------------------------------------

def _http(
    method: str, url: str, headers: dict[str, str] | None = None,
    body: bytes | None = None, timeout: float = 10.0,
) -> tuple[int, dict[str, str], str]:
    """Return (status, headers, body). Raises BoardUnreachable on network failure."""
    req = request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except (error.URLError, OSError, ValueError) as e:
        raise BoardUnreachable(f"{url}: {e}") from e


# --- discovery ---------------------------------------------------------------

def _my_prefix() -> str | None:
    """Our /24 prefix, e.g. '192.168.1' (None if we can't tell)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0].rsplit(".", 1)[0]
    except OSError:
        return None
    finally:
        s.close()


def _probe(host: str, api_key: str | None, timeout: float = 1.5) -> str | None:
    """
    Classify what answers at `host`:
      'auth'  - a Vestaboard that accepted our key (HTTP 200)
      'board' - a Vestaboard that rejected our key, or answered without one
      None    - nothing there, or something that is not a Vestaboard
    """
    headers = {"X-Vestaboard-Local-Api-Key": api_key} if api_key else {}
    try:
        status, resp_headers, _ = _http(
            "GET", f"http://{host}:{PORT}/local-api/message",
            headers=headers, timeout=timeout,
        )
    except BoardUnreachable:
        return None
    server = next((v for k, v in resp_headers.items() if k.lower() == "server"), "")
    if "airtunes" in server.lower():  # macOS AirPlay also listens on :7000
        return None
    is_board = "vestaboard" in server.lower() or "javalin" in server.lower()
    if status == 200:
        return "auth" if (api_key and is_board) else "board"
    return "board" if is_board else None


def discover_all(api_key: str | None = None) -> list[tuple[str, str]]:
    """Scan our /24. Returns [(ip, 'auth'|'board'), ...] for every board found."""
    prefix = _my_prefix()
    if not prefix:
        return []
    hosts = [f"{prefix}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=128) as pool:
        results = pool.map(lambda h: _probe(h, api_key), hosts)
        return [(ip, kind) for ip, kind in zip(hosts, results) if kind]


def discover(api_key: str | None = None) -> str | None:
    """
    Scan our /24 for *our* board. Prefers a board that accepts the key; falls
    back to the only board on the network. Returns None when nothing answers or
    when several boards answer and none accepts the key (ambiguous).
    """
    found = discover_all(api_key)
    auth = [ip for ip, kind in found if kind == "auth"]
    if len(auth) == 1:
        return auth[0]
    if len(auth) > 1:
        print(f"warning: several boards accept this key: {', '.join(auth)}; "
              f"using {auth[0]}. Set VESTABOARD_HOST to choose.", file=sys.stderr)
        return auth[0]
    if len(found) == 1:
        return found[0][0]
    if found:
        print("warning: several Vestaboards answered but none accepted the key: "
              + ", ".join(ip for ip, _ in found)
              + ". Not guessing; set VESTABOARD_HOST to the right one.",
              file=sys.stderr)
    return None


# --- client ------------------------------------------------------------------

class Vestaboard:
    def __init__(
        self, api_key: str | None = None, host: str | None = None,
        timeout: float = 10.0, auto_discover: bool = True,
    ):
        self.api_key = api_key or load_key()
        self.host = host or load_host()
        # A host the user named (arg, env, or config) is never replaced by a guess.
        self.host_is_configured = bool(
            host or os.environ.get("VESTABOARD_HOST") or load_config().get("host")
        )
        self.timeout = timeout
        self.auto_discover = auto_discover

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{PORT}/local-api"

    def _cache_host(self, ip: str) -> None:
        """Remember the board's IP in the config file."""
        self.host = ip
        cfg = load_config()
        cfg["host"] = ip
        save_config(cfg)

    def _ensure_reachable(self) -> None:
        """
        Make sure the configured host answers. If it does not and the host was
        never configured (mDNS default), discover the board and save its IP.
        A configured host is never silently replaced: writing to the wrong
        physical board is not recoverable, so we raise with the details instead.
        """
        for timeout in (3.0, 6.0):  # the Note can be slow to answer; retry once
            if _probe(self.host, self.api_key, timeout=timeout):
                return
        if not self.auto_discover:
            raise BoardUnreachable(f"Board not reachable at {self.host}")
        print(f"{self.host} did not answer; scanning the network for the board ...")
        found = discover_all(self.api_key)
        if not found:
            raise BoardUnreachable(
                f"{self.host} did not answer and no Vestaboard was found on this network.")
        ips = ", ".join(f"{ip} ({kind})" for ip, kind in found)
        if self.host_is_configured:
            raise BoardUnreachable(
                f"Configured board {self.host} did not answer. Other board(s) found: {ips}.\n"
                f"  Not switching automatically. If your board's address changed, set\n"
                f"  VESTABOARD_HOST=<ip> or run `discover` to update the config on purpose.")
        ip = discover(self.api_key)
        if not ip:
            raise BoardUnreachable(
                f"Several Vestaboards found ({ips}) and none accepted the key. "
                f"Set VESTABOARD_HOST to the right one.")
        self._cache_host(ip)
        print(f"Found the board at {ip} (saved).")

    @property
    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise VestaboardError(
                "No API key. Run `python3 vestaboard.py enable <TOKEN>` first, "
                "or set VESTABOARD_LOCAL_API_KEY."
            )
        return {
            "X-Vestaboard-Local-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: bytes | None = None) -> str:
        status, _, text = _http(
            method, f"{self.base_url}{path}", headers=self._headers,
            body=body, timeout=self.timeout,
        )
        if status >= 400:
            raise BoardHTTPError(status, text)
        return text

    def read(self) -> list[list[int]]:
        """Return the board's current 6x22 grid of character codes."""
        self._headers  # fail early with a clear message when no key is set
        self._ensure_reachable()
        text = self._request("GET", "/message")
        if not text.strip():
            # The board returns an empty body until a message is set via Local API.
            return [[0] * COLS for _ in range(ROWS)]
        data = json.loads(text)
        # The board may wrap the grid as {"message": {"layout": "[[...]]"}} or
        # return the raw grid; handle both.
        if isinstance(data, dict):
            msg = data.get("message", data)
            layout = msg.get("layout") if isinstance(msg, dict) else None
            if isinstance(layout, str):
                return json.loads(layout)
            if isinstance(layout, list):
                return layout
            if isinstance(msg, list):
                return msg
        if isinstance(data, list):
            return data
        raise VestaboardError(f"Unexpected read response: {data!r}")

    def write_grid(self, grid: list[list[int]]) -> dict:
        """Write a raw 6x22 grid of character codes to the board."""
        _validate_grid(grid)
        self._headers  # fail early with a clear message when no key is set
        self._ensure_reachable()
        text = self._request("POST", "/message", body=json.dumps(grid).encode())
        try:
            return json.loads(text)
        except ValueError:
            return {"status": "ok", "text": text}

    def write_text(self, text: str, align: str = "center") -> dict:
        """Encode `text` (word-wrapped, fitted) and write it."""
        return self.write_grid(encode_text(text, align=align))

    def write_rows(self, lines: list[str], align: str = "left") -> dict:
        """Write one line per row (no wrapping), top-anchored."""
        return self.write_grid(encode_rows(lines, align=align))

    def clear(self) -> dict:
        return self.write_grid([[0] * COLS for _ in range(ROWS)])


def enable(enablement_token: str, host: str | None = None) -> str:
    """
    One-time: exchange an enablement token for a permanent API key and save it
    (with the host) to the config file. Returns the key.
    """
    host = host or load_host()
    status, _, text = _http(
        "POST", f"http://{host}:{PORT}/local-api/enablement",
        headers={"X-Vestaboard-Local-Api-Enablement-Token": enablement_token.strip()},
    )
    if status >= 400:
        raise BoardHTTPError(status, text)
    try:
        data = json.loads(text)
    except ValueError:
        raise VestaboardError(f"Unexpected enablement response: {text[:200]!r}")
    key = data.get("apiKey") if isinstance(data, dict) else None
    if not key and isinstance(data, dict) and isinstance(data.get("message"), dict):
        key = data["message"].get("apiKey")
    if not key:
        raise VestaboardError(f"No apiKey in enablement response: {data!r}")
    cfg = load_config()
    cfg["key"] = key
    cfg["host"] = host
    save_config(cfg)
    print(f"Saved API key to {CONFIG_FILE}")
    return key


# --- CLI ---------------------------------------------------------------------

USAGE = """\
Usage: python3 vestaboard.py <command> [args]

Commands:
  enable <TOKEN>     One-time: exchange an enablement token for an API key
  config             Show where the config lives and whether a key is set
  discover           Scan the LAN for the board and save its IP
  test               Read the board to verify the key and connection
  read               Print the board's current contents
  say "TEXT"         Show text: word-wrapped, centered ({red} etc. for tiles)
  rows "R1" "R2" ... Show one argument per row, top-anchored, no wrapping
  grid <JSON|FILE|-> Show a raw 6x22 grid of tile codes (JSON, a file, or stdin)
  clear              Blank the board

Alignment flags for say/rows: --left  --center  --right
"""


def _split_align(args: list[str], default: str) -> tuple[str, list[str]]:
    align, rest = default, []
    for tok in args:
        if tok in ("--left", "--right", "--center"):
            align = tok.lstrip("-")
        else:
            rest.append(tok)
    return align, rest


def _load_grid_arg(arg: str) -> list[list[int]]:
    if arg == "-":
        raw = sys.stdin.read()
    elif Path(arg).is_file():
        raw = Path(arg).read_text()
    else:
        raw = arg
    return json.loads(raw)


def _main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    cmd, *rest = argv
    try:
        if cmd == "config":
            print(f"Config file: {CONFIG_FILE}")
            print(f"  exists:  {'yes' if CONFIG_FILE.exists() else 'no'}")
            print(f"  API key: {'set' if load_key() else 'NOT SET (run: enable <TOKEN>)'}")
            print(f"  host:    {load_host()}")
            return 0

        if cmd == "enable":
            if not rest:
                print("Usage: enable <ENABLEMENT_TOKEN>")
                return 2
            enable(rest[0])
            print("Enabled. Try: python3 vestaboard.py test")
            return 0

        vb = Vestaboard()

        if cmd == "discover":
            found = discover_all(vb.api_key)
            for ip, kind in found:
                note = "accepts this key" if kind == "auth" else "Vestaboard, key rejected/untested"
                print(f"  {ip:15} {note}")
            ip = discover(vb.api_key)
            if ip:
                if vb.host_is_configured and ip != vb.host:
                    print(f"Configured host is {vb.host}; updating config to {ip}.")
                vb._cache_host(ip)
                print(f"Board found at {ip} (saved).")
                return 0
            if found:
                print("Could not tell which board is yours. Set VESTABOARD_HOST or edit "
                      f"{CONFIG_FILE} by hand.")
            else:
                print("No Vestaboard found on this network.")
            return 1

        if cmd in ("test", "read"):
            grid = vb.read()
            print(f"Connected to {vb.host}. Current board:\n")
            print(decode_grid(grid))
            return 0

        if cmd == "say":
            align, words = _split_align(rest, "center")
            if not words:
                print('Usage: say "YOUR TEXT" [--left|--center|--right]')
                return 2
            result = vb.write_text(" ".join(words), align=align)
            print(f"Sent ({align}). Board responded: {result}")
            return 0

        if cmd == "rows":
            align, args = _split_align(rest, "left")
            # One arg with newlines -> split into rows; else each arg is a row.
            lines = args[0].split("\n") if len(args) == 1 else args
            if not lines:
                print('Usage: rows "ROW1" "ROW2" ...   (or one "R1\\nR2\\n..." arg)')
                return 2
            result = vb.write_rows(lines, align=align)
            print(f"Sent {len(lines)} row(s). Board responded: {result}")
            return 0

        if cmd == "grid":
            if not rest:
                print("Usage: grid '<json 6x22 array>' | grid path/to/grid.json | grid -")
                return 2
            result = vb.write_grid(_load_grid_arg(rest[0]))
            print(f"Sent grid. Board responded: {result}")
            return 0

        if cmd == "clear":
            result = vb.clear()
            print(f"Cleared. Board responded: {result}")
            return 0

        print(f"Unknown command: {cmd}\n")
        print(USAGE)
        return 2

    except BoardUnreachable as e:
        print(
            f"Could not reach the board.\n  {e}\n"
            "  - Make sure this computer is on the same network as the Vestaboard.\n"
            "  - Point at a specific IP with: VESTABOARD_HOST=192.168.1.x python3 vestaboard.py test\n"
            "  - Or run: python3 vestaboard.py discover"
        )
        return 1
    except BoardHTTPError as e:
        print(e)
        if e.status in (401, 403):
            print(
                "  -> The API key was rejected. Request a new enablement token at\n"
                "     https://www.vestaboard.com/local-api and run: enable <TOKEN>"
            )
        return 1
    except (VestaboardError, ValueError) as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
