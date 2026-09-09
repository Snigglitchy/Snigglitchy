#!/usr/bin/env python3
"""Collect per-repo commit activity and write data/activity.json.

Stdlib only. Reads GH_TOKEN from the environment (the workflow passes
${{ github.token }}). A missing or private repo yields zeros rather than
failing the build, so the picture always renders.
"""

import json
import os
import pathlib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "regions.json").read_text())
TOKEN = os.environ.get("GH_TOKEN", "")
WEEKS = 12
NOW = datetime.now(timezone.utc)


def api(path):
    """GET one page of the GitHub API. Returns [] on any failure."""
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "brainmap-readme",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  skipped {path}: {e}")
        return []


def commit_dates(owner, repo):
    """Every commit date on the default branch in the last WEEKS weeks."""
    since = (NOW - timedelta(weeks=WEEKS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dates, page = [], 1
    while page <= 5:  # 500 commits is plenty for a 12-week window
        batch = api(f"/repos/{owner}/{repo}/commits?since={since}&per_page=100&page={page}")
        if not batch:
            break
        for c in batch:
            stamp = c.get("commit", {}).get("author", {}).get("date")
            if stamp:
                dates.append(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
        if len(batch) < 100:
            break
        page += 1
    return dates


def main():
    owner = CONFIG["owner"]
    window = CONFIG.get("window_days", 30)
    out = {}

    for region in CONFIG["regions"]:
        repo = region["repo"]
        print(f"collecting {owner}/{repo}")
        dates = commit_dates(owner, repo)

        recent = sum(1 for d in dates if (NOW - d).days < window)
        buckets = [0] * WEEKS
        for d in dates:
            idx = WEEKS - 1 - int((NOW - d).days // 7)
            if 0 <= idx < WEEKS:
                buckets[idx] += 1

        meta = api(f"/repos/{owner}/{repo}")
        out[region["id"]] = {
            "repo": repo,
            "commits": recent,
            "weeks": buckets,
            "stars": (meta or {}).get("stargazers_count", 0),
            "url": (meta or {}).get("html_url", f"https://github.com/{owner}/{repo}"),
        }
        print(f"  {recent} commits in {window} days")

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "activity.json").write_text(
        json.dumps({"generated": NOW.strftime("%Y-%m-%d"), "window_days": window, "repos": out}, indent=2)
    )
    print("wrote data/activity.json")


if __name__ == "__main__":
    main()
