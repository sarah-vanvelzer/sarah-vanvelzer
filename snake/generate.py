"""
Collage snake: reads your GitHub contribution graph and draws an animated SVG
where a snake eats every square that has commits. Each time it eats, it grows
by one segment, and the new segment takes the colour of the square it ate.

Runs in GitHub Actions (see .github/workflows/snake.yml). No packages needed.
"""
import json
import os
import sys
import urllib.request

# ---------- look and feel ----------
CELL = 12          # size of each square (and each snake segment)
GAP = 3            # space between squares
PAD = 8            # space around the grid
STEP = 0.07        # seconds per move (smaller = faster snake)
PAUSE = 1.5        # seconds to wait before the snake comes back
START_LENGTH = 3   # how long the snake is before it eats anything

THEMES = {
    "light": {
        "empty": "#ece7dc",
        "levels": ["#f2a7c6", "#e8782a", "#d6247d", "#3b4fa0"],
        "head": "#1f1f1f",
        "body": "#1f1f1f",
    },
    "dark": {
        "empty": "#2a2a2a",
        "levels": ["#7a1f4a", "#e8782a", "#d6247d", "#7fb8bd"],
        "head": "#f2e9d8",
        "body": "#f2e9d8",
    },
}

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def fetch_grid(login, token):
    """Ask GitHub for the contribution calendar. Returns {(col, row): level}."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { weekday contributionLevel } }
          }
        }
      }
    }"""
    body = json.dumps({"query": query, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "collage-snake"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        sys.exit(f"GitHub said: {data['errors']}")
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    grid = {}
    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            grid[(col, day["weekday"])] = LEVELS[day["contributionLevel"]]
    return grid, len(weeks)


def build_route(grid, cols):
    """
    A path of single steps that never crosses itself, so a growing snake can
    follow it safely. Columns with food get a full up/down sweep; empty columns
    are crossed in one step. The snake enters from the left and leaves right.
    """
    route = [(-i, 0) for i in range(START_LENGTH, 0, -1)]   # wait off-screen
    row, going_down = 0, True
    for col in range(cols):
        has_food = any(grid.get((col, r), 0) > 0 for r in range(7))
        if has_food:
            rows = range(7) if going_down else range(6, -1, -1)
            route += [(col, r) for r in rows]
            row = 6 if going_down else 0
            going_down = not going_down
        else:
            route.append((col, row))
    return route


def px(col, row):
    return PAD + col * (CELL + GAP), PAD + row * (CELL + GAP)


def render(grid, cols, theme):
    t = THEMES[theme]
    route = build_route(grid, cols)

    # When does the head reach each square with food?
    meals = []                       # (step index, colour) in eating order
    for i, cell in enumerate(route):
        lvl = grid.get(cell, 0)
        if lvl > 0:
            meals.append((i, t["levels"][lvl - 1]))

    max_len = START_LENGTH + len(meals)
    exit_row = route[-1][1]
    route += [(cols + i, exit_row) for i in range(max_len + 1)]   # slide off-screen
    moves = len(route) - 1
    total = (moves + max_len) * STEP + PAUSE

    width = PAD * 2 + cols * (CELL + GAP) - GAP
    height = PAD * 2 + 7 * (CELL + GAP) - GAP
    frac = lambda seconds: f"{min(seconds / total, 1):.5f}"

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">']

    d = "M" + " L".join(f"{x},{y}" for x, y in (px(*c) for c in route))
    out.append(f'<defs><path id="route" d="{d}"/>'
               f'<clipPath id="board"><rect width="{width}" height="{height}"/></clipPath></defs>')
    out.append('<g clip-path="url(#board)">')

    # the squares
    eaten_at = {route[i]: i for i, _ in meals}
    for (col, row), lvl in sorted(grid.items()):
        x, y = px(col, row)
        if lvl == 0:
            out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{t["empty"]}"/>')
        else:
            when = eaten_at[(col, row)] * STEP
            out.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{t["levels"][lvl - 1]}">'
                f'<animate attributeName="fill" values="{t["levels"][lvl - 1]};{t["empty"]}" '
                f'keyTimes="0;{frac(when)}" dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/></rect>')

    # the snake: segment k follows the head's path, k steps behind.
    # Tail segments are drawn first so the head sits on top.
    colours = [t["head"]] + [t["body"]] * (START_LENGTH - 1) + [c for _, c in meals]
    appears = [0.0] * START_LENGTH + [i * STEP for i, _ in meals]
    travel = moves * STEP
    for k in reversed(range(max_len)):
        start, end = k * STEP, k * STEP + travel
        show = (f'<animate attributeName="opacity" values="0;1" keyTimes="0;{frac(appears[k])}" '
                f'dur="{total:.2f}s" calcMode="discrete" repeatCount="indefinite"/>') if k >= START_LENGTH else ""
        out.append(
            f'<rect x="0" y="0" width="{CELL}" height="{CELL}" rx="3" fill="{colours[k]}" opacity="{0 if show else 1}">'
            f'<animateMotion dur="{total:.2f}s" repeatCount="indefinite" calcMode="linear" '
            f'keyPoints="0;0;1;1" keyTimes="0;{frac(start)};{frac(end)};1">'
            f'<mpath xlink:href="#route" href="#route"/></animateMotion>{show}</rect>')

    out.append('</g></svg>')
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sample":
        import random
        random.seed(4)
        cols = 53
        grid = {(c, r): random.choice([0, 0, 0, 1, 1, 2, 3, 4]) for c in range(cols) for r in range(7)}
    else:
        grid, cols = fetch_grid(os.environ["LOGIN"], os.environ["GITHUB_TOKEN"])

    os.makedirs("dist", exist_ok=True)
    for theme in THEMES:
        with open(f"dist/snake-{theme}.svg", "w") as f:
            f.write(render(grid, cols, theme))
    print("drew dist/snake-light.svg and dist/snake-dark.svg")
