# Vestaboard layouts

Use this reference only for custom cell-by-cell layouts or color art. Prefer the
CLI's `say` and `rows` commands for normal text.

## Geometry and API shape

- The Flagship display is exactly 6 rows by 22 columns.
- A raw grid is a list of 6 lists, each containing 22 integer tile codes.
- A custom grid replaces the whole current display.

Send a grid with the `grid` command. It accepts a JSON literal, a path to a
JSON file, or `-` for stdin, and validates the shape before writing:

```bash
python3 "<skill-root>/scripts/vestaboard.py" grid path/to/grid.json
python3 "<skill-root>/scripts/vestaboard.py" grid '[[63,63,...22 codes...],[...],[...],[...],[...],[...]]'
```

From Python, without copying credential data:

```python
import sys
sys.path.insert(0, "<skill-root>/scripts")
from vestaboard import Vestaboard

board = Vestaboard()
board.write_grid([[0] * 22 for _ in range(6)])
```

## Tile codes

- `0`: blank
- `1` through `26`: A through Z
- `27` through `35`: 1 through 9
- `36`: 0
- `37`: `!`
- `38`: `@`
- `39`: `#`
- `40`: `$`
- `41`: `(`
- `42`: `)`
- `44`: `-`
- `46`: `+`
- `47`: `&`
- `48`: `=`
- `49`: `;`
- `50`: `:`
- `52`: `'`
- `53`: `"`
- `54`: `%`
- `55`: `,`
- `56`: `.`
- `59`: `/`
- `60`: `?`
- `62`: degree symbol
- `63`: red
- `64`: orange
- `65`: yellow
- `66`: green
- `67`: blue
- `68`: violet
- `69`: white
- `70`: black
- `71`: filled

Letters are white-on-black character tiles. A color code creates a solid color
tile, not a colored character.
