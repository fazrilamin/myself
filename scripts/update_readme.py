"""Write the user's recently played Spotify tracks into README.md.

Needs the environment variables SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and
SPOTIFY_REFRESH_TOKEN. If Spotify fails, the old track list is kept and only
the timestamp changes, so the workflow still commits.
"""

import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!-- SPOTIFY:START -->", "<!-- SPOTIFY:END -->"
MYT = timezone(timedelta(hours=8))
LIMIT = 5


def get_access_token() -> str:
    cid = os.environ["SPOTIFY_CLIENT_ID"]
    secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    refresh = os.environ["SPOTIFY_REFRESH_TOKEN"]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh}
    ).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["access_token"]


def get_recently_played(token: str) -> list[dict]:
    req = urllib.request.Request(
        f"https://api.spotify.com/v1/me/player/recently-played?limit={LIMIT}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp).get("items", [])


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def render_tracks(items: list[dict]) -> str:
    if not items:
        return "_Nothing played recently._"
    rows = ["| | Track | Artist | Played |", "|---|---|---|---|"]
    for item in items:
        t = item["track"]
        images = t["album"].get("images") or []
        art = f'<img src="{images[-1]["url"]}" width="40">' if images else ""
        name = md_escape(t["name"])
        url = t["external_urls"].get("spotify", "")
        track = f"[{name}]({url})" if url else name
        artists = md_escape(", ".join(a["name"] for a in t["artists"]))
        played = datetime.fromisoformat(item["played_at"].replace("Z", "+00:00"))
        rows.append(
            f"| {art} | {track} | {artists} | {played.astimezone(MYT):%d %b, %H:%M} |"
        )
    return "\n".join(rows)


def main() -> None:
    readme = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r"(.*?)" + re.escape(END), re.S)
    match = pattern.search(readme)
    if not match:
        sys.exit(f"Markers {START} / {END} not found in README.md")

    # Keep the previous table if Spotify fails, minus its old timestamp line.
    old_body = re.sub(r"\n*<sub>Last updated:.*?</sub>\s*$", "", match.group(1).strip())

    try:
        tracks = render_tracks(get_recently_played(get_access_token()))
    except Exception as exc:  # network, auth, or API errors
        print(f"Spotify fetch failed, keeping previous list: {exc}", file=sys.stderr)
        tracks = old_body or "_Couldn't reach Spotify right now._"

    stamp = datetime.now(MYT).strftime("%d %b %Y, %H:%M MYT")
    body = f"{tracks}\n\n<sub>Last updated: {stamp}</sub>"
    readme = pattern.sub(lambda _: f"{START}\n{body}\n{END}", readme)
    README.write_text(readme, encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
