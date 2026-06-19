#!/usr/bin/env python3
"""Static site builder for x4gen7.github.io.

Renders README.md into index.html and each Weekly Summary markdown into its
own page, plus a hub. Self-contained: no external deps, no other repo needed.

The README is generated with a stable structure, so this parses its known
sections (Daily Timeline, Daily Summary, Weekly Progress, Weekly Insights,
Monthly Progress, Study Summary) and renders each as a scannable visual block:
color-coded day cards, real progress bars, and category bar charts.

Standalone output (CSS embedded, no server, no dependencies). Run:
    python3 render_readme.py --open
"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime
from pathlib import Path

LOW_MIN = 135   # 2h15m
HIGH_MIN = 270  # 4h30m


# ----------------------------- parsing helpers -----------------------------

def hm_to_min(text: str) -> int | None:
    m = re.search(r"(\d+)\s*h\s*(\d+)\s*m", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def esc(text: str) -> str:
    return html.escape(text)


def split_sections(md: str) -> list[tuple[str, list[str]]]:
    """Split into (h2-title, body-lines) sections."""
    sections: list[tuple[str, list[str]]] = []
    title = ""
    body: list[str] = []
    for line in md.splitlines():
        m = re.match(r"##\s+(?!#)(.*)", line)
        if m:
            if title or body:
                sections.append((title, body))
            title = m.group(1).strip()
            body = []
        else:
            body.append(line)
    if title or body:
        sections.append((title, body))
    return sections


def strip_emoji_key(title: str) -> str:
    return re.sub(r"[^\w ]+", "", title).strip().lower()


# ----------------------------- visual builders -----------------------------

def color_for(minutes: int) -> str:
    if minutes >= HIGH_MIN:
        return "var(--dark)"
    if minutes >= LOW_MIN:
        t = (minutes - LOW_MIN) / (HIGH_MIN - LOW_MIN)
        return mix("#3ddc84", "#14532d", t)
    t = max(0.0, min(1.0, minutes / LOW_MIN))
    return mix("#ef6461", "#3ddc84", t)


def mix(a: str, b: str, t: float) -> str:
    ah = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    bh = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ah, bh))


def bar(pct: float, ok_at: float = 100.0) -> str:
    pct = max(0.0, pct)
    cls = "fill ok" if pct >= ok_at else "fill"
    return f'<span class="track"><span class="{cls}" style="width:{min(100, pct):.0f}%"></span></span>'


def render_daily_timeline(body: list[str]) -> str:
    text = "\n".join(body)
    weekly_target = ""
    mt = re.search(r"Weekly target:\*\*\s*([\dhm: ]+)", text)
    if mt:
        weekly_target = mt.group(1).strip()

    cards = []
    # Each day: ### DATE (Weekday) ... bullets ... Today/Weekly/Remaining
    blocks = re.split(r"^###\s+", text, flags=re.M)[1:]
    for blk in blocks:
        lines = blk.splitlines()
        header = lines[0].strip()
        cats = []
        for ln in lines[1:]:
            bm = re.match(r"-\s+(.*?):\s*(.*)", ln.strip())
            if bm:
                cats.append((bm.group(1), bm.group(2)))
        today = re.search(r"Today:\*\*\s*([\dhm: ]+)", blk)
        prog = re.search(r"Weekly progress:\*\*\s*([\dhm: ]+)/\s*([\dhm: ]+)", blk)
        today_str = today.group(1).strip() if today else "0h 00m"
        today_min = hm_to_min(today_str) or 0
        pct = 0.0
        if prog:
            cur = hm_to_min(prog.group(1)) or 0
            tgt = hm_to_min(prog.group(2)) or 1
            pct = cur / tgt * 100
        cat_rows = "".join(
            f'<div class="catline"><span>{esc(c)}</span><b>{esc(v)}</b></div>'
            for c, v in cats
        )
        cards.append(
            f'''<div class="day">
              <div class="day-head">{esc(header)}</div>
              <div class="day-total" style="color:{color_for(today_min)}">{esc(today_str)}</div>
              {bar(pct)}
              <div class="cats">{cat_rows}</div>
            </div>'''
        )
    target_chip = (
        f'<span class="chip">Weekly target {esc(weekly_target)}</span>' if weekly_target else ""
    )
    return f'<div class="targetbar">{target_chip}</div><div class="day-grid">{"".join(cards)}</div>'


def render_daily_summary(body: list[str]) -> str:
    items = []
    for ln in body:
        m = re.match(r"-\s+\*\*(.*?)\*\*\s*->\s*(.*)", ln.strip())
        if m:
            mins = hm_to_min(m.group(2)) or 0
            items.append((m.group(1), m.group(2).strip(), mins))
    if not items:
        return ""
    cells = "".join(
        f'''<div class="sumcell">
          <div class="dot" style="background:{color_for(mn)}"></div>
          <div class="sd">{esc(d[5:])}</div>
          <div class="sh">{esc(v)}</div>
        </div>'''
        for d, v, mn in items
    )
    return f'<div class="sumrow">{cells}</div>'


def render_weekly_progress(body: list[str]) -> str:
    text = "\n".join(body)
    cards = []
    blocks = re.split(r"^###\s+", text, flags=re.M)[1:]
    for blk in blocks:
        lines = blk.splitlines()
        name = lines[0].strip()
        fields = {}
        for ln in lines[1:]:
            m = re.match(r"-\s+\*\*(.*?):\*\*\s*(.*)", ln.strip())
            if m:
                fields[m.group(1)] = m.group(2).strip()
        total = fields.get("Total", "")
        pm = re.search(r"(\d+)%", fields.get("Progress", ""))
        pct = float(pm.group(1)) if pm else 0.0
        trend = fields.get("Trend", "")
        tcls = "up" if "↑" in trend else "down" if "↓" in trend else "flat"
        status = fields.get("Status", "")
        top = fields.get("Top category", "")
        off = fields.get("Off days", "0")
        cards.append(
            f'''<div class="wk">
              <div class="wk-top"><b>{esc(name)}</b><span class="pct">{pct:.0f}%</span></div>
              <div class="wk-range">{esc(fields.get("Range",""))}</div>
              {bar(pct)}
              <div class="wk-total">{esc(total)}</div>
              <div class="wk-meta">
                <span class="trend {tcls}">{esc(trend)}</span>
                <span>{esc(status)}</span>
              </div>
              <div class="wk-foot"><span>Top: {esc(top)}</span><span>Off: {esc(off)}</span></div>
            </div>'''
        )
    return f'<div class="wk-grid">{"".join(cards)}</div>'


def render_kv_and_subsections(body: list[str]) -> str:
    """Generic: render **Key:** value lines as stat chips, bullets, ### subheads."""
    out = []
    in_list = False

    def close():
        nonlocal in_list
        if in_list:
            out.append("</div>")
            in_list = False

    for ln in body:
        s = ln.strip()
        if not s or re.fullmatch(r"[-*=_]{3,}", s):
            continue
        sub = re.match(r"###\s+(.*)", s)
        if sub:
            close()
            out.append(f"<h3>{esc(sub.group(1))}</h3>")
            continue
        m = re.match(r"-\s+\*\*(.*?):\*\*\s*(.*)", s)
        if m:
            if not in_list:
                out.append('<div class="kv">')
                in_list = True
            key, val = m.group(1), m.group(2)
            out.append(f'<div class="kvrow"><span>{esc(key)}</span><b>{render_inline_bar(key, val)}</b></div>')
            continue
        m2 = re.match(r"-\s+(.*)", s)
        if m2:
            if not in_list:
                out.append('<div class="kv">')
                in_list = True
            out.append(f'<div class="kvrow"><span>{esc(m2.group(1))}</span></div>')
            continue
        close()
        out.append(f"<p>{esc(re.sub(r'\\*\\*','',s))}</p>")
    close()
    return "\n".join(out)


def render_inline_bar(key: str, val: str) -> str:
    return esc(re.sub(r"\*\*", "", val))


def render_hours_chart(body: list[str], date_label: bool = True) -> str:
    rows = []
    for ln in body:
        m = re.match(r"-\s+\*\*(.*?):?\*\*\s*->?\s*(.*)", ln.strip()) or \
            re.match(r"-\s+\*\*(.*?):\*\*\s*(.*)", ln.strip())
        if m:
            mins = hm_to_min(m.group(2))
            if mins is not None:
                rows.append((m.group(1), m.group(2).strip(), mins))
    if not rows:
        return ""
    mx = max(mn for _, _, mn in rows) or 1
    out = []
    for label, val, mn in rows:
        out.append(
            f'''<div class="chrow">
              <span class="chlabel">{esc(label)}</span>
              <span class="chbar"><span style="width:{mn/mx*100:.0f}%"></span></span>
              <span class="chval">{esc(val)}</span>
            </div>'''
        )
    return f'<div class="chart">{"".join(out)}</div>'


# ----------------------------- assembly -----------------------------

def build_body(md: str) -> tuple[str, list[tuple[str, str]], dict]:
    sections = split_sections(md)
    blocks = []
    nav = []
    headline = {}
    idx = 0

    for title, body in sections:
        if not title and not any(l.strip() for l in body):
            continue
        key = strip_emoji_key(title)
        anchor = f"sec{idx}"
        idx += 1
        nav.append((anchor, title or "Intro"))

        if "daily timeline" in key:
            inner = render_daily_timeline(body)
        elif "daily summary" in key:
            inner = render_daily_summary(body)
        elif "weekly progress" in key:
            inner = render_weekly_progress(body)
        elif "monthly progress" in key:
            inner = render_hours_chart(body)
            # capture latest month for headline? skip
        elif "study summary" in key:
            inner = render_study_summary(body, headline)
        elif "weekly insights" in key:
            inner = render_kv_and_subsections(body)
        else:
            inner = render_kv_and_subsections(body)

        blocks.append(
            f'<section id="{anchor}"><h2>{esc(title) or "Overview"}</h2>{inner}</section>'
        )

    return "\n".join(blocks), nav, headline


def render_study_summary(body: list[str], headline: dict) -> str:
    text = "\n".join(body)
    tot = re.search(r"Total study time:\*\*\s*\*\*([\dhm: ]+)\*\*", text)
    if tot:
        headline["total"] = tot.group(1).strip()
    # Category Totals chart sits after a ### Category Totals subhead.
    parts = re.split(r"^###\s+", text, flags=re.M)
    out = []
    for part in parts:
        lines = part.splitlines()
        head = lines[0].strip() if lines else ""
        rest = lines[1:] if lines else []
        if "Category Totals" in head:
            out.append("<h3>Category Totals</h3>")
            out.append(render_hours_chart(rest))
        elif "Overall Total" in head:
            out.append("<h3>Overall Total</h3>")
            out.append(render_kv_and_subsections(rest))
        elif head:
            out.append(render_kv_and_subsections(lines))
    return "\n".join(out)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Study Logs</title>
<style>
  :root{
    --bg:#0f1419;--panel:#161b22;--panel2:#1b222c;--border:#283341;
    --text:#dbe4ec;--dim:#8b97a3;--accent:#58c4f0;--green:#3ddc84;
    --dark:#14532d;--red:#ef6461;--track:#0e1620;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font:15px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}
  a{color:inherit;text-decoration:none}
  nav{position:sticky;top:0;z-index:5;background:rgba(15,20,25,.9);
    backdrop-filter:blur(8px);border-bottom:1px solid var(--border);
    padding:12px 20px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  nav .brand{font-weight:700;margin-right:8px}
  nav .headline{margin-left:auto;color:var(--green);font-weight:700}
  nav a.jump{font-size:12px;color:var(--dim);padding:4px 10px;border:1px solid var(--border);
    border-radius:999px}
  nav a.jump:hover{color:var(--text);border-color:var(--accent)}
  .wrap{max-width:1080px;margin:0 auto;padding:24px 20px 80px}
  section{margin:30px 0}
  h2{font-size:18px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--border)}
  h3{font-size:14px;color:var(--accent);margin:18px 0 10px;text-transform:uppercase;letter-spacing:.5px}
  .targetbar{margin-bottom:12px}
  .chip{display:inline-block;font-size:12px;color:var(--dim);background:var(--panel);
    border:1px solid var(--border);border-radius:999px;padding:4px 12px}
  /* day grid */
  .day-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
  .day{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
  .day-head{font-size:12px;color:var(--dim);margin-bottom:6px}
  .day-total{font-size:26px;font-weight:800;letter-spacing:-.5px}
  .cats{margin-top:10px}
  .catline{display:flex;justify-content:space-between;font-size:12px;color:var(--dim);padding:2px 0}
  .catline b{color:var(--text);font-weight:600}
  /* progress track */
  .track{display:block;height:6px;background:var(--track);border-radius:6px;overflow:hidden;margin:8px 0}
  .track .fill{display:block;height:100%;background:var(--accent);border-radius:6px}
  .track .fill.ok{background:var(--green)}
  /* daily summary strip */
  .sumrow{display:flex;gap:8px;flex-wrap:wrap}
  .sumcell{background:var(--panel);border:1px solid var(--border);border-radius:10px;
    padding:10px 14px;text-align:center;min-width:84px}
  .sumcell .dot{width:100%;height:6px;border-radius:4px;margin-bottom:8px}
  .sumcell .sd{font-size:12px;color:var(--dim)}
  .sumcell .sh{font-weight:700;font-size:15px}
  /* weekly cards */
  .wk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
  .wk{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
  .wk-top{display:flex;justify-content:space-between;align-items:baseline}
  .wk-top .pct{font-weight:800;color:var(--accent)}
  .wk-range{font-size:12px;color:var(--dim);margin:2px 0 4px}
  .wk-total{font-size:18px;font-weight:700;margin-top:6px}
  .wk-meta{display:flex;flex-direction:column;gap:2px;font-size:12px;color:var(--dim);margin-top:6px}
  .trend.up{color:var(--green)}.trend.down{color:var(--red)}.trend.flat{color:var(--dim)}
  .wk-foot{display:flex;justify-content:space-between;font-size:11px;color:var(--dim);
    margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}
  /* generic kv + chart */
  .kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:4px 18px}
  .kvrow{display:flex;justify-content:space-between;gap:10px;font-size:13px;
    padding:5px 0;border-bottom:1px solid var(--border)}
  .kvrow span{color:var(--dim)}.kvrow b{color:var(--text);font-weight:600;text-align:right}
  .chart{display:flex;flex-direction:column;gap:6px}
  .chrow{display:grid;grid-template-columns:200px 1fr 80px;align-items:center;gap:10px;font-size:13px}
  .chlabel{color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .chbar{background:var(--track);border-radius:5px;height:10px;overflow:hidden}
  .chbar span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--green));border-radius:5px}
  .chval{text-align:right;font-variant-numeric:tabular-nums}
  p{margin:6px 0}
  .meta{color:var(--dim);font-size:12px;text-align:center;margin-top:30px}
  @media(max-width:560px){.chrow{grid-template-columns:120px 1fr 64px}}
</style>
</head>
<body>
<nav>
  <span class="brand">__BRAND__</span>
  __BACK__
  __NAV__
  <span class="headline">__HEADLINE__</span>
</nav>
<div class="wrap">
__BODY__
<p class="meta">__SOURCE__ — __TS__</p>
</div>
</body>
</html>
"""


def render_markdown_to_page(
    md: str,
    brand: str = "Study Logs",
    source: str = "Rendered from README.md",
    back_href: str | None = None,
    back_label: str = "← Home",
) -> str:
    """Convert a markdown string into a full standalone HTML page."""
    body_html, nav, headline = build_body(md)
    nav_html = ""  # section jump-links removed
    headline_html = (
        f'All-time {esc(headline["total"])}' if headline.get("total") else ""
    )
    back_html = (
        f'<a class="jump" href="{esc(back_href)}">{esc(back_label)}</a>'
        if back_href
        else ""
    )
    return (
        TEMPLATE.replace("__BRAND__", esc(brand))
        .replace("__BACK__", back_html)
        .replace("__NAV__", nav_html)
        .replace("__HEADLINE__", headline_html)
        .replace("__BODY__", body_html)
        .replace("__SOURCE__", esc(source))
        .replace("__TS__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )


def render_file(
    src: Path,
    out: Path,
    brand: str = "Study Logs",
    back_href: str | None = None,
) -> None:
    page = render_markdown_to_page(
        src.read_text(encoding="utf-8"),
        brand=brand,
        source=f"Rendered from {src.name}",
        back_href=back_href,
    )
    out.write_text(page, encoding="utf-8")
    print(f"[+] wrote {out}")


# ----------------------------- weekly summary pages -----------------------------

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def folder_label(name: str) -> tuple[str, tuple[int, int]]:
    """'6:26' or '06:2026' -> ('June 2026', (2026, 6)) for display + sorting."""
    nums = re.findall(r"\d+", name)
    if len(nums) >= 2:
        month, year = int(nums[-2]), int(nums[-1])
        if year < 100:
            year += 2000
        return f"{MONTHS.get(month, month)} {year}", (year, month)
    return name, (0, 0)


def hub_page(entries: list[tuple[str, str]]) -> str:
    cards = "".join(
        f'<a class="hubcard" href="{esc(href)}"><b>{esc(label)}</b>'
        f'<span>Weekly summary &rarr;</span></a>'
        for label, href in entries
    )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Weekly Summaries</title><style>'
        ':root{--bg:#0f1419;--panel:#161b22;--border:#283341;--text:#dbe4ec;--dim:#8b97a3;--accent:#58c4f0}'
        '*{box-sizing:border-box}'
        'body{margin:0;background:var(--bg);color:var(--text);'
        'font:15px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}'
        'a{color:inherit;text-decoration:none}'
        'nav{position:sticky;top:0;background:rgba(15,20,25,.9);backdrop-filter:blur(8px);'
        'border-bottom:1px solid var(--border);padding:12px 20px;display:flex;gap:10px;align-items:center}'
        'nav .brand{font-weight:700}'
        'nav a.jump{font-size:12px;color:var(--dim);padding:4px 10px;border:1px solid var(--border);border-radius:999px}'
        'nav a.jump:hover{color:var(--text);border-color:var(--accent)}'
        '.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}'
        'h1{font-size:20px;margin:0 0 18px}'
        '.hubgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}'
        '.hubcard{background:var(--panel);border:1px solid var(--border);border-radius:12px;'
        'padding:20px;display:flex;flex-direction:column;gap:6px;transition:border-color .15s}'
        '.hubcard:hover{border-color:var(--accent)}'
        '.hubcard b{font-size:18px}.hubcard span{color:var(--dim);font-size:13px}'
        '.meta{color:var(--dim);font-size:12px;text-align:center;margin-top:30px}'
        '</style></head><body>'
        '<nav><span class="brand">Study Logs</span>'
        '<a class="jump" href="../index.html">&larr; Home</a></nav>'
        '<div class="wrap"><h1>Weekly Summaries</h1>'
        f'<div class="hubgrid">{cards}</div>'
        f'<p class="meta">Generated {ts}</p>'
        '</div></body></html>'
    )


def main() -> int:
    base = Path(__file__).resolve().parent

    readme = base / "README.md"
    if readme.exists():
        page = render_markdown_to_page(
            readme.read_text(encoding="utf-8"),
            brand="Study Logs",
            source="Rendered from README.md",
            back_href="Weekly%20Summary/index.html",
            back_label="Weekly Summaries \u2192",
        )
        (base / "index.html").write_text(page, encoding="utf-8")
        print("[+] index.html")

    weekly_dir = base / "Weekly Summary"
    if weekly_dir.is_dir():
        folders = []
        for child in weekly_dir.iterdir():
            if not child.is_dir():
                continue
            mds = sorted(child.glob("*.md"))
            if mds:
                label, key = folder_label(child.name)
                folders.append((key, label, child, mds[0]))
        folders.sort(reverse=True)

        entries = []
        for _, label, folder, md in folders:
            page = render_markdown_to_page(
                md.read_text(encoding="utf-8"),
                brand=f"Weekly Summary \u2014 {label}",
                source=f"Rendered from {md.name}",
                back_href="../index.html",
                back_label="\u2190 All summaries",
            )
            (folder / "index.html").write_text(page, encoding="utf-8")
            entries.append((label, f"{folder.name}/index.html"))
            print(f"[+] Weekly Summary/{folder.name}/index.html")

        (weekly_dir / "index.html").write_text(hub_page(entries), encoding="utf-8")
        print("[+] Weekly Summary/index.html (hub)")

    if "--open" in sys.argv:
        import webbrowser
        webbrowser.open((base / "index.html").resolve().as_uri())

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
