#!/usr/bin/env python3
"""Generate self-hosted GitHub profile SVG cards using GitHub's GraphQL API."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "AlNahianFatin")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
OUTPUT = Path(os.environ.get("OUTPUT_DIR", "profile"))
PURPLE = "#8957E5"
LILAC = "#A78BFA"
YELLOW = "#FACC15"
MUTED = "#808080"
TEXT = "#C9D1D9"
BG = "#00000000"
BORDER = "#8957E5"
FONT = "'Segoe UI', Ubuntu, sans-serif"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $cursor: String) {
  user(login: $login) {
    login
    name
    followers { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        isPrivate
        stargazerCount
        forkCount
        languages(first: 20, orderBy: SIZE) {
          edges { size node { name } }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def graphql(token: str, variables: dict) -> dict:
    payload = json.dumps({"query": QUERY, "variables": variables}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "AlNahianFatin-profile-graph-generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc
    if result.get("errors"):
        messages = "; ".join(e.get("message", "Unknown GraphQL error") for e in result["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {messages}")
    return result["data"]["user"]


def fetch_data() -> dict:
    if not TOKEN:
        raise RuntimeError("Set GITHUB_TOKEN to your GH_PAT repository secret.")
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    variables = {
        "login": USERNAME,
        "from": datetime.combine(start, datetime.min.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
        "to": datetime.combine(today, datetime.max.time(), timezone.utc).isoformat().replace("+00:00", "Z"),
        "cursor": None,
    }
    first = graphql(TOKEN, variables)
    if first is None:
        raise RuntimeError(f"GitHub user '{USERNAME}' was not found or is inaccessible.")

    repos = list(first["repositories"]["nodes"])
    page = first["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        variables["cursor"] = page["endCursor"]
        next_user = graphql(TOKEN, variables)
        repos.extend(next_user["repositories"]["nodes"])
        page = next_user["repositories"]["pageInfo"]

    first["allRepos"] = repos
    return first


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def svg_start(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<title>{esc(title)}</title>',
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="8" fill="{BG}" stroke="{BORDER}" stroke-opacity="0.65"/>',
    ]


def text(x, y, value, size=13, color=TEXT, weight=400, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" '
            f'font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>')


def save_svg(name: str, lines: list[str]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text("\n".join(lines + ["</svg>"]), encoding="utf-8")
    print(f"Generated {path} ({path.stat().st_size} bytes)")


def generate_stats(user: dict, repos: list[dict], contrib: dict) -> None:
    commits = contrib["totalCommitContributions"]
    issues = contrib["totalIssueContributions"]
    prs = contrib["totalPullRequestContributions"]
    reviews = contrib["totalPullRequestReviewContributions"]
    total = contrib["contributionCalendar"]["totalContributions"]
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    private_repos = sum(1 for r in repos if r["isPrivate"])
    public_repos = len(repos) - private_repos

    cards = [
        ("Total Contributions", total, PURPLE),
        ("Commits", commits, LILAC),
        ("Pull Requests", prs, PURPLE),
        ("Issues", issues, LILAC),
        ("Code Reviews", reviews, PURPLE),
        ("Stars Earned", stars, YELLOW),
        ("Repositories", len(repos), LILAC),
        ("Followers", user["followers"]["totalCount"], PURPLE),
    ]
    lines = svg_start(720, 245, f"{USERNAME} GitHub Statistics")
    lines.append(text(24, 34, "GitHub Statistics", 19, PURPLE, 700))
    lines.append(text(696, 32, "Last 365 days", 11, MUTED, 400, "end"))
    for i, (label, value, color) in enumerate(cards):
        col, row = i % 4, i // 4
        x, y = 24 + col * 174, 83 + row * 91
        lines.append(f'<rect x="{x}" y="{y-28}" width="154" height="68" rx="7" fill="#8957E5" fill-opacity="0.08" stroke="#8957E5" stroke-opacity="0.25"/>')
        lines.append(text(x + 12, y, f"{value:,}", 23, color, 700))
        lines.append(text(x + 12, y + 23, label, 11, MUTED, 500))
    lines.append(text(24, 229, f"{public_repos} public · {private_repos} private repositories · {forks:,} forks", 10, MUTED))
    save_svg("stats.svg", lines)


def generate_languages(repos: list[dict]) -> None:
    totals = defaultdict(int)
    for repo in repos:
        for edge in repo.get("languages", {}).get("edges", []):
            totals[edge["node"]["name"]] += edge["size"]
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:8]
    lines = svg_start(495, 310, f"{USERNAME} Most Used Languages")
    lines.append(text(22, 34, "Most Used Languages", 18, PURPLE, 700))
    if not ranked:
        lines.append(text(22, 85, "No language data available", 13, MUTED))
    else:
        total_bytes = sum(v for _, v in ranked)
        palette = [PURPLE, LILAC, "#FACC15", "#58A6FF", "#3FB950", "#F78166", "#D2A8FF", "#8B949E"]
        x, y, bar_w, gap = 22, 63, 451, 12
        cursor = x
        for idx, (lang, amount) in enumerate(ranked):
            width = bar_w * amount / total_bytes if total_bytes else 0
            lines.append(f'<rect x="{cursor:.2f}" y="{y}" width="{max(width, 1):.2f}" height="10" fill="{palette[idx % len(palette)]}"/>')
            cursor += width
        for idx, (lang, amount) in enumerate(ranked):
            row_y = 103 + idx * gap * 2
            pct = amount / total_bytes * 100 if total_bytes else 0
            lines.append(f'<circle cx="28" cy="{row_y-4}" r="4" fill="{palette[idx % len(palette)]}"/>')
            lines.append(text(42, row_y, lang, 11, TEXT, 500))
            lines.append(text(470, row_y, f"{pct:.1f}%", 11, MUTED, 500, "end"))
    lines.append(text(22, 297, "Based on language bytes across accessible, non-fork repositories", 9, MUTED))
    save_svg("top-langs.svg", lines)


def generate_activity(contrib: dict) -> None:
    days = []
    for week in contrib["contributionCalendar"]["weeks"]:
        days.extend(week["contributionDays"])
    days.sort(key=lambda item: item["date"])
    if len(days) > 371:
        days = days[-371:]
    max_count = max((d["contributionCount"] for d in days), default=0)
    palette = ["#161B22", "#2D1B4E", "#55318A", "#8957E5", "#C4A7FF"]
    lines = svg_start(960, 225, f"{USERNAME} Contribution Activity")
    lines.append(text(22, 31, "Contribution Activity", 18, PURPLE, 700))
    lines.append(text(938, 30, f"{contrib['contributionCalendar']['totalContributions']:,} contributions in the last year", 10, MUTED, 400, "end"))
    left, top, cell, gap = 24, 62, 10, 3
    first_date = date.fromisoformat(days[0]["date"]) if days else date.today()
    first_week_start = first_date - timedelta(days=first_date.weekday())
    for day in days:
        dt = date.fromisoformat(day["date"])
        # Align columns to calendar weeks and rows to Monday-Sunday.
        week_index = (dt - first_week_start).days // 7
        weekday = dt.weekday()
        count = day["contributionCount"]
        if count == 0:
            color = palette[0]
        elif max_count and count / max_count <= 0.25:
            color = palette[1]
        elif max_count and count / max_count <= 0.5:
            color = palette[2]
        elif max_count and count / max_count <= 0.75:
            color = palette[3]
        else:
            color = palette[4]
        x = left + week_index * (cell + gap)
        y = top + weekday * (cell + gap)
        lines.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{esc(day["date"])}: {count} contributions</title></rect>')
    lines.append(text(24, 190, "Less", 9, MUTED))
    for i, color in enumerate(palette):
        lines.append(f'<rect x="{55 + i * 13}" y="181" width="10" height="10" rx="2" fill="{color}"/>')
    lines.append(text(127, 190, "More", 9, MUTED))
    lines.append(text(938, 211, "Daily contributions · GitHub contribution calendar", 9, MUTED, 400, "end"))
    save_svg("activity.svg", lines)


def generate_milestones(user: dict, repos: list[dict], contrib: dict) -> None:
    """A transparent, API-derived replacement; not GitHub's official trophy awards."""
    total_contrib = contrib["contributionCalendar"]["totalContributions"]
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    metrics = [
        ("Contributions", total_contrib, YELLOW),
        ("Stars earned", stars, PURPLE),
        ("Repositories", len(repos), LILAC),
        ("Followers", user["followers"]["totalCount"], PURPLE),
        ("Forks received", forks, YELLOW),
    ]
    lines = svg_start(720, 170, f"{USERNAME} GitHub Milestones")
    lines.append(text(24, 34, "GitHub Milestones", 19, PURPLE, 700))
    lines.append(text(696, 32, "Live metrics · not official GitHub trophies", 10, MUTED, 400, "end"))
    for i, (label, value, color) in enumerate(metrics):
        x = 24 + i * 139
        lines.append(f'<rect x="{x}" y="57" width="123" height="76" rx="8" fill="#8957E5" fill-opacity="0.08" stroke="#8957E5" stroke-opacity="0.25"/>')
        lines.append(text(x + 61.5, 91, f"{value:,}", 21, color, 700, "middle"))
        lines.append(text(x + 61.5, 113, label, 10, MUTED, 500, "middle"))
    lines.append(text(24, 153, "Generated from data available through the GitHub GraphQL API", 9, MUTED))
    save_svg("milestones.svg", lines)


def main() -> int:
    try:
        user = fetch_data()
        repos = user.pop("allRepos")
        contrib = user["contributionsCollection"]
        generate_stats(user, repos, contrib)
        generate_languages(repos)
        generate_activity(contrib)
        generate_milestones(user, repos, contrib)
        print("All four GitHub graph SVGs generated successfully.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
