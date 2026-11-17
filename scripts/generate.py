"""Generate the SVG cards used by the profile README.

Runs in GitHub Actions with the built-in GITHUB_TOKEN (no secrets, no third-party
services), so the images never break because an external stats API is down.
Stdlib only.

    python scripts/generate.py            # fetch live data, then render
    python scripts/generate.py --offline  # render from assets/data.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

USER = "shadow-lo"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "generated"
DATA = ROOT / "assets" / "data.json"
SKIP_REPOS = {USER}  # the profile repo itself

PROJECTS = [
    {
        "repo": "intent-check",
        "icon": "🎯",
        "kind": "Claude Code skill",
        "en": "Checks finished AI work against your original request, with evidence, and fixes what doesn't match.",
        "tr": "Biten yapay zeka işini ilk isteğinle kanıtlı şekilde karşılaştırır, uymayanı düzeltir.",
    },
    {
        "repo": "token-budget",
        "icon": "🧮",
        "kind": "Python CLI",
        "en": "Scan a folder, count its tokens, and find out if it fits your model's context window.",
        "tr": "Bir klasörü tarar, token sayar ve modelin bağlam penceresine sığıp sığmadığını söyler.",
    },
    {
        "repo": "envdiff",
        "icon": "🔐",
        "kind": "Python CLI",
        "en": "Keeps .env and .env.example in sync and catches real secrets, without printing a value.",
        "tr": ".env ile .env.example'ı senkron tutar, gerçek sırları değer göstermeden yakalar.",
    },
]

LANG_COLORS = {
    "C#": "#9b4dff", "Dart": "#4fc3f7", "Python": "#ffd166", "TypeScript": "#3b82f6",
    "JavaScript": "#f7df1e", "HTML": "#ff7a59", "CSS": "#c084fc", "Shell": "#7ee787",
    "Kotlin": "#b388ff", "Swift": "#ff8a65", "C++": "#f06292", "Java": "#ffab40",
    "PowerShell": "#64b5f6", "Go": "#4dd0e1", "Rust": "#ffb199",
}
FALLBACK_COLORS = ["#a970ff", "#d16bff", "#7dd3fc", "#f9a8d4", "#fcd34d", "#86efac"]

T = {
    "en": {
        "overview": "Overview", "contrib": "Total contributions", "commits": "Commits",
        "repos": "Public repos", "stars": "Stars earned", "prs": "Pull requests",
        "streak": "Current streak", "longest": "Longest streak", "days": "days",
        "since": "since", "langs": "Most used languages",
        "updated": "updated",
    },
    "tr": {
        "overview": "Genel Bakış", "contrib": "Toplam katkı", "commits": "Commit",
        "repos": "Açık repo", "stars": "Kazanılan yıldız", "prs": "Pull request",
        "streak": "Güncel seri", "longest": "En uzun seri", "days": "gün",
        "since": "başlangıç", "langs": "En çok kullanılan diller",
        "updated": "güncellendi",
    },
}

# Night / purple-moon palette (matches the avatar)
BG_A, BG_B = "#0e0a24", "#1d1046"
BORDER = "#3b2a78"
TEXT, MUTED = "#ece8ff", "#a59bd0"
ACCENT, ACCENT2, MOON = "#a970ff", "#d16bff", "#f3f0ff"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, 'Courier New', monospace"


# --------------------------------------------------------------------- data

def _request(url: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-readme-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _graphql(token: str, query: str, variables: dict) -> dict:
    res = _request("https://api.github.com/graphql", token, {"query": query, "variables": variables})
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


def fetch(token: str) -> dict:
    api = "https://api.github.com"
    repos, page = [], 1
    while True:
        batch = _request(f"{api}/users/{USER}/repos?per_page=100&type=owner&page={page}", token)
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"] and r["name"] not in SKIP_REPOS]

    langs: dict[str, int] = {}
    for r in own:
        for name, size in _request(f"{api}/repos/{USER}/{r['name']}/languages", token).items():
            langs[name] = langs.get(name, 0) + size

    by_name = {r["name"]: r for r in repos}
    projects = {}
    for p in PROJECTS:
        r = by_name.get(p["repo"])
        projects[p["repo"]] = (
            {"exists": True, "stars": r["stargazers_count"], "forks": r["forks_count"],
             "language": r["language"]} if r else {"exists": False}
        )

    years = _graphql(token, "query($u:String!){user(login:$u){createdAt contributionsCollection{contributionYears}}}",
                     {"u": USER})["user"]
    created = years["createdAt"][:10]
    total, days, commits, prs = 0, {}, 0, 0
    this_year = dt.date.today().year
    q = ("query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){contributionsCollection(from:$f,to:$t){"
         "totalCommitContributions totalPullRequestContributions "
         "contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}")
    for y in years["contributionsCollection"]["contributionYears"]:
        c = _graphql(token, q, {"u": USER, "f": f"{y}-01-01T00:00:00Z", "t": f"{y}-12-31T23:59:59Z"})
        c = c["user"]["contributionsCollection"]
        total += c["contributionCalendar"]["totalContributions"]
        prs += c["totalPullRequestContributions"]
        if y == this_year:
            commits = c["totalCommitContributions"]
        for w in c["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    return {
        "updated": dt.date.today().isoformat(),
        "created": created,
        "repos": len(own),
        "stars": sum(r["stargazers_count"] for r in own),
        "total": total,
        "commits_year": commits,
        "prs": prs,
        "days": days,
        "langs": langs,
        "projects": projects,
    }


def streaks(days: dict[str, int], today: dt.date) -> tuple[int, int]:
    active = {d for d, n in days.items() if n > 0}
    cur, day = 0, today
    if day.isoformat() not in active:  # today is not over yet
        day -= dt.timedelta(days=1)
    while day.isoformat() in active:
        cur += 1
        day -= dt.timedelta(days=1)
    longest = run = 0
    prev = None
    for d in sorted(active):
        dd = dt.date.fromisoformat(d)
        run = run + 1 if prev and (dd - prev).days == 1 else 1
        longest = max(longest, run)
        prev = dd
    return cur, longest


# --------------------------------------------------------------------- svg

def _defs(uid: str) -> str:
    return f"""<defs>
  <linearGradient id="bg{uid}" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{BG_A}"/><stop offset="1" stop-color="{BG_B}"/>
  </linearGradient>
  <linearGradient id="ac{uid}" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT2}"/>
  </linearGradient>
  <filter id="glow{uid}" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>"""


def _frame(w: int, h: int, uid: str, body: str, title: str) -> str:
    stars = "".join(
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{MOON}" opacity="{o}"/>'
        for x, y, r, o in [(w - 40, 22, 1.2, .7), (w - 90, 40, .8, .5), (w - 150, 18, 1, .4),
                           (w - 60, h - 30, .8, .35), (40, h - 22, .9, .3)]
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
{_defs(uid)}
<style>
  .t{{font:600 18px {FONT};fill:{TEXT}}}
  .l{{font:400 13px {FONT};fill:{MUTED}}}
  .v{{font:700 15px {MONO};fill:{TEXT}}}
  .big{{font:800 34px {FONT};fill:{MOON}}}
  .s{{font:400 11px {FONT};fill:{MUTED}}}
</style>
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="url(#bg{uid})" stroke="{BORDER}"/>
{stars}
{body}
</svg>
"""


def _fmt_date(iso: str, lang: str) -> str:
    d = dt.date.fromisoformat(iso)
    months = {
        "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        "tr": "Oca Şub Mar Nis May Haz Tem Ağu Eyl Eki Kas Ara",
    }[lang].split()
    return f"{d.day} {months[d.month - 1]} {d.year}"


def overview_svg(data: dict, lang: str) -> str:
    t = T[lang]
    cur, longest = streaks(data["days"], dt.date.fromisoformat(data["updated"]))
    rows = [
        ("✦", t["contrib"], data["total"]),
        ("◆", f'{t["commits"]} ({data["updated"][:4]})', data["commits_year"]),
        ("❖", t["repos"], data["repos"]),
        ("★", t["stars"], data["stars"]),
        ("⇄", t["prs"], data["prs"]),
    ]
    body = [f'<text x="28" y="40" class="t">🌙 {escape(t["overview"])}</text>',
            f'<rect x="28" y="52" width="46" height="3" rx="1.5" fill="url(#acov{lang})"/>']
    for i, (ic, label, val) in enumerate(rows):
        y = 86 + i * 28
        body.append(
            f'<g class="fade" style="animation-delay:{i * 120}ms">'
            f'<text x="30" y="{y}" class="l" fill="{ACCENT}" style="fill:{ACCENT}">{ic}</text>'
            f'<text x="52" y="{y}" class="l">{escape(label)}</text>'
            f'<text x="330" y="{y}" class="v" text-anchor="end">{val:,}</text></g>'
        )
    # streak ring
    cx, cy, r = 515, 112, 52
    circ = 2 * 3.14159 * r
    frac = min(cur / max(longest, 1), 1) if longest else 0
    body.append(f"""
<line x1="370" y1="40" x2="370" y2="206" stroke="{BORDER}"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-width="8"/>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#acov{lang})" stroke-width="8" stroke-linecap="round"
  stroke-dasharray="{circ * frac:.1f} {circ:.1f}" transform="rotate(-90 {cx} {cy})" filter="url(#glowov{lang})"/>
<text x="{cx}" y="{cy + 12}" class="big" text-anchor="middle">{cur}</text>
<text x="{cx}" y="{cy + r + 30}" class="l" text-anchor="middle" style="font-weight:600;fill:{TEXT}">🔥 {escape(t["streak"])}</text>
<text x="{cx}" y="{cy + r + 47}" class="s" text-anchor="middle">{escape(t["longest"])}: {longest} {escape(t["days"])}</text>
<text x="{cx}" y="32" class="s" text-anchor="middle">{escape(t["since"])} {_fmt_date(data["created"], lang)}</text>
""")
    return _frame(640, 240, f"ov{lang}", "\n".join(body), t["overview"])


def langs_svg(data: dict, lang: str) -> str:
    t = T[lang]
    items = sorted(data["langs"].items(), key=lambda kv: -kv[1])[:6]
    total = sum(v for _, v in items) or 1
    w, x0, bar_w = 640, 28, 584
    body = [f'<text x="28" y="40" class="t">💻 {escape(t["langs"])}</text>',
            f'<rect x="28" y="52" width="46" height="3" rx="1.5" fill="url(#aclg{lang})"/>',
            f'<clipPath id="barclip{lang}"><rect x="{x0}" y="72" width="{bar_w}" height="12" rx="6"/></clipPath>',
            f'<g clip-path="url(#barclip{lang})"><rect x="{x0}" y="72" width="{bar_w}" height="12" fill="{BORDER}"/>']
    x = x0
    for i, (name, v) in enumerate(items):
        seg = bar_w * v / total
        color = LANG_COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        body.append(f'<rect x="{x:.1f}" y="72" width="{seg:.1f}" height="12" fill="{color}"/>')
        x += seg
    body.append("</g>")
    for i, (name, v) in enumerate(items):
        col, row = i % 3, i // 3
        lx, ly = 30 + col * 200, 116 + row * 30
        color = LANG_COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        body.append(
            f'<g class="fade" style="animation-delay:{i * 100}ms">'
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 18}" y="{ly}" class="l" style="fill:{TEXT}">{escape(name)}'
            f'<tspan dx="8" style="font-size:11px;fill:{MUTED}">{100 * v / total:.1f}%</tspan></text></g>'
        )
    h = 116 + ((len(items) + 2) // 3) * 30
    if not items:
        body.append(f'<text x="30" y="116" class="l">—</text>')
        h = 140
    return _frame(w, h, f"lg{lang}", "\n".join(body), t["langs"])


def _wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def project_svg(p: dict, info: dict, lang: str) -> str:
    lines = _wrap(p[lang], 46)[:3]
    desc = "".join(f'<tspan x="24" dy="{0 if i == 0 else 19}">{escape(s)}</tspan>' for i, s in enumerate(lines))
    foot = (f'<circle cx="30" cy="149" r="5" fill="{LANG_COLORS.get(info.get("language") or "", ACCENT)}"/>'
            f'<text x="42" y="153" class="s" style="fill:{TEXT}">{escape(info.get("language") or p["kind"])}</text>'
            f'<text x="140" y="153" class="s">★ {info.get("stars", 0)}</text>'
            f'<text x="190" y="153" class="s">⑂ {info.get("forks", 0)}</text>')
    body = f"""
<text x="24" y="42" class="t" style="font-size:19px">{p["icon"]} <tspan style="fill:{MOON}">{escape(p["repo"])}</tspan></text>
<text x="396" y="40" class="s" text-anchor="end" style="fill:{ACCENT2}">{escape(p["kind"])}</text>
<rect x="24" y="54" width="40" height="3" rx="1.5" fill="url(#acpj{p['repo']}{lang})"/>
<text y="84" class="l">{desc}</text>
{foot}
"""
    svg = _frame(420, 176, f"pj{p['repo']}{lang}", body, f"{p['repo']}: {p[lang]}")
    return svg


def render(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "tr"):
        (OUT / f"overview-{lang}.svg").write_text(overview_svg(data, lang), encoding="utf-8")
        (OUT / f"languages-{lang}.svg").write_text(langs_svg(data, lang), encoding="utf-8")
        for p in PROJECTS:
            info = data["projects"].get(p["repo"], {"exists": False})
            if not info.get("exists"):  # only published repos are shown
                continue
            (OUT / f"project-{p['repo']}-{lang}.svg").write_text(project_svg(p, info, lang), encoding="utf-8")


def main() -> int:
    if "--offline" in sys.argv:
        data = json.loads(DATA.read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("GITHUB_TOKEN is not set (use --offline to render cached data)", file=sys.stderr)
            return 2
        data = fetch(token)
        DATA.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    render(data)
    print(f"rendered cards for {USER} ({data['updated']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
