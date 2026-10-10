#!/usr/bin/env python3
"""
Generate GitHub Profile README & Vector Card Assets
from profile.yaml (or profile.json).

Usage:
    python3 generate.py
"""

import os
import sys
import json
import html
import re
import argparse
import urllib.request
import textwrap
import xml.etree.ElementTree as ET

# Try loading YAML; fallback to JSON if PyYAML isn't available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_YAML = os.path.join(WORKSPACE_DIR, "profile.yaml")
CONFIG_JSON = os.path.join(WORKSPACE_DIR, "profile.json")
CARDS_DIR = os.path.join(WORKSPACE_DIR, "assets", "cards")
README_PATH = os.path.join(WORKSPACE_DIR, "README.md")

os.makedirs(CARDS_DIR, exist_ok=True)

THEMES = {
    "dark": {
        "card_bg": "#18181b",
        "border": "#26262b",
        "text_primary": "#e9e6e2",
        "text_secondary": "#cac5bd",
        "text_muted": "#a6a096",
        "accent": "#5c8beb",
        "accent_soft": "rgba(92, 139, 235, 0.12)",
        "accent_border": "rgba(92, 139, 235, 0.28)",
        "tag_bg": "rgba(92, 139, 235, 0.12)",
        "tag_border": "rgba(92, 139, 235, 0.25)",
        "tag_text": "#5c8beb",
        "glow": "#5c8beb",
        "glow_opacity": "0.12",
        "badge_bg": "#242429",
        "badge_border": "#32323a",
        "dot_off": "#3f3f46",
        "btn_cta_bg": "#2563eb",
        "btn_cta_text": "#ffffff",
    },
    "light": {
        "card_bg": "#fafafa",
        "border": "#e0e0e0",
        "text_primary": "#121212",
        "text_secondary": "#383838",
        "text_muted": "#6b6b6b",
        "accent": "#1e51b8",
        "accent_soft": "rgba(30, 81, 184, 0.08)",
        "accent_border": "rgba(30, 81, 184, 0.25)",
        "tag_bg": "rgba(30, 81, 184, 0.08)",
        "tag_border": "rgba(30, 81, 184, 0.25)",
        "tag_text": "#1e51b8",
        "glow": "#1e51b8",
        "glow_opacity": "0.07",
        "badge_bg": "#f0f0f2",
        "badge_border": "#dcdce0",
        "dot_off": "#d4d4d8",
        "btn_cta_bg": "#1e51b8",
        "btn_cta_text": "#ffffff",
    }
}

FONTS_CSS = """
  .sans { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .serif { font-family: Rasa, Georgia, "Times New Roman", serif; }
  .mono { font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
"""

def esc(text):
    if text is None:
        return ""
    return html.escape(str(text), quote=True)

def load_config():
    if os.path.exists(CONFIG_YAML) and HAS_YAML:
        with open(CONFIG_YAML, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    elif os.path.exists(CONFIG_JSON):
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        print(f"Error: Config file not found at {CONFIG_YAML} or {CONFIG_JSON}")
        sys.exit(1)

# ------------------------------------------------------------------------------
# GITHUB API LIVE SYNC
# ------------------------------------------------------------------------------

def fetch_github_repos(username="ccd97"):
    """Fetch public repositories from GitHub API with optional token authentication."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "User-Agent": "GitHub-Profile-Card-Generator",
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/users/{username}/repos?per_page=100"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] Unable to fetch repos from GitHub API ({e}). Falling back to local data.")
        return None

def get_existing_stats(proj_id):
    """Extracts existing (stars, forks) from the currently generated dark SVG card on disk."""
    svg_file = os.path.join(CARDS_DIR, f"card-{proj_id}-dark.svg")
    if not os.path.exists(svg_file):
        return 0, 0
    try:
        with open(svg_file, "r", encoding="utf-8") as f:
            content = f.read()
        nums = re.findall(r'class="mono">(\d+)</text>', content)
        if len(nums) >= 2:
            return int(nums[-2]), int(nums[-1])
    except Exception:
        pass
    return 0, 0

def sync_stats(config, only_if_increased=False):
    """
    Fetches live stats from GitHub API and populates stars/forks directly into config in-memory.
    Compares with existing SVG numbers on disk.
    If only_if_increased=True and no star/fork count has increased, returns (False, config).
    """
    repos_data = fetch_github_repos("ccd97")
    repo_map = {r["name"].lower(): r for r in repos_data} if repos_data else {}
    total_stars = sum(r.get("stargazers_count", 0) for r in repos_data) if repos_data else 0
    total_forks = sum(r.get("forks_count", 0) for r in repos_data) if repos_data else 0
    total_repos = len(repos_data) if repos_data else 0

    proj_items = config.get("projects", {}).get("items", [])
    
    increased_items = []
    changed_items = []

    for proj in proj_items:
        p_id = proj.get("id")
        old_stars, old_forks = get_existing_stats(p_id)
        repo_ref = proj.get("repo", "")

        if repo_ref == "_all":
            new_stars = total_stars if repos_data else old_stars
            new_forks = total_forks if repos_data else old_forks
            if total_repos:
                tags = proj.get("tags", [])
                proj["tags"] = [t for t in tags if not t.endswith("Repos")] + [f"{total_repos} Repos"]
        else:
            repo_name = repo_ref.split("/")[-1].lower() if repo_ref else proj.get("title", "").lower()
            repo_info = repo_map.get(repo_name)
            if repo_info:
                new_stars = int(repo_info.get("stargazers_count", 0))
                new_forks = int(repo_info.get("forks_count", 0))
            else:
                new_stars = old_stars
                new_forks = old_forks

        proj["stars"] = new_stars
        proj["forks"] = new_forks

        if (new_stars > old_stars) or (new_forks > old_forks):
            increased_items.append((proj.get('title'), f"stars: {old_stars}->{new_stars}", f"forks: {old_forks}->{new_forks}"))
        if (new_stars != old_stars) or (new_forks != old_forks):
            changed_items.append((proj.get('title'), f"stars: {old_stars}->{new_stars}", f"forks: {old_forks}->{new_forks}"))

    if only_if_increased and not increased_items:
        print("[SYNC] No star or fork count increase detected across any project. Skipping regeneration and commit.")
        return False, config

    if increased_items:
        print(f"[SYNC] Detected count increase in {len(increased_items)} project(s):")
        for title, s_diff, f_diff in increased_items:
            print(f"  • {title}: {s_diff}, {f_diff}")
    elif changed_items:
        print(f"[SYNC] Detected count changes in {len(changed_items)} project(s).")
    else:
        print("[SYNC] All stats are up to date.")

    return True, config


def save_svg(filename, content):
    content = content.strip() + "\n"
    try:
        ET.fromstring(content)
    except Exception as e:
        print(f"ERROR: XML validation failed for {filename}: {e}")
        raise e

    target_path = os.path.join(CARDS_DIR, filename)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)

# ------------------------------------------------------------------------------
# SVG BUILDERS
# ------------------------------------------------------------------------------

def build_hero(hero_data, theme):
    c = THEMES[theme]
    w = 850
    name = esc(hero_data.get("name", "Cyprien Dcunha"))
    website_text = esc(hero_data.get("website_text", "cyprien.in ↗"))
    headline = esc(hero_data.get("headline", "")).strip()
    status_badge = esc(hero_data.get("status", {}).get("badge", "CURRENTLY"))
    status_text = esc(hero_data.get("status", {}).get("text", ""))

    badge_w = round(len(status_badge) * 6.4 + 16) if status_badge else 0
    badge_x = 28
    badge_h = 19
    badge_y = 106 if headline else 74
    badge_center_x = badge_x + badge_w / 2
    badge_center_y = badge_y + badge_h / 2 + 0.5
    status_text_x = badge_x + badge_w + 12
    h = 148 if headline else 118

    body_elements = [
        f'  <text x="28" y="52" fill="{c["text_primary"]}" font-size="32" font-weight="600" class="serif">{name}</text>',
        f'  <text x="822" y="44" text-anchor="end" fill="{c["accent"]}" font-size="11" font-weight="600" class="mono">{website_text}</text>',
    ]
    if headline:
        body_elements.append(f'  <text x="28" y="86" fill="{c["text_primary"]}" font-size="13" font-weight="400" class="sans">{headline}</text>')
    body_elements.extend([
        f'  <rect x="{badge_x}" y="{badge_y}" width="{badge_w}" height="{badge_h}" rx="4" fill="{c["accent_soft"]}" stroke="{c["accent_border"]}" stroke-width="1"/>',
        f'  <text x="{badge_center_x}" y="{badge_center_y}" text-anchor="middle" dominant-baseline="central" fill="{c["accent"]}" font-size="9" font-weight="600" class="mono" letter-spacing="1">{status_badge}</text>',
        f'  <text x="{status_text_x}" y="{badge_center_y}" dominant-baseline="central" fill="{c["text_muted"]}" font-size="12" class="sans">{status_text}</text>',
    ])
    body_svg = "\n".join(body_elements)

    svg = f"""<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
  <radialGradient id="glow-hero-{theme}" cx="800" cy="0" r="280" gradientUnits="userSpaceOnUse">
    <stop offset="0%" stop-color="{c['glow']}" stop-opacity="{c['glow_opacity']}"/>
    <stop offset="100%" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>{FONTS_CSS}</style>
  <rect width="{w}" height="{h}" rx="8" fill="{c['card_bg']}" stroke="{c['border']}" stroke-width="1"/>
  <rect width="{w}" height="{h}" rx="8" fill="url(#glow-hero-{theme})"/>
{body_svg}
</svg>"""
    save_svg(f"card-hero-{theme}.svg", svg)

def build_experience(exp_data, theme):
    c = THEMES[theme]
    # Native 850-wide banner: at README 100% width it renders ~1:1, so fonts
    # read at their designed size (the old 415-wide card rendered 2x here).
    w, h = 850, 216
    items = exp_data.get("items", [])

    y_step = 48
    start_y = 32
    line_end_y = start_y + (len(items) - 1) * y_step if items else start_y

    rows_svg = []
    for i, item in enumerate(items):
        cy = start_y + i * y_step
        dot_color = c["accent"] if item.get("active") else c["dot_off"]
        dot_r = 4.0 if item.get("active") else 3.5
        company_color = c["accent"] if item.get("active") else c["text_primary"]
        
        company = esc(item.get("company", ""))
        team = esc(item.get("team", ""))
        period = esc(item.get("period", ""))
        role = esc(item.get("role", ""))
        location = esc(item.get("location", ""))
        muted_color = c["text_muted"]
        team_tspan = f'<tspan fill="{muted_color}" font-size="11" font-weight="400" class="sans"> · {team}</tspan>' if team else ""

        rows_svg.append(f"""  <circle cx="53" cy="{cy}" r="{dot_r}" fill="{dot_color}"/>
  <text x="82" y="{cy + 1}"><tspan fill="{company_color}" font-size="14" font-weight="600" class="sans">{company}</tspan>{team_tspan}</text>
  <text x="809" y="{cy + 1}" text-anchor="end" fill="{c['text_muted']}" font-size="10" class="mono">{period}</text>
  <text x="82" y="{cy + 18}" fill="{c['text_secondary']}" font-size="12" class="sans">{role}</text>
  <text x="809" y="{cy + 18}" text-anchor="end" fill="{c['text_muted']}" font-size="9" class="mono">{location}</text>""")

    content = "\n".join(rows_svg)

    svg = f"""<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
  <radialGradient id="glow-exp-{theme}" cx="800" cy="0" r="280" gradientUnits="userSpaceOnUse">
    <stop offset="0%" stop-color="{c['glow']}" stop-opacity="{c['glow_opacity']}"/>
    <stop offset="100%" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>{FONTS_CSS}</style>
  <rect width="{w}" height="{h}" rx="8" fill="{c['card_bg']}" stroke="{c['border']}" stroke-width="1"/>
  <rect width="{w}" height="{h}" rx="8" fill="url(#glow-exp-{theme})"/>
  <line x1="53" y1="{start_y}" x2="53" y2="{line_end_y}" stroke="{c['border']}" stroke-width="1.5"/>
{content}
</svg>"""
    save_svg(f"card-experience-{theme}.svg", svg)

def build_contact_card(item, theme):
    c = THEMES[theme]
    # Compact tile (415x90) for the 3-up contact strip. Content block is
    # the original 60px card design shifted +15 to vertical center.
    w, card_h, canvas_h = 415, 90, 90
    item_id = item.get("id", "contact")
    label = esc(item.get("label", ""))
    val = esc(item.get("value", ""))
    icon_type = item.get("icon", "email")

    if icon_type == "email":
        icon_svg = f"""  <g transform="translate(32, 34) scale(1.5)">
    <rect width="20" height="15" rx="3" fill="none" stroke="{c['accent']}" stroke-width="1.3"/>
    <path d="M2 3l8 5 8-5" stroke="{c['accent']}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
  </g>"""
    elif icon_type == "linkedin":
        icon_svg = f"""  <g transform="translate(32, 32) scale(1.5)">
    <rect width="20" height="18" rx="3.5" fill="none" stroke="{c['accent']}" stroke-width="1.3"/>
    <path d="M5 8v6M5 5v.01M10 14v-4a2 2 0 0 1 4 0v4M10 10v4" stroke="{c['accent']}" stroke-width="1.3" stroke-linecap="round"/>
  </g>"""
    elif icon_type == "resume":
        icon_svg = f"""  <g transform="translate(32, 32) scale(1.5)">
    <path d="M2 1h9l4 4v10a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2z" fill="none" stroke="{c['accent']}" stroke-width="1.3"/>
    <path d="M11 1v4h4M5 9h6M5 13h7" stroke="{c['accent']}" stroke-width="1.3" stroke-linecap="round"/>
  </g>"""
    else:
        icon_svg = f"""  <g transform="translate(32, 32) scale(1.5)">
    <circle cx="10" cy="10" r="8" fill="none" stroke="{c['accent']}" stroke-width="1.3"/>
    <path d="M10 6v8M6 10h8" stroke="{c['accent']}" stroke-width="1.3" stroke-linecap="round"/>
  </g>"""

    svg = f"""<svg width="100%" height="{canvas_h}" viewBox="0 0 {w} {canvas_h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
  <radialGradient id="glow-{item_id}-{theme}" cx="390" cy="0" r="140" gradientUnits="userSpaceOnUse">
    <stop offset="0%" stop-color="{c['glow']}" stop-opacity="{c['glow_opacity']}"/>
    <stop offset="100%" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>{FONTS_CSS}</style>
  <rect width="{w}" height="{card_h}" rx="8" fill="{c['card_bg']}" stroke="{c['border']}" stroke-width="1"/>
  <rect width="{w}" height="{card_h}" rx="8" fill="url(#glow-{item_id}-{theme})"/>
{icon_svg}
  <text x="76" y="35" fill="{c['accent']}" font-size="11" font-weight="600" class="mono" letter-spacing="1">{label}</text>
  <text x="76" y="63" fill="{c['text_primary']}" font-size="17.5" class="sans">{val}</text>
  <text x="395" y="49" text-anchor="end" fill="{c['accent']}" font-size="11" class="mono">&#8599;</text>
</svg>"""
    save_svg(f"card-{item_id}-{theme}.svg", svg)

def build_section_header(filename, title, subtitle, theme):
    c = THEMES[theme]
    w, h = 850, 32
    title_escaped = esc(title)
    sub_escaped = esc(subtitle).strip() if subtitle else ""
    title_width_approx = len(title) * 11 + 10

    sub_svg = f'<text x="{title_width_approx}" y="22" fill="{c["text_muted"]}" font-size="12.5" class="sans">· {sub_escaped}</text>' if sub_escaped else ''

    svg = f"""<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<style>{FONTS_CSS}</style>
  <text x="4" y="22" fill="{c['text_primary']}" font-size="20" font-weight="500" class="serif">{title_escaped}</text>
  {sub_svg}
</svg>"""
    save_svg(f"{filename}-{theme}.svg", svg)

def build_project_card(proj, theme):
    c = THEMES[theme]
    w, h = 415, 114
    card_id = proj.get("id", "proj")
    filename = f"card-{card_id}-{theme}.svg"
    title = esc(proj.get("title", ""))
    raw_badge = proj.get("badge", "")
    b_clean = str(raw_badge).replace("↗", "").strip()
    badge_text = esc(f"{b_clean} ↗") if b_clean else ""
    tags = proj.get("tags", [])

    desc_raw = proj.get("desc", [])
    if isinstance(desc_raw, str):
        desc_lines = textwrap.wrap(desc_raw, width=54)
    else:
        desc_lines = desc_raw

    # Description lines
    desc_svg_elements = []
    y_start = 48
    for i, line in enumerate(desc_lines[:2]):
        desc_svg_elements.append(f'<text x="20" y="{y_start + i * 15}" fill="{c["text_secondary"]}" font-size="11.2" class="sans">{esc(line)}</text>')
    desc_svg = "\n  ".join(desc_svg_elements)

    # Tags
    tag_elements = []
    cur_x = 20
    tag_y = 80
    tag_h = 19
    for tag in tags:
        tag_escaped = esc(tag)
        tag_w = round(len(tag) * 6.2 + 14)
        tag_elements.append(f"""    <rect x="{cur_x}" y="{tag_y}" width="{tag_w}" height="{tag_h}" rx="4" fill="{c['tag_bg']}" stroke="{c['tag_border']}" stroke-width="1"/>
    <text x="{cur_x + tag_w / 2}" y="{tag_y + tag_h / 2 + 0.5}" text-anchor="middle" dominant-baseline="central" fill="{c['tag_text']}" font-size="8.5" font-weight="500" class="mono">{tag_escaped}</text>""")
        cur_x += tag_w + 6
    tags_svg = "\n".join(tag_elements)

    # Link CTA button
    badge_svg = ""
    if badge_text:
        badge_w = round(len(badge_text) * 5.2 + 16)
        badge_h = 20
        badge_y = 15
        badge_x = 395 - badge_w
        badge_center_x = badge_x + badge_w / 2
        badge_center_y = badge_y + badge_h / 2
        badge_svg = f"""  <rect x="{badge_x}" y="{badge_y}" width="{badge_w}" height="{badge_h}" rx="5" fill="{c['btn_cta_bg']}"/>
  <text x="{badge_center_x}" y="{badge_center_y}" text-anchor="middle" dominant-baseline="central" fill="{c['btn_cta_text']}" font-size="8.5" font-weight="600" class="mono">{badge_text}</text>"""

    # Stats pill (stars & forks)
    stats_svg = ""
    if proj.get("stars") is not None and proj.get("forks") is not None:
        s_str = str(proj.get("stars"))
        f_str = str(proj.get("forks"))
        content_w = 11 + 4 + len(s_str) * 6.2 + 8 + 11 + 4 + len(f_str) * 6.2
        pill_w = round(content_w + 14)
        pill_x = 395 - pill_w
        star_x = pill_x + 7
        star_txt_x = star_x + 13
        fork_x = round(star_txt_x + len(s_str) * 6.2 + 7)
        fork_txt_x = fork_x + 13

        star_path = "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"
        fork_path = "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3 6.25v-.878a2.25 2.25 0 1 1 2 0ZM3.25 3.5a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0ZM7.25 13a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"

        stats_svg = f"""  <rect x="{pill_x}" y="{tag_y}" width="{pill_w}" height="{tag_h}" rx="4" fill="{c['badge_bg']}" stroke="{c['badge_border']}" stroke-width="1"/>
  <g transform="translate({star_x}, {tag_y + 4.5}) scale(0.65)">
    <path d="{star_path}" fill="{c['text_muted']}"/>
  </g>
  <text x="{star_txt_x}" y="{tag_y + tag_h / 2 + 0.5}" dominant-baseline="central" fill="{c['text_secondary']}" font-size="9" font-weight="500" class="mono">{s_str}</text>
  <g transform="translate({fork_x}, {tag_y + 4.5}) scale(0.65)">
    <path d="{fork_path}" fill="{c['text_muted']}"/>
  </g>
  <text x="{fork_txt_x}" y="{tag_y + tag_h / 2 + 0.5}" dominant-baseline="central" fill="{c['text_secondary']}" font-size="9" font-weight="500" class="mono">{f_str}</text>"""

    svg = f"""<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
  <radialGradient id="glow-{card_id}-{theme}" cx="390" cy="0" r="160" gradientUnits="userSpaceOnUse">
    <stop offset="0%" stop-color="{c['glow']}" stop-opacity="{c['glow_opacity']}"/>
    <stop offset="100%" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>{FONTS_CSS}</style>
  <rect width="{w}" height="{h}" rx="8" fill="{c['card_bg']}" stroke="{c['border']}" stroke-width="1"/>
  <rect width="{w}" height="{h}" rx="8" fill="url(#glow-{card_id}-{theme})"/>
  <text x="20" y="28" fill="{c['text_primary']}" font-size="15" font-weight="600" class="serif">{title}</text>
{badge_svg}
  {desc_svg}
{tags_svg}
{stats_svg}
</svg>"""
    save_svg(filename, svg)

def build_skills(skills_data, theme):
    c = THEMES[theme]
    w = 850
    categories = skills_data.get("categories", [])

    line_h = 18
    cat_gap = 10
    div_offset = 6
    start_y = 22
    cur_y = start_y
    svg_rows = []

    for i, cat in enumerate(categories):
        name = esc(cat.get("name", ""))
        lines = cat.get("lines", [])

        svg_rows.append(f"""  <circle cx="26" cy="{cur_y + 2}" r="3" fill="{c['accent']}"/>
  <text x="38" y="{cur_y + 5}" fill="{c['accent']}" font-size="9.5" font-weight="600" class="mono" letter-spacing="1.2">{name}</text>""")

        for j, line in enumerate(lines):
            ly = cur_y + j * line_h
            line_spaced = esc(line).replace(" · ", "  ·  ")
            svg_rows.append(f"""  <text x="180" y="{ly + 5}" fill="{c['text_primary']}" font-size="11" class="mono" xml:space="preserve">{line_spaced}</text>""")

        cur_y += len(lines) * line_h
        if i < len(categories) - 1:
            div_y = cur_y + div_offset
            svg_rows.append(f"""  <line x1="20" y1="{div_y}" x2="830" y2="{div_y}" stroke="{c['border']}" stroke-width="0.8" stroke-dasharray="3 3"/>""")
            cur_y += cat_gap

    h = cur_y + 14
    content = "\n".join(svg_rows)

    svg = f"""<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" fill="none" xmlns="http://www.w3.org/2000/svg">
<defs>
  <radialGradient id="glow-skills-{theme}" cx="800" cy="0" r="180" gradientUnits="userSpaceOnUse">
    <stop offset="0%" stop-color="{c['glow']}" stop-opacity="{c['glow_opacity']}"/>
    <stop offset="100%" stop-color="{c['glow']}" stop-opacity="0"/>
  </radialGradient>
</defs>
<style>{FONTS_CSS}</style>
  <rect width="{w}" height="{h}" rx="8" fill="{c['card_bg']}" stroke="{c['border']}" stroke-width="1"/>
  <rect width="{w}" height="{h}" rx="8" fill="url(#glow-skills-{theme})"/>
{content}
</svg>"""
    save_svg(f"card-skills-{theme}.svg", svg)

# ------------------------------------------------------------------------------
# README.md BUILDER
# ------------------------------------------------------------------------------

def build_readme(config):
    hero = config.get("hero", {})
    projects = config.get("projects", {})
    contact = config.get("contact", {})

    lines = []
    
    # Hero
    lines.append('<!-- HERO -->')
    hero_url = esc(hero.get("website_url", "https://cyprien.in/"))
    hero_name = esc(hero.get("name", "Cyprien Dcunha"))
    lines.append(f'<p><a href="{hero_url}" target="_blank"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-hero-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-hero-light.svg"><img src="assets/cards/card-hero-dark.svg" width="100%" alt="{hero_name}" /></picture></a></p>\n')
    # No <br/> here: the paragraph margin alone (16px) sets the rhythm,
    # matching every other section transition on the page.

    # Contact (3-up row under the hero) + Experience (full width below).
    # All tiles are plain centered inline flow: no floats, no align
    # attributes, so no GitHub align padding and no mobile failure modes.
    # 3-up row totals 31.5+2+31.5+2+31.5 = 98.5% with zero whitespace
    # (font-independent); experience spans 100% like hero/skills headers.
    def tile_pic(card_id, alt, width):
        return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-{card_id}-dark.svg">'
                f'<source media="(prefers-color-scheme: light)" srcset="assets/cards/card-{card_id}-light.svg">'
                f'<img src="assets/cards/card-{card_id}-dark.svg" width="{width}" alt="{alt}" /></picture>')

    contact_by_id = {item.get("id"): item for item in contact.get("items", [])}

    def contact_cell(c_id, width="31.5%"):
        item = contact_by_id.get(c_id, {})
        url = esc(item.get("url", "#"))
        label = esc(item.get("label", ""))
        target = ' target="_blank"' if not url.startswith("mailto:") else ''
        return f'<a href="{url}"{target}>{tile_pic(c_id, label, width)}</a>'

    lines.append('<!-- GET IN TOUCH -->')
    gap = '<img src="assets/cards/spacer.svg" width="2%" alt="" />'
    lines.append(f'<p align="center">{contact_cell("contact-email")}{gap}{contact_cell("contact-linkedin")}{gap}{contact_cell("contact-resume")}</p>\n')
    # (Experience section removed.)
    # (Experience header removed.)

    # Projects
    lines.append('<!-- PROJECTS -->')
    lines.append('<p><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-projects-intro-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-projects-intro-light.svg"><img src="assets/cards/card-projects-intro-dark.svg" width="100%" alt="Projects" /></picture></p>\n')

    # Pair up project items 2 per row
    proj_items = projects.get("items", [])
    for i in range(0, len(proj_items), 2):
        row = proj_items[i:i+2]
        card1 = row[0]
        c1_id = card1.get("id")
        c1_url = esc(card1.get("url", "#"))
        c1_title = esc(card1.get("title", ""))
        p1 = f'<a href="{c1_url}" target="_blank"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-{c1_id}-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-{c1_id}-light.svg"><img src="assets/cards/card-{c1_id}-dark.svg" width="48%" alt="{c1_title}" /></picture></a>'

        if len(row) > 1:
            card2 = row[1]
            c2_id = card2.get("id")
            c2_url = esc(card2.get("url", "#"))
            c2_title = esc(card2.get("title", ""))
            p2 = f'<a href="{c2_url}" target="_blank"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-{c2_id}-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-{c2_id}-light.svg"><img src="assets/cards/card-{c2_id}-dark.svg" width="48%" alt="{c2_title}" /></picture></a>'
            # Gutter via 2% transparent spacer, elements fully adjacent:
            # 48 + 2 + 48 = 98% — exact, collapsible-whitespace-free and
            # font-independent (the old &nbsp; run overflowed on mobile).
            # Centered paragraph absorbs the leftover 2% as even side insets.
            gap = '<img src="assets/cards/spacer.svg" width="2%" alt="" />'
            lines.append(f'<p align="center">{p1}{gap}{p2}</p>\n')
        else:
            lines.append(f'<p align="center">{p1}</p>\n')

    lines.append('<br/>\n')

    # Skills
    lines.append('<!-- SKILLS -->')
    lines.append('<p><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-skills-intro-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-skills-intro-light.svg"><img src="assets/cards/card-skills-intro-dark.svg" width="100%" alt="Skills" /></picture></p>\n')
    lines.append('<p><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/card-skills-dark.svg"><source media="(prefers-color-scheme: light)" srcset="assets/cards/card-skills-light.svg"><img src="assets/cards/card-skills-dark.svg" width="100%" alt="Skills" /></picture></p>\n')

    readme_content = "\n".join(lines).strip() + "\n"
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("README.md updated successfully!")

# ------------------------------------------------------------------------------
# MAIN PIPELINE
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate GitHub Profile README & Vector Cards")
    parser.add_argument("--sync-stats", action="store_true", help="Fetch live stars and forks from GitHub API")
    parser.add_argument("--only-if-increased", action="store_true", help="Only generate cards if star/fork count has increased")
    parser.add_argument("--no-sync", action="store_true", help="Skip fetching live stats and use local profile.yaml only")
    args = parser.parse_args()

    print("Loading profile configuration...")
    config = load_config()

    if not args.no_sync:
        should_proceed, config = sync_stats(config, only_if_increased=args.only_if_increased)
        if not should_proceed:
            print("[INFO] Exiting cleanly without modifying files.")
            return
    else:
        # Offline mode: populate stats from existing SVG cards on disk
        for proj in config.get("projects", {}).get("items", []):
            proj["stars"], proj["forks"] = get_existing_stats(proj.get("id"))

    print("Building vector cards...")
    for theme in ["dark", "light"]:
        # Hero
        build_hero(config.get("hero", {}), theme)
        
        # (Experience rendering removed; data stays in profile.yaml for easy restore.)

        # Contact (3 separate cards with individual links)
        contact_sec = config.get("contact", {})
        for c_item in contact_sec.get("items", []):
            build_contact_card(c_item, theme)
        
        # Projects Section
        proj_sec = config.get("projects", {})
        build_section_header("card-projects-intro", proj_sec.get("header", "Projects"), proj_sec.get("subtitle", ""), theme)
        for proj in proj_sec.get("items", []):
            build_project_card(proj, theme)

        # Skills Section
        skills_sec = config.get("skills", {})
        build_section_header("card-skills-intro", skills_sec.get("header", "Skills"), "", theme)
        build_skills(skills_sec, theme)

    print("Building README.md...")
    build_readme(config)

    print("\nAll cards and documentation generated successfully!")
    print("To add or update cards, just edit 'profile.yaml' and rerun: python3 generate.py")

if __name__ == "__main__":
    main()
