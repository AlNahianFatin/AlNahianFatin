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

# Transparent README palette shared across all generated SVGs.
PURPLE = "#8957E5"
LILAC = "#A78BFA"
YELLOW = "#FACC15"
MUTED = "#808080"
LABEL = LILAC
VALUE = PURPLE
ICON = PURPLE
BORDER = PURPLE
FONT = "Segoe UI, Ubuntu, sans-serif"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!, $cursor: String) {
  user(login: $login) {
    login
    name
    followers { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false,
      orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name
        isPrivate
        stargazerCount
        forkCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
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
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def graphql(token: str, variables: dict) -> dict:
    payload = json.dumps({"query": QUERY, "variables": variables}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql", data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "AlNahianFatin-profile-graph-generator",
        }, method="POST",
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
    # No background rectangle: the README/page background remains visible.
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<title>{esc(title)}</title>',
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="9" fill="none" stroke="{BORDER}" stroke-opacity="0.28"/>',
    ]


def text(x, y, value, size=13, color=MUTED, weight=400, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" '
            f'font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>')


def save_svg(name: str, lines: list[str]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text("\n".join(lines + ["</svg>"]), encoding="utf-8")
    print(f"Generated {path} ({path.stat().st_size} bytes)")


def icon_svg(kind: str, x: float, y: float, color: str = ICON) -> str:
    """Small outline icons used in the compact reference-style stats card."""
    common = f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    paths = {
        "star": f'<path d="M12 2.8l2.8 5.7 6.3.9-4.55 4.45 1.08 6.28L12 17.2l-5.63 2.96 1.08-6.28L2.9 9.4l6.3-.9z" {common}/>',
        "clock": f'<circle cx="12" cy="12" r="9" {common}/><path d="M12 6.5v5.8l4 2.2" {common}/>',
        "pr": f'<circle cx="6" cy="5" r="2" {common}/><circle cx="18" cy="19" r="2" {common}/><circle cx="6" cy="19" r="2" {common}/><path d="M6 7v10M18 17v-4a4 4 0 0 0-4-4H9" {common}/><path d="M11 6l-2 3 2 3" {common}/>',
        "issue": f'<circle cx="12" cy="12" r="9" {common}/><path d="M12 7v6" {common}/><circle cx="12" cy="16.5" r=".8" fill="{color}" stroke="none"/>',
        "repo": f'<path d="M6 3.5h12v17l-6-3.5-6 3.5z" {common}/><path d="M9 7h6" {common}/>',
    }
    return f'<svg x="{x}" y="{y}" width="18" height="18" viewBox="0 0 24 24">{paths[kind]}</svg>'


def github_mark(cx: float, cy: float) -> list[str]:
    """Draw a recognizable GitHub Octocat mark as native SVG geometry.

    The official-style 24x24 silhouette is placed in a nested SVG viewport,
    which avoids transform-order/scaling issues and keeps it centered.
    """
    octocat = (
        "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 "
        "8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04 "
        "-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756 "
        "-1.09-.745.083-.729.083-.729 1.205.084 1.84 1.237 1.84 1.237 "
        "1.07 1.834 2.807 1.304 3.492.997.108-.775.418-1.305.762-1.605 "
        "-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22 "
        "-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23 "
        ".96-.267 1.98-.4 3-.405 1.02.005 2.04.138 3 .405 "
        "2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176 "
        ".765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92 "
        ".435.375.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 "
        "0 .315.21.69.825.57C20.565 21.795 24 17.295 24 12 "
        "c0-6.627-5.373-12-12-12"
    )
    mark_size = 44
    return [
        f'<circle cx="{cx}" cy="{cy}" r="42" fill="none" stroke="{LILAC}" stroke-opacity="0.35" stroke-width="6"/>',
        f'<path d="M {cx} {cy-42} A 42 42 0 0 1 {cx+17} {cy-38}" fill="none" stroke="{PURPLE}" stroke-width="6" stroke-linecap="round"/>',
        f'<circle cx="{cx}" cy="{cy}" r="33" fill="{PURPLE}" fill-opacity="0.12" stroke="{LILAC}" stroke-opacity="0.5"/>',
        f'<svg x="{cx-mark_size/2:.1f}" y="{cy-mark_size/2:.1f}" width="{mark_size}" height="{mark_size}" viewBox="0 0 24 24" aria-label="GitHub Octocat logo"><path d="{octocat}" fill="{PURPLE}"/></svg>',
    ]


def generate_stats(user: dict, repos: list[dict], contrib: dict) -> None:
    """Generate the compact, icon-led card matching the user's reference image."""
    stars = sum(r["stargazerCount"] for r in repos)
    commits = contrib["totalCommitContributions"]
    prs = contrib["totalPullRequestContributions"]
    issues = contrib["totalIssueContributions"]
    contributed_repos = contrib.get("totalRepositoriesWithContributedCommits", 0)

    lines = svg_start(467, 195, f"{USERNAME}'s GitHub Stats")
    display_name = user.get("name") or user.get("login") or USERNAME
    lines.append(text(24, 35, f"{display_name}'s GitHub Stats", 18, PURPLE, 700))
    rows = [
        ("star", "Total Stars Earned:", stars),
        ("clock", "Total Commits (last year):", commits),
        ("pr", "Total PRs:", prs),
        ("issue", "Total Issues:", issues),
        ("repo", "Contributed to (last year):", contributed_repos),
    ]
    for i, (kind, label, value) in enumerate(rows):
        y = 68 + i * 26
        lines.append(icon_svg(kind, 24, y - 14))
        lines.append(text(50, y, label, 13, LILAC, 650))
        lines.append(text(255, y, f"{value:,}", 13, PURPLE, 700, "end"))
    lines.extend(github_mark(380, 111))
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
        palette = [PURPLE, LILAC, YELLOW, "#58A6FF", "#3FB950", "#F78166", "#D2A8FF", "#8B949E"]
        x, y, bar_w = 22, 63, 451
        cursor = x
        for idx, (_, amount) in enumerate(ranked):
            width = bar_w * amount / total_bytes if total_bytes else 0
            lines.append(f'<rect x="{cursor:.2f}" y="{y}" width="{max(width, 1):.2f}" height="10" fill="{palette[idx % len(palette)]}"/>')
            cursor += width
        for idx, (lang, amount) in enumerate(ranked):
            row_y = 103 + idx * 24
            pct = amount / total_bytes * 100 if total_bytes else 0
            lines.append(f'<circle cx="28" cy="{row_y-4}" r="4" fill="{palette[idx % len(palette)]}"/>')
            lines.append(text(42, row_y, lang, 11, LILAC, 500))
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
    palette = ["#8957E5", "#5D359A", "#7040C0", PURPLE, LILAC]
    lines = svg_start(960, 225, f"{USERNAME} Contribution Activity")
    lines.append(text(22, 31, "Contribution Activity", 18, PURPLE, 700))
    lines.append(text(938, 30, f"{contrib['contributionCalendar']['totalContributions']:,} contributions in the last year", 10, MUTED, 400, "end"))
    left, top, cell, gap = 24, 62, 10, 3
    first_date = date.fromisoformat(days[0]["date"]) if days else date.today()
    first_week_start = first_date - timedelta(days=first_date.weekday())
    for day in days:
        dt = date.fromisoformat(day["date"])
        week_index = (dt - first_week_start).days // 7
        weekday = dt.weekday()
        count = day["contributionCount"]
        if count == 0:
            color, opacity = PURPLE, "0.10"
        elif max_count and count / max_count <= .25:
            color, opacity = palette[1], "0.55"
        elif max_count and count / max_count <= .5:
            color, opacity = palette[2], "0.72"
        elif max_count and count / max_count <= .75:
            color, opacity = palette[3], "0.88"
        else:
            color, opacity = palette[4], "1"
        x, y = left + week_index * (cell + gap), top + weekday * (cell + gap)
        lines.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}" fill-opacity="{opacity}" stroke="{PURPLE}" stroke-opacity="0.12"><title>{esc(day["date"])}: {count} contributions</title></rect>')
    lines.append(text(24, 190, "Less", 9, MUTED))
    for i, color in enumerate(palette):
        lines.append(f'<rect x="{55 + i * 13}" y="181" width="10" height="10" rx="2" fill="{color}"/>')
    lines.append(text(127, 190, "More", 9, MUTED))
    lines.append(text(938, 211, "Daily contributions · GitHub contribution calendar", 9, MUTED, 400, "end"))
    save_svg("activity.svg", lines)


# Custom, transparent milestone thresholds. These are not GitHub-issued badges.
MILESTONE_THRESHOLDS = {
    "Commits (last year)": [10, 50, 100, 250, 500, 1000],
    "Contributions (last year)": [100, 250, 500, 1000, 2500, 5000],
    "Pull requests (last year)": [1, 5, 10, 25, 50, 100],
    "Issues (last year)": [1, 5, 10, 25, 50, 100],
    "Stars earned": [1, 5, 10, 25, 50, 100, 250, 500],
    "Repositories owned": [1, 5, 10, 25, 50, 100],
    "Followers": [1, 5, 10, 25, 50, 100, 250, 500],
    "Forks received": [1, 5, 10, 25, 50, 100],
    "Repositories contributed to": [1, 5, 10, 25, 50, 100],
}


def milestone_card(x: int, y: int, width: int, height: int, label: str, value: int, thresholds: list[int], accent: str) -> list[str]:
    out = [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="9" fill="none" stroke="{PURPLE}" stroke-opacity="0.30"/>']
    out.append(text(x + 13, y + 23, label, 11, LILAC, 600))
    out.append(text(x + width - 13, y + 24, f"{value:,}", 19, accent, 700, "end"))
    reached = [t for t in thresholds if value >= t]
    next_target = next((t for t in thresholds if value < t), None)
    previous = reached[-1] if reached else 0
    if next_target is None:
        progress = 1.0
        progress_label = "All listed milestones reached"
    else:
        span = max(next_target - previous, 1)
        progress = min(max((value - previous) / span, 0), 1)
        progress_label = f"Next: {next_target:,}"
    bar_x, bar_y, bar_w = x + 13, y + 39, width - 26
    out.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="7" rx="3.5" fill="{PURPLE}" fill-opacity="0.12"/>')
    out.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w * progress:.2f}" height="7" rx="3.5" fill="{accent}"/>')
    reached_text = "Reached: " + (" · ".join(f"{t:,}" for t in reached) if reached else "none yet")
    out.append(text(x + 13, y + 65, reached_text, 9, MUTED, 400))
    out.append(text(x + width - 13, y + 85, progress_label, 9, accent, 600, "end"))
    return out


def generate_milestones(user: dict, repos: list[dict], contrib: dict) -> None:
    """Show custom measurable milestone tiers and progress toward the next tier."""
    metrics = {
        "Commits (last year)": contrib["totalCommitContributions"],
        "Contributions (last year)": contrib["contributionCalendar"]["totalContributions"],
        "Pull requests (last year)": contrib["totalPullRequestContributions"],
        "Issues (last year)": contrib["totalIssueContributions"],
        "Stars earned": sum(r["stargazerCount"] for r in repos),
        "Repositories owned": len(repos),
        "Followers": user["followers"]["totalCount"],
        "Forks received": sum(r["forkCount"] for r in repos),
        "Repositories contributed to": contrib.get("totalRepositoriesWithContributedCommits", 0),
    }
    accents = [YELLOW, PURPLE, LILAC, PURPLE, YELLOW, LILAC, PURPLE, YELLOW, LILAC]
    width, height = 720, 405
    lines = svg_start(width, height, f"{USERNAME} GitHub Milestones")
    lines.append(text(20, 31, "GitHub Milestones", 19, PURPLE, 700))
    lines.append(text(700, 29, "Achievement tiers & progress", 10, MUTED, 400, "end"))
    card_w, card_h = 220, 100
    for i, (label, value) in enumerate(metrics.items()):
        col, row = i % 3, i // 3
        x, y = 20 + col * 233, 47 + row * 115
        lines.extend(milestone_card(x, y, card_w, card_h, label, value, MILESTONE_THRESHOLDS[label], accents[i]))
    lines.append(text(20, 393, "Custom thresholds based on GitHub API data · Not official GitHub achievement badges", 9, MUTED))
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
