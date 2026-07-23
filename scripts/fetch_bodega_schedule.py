#!/usr/bin/env python3
"""Fetch Team Bodega schedules from PicklePodium Baseline Cup and write JSON for GitHub Pages."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "schedule" / "bodega-schedule.json"
TOURNAMENT_URL = "https://picklepodium.vercel.app/t/1st-baseline-cup"

# Official PicklePodium player keys for Team Bodega
BODEGA_KEYS = [
    "nalangan, clyde",
    "canete, patricia marie",
    "vargas, maynard",
    "vargas, mary celeste",
    "ylanan, harvey",
    "ileto, archie",
    "torres, paul patrick",
    "catunao, joy",
    "masangya, marc nher",
    "francisco, louie andrew",
    "de guzman, john carlo",
    "baltazar, irish gail",
    "lucerio, brian matthew",
    "acsay, leo vincent",
    "delos santos, allyssah marie",
    "tirol, jarre may",
    "fuentes, gracia gay",
    "reyes, zabdiel",
]


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "bodega-pickleball-schedule-bot/1.0 (+https://github.com/May-nerd/bodega-pickleball-merch)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as primary_err:
        # Fallback for environments where urllib DNS/TLS fails but curl works
        import subprocess

        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", "60", "-A", headers["User-Agent"], url],
                check=True,
                capture_output=True,
            )
            return result.stdout.decode("utf-8", errors="ignore")
        except Exception:
            raise primary_err from None


def find_player_json(html: str, key: str) -> dict | None:
    needle = f'\\"key\\":\\"{key}\\"'
    i = html.find(needle)
    if i < 0:
        return None

    start = html.rfind("{", max(0, i - 5), i + 1)
    chunk = html[start : start + 200000]
    unesc = chunk.replace('\\"', '"').replace("\\\\", "\\")
    if not unesc.startswith("{"):
        j = unesc.find("{")
        if j < 0:
            return None
        unesc = unesc[j:]

    depth = 0
    end = None
    in_str = False
    esc = False
    for idx, ch in enumerate(unesc):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    if end is None:
        raise RuntimeError(f"Could not parse player object for key={key!r}")
    return json.loads(unesc[:end])


def build_payload(players: list[dict]) -> dict:
    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": TOURNAMENT_URL,
        "scheduleUrl": f"{TOURNAMENT_URL}/schedule",
        "event": {
            "name": "Baseline Cup 2026",
            "venue": "Habagat Sports Center, Kalibo",
            "dates": "Jul 24–26, 2026",
        },
        "players": players,
    }


def main() -> int:
    print(f"Fetching {TOURNAMENT_URL} …", flush=True)
    html = fetch_html(TOURNAMENT_URL)
    print(f"Downloaded {len(html):,} bytes", flush=True)

    players: list[dict] = []
    missing: list[str] = []
    for key in BODEGA_KEYS:
        obj = find_player_json(html, key)
        if not obj:
            missing.append(key)
            print(f"  MISSING {key}", flush=True)
            continue
        match_count = sum(len(e.get("matches", [])) for e in obj.get("entries", []))
        print(f"  OK {obj.get('name')} — {len(obj.get('entries', []))} events, {match_count} matches", flush=True)
        players.append(obj)

    if missing:
        print(f"ERROR: missing {len(missing)} players: {missing}", file=sys.stderr)
        return 1
    if len(players) != len(BODEGA_KEYS):
        print("ERROR: unexpected player count", file=sys.stderr)
        return 1

    payload = build_payload(players)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    new_players = json.dumps(players, sort_keys=True, ensure_ascii=False)
    if OUT_PATH.exists():
        try:
            old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            old_players = json.dumps(old.get("players", []), sort_keys=True, ensure_ascii=False)
            if old_players == new_players:
                # Keep prior stamp when nothing schedule-related changed
                payload["updatedAt"] = old.get("updatedAt") or payload["updatedAt"]
                print("No schedule changes detected.", flush=True)
                # Still rewrite event/source metadata if needed, but skip if fully identical sans formatting
                text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
                if OUT_PATH.read_text(encoding="utf-8") == text:
                    return 0
                OUT_PATH.write_text(text, encoding="utf-8")
                print(f"Refreshed metadata only → {OUT_PATH}", flush=True)
                return 0
        except Exception:
            pass

    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(players)} players)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
