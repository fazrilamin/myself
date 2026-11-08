"""Generate stats.svg and top-langs.svg from the GitHub GraphQL API.

Usage: python scripts/stats_cards.py <output_dir>
Needs GITHUB_TOKEN in the environment (the Actions token is enough).
"""

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

USER = "fazrilamin"
MYT = timezone(timedelta(hours=8))
TOP_LANGS = 6

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

STYLE = """
  <style>
    .bg { fill: #ffffff; stroke: #d0d7de; }
    .title { font: 600 15px 'Segoe UI', Ubuntu, sans-serif; fill: #0969da; }
    .label { font: 400 13px 'Segoe UI', Ubuntu, sans-serif; fill: #57606a; }
    .value { font: 600 13px 'Segoe UI', Ubuntu, sans-serif; fill: #24292f; }
    @media (prefers-color-scheme: dark) {
      .bg { fill: #0d1117; stroke: #30363d; }
      .title { fill: #58a6ff; }
      .label { fill: #8b949e; }
      .value { fill: #e6edf3; }
    }
  </style>"""


def fetch() -> dict:
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def streaks(days: list[dict], today: date) -> tuple[int, int]:
    counts = {d["date"]: d["contributionCount"] for d in days}
    ordered = sorted(counts)

    longest = run = 0
    for day in ordered:
        run = run + 1 if counts[day] > 0 else 0
        longest = max(longest, run)

    # Today with zero contributions doesn't break the streak yet.
    cursor = today if counts.get(today.isoformat(), 0) > 0 else today - timedelta(days=1)
    current = 0
    while counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def card(height: int, title: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="{height}" '
        f'viewBox="0 0 400 {height}">{STYLE}\n'
        f'  <rect class="bg" x="0.5" y="0.5" width="399" height="{height - 1}" rx="6"/>\n'
        f'  <text class="title" x="20" y="32">{escape(title)}</text>\n{body}</svg>\n'
    )


def stats_svg(rows: list[tuple[str, str]]) -> str:
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 62 + i * 24
        body += (
            f'  <text class="label" x="20" y="{y}">{escape(label)}</text>\n'
            f'  <text class="value" x="380" y="{y}" text-anchor="end">{escape(value)}</text>\n'
        )
    return card(62 + len(rows) * 24 - 2, "GitHub Stats", body)


def langs_svg(langs: list[tuple[str, str, float]]) -> str:
    if not langs:
        return card(80, "Top Languages", '  <text class="label" x="20" y="58">No code yet</text>\n')
    body = '  <clipPath id="bar"><rect x="20" y="48" width="360" height="10" rx="5"/></clipPath>\n'
    body += '  <g clip-path="url(#bar)">\n'
    x = 20.0
    for _, color, pct in langs:
        w = 360 * pct / 100
        body += f'    <rect x="{x:.2f}" y="48" width="{w:.2f}" height="10" fill="{color}"/>\n'
        x += w
    body += "  </g>\n"
    for i, (name, color, pct) in enumerate(langs):
        cx = 20 + (i % 2) * 185
        cy = 84 + (i // 2) * 24
        body += (
            f'  <circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>\n'
            f'  <text class="value" x="{cx + 16}" y="{cy}">{escape(name)}</text>\n'
            f'  <text class="label" x="{cx + 170}" y="{cy}" text-anchor="end">{pct:.1f}%</text>\n'
        )
    rows = (len(langs) + 1) // 2
    return card(84 + rows * 24 - 6, "Top Languages", body)


def build(user: dict, today: date) -> tuple[str, str]:
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days, today)
    repos = user["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    sizes: dict[str, list] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            entry = sizes.setdefault(name, [0, edge["node"]["color"] or "#8b949e"])
            entry[0] += edge["size"]
    total = sum(v[0] for v in sizes.values())
    top = sorted(sizes.items(), key=lambda kv: kv[1][0], reverse=True)[:TOP_LANGS]
    langs = [(name, color, size * 100 / total) for name, (size, color) in top] if total else []

    def plural(n: int, word: str) -> str:
        return f"{n:,} {word}{'' if n == 1 else 's'}"

    rows = [
        ("Contributions (last year)", f"{cc['contributionCalendar']['totalContributions']:,}"),
        ("Commits this year", f"{cc['totalCommitContributions']:,}"),
        ("Current streak", plural(current, "day")),
        ("Longest streak", plural(longest, "day")),
        ("Stars earned", f"{stars:,}"),
    ]
    return stats_svg(rows), langs_svg(langs)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    out.mkdir(parents=True, exist_ok=True)
    stats, langs = build(fetch(), datetime.now(MYT).date())
    (out / "stats.svg").write_text(stats, encoding="utf-8")
    (out / "top-langs.svg").write_text(langs, encoding="utf-8")
    print(f"Wrote {out / 'stats.svg'} and {out / 'top-langs.svg'}")


if __name__ == "__main__":
    main()
