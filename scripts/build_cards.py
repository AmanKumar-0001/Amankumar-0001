#!/usr/bin/env python3
"""Generate animated SVG profile cards for AmanKumar-0001/AmanKumar-0001.

All cards are engineered strictly for GitHub's sandboxed <img> rendering:
- Inline <style> blocks with CSS @keyframes (zero JavaScript, zero external URLs)
- SMIL <animate> elements for geometry/height transitions
- Fonts subset per-card via pyftsubset / fontTools.subset and embedded as
  base64 WOFF data URIs
- Staggered top-to-bottom animation delays across the full README stack
- Full animation shutdown under @media (prefers-reduced-motion: reduce)
- STATIC=1 environment variable (or --static) to render the final frame directly
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Brand Palette & Typography Tokens
# Update these hex codes or drop custom .ttf/.otf files into assets/fonts/
# to match a personal website palette at any time.
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#0B0F17",
    "surface": "#111827",
    "surface_alt": "#162032",
    "border": "#1F2A3C",
    "border_hi": "#2E405B",
    "text": "#F3F4F6",
    "text_soft": "#CBD5E1",
    "muted": "#8B9BB4",
    "brand": "#22D3EE",       # Primary brand accent (cyan)
    "brand_dim": "#0891B2",   # Secondary brand accent
    "brand_glow": "#67E8F9",
    "ramp": [
        "#161F2E",            # Level 0 (no contributions)
        "#0E3A4A",            # Level 1
        "#0E6075",            # Level 2
        "#0891B2",            # Level 3
        "#22D3EE",            # Level 4 (peak)
    ],
}

PROFILE = {
    "name": "Aman Kumar",
    "handle": "@AmanKumar-0001",
    "tagline": "CSE (AI & ML) student building fast, local-first AI, vision & Android software.",
    "badge": "LOCAL-FIRST · AI & VISION",
    "location": "Faridabad, IN",
}

TILES = [
    {
        "filename": "tile-github.svg",
        "eyebrow": "GITHUB",
        "title": "Repositories",
        "subtitle": "AI, CV & Android builds",
        "accent": THEME["brand"],
        "icon": "code",
    },
    {
        "filename": "tile-email.svg",
        "eyebrow": "CONTACT",
        "title": "Email Me",
        "subtitle": "amankumaraz.0009",
        "accent": "#38BDF8",
        "icon": "mail",
    },
    {
        "filename": "tile-focus.svg",
        "eyebrow": "CURRENT FOCUS",
        "title": "Local AI Stack",
        "subtitle": "PyTorch · OpenCV · Kotlin",
        "accent": "#34D399",
        "icon": "spark",
    },
]

# Top-to-bottom staggered entrance delays (seconds)
DELAYS = {
    "hero": 0.00,
    "tiles": [0.35, 0.50, 0.65],
    "monthly": 0.85,
    "repos_start": 1.25,
    "repos_step": 0.16,
    "graph": 1.95,
}

FONT_CANDIDATES = {
    "display": [
        "assets/fonts/Display-Bold.otf",
        "assets/fonts/Display-Bold.ttf",
        "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "sans": [
        "assets/fonts/Sans-Regular.otf",
        "assets/fonts/Sans-Regular.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
        "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "sans_semi": [
        "assets/fonts/Sans-SemiBold.otf",
        "assets/fonts/Sans-SemiBold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
        "/usr/share/fonts/truetype/inter/Inter-SemiBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "mono": [
        "assets/fonts/Mono-Regular.ttf",
        "assets/fonts/Mono-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ],
}

_FONT_CACHE: dict[tuple[str, str], str] = {}


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def resolve_font(role: str, repo_root: Path) -> Path:
    for candidate in FONT_CANDIDATES[role]:
        p = Path(candidate)
        if not p.is_absolute():
            p = repo_root / p
        if p.exists():
            return p
    raise FileNotFoundError(
        f"No font found for role '{role}'. Install fonts-inter / fonts-dejavu-core "
        f"or place fonts in assets/fonts/."
    )


def subset_font_woff_b64(font_path: Path, text: str) -> str:
    """Subset a font to the exact characters in `text` via pyftsubset -> WOFF base64."""
    unique_chars = "".join(sorted(set(text + " 0123456789")))
    cache_key = (str(font_path), unique_chars)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    pyftsubset_bin = shutil.which("pyftsubset")
    with tempfile.TemporaryDirectory(prefix="svg_font_") as tmpdir:
        out_woff = Path(tmpdir) / "subset.woff"
        text_file = Path(tmpdir) / "chars.txt"
        text_file.write_text(unique_chars, encoding="utf-8")

        if pyftsubset_bin:
            cmd = [pyftsubset_bin]
        else:
            cmd = [sys.executable, "-m", "fontTools.subset"]

        cmd.extend([
            str(font_path),
            f"--text-file={text_file}",
            f"--output-file={out_woff}",
            "--flavor=woff",
            "--layout-features=*",
            "--no-hinting",
            "--desubroutinize",
        ])
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        encoded = base64.b64encode(out_woff.read_bytes()).decode("ascii")
        _FONT_CACHE[cache_key] = encoded
        return encoded


def build_font_faces(repo_root: Path, used_text: str) -> str:
    """Return @font-face declarations with embedded base64 WOFF data URIs."""
    specs = [
        ("CardDisplay", 700, resolve_font("display", repo_root)),
        ("CardSans", 400, resolve_font("sans", repo_root)),
        ("CardSans", 600, resolve_font("sans_semi", repo_root)),
        ("CardMono", 400, resolve_font("mono", repo_root)),
    ]
    blocks = []
    for family, weight, path in specs:
        b64 = subset_font_woff_b64(path, used_text)
        blocks.append(
            f"@font-face {{"
            f"font-family:'{family}';"
            f"font-weight:{weight};"
            f"font-style:normal;"
            f"src:url('data:font/woff;base64,{b64}') format('woff');"
            f"}}"
        )
    return "\n    ".join(blocks)


def base_style(font_faces: str, extra_css: str, static: bool) -> str:
    reduced_css = """
    .reduced-static { display: none; }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
      }
      .fade-up, .fade-in { opacity: 1 !important; transform: none !important; }
      .smil-anim { display: none !important; }
      .reduced-static { display: inline !important; }
    }
    """
    anim_css = (
        """
    .fade-up, .fade-in { opacity: 1; transform: none; }
    """
        if static
        else """
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to   { opacity: 1; }
    }
    @keyframes pulseDot {
      0%, 100% { opacity: 1; }
      50%      { opacity: 0.35; }
    }
    .fade-up { opacity: 0; animation: fadeUp 0.55s cubic-bezier(0.22,1,0.36,1) forwards; }
    .fade-in { opacity: 0; animation: fadeIn 0.55s ease-out forwards; }
    """
    )
    return f"""<style>
    {font_faces}
    .f-display {{ font-family: 'CardDisplay', sans-serif; font-weight: 700; }}
    .f-sans    {{ font-family: 'CardSans', sans-serif; font-weight: 400; }}
    .f-semi    {{ font-family: 'CardSans', sans-serif; font-weight: 600; }}
    .f-mono    {{ font-family: 'CardMono', monospace; font-weight: 400; }}
    {anim_css}
    {extra_css}
    {"" if static else reduced_css}
  </style>"""


def load_portrait_data_uri(portrait_path: Path | None) -> str | None:
    if not portrait_path or not portrait_path.exists():
        return None
    mime, _ = mimetypes.guess_type(str(portrait_path))
    if not mime:
        mime = "image/png"
    b64 = base64.b64encode(portrait_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def render_hero(repo_root: Path, portrait_path: Path | None, static: bool) -> str:
    delay = DELAYS["hero"]
    portrait_uri = load_portrait_data_uri(portrait_path)
    used_text = (
        PROFILE["name"]
        + PROFILE["handle"]
        + PROFILE["tagline"]
        + PROFILE["badge"]
        + PROFILE["location"]
        + "AK"
    )
    fonts = build_font_faces(repo_root, used_text)
    extra_css = (
        ""
        if static
        else f"""
    .hero-card {{ animation-delay: {delay:.2f}s; }}
    .hero-badge {{ animation-delay: {delay + 0.08:.2f}s; }}
    .hero-name {{ animation-delay: {delay + 0.14:.2f}s; }}
    .hero-tag {{ animation-delay: {delay + 0.22:.2f}s; }}
    .status-dot {{ animation: pulseDot 2.4s ease-in-out infinite; }}
    """
    )

    if portrait_uri:
        avatar_block = f"""
  <g class="fade-in hero-card">
    <circle cx="748" cy="88" r="50" fill="{THEME['surface_alt']}" stroke="{THEME['brand']}" stroke-width="2" stroke-opacity="0.75"/>
    <image href="{portrait_uri}" x="702" y="42" width="92" height="92" preserveAspectRatio="xMidYMid slice" clip-path="url(#avatarClip)"/>
  </g>"""
    else:
        avatar_block = f"""
  <g class="fade-in hero-card">
    <circle cx="748" cy="88" r="46" fill="{THEME['surface_alt']}" stroke="{THEME['border_hi']}" stroke-width="1.5"/>
    <circle cx="748" cy="88" r="38" fill="none" stroke="{THEME['brand']}" stroke-width="1.5" stroke-dasharray="6 5" stroke-opacity="0.7"/>
    <text x="748" y="96" text-anchor="middle" class="f-display" font-size="24" fill="{THEME['brand']}">AK</text>
  </g>"""

    accent_bar_anim = (
        f'<rect x="0" y="0" width="840" height="3" fill="url(#brandBar)"/>'
        if static
        else f"""<g class="smil-anim">
    <rect x="0" y="0" width="0" height="3" fill="url(#brandBar)">
      <animate attributeName="width" from="0" to="840" begin="{delay:.2f}s" dur="0.75s" fill="freeze" calcMode="spline" keySplines="0.22 1 0.36 1"/>
    </rect>
  </g>
  <rect class="reduced-static" x="0" y="0" width="840" height="3" fill="url(#brandBar)"/>"""
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="840" height="176" viewBox="0 0 840 176" role="img" aria-label="{esc(PROFILE['name'])} — {esc(PROFILE['tagline'])}">
  <defs>
    <linearGradient id="heroBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{THEME['surface']}"/>
      <stop offset="100%" stop-color="{THEME['bg']}"/>
    </linearGradient>
    <linearGradient id="brandBar" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{THEME['brand']}"/>
      <stop offset="55%" stop-color="{THEME['brand_dim']}"/>
      <stop offset="100%" stop-color="{THEME['surface']}"/>
    </linearGradient>
    <clipPath id="cardClip"><rect x="0.5" y="0.5" width="839" height="175" rx="14"/></clipPath>
    <clipPath id="avatarClip"><circle cx="748" cy="88" r="46"/></clipPath>
  </defs>
  {base_style(fonts, extra_css, static)}
  <g clip-path="url(#cardClip)">
    <rect x="0.5" y="0.5" width="839" height="175" rx="14" fill="url(#heroBg)" stroke="{THEME['border']}" stroke-width="1"/>
    <circle cx="748" cy="88" r="120" fill="{THEME['brand']}" fill-opacity="0.05"/>
    {accent_bar_anim}
  </g>

  <g class="fade-up hero-badge">
    <rect x="32" y="28" width="218" height="24" rx="12" fill="{THEME['surface_alt']}" stroke="{THEME['border_hi']}" stroke-width="1"/>
    <circle cx="46" cy="40" r="3.5" fill="{THEME['brand']}" class="status-dot"/>
    <text x="58" y="44" class="f-mono" font-size="10.5" letter-spacing="0.8" fill="{THEME['brand']}">{esc(PROFILE['badge'])}</text>
  </g>

  <g class="fade-up hero-name">
    <text x="32" y="94" class="f-display" font-size="36" fill="{THEME['text']}" letter-spacing="-0.6">{esc(PROFILE['name'])}</text>
    <text x="262" y="92" class="f-mono" font-size="14" fill="{THEME['muted']}">{esc(PROFILE['handle'])}</text>
  </g>

  <g class="fade-up hero-tag">
    <text x="32" y="128" class="f-sans" font-size="14.5" fill="{THEME['text_soft']}">{esc(PROFILE['tagline'])}</text>
    <text x="32" y="152" class="f-mono" font-size="11.5" fill="{THEME['muted']}">{esc(PROFILE['location'])}</text>
  </g>

  {avatar_block}
</svg>
"""


def tile_icon_svg(kind: str, color: str) -> str:
    if kind == "code":
        return (
            f'<path d="M226 30 l-6 6 l6 6 M238 30 l6 6 l-6 6 M234 28 l-4 16" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if kind == "mail":
        return (
            f'<rect x="219" y="28" width="24" height="16" rx="3" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<path d="M220 30 l11 8 l11 -8" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<path d="M231 24 l2.6 8.4 l8.4 2.6 l-8.4 2.6 l-2.6 8.4 l-2.6 -8.4 l-8.4 -2.6 l8.4 -2.6 z" '
        f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round"/>'
    )


def render_tile(repo_root: Path, tile: dict[str, str], delay: float, static: bool) -> str:
    used_text = tile["eyebrow"] + tile["title"] + tile["subtitle"] + "→"
    fonts = build_font_faces(repo_root, used_text)
    extra_css = "" if static else f".tile-in {{ animation-delay: {delay:.2f}s; }}"
    bar_svg = (
        f'<rect x="20" y="92" width="44" height="3" rx="1.5" fill="{tile["accent"]}"/>'
        if static
        else f"""<g class="smil-anim">
    <rect x="20" y="92" width="0" height="3" rx="1.5" fill="{tile['accent']}">
      <animate attributeName="width" from="0" to="44" begin="{delay + 0.15:.2f}s" dur="0.45s" fill="freeze"/>
    </rect>
  </g>
  <rect class="reduced-static" x="20" y="92" width="44" height="3" rx="1.5" fill="{tile['accent']}"/>"""
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="272" height="106" viewBox="0 0 272 106" role="img" aria-label="{esc(tile['title'])} — {esc(tile['subtitle'])}">
  {base_style(fonts, extra_css, static)}
  <g class="fade-up tile-in">
    <rect x="0.5" y="0.5" width="271" height="105" rx="12" fill="{THEME['surface']}" stroke="{THEME['border']}" stroke-width="1"/>
    <circle cx="231" cy="36" r="18" fill="{tile['accent']}" fill-opacity="0.10"/>
    {tile_icon_svg(tile['icon'], tile['accent'])}
    <text x="20" y="30" class="f-mono" font-size="10" letter-spacing="1.1" fill="{tile['accent']}">{esc(tile['eyebrow'])}</text>
    <text x="20" y="56" class="f-display" font-size="18" fill="{THEME['text']}">{esc(tile['title'])}</text>
    <text x="20" y="78" class="f-sans" font-size="12.5" fill="{THEME['muted']}">{esc(tile['subtitle'])}</text>
    <text x="246" y="88" text-anchor="end" class="f-mono" font-size="13" fill="{THEME['muted']}">→</text>
    {bar_svg}
  </g>
</svg>
"""


def render_monthly_chart(repo_root: Path, data: dict[str, Any], static: bool) -> str:
    delay = DELAYS["monthly"]
    monthly = data.get("monthly", [])[-12:]
    current_streak = int(data.get("current_streak", 0))
    longest_streak = int(data.get("longest_streak", 0))
    active_days = int(data.get("active_days", 0))
    busiest = data.get("busiest_day") or {}
    busiest_count = int(busiest.get("count", 0))
    busiest_date_raw = busiest.get("date", "—")
    try:
        busiest_label = dt.date.fromisoformat(busiest_date_raw).strftime("%b %d")
    except ValueError:
        busiest_label = str(busiest_date_raw)

    max_val = max((int(m.get("count", 0)) for m in monthly), default=1)
    max_val = max(max_val, 1)

    kpis = [
        ("CURRENT STREAK", f"{current_streak}d"),
        ("LONGEST STREAK", f"{longest_streak}d"),
        ("ACTIVE DAYS", f"{active_days}"),
        ("BUSIEST DAY", f"{busiest_label} ({busiest_count})"),
    ]

    used_text = (
        "MONTHLY CONTRIBUTIONS · LAST 12 MONTHS"
        + "".join(k + v for k, v in kpis)
        + "".join(str(m.get("label", "")) + str(m.get("count", "")) for m in monthly)
    )
    fonts = build_font_faces(repo_root, used_text)
    extra_css = "" if static else f".chart-in {{ animation-delay: {delay:.2f}s; }}"

    # KPI boxes across top row
    kpi_svg = []
    kpi_w = 186
    kpi_gap = 12
    start_x = 28
    for idx, (label, val) in enumerate(kpis):
        kx = start_x + idx * (kpi_w + kpi_gap)
        val_color = THEME["brand"] if idx in (0, 3) else THEME["text"]
        kpi_svg.append(
            f'<g>'
            f'<rect x="{kx}" y="48" width="{kpi_w}" height="52" rx="9" fill="{THEME["surface_alt"]}" stroke="{THEME["border"]}" stroke-width="1"/>'
            f'<text x="{kx + 14}" y="66" class="f-mono" font-size="9.5" letter-spacing="0.8" fill="{THEME["muted"]}">{esc(label)}</text>'
            f'<text x="{kx + 14}" y="89" class="f-display" font-size="18" fill="{val_color}">{esc(val)}</text>'
            f'</g>'
        )

    # 12-month bar chart
    chart_left = 36
    chart_right = 804
    chart_top = 124
    chart_bottom = 216
    chart_h = chart_bottom - chart_top
    slot_w = (chart_right - chart_left) / max(len(monthly), 1)
    bar_w = min(38.0, slot_w * 0.56)

    grid_lines = []
    for frac in (0.0, 0.5, 1.0):
        gy = chart_bottom - frac * chart_h
        grid_lines.append(
            f'<line x1="{chart_left}" y1="{gy:.1f}" x2="{chart_right}" y2="{gy:.1f}" '
            f'stroke="{THEME["border"]}" stroke-width="1" stroke-dasharray="3 4"/>'
        )

    bars_svg = []
    for idx, item in enumerate(monthly):
        count = int(item.get("count", 0))
        label = str(item.get("label", ""))
        cx = chart_left + idx * slot_w + slot_w / 2
        bx = cx - bar_w / 2
        bh = max(4.0, (count / max_val) * chart_h) if count > 0 else 3.0
        by = chart_bottom - bh
        fill = "url(#barGrad)" if count > 0 else THEME["border"]
        b_delay = delay + 0.15 + idx * 0.04

        if static:
            bars_svg.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="4" fill="{fill}"/>'
            )
        else:
            bars_svg.append(
                f'<g class="smil-anim">'
                f'<rect x="{bx:.1f}" y="{chart_bottom:.1f}" width="{bar_w:.1f}" height="0" rx="4" fill="{fill}">'
                f'<animate attributeName="y" from="{chart_bottom:.1f}" to="{by:.1f}" begin="{b_delay:.2f}s" dur="0.55s" fill="freeze" calcMode="spline" keySplines="0.22 1 0.36 1"/>'
                f'<animate attributeName="height" from="0" to="{bh:.1f}" begin="{b_delay:.2f}s" dur="0.55s" fill="freeze" calcMode="spline" keySplines="0.22 1 0.36 1"/>'
                f'</rect></g>'
                f'<rect class="reduced-static" x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="4" fill="{fill}"/>'
            )

        if count > 0:
            bars_svg.append(
                f'<text x="{cx:.1f}" y="{by - 6:.1f}" text-anchor="middle" class="f-mono" font-size="10.5" fill="{THEME["brand_glow"]}">{count}</text>'
            )
        bars_svg.append(
            f'<text x="{cx:.1f}" y="{chart_bottom + 18:.1f}" text-anchor="middle" class="f-mono" font-size="10.5" fill="{THEME["muted"]}">{esc(label)}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="840" height="252" viewBox="0 0 840 252" role="img" aria-label="Monthly contributions chart with streak, active days, and busiest day">
  <defs>
    <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{THEME['brand']}"/>
      <stop offset="100%" stop-color="{THEME['brand_dim']}"/>
    </linearGradient>
  </defs>
  {base_style(fonts, extra_css, static)}
  <g class="fade-up chart-in">
    <rect x="0.5" y="0.5" width="839" height="251" rx="14" fill="{THEME['surface']}" stroke="{THEME['border']}" stroke-width="1"/>
    <text x="28" y="31" class="f-mono" font-size="11" letter-spacing="1.1" fill="{THEME['brand']}">MONTHLY CONTRIBUTIONS · LAST 12 MONTHS</text>
    {"".join(kpi_svg)}
    {"".join(grid_lines)}
    {"".join(bars_svg)}
  </g>
</svg>
"""


def render_repo_card(repo_root: Path, repo: dict[str, Any], index: int, static: bool) -> str:
    delay = DELAYS["repos_start"] + index * DELAYS["repos_step"]
    name = repo["name"]
    desc = repo.get("description", "")
    lang = repo.get("language", "Code")
    lang_color = repo.get("language_color", THEME["brand"])
    stars = int(repo.get("stars", 0))
    topics = repo.get("topics", [])[:3]

    used_text = (
        f"FEATURED REPOSITORY {name} {desc} {lang} ★ {stars} "
        + " ".join(topics)
        + "→"
    )
    fonts = build_font_faces(repo_root, used_text)
    extra_css = "" if static else f".repo-in {{ animation-delay: {delay:.2f}s; }}"

    # Topic pills
    pills = []
    px = 28
    for topic in topics:
        tw = max(56, len(topic) * 7.2 + 20)
        pills.append(
            f'<rect x="{px:.1f}" y="78" width="{tw:.1f}" height="22" rx="11" '
            f'fill="{THEME["surface_alt"]}" stroke="{THEME["border_hi"]}" stroke-width="1"/>'
            f'<text x="{px + tw / 2:.1f}" y="92.5" text-anchor="middle" class="f-mono" font-size="10" fill="{THEME["text_soft"]}">{esc(topic)}</text>'
        )
        px += tw + 8

    left_bar = (
        f'<rect x="0.5" y="18" width="3.5" height="80" rx="1.75" fill="{lang_color}"/>'
        if static
        else f"""<g class="smil-anim">
      <rect x="0.5" y="18" width="3.5" height="0" rx="1.75" fill="{lang_color}">
        <animate attributeName="height" from="0" to="80" begin="{delay + 0.12:.2f}s" dur="0.45s" fill="freeze"/>
      </rect>
    </g>
    <rect class="reduced-static" x="0.5" y="18" width="3.5" height="80" rx="1.75" fill="{lang_color}"/>"""
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="840" height="116" viewBox="0 0 840 116" role="img" aria-label="Featured repository {esc(name)}">
  {base_style(fonts, extra_css, static)}
  <g class="fade-up repo-in">
    <rect x="0.5" y="0.5" width="839" height="115" rx="12" fill="{THEME['surface']}" stroke="{THEME['border']}" stroke-width="1"/>
    {left_bar}
    <text x="28" y="34" class="f-display" font-size="18.5" fill="{THEME['text']}">{esc(name)}</text>
    <circle cx="696" cy="28" r="5" fill="{lang_color}"/>
    <text x="708" y="32" class="f-mono" font-size="11.5" fill="{THEME['text_soft']}">{esc(lang)}</text>
    <text x="782" y="32" class="f-mono" font-size="11.5" fill="{THEME['muted']}">★ {stars}</text>
    <text x="28" y="60" class="f-sans" font-size="13.2" fill="{THEME['muted']}">{esc(desc)}</text>
    {"".join(pills)}
    <text x="812" y="94" text-anchor="end" class="f-mono" font-size="14" fill="{THEME['brand']}">→</text>
  </g>
</svg>
"""


def build_year_grid(days_list: list[dict[str, Any]], end_date: dt.date) -> list[list[tuple[dt.date, int]]]:
    """Return 53 week-columns of (date, count) ending on end_date's week."""
    counts = {d["date"]: int(d["count"]) for d in days_list}
    # Align grid start to Sunday, 52 weeks prior
    days_since_sun = (end_date.weekday() + 1) % 7
    last_sunday = end_date - dt.timedelta(days=days_since_sun)
    start_sunday = last_sunday - dt.timedelta(weeks=52)

    weeks: list[list[tuple[dt.date, int]]] = []
    cur = start_sunday
    for _ in range(53):
        col: list[tuple[dt.date, int]] = []
        for _ in range(7):
            c = counts.get(cur.isoformat(), 0) if cur <= end_date else -1
            col.append((cur, c))
            cur += dt.timedelta(days=1)
        weeks.append(col)
    return weeks


def level_for_count(count: int, max_count: int) -> int:
    if count <= 0:
        return 0
    if max_count <= 4:
        return min(count, 4)
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.50:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def render_contribution_graph(repo_root: Path, data: dict[str, Any], static: bool) -> str:
    delay = DELAYS["graph"]
    total = int(data.get("total_contributions", 0))
    gen_raw = str(data.get("generated_at", ""))[:10]
    try:
        end_date = dt.date.fromisoformat(gen_raw)
    except ValueError:
        end_date = dt.date.today()

    weeks = build_year_grid(data.get("days", []), end_date)
    max_day = max((c for col in weeks for _, c in col if c > 0), default=1)

    header_left = "CONTRIBUTION GRAPH"
    header_right = f"{total} contributions in the last year"
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    used_text = header_left + header_right + "MonWedFriLessMore" + "".join(month_names)
    fonts = build_font_faces(repo_root, used_text)
    extra_css = "" if static else f".graph-in {{ animation-delay: {delay:.2f}s; }}"

    cell = 11.5
    gap = 2.8
    step = cell + gap
    origin_x = 56.0
    origin_y = 60.0

    # Month labels
    month_svg = []
    seen_month = -1
    for w_idx, col in enumerate(weeks):
        first_day = col[0][0]
        if first_day.month != seen_month and w_idx < 51:
            seen_month = first_day.month
            mx = origin_x + w_idx * step
            month_svg.append(
                f'<text x="{mx:.1f}" y="{origin_y - 9:.1f}" class="f-mono" font-size="9.5" fill="{THEME["muted"]}">{month_names[first_day.month - 1]}</text>'
            )

    # Day labels (Mon=1, Wed=3, Fri=5)
    day_svg = []
    for row_idx, dlabel in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        dy = origin_y + row_idx * step + 9.2
        day_svg.append(
            f'<text x="26" y="{dy:.1f}" class="f-mono" font-size="9.5" fill="{THEME["muted"]}">{dlabel}</text>'
        )

    # Heatmap cells with column-by-column reveal wave
    cells_svg = []
    for w_idx, col in enumerate(weeks):
        col_delay = delay + 0.12 + w_idx * 0.015
        for d_idx, (day_dt, count) in enumerate(col):
            if count < 0:
                continue
            cx = origin_x + w_idx * step
            cy = origin_y + d_idx * step
            lvl = level_for_count(count, max_day)
            fill = THEME["ramp"][lvl]
            title_txt = f"{day_dt.isoformat()}: {count} contribution{'s' if count != 1 else ''}"
            if static:
                cells_svg.append(
                    f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{fill}">'
                    f'<title>{title_txt}</title></rect>'
                )
            else:
                cells_svg.append(
                    f'<g class="smil-anim">'
                    f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{fill}" opacity="0">'
                    f'<animate attributeName="opacity" from="0" to="1" begin="{col_delay:.2f}s" dur="0.32s" fill="freeze"/>'
                    f'<title>{title_txt}</title></rect></g>'
                    f'<rect class="reduced-static" x="{cx:.1f}" y="{cy:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{fill}"/>'
                )

    # Legend
    legend_x = 674.0
    legend_y = 171.0
    legend_svg = [
        f'<text x="{legend_x - 8:.1f}" y="{legend_y + 9:.1f}" text-anchor="end" class="f-mono" font-size="9.5" fill="{THEME["muted"]}">Less</text>'
    ]
    for idx, swatch in enumerate(THEME["ramp"]):
        sx = legend_x + idx * (cell + 4)
        legend_svg.append(
            f'<rect x="{sx:.1f}" y="{legend_y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{swatch}"/>'
        )
    legend_svg.append(
        f'<text x="{legend_x + 5 * (cell + 4) + 6:.1f}" y="{legend_y + 9:.1f}" class="f-mono" font-size="9.5" fill="{THEME["muted"]}">More</text>'
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="840" height="198" viewBox="0 0 840 198" role="img" aria-label="Contribution graph: {esc(header_right)}">
  {base_style(fonts, extra_css, static)}
  <g class="fade-up graph-in">
    <rect x="0.5" y="0.5" width="839" height="197" rx="14" fill="{THEME['surface']}" stroke="{THEME['border']}" stroke-width="1"/>
    <text x="26" y="30" class="f-mono" font-size="11" letter-spacing="1.1" fill="{THEME['brand']}">{esc(header_left)}</text>
    <text x="814" y="30" text-anchor="end" class="f-mono" font-size="11" fill="{THEME['text_soft']}">{esc(header_right)}</text>
    {"".join(month_svg)}
    {"".join(day_svg)}
    {"".join(cells_svg)}
    {"".join(legend_svg)}
  </g>
</svg>
"""


def slugify(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build animated SVG profile cards.")
    parser.add_argument("--data", default="data/contributions.json", help="Path to contributions JSON")
    parser.add_argument("--out", default="cards", help="Output directory for SVG cards")
    parser.add_argument("--portrait", default=os.environ.get("PORTRAIT_PATH", ""), help="Optional portrait image path")
    parser.add_argument("--static", action="store_true", help="Render final frame with no animations (same as STATIC=1)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    static = args.static or os.environ.get("STATIC", "0").strip() in ("1", "true", "TRUE", "yes")

    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = repo_root / data_path
    data = json.loads(data_path.read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    portrait_path: Path | None = None
    if args.portrait:
        p = Path(args.portrait)
        portrait_path = p if p.is_absolute() else repo_root / p
    else:
        for default_name in ("assets/portrait.png", "assets/portrait.jpg", "assets/portrait.webp"):
            cand = repo_root / default_name
            if cand.exists():
                portrait_path = cand
                break

    written: list[Path] = []

    # 1. Hero card
    hero_path = out_dir / "hero.svg"
    hero_path.write_text(render_hero(repo_root, portrait_path, static), encoding="utf-8")
    written.append(hero_path)

    # 2. Three linked tiles
    for tile, t_delay in zip(TILES, DELAYS["tiles"]):
        t_path = out_dir / tile["filename"]
        t_path.write_text(render_tile(repo_root, tile, t_delay, static), encoding="utf-8")
        written.append(t_path)

    # 3. Monthly chart + streak / active days / busiest day
    monthly_path = out_dir / "monthly-activity.svg"
    monthly_path.write_text(render_monthly_chart(repo_root, data, static), encoding="utf-8")
    written.append(monthly_path)

    # 4. One card per featured repo
    for idx, repo in enumerate(data.get("featured_repos", [])):
        r_path = out_dir / f"repo-{slugify(repo['name'])}.svg"
        r_path.write_text(render_repo_card(repo_root, repo, idx, static), encoding="utf-8")
        written.append(r_path)

    # 5. Contribution graph in brand colour
    graph_path = out_dir / "contribution-graph.svg"
    graph_path.write_text(render_contribution_graph(repo_root, data, static), encoding="utf-8")
    written.append(graph_path)

    mode = "STATIC=1 (final frame)" if static else "ANIMATED"
    print(f"Rendered {len(written)} SVG cards into {out_dir} [{mode}]:")
    for p in written:
        print(f"  - {p.name} ({p.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
