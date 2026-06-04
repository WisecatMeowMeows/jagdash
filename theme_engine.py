"""
theme_engine.py — JagDash theme system

Reads a theme dict from the active profile and generates a CSS <style> block
that overrides the custom properties defined in jagdash.css.

jagdash.css defines the defaults. This module generates overrides on top.
That means jagdash.css always works standalone — the theme system is additive.

How it works:
  1. jagdash.css defines :root { --color-bg: #0d1117; ... }
  2. This module generates <style>:root { --color-bg: #1a1a2e; }</style>
  3. base.html injects that block into <head> AFTER the CSS link
  4. CSS cascade: same specificity, later position wins — overrides work

Profile theme dict shape (all fields optional):
  {
    "preset":               "dark",
    "color_bg":             "#0d1117",
    "color_surface":        "#161b22",
    "color_surface_raised": "#21262d",
    "color_border":         "#30363d",
    "color_fg":             "#e6edf3",
    "color_fg_muted":       "#8b949e",
    "color_accent":         "#58a6ff",
    "color_success":        "#3fb950",
    "color_error":          "#f85149",
    "color_warning":        "#d29922",
    "font_size_base":       14,        # integer px
    "space_scale":          1.0,       # float: 0.7=compact, 1.0=normal, 1.3=relaxed
    "sidebar_width":        220,       # integer px
    "border_radius":        "medium",  # "none"|"small"|"medium"|"large"
    "bg_image":             "",        # path or URL
    "bg_image_opacity":     0.15,      # 0.0-1.0
  }
"""

PRESETS = {
    "dark": {
        "preset":               "dark",
        "color_bg":             "#0d1117",
        "color_surface":        "#161b22",
        "color_surface_raised": "#21262d",
        "color_border":         "#30363d",
        "color_fg":             "#e6edf3",
        "color_fg_muted":       "#8b949e",
        "color_accent":         "#58a6ff",
        "color_success":        "#3fb950",
        "color_error":          "#f85149",
        "color_warning":        "#d29922",
        "font_size_base":       14,
        "space_scale":          1.0,
        "sidebar_width":        220,
        "border_radius":        "medium",
        "bg_image":             "",
        "bg_image_opacity":     0.15,
    },
    "light": {
        "preset":               "light",
        "color_bg":             "#ffffff",
        "color_surface":        "#f6f8fa",
        "color_surface_raised": "#eaeef2",
        "color_border":         "#d0d7de",
        "color_fg":             "#1f2328",
        "color_fg_muted":       "#656d76",
        "color_accent":         "#0969da",
        "color_success":        "#1a7f37",
        "color_error":          "#cf222e",
        "color_warning":        "#9a6700",
        "font_size_base":       14,
        "space_scale":          1.0,
        "sidebar_width":        220,
        "border_radius":        "medium",
        "bg_image":             "",
        "bg_image_opacity":     0.15,
    },
    "high_contrast": {
        "preset":               "high_contrast",
        "color_bg":             "#000000",
        "color_surface":        "#0a0a0a",
        "color_surface_raised": "#1a1a1a",
        "color_border":         "#555555",
        "color_fg":             "#ffffff",
        "color_fg_muted":       "#aaaaaa",
        "color_accent":         "#ffcc00",
        "color_success":        "#00ff88",
        "color_error":          "#ff4444",
        "color_warning":        "#ffaa00",
        "font_size_base":       15,
        "space_scale":          1.0,
        "sidebar_width":        220,
        "border_radius":        "small",
        "bg_image":             "",
        "bg_image_opacity":     0.15,
    },
    "night_trader": {
        "preset":               "night_trader",
        "color_bg":             "#080c14",
        "color_surface":        "#0e1420",
        "color_surface_raised": "#161e2e",
        "color_border":         "#1e2d40",
        "color_fg":             "#c8d8e8",
        "color_fg_muted":       "#5a7a9a",
        "color_accent":         "#00d4ff",
        "color_success":        "#00ff9d",
        "color_error":          "#ff3860",
        "color_warning":        "#ffdd57",
        "font_size_base":       13,
        "space_scale":          0.85,
        "sidebar_width":        200,
        "border_radius":        "small",
        "bg_image":             "",
        "bg_image_opacity":     0.15,
    },
    "compact": {
        "preset":               "compact",
        "color_bg":             "#0d1117",
        "color_surface":        "#161b22",
        "color_surface_raised": "#21262d",
        "color_border":         "#30363d",
        "color_fg":             "#e6edf3",
        "color_fg_muted":       "#8b949e",
        "color_accent":         "#58a6ff",
        "color_success":        "#3fb950",
        "color_error":          "#f85149",
        "color_warning":        "#d29922",
        "font_size_base":       12,
        "space_scale":          0.7,
        "sidebar_width":        180,
        "border_radius":        "none",
        "bg_image":             "",
        "bg_image_opacity":     0.15,
    },
}

BORDER_RADIUS_MAP = {
    "none":   {"sm": "0px",  "md": "0px",  "lg": "0px"},
    "small":  {"sm": "2px",  "md": "4px",  "lg": "6px"},
    "medium": {"sm": "4px",  "md": "6px",  "lg": "10px"},
    "large":  {"sm": "8px",  "md": "12px", "lg": "18px"},
}


def get_theme(profile: dict) -> dict:
    """
    Resolve the theme for a profile.
    Starts from the named preset, then applies per-field overrides.

    Handles two formats:
      New: profile["theme"] is a dict  {"preset": "dark", "color_bg": "#0d1117", ...}
      Old: profile["theme"] is a str   "dark"  (legacy Streamlit config format)
    """
    raw = profile.get("theme", {})

    # Legacy format: theme was stored as a plain string preset name
    if isinstance(raw, str):
        preset_name = raw if raw in PRESETS else "dark"
        return dict(PRESETS[preset_name])

    # Expected format: dict with optional preset + overrides
    preset_name = raw.get("preset", "dark")
    base        = dict(PRESETS.get(preset_name, PRESETS["dark"]))
    base.update(raw)
    return base


def normalize_asset_path(path: str) -> str:
    """
    Convert any user-supplied asset path to an absolute URL path.

    The browser resolves url() in CSS and src= in HTML relative to the
    current page URL — not the server root. This breaks relative paths
    when the page URL is /plugin/something rather than /.

    Examples:
        "images/bg.jpg"          -> "/images/bg.jpg"
        "static/logo.png"        -> "/static/logo.png"
        "bg.jpg"                 -> "/images/bg.jpg"  (bare filename: assume images/)
        "/images/bg.jpg"         -> "/images/bg.jpg"  (already absolute: unchanged)
        "http://example.com/x"   -> "http://example.com/x"  (full URL: unchanged)
    """
    path = path.strip()
    if not path:
        return ""
    # Already absolute — pass through unchanged
    if path.startswith(("http://", "https://", "/")):
        return path
    # Has a directory component — just prepend /
    if "/" in path:
        return "/" + path
    # Bare filename with no directory — assume images/
    return "/images/" + path


def generate_css(theme: dict) -> str:
    """Generate a CSS :root override block from a theme dict."""
    t     = theme
    scale = float(t.get("space_scale", 1.0))
    font  = int(t.get("font_size_base", 14))
    sw    = int(t.get("sidebar_width", 220))
    br    = BORDER_RADIUS_MAP.get(t.get("border_radius", "medium"),
                                   BORDER_RADIUS_MAP["medium"])

    spaces = {
        "--space-xs":  round(4  * scale, 1),
        "--space-sm":  round(8  * scale, 1),
        "--space-md":  round(12 * scale, 1),
        "--space-lg":  round(20 * scale, 1),
        "--space-xl":  round(28 * scale, 1),
        "--space-2xl": round(40 * scale, 1),
    }

    lines = [":root {"]

    color_map = {
        "--color-bg":             t.get("color_bg"),
        "--color-surface":        t.get("color_surface"),
        "--color-surface-raised": t.get("color_surface_raised"),
        "--color-border":         t.get("color_border"),
        "--color-fg":             t.get("color_fg"),
        "--color-fg-muted":       t.get("color_fg_muted"),
        "--color-accent":         t.get("color_accent"),
        "--color-success":        t.get("color_success"),
        "--color-error":          t.get("color_error"),
        "--color-warning":        t.get("color_warning"),
    }
    for var, val in color_map.items():
        if val:
            lines.append(f"    {var}: {val};")

    lines.append(f"    --font-size-base: {font}px;")
    for var, val in spaces.items():
        lines.append(f"    {var}: {val}px;")
    lines.append(f"    --sidebar-width: {sw}px;")
    lines.append(f"    --border-radius-sm: {br['sm']};")
    lines.append(f"    --border-radius-md: {br['md']};")
    lines.append(f"    --border-radius-lg: {br['lg']};")
    lines.append("}")

    bg_image = t.get("bg_image", "").strip()
    if bg_image:
        opacity  = float(t.get("bg_image_opacity", 0.15))
        bg_color = t.get("color_bg", "#0d1117")

        # Normalize to an absolute URL so CSS url() works from any page.
        # Browser resolves CSS url() relative to the current page URL, not
        # the server root. A relative path breaks on /plugin/* pages.
        # Rule: anything not already absolute gets a leading / prepended.
        bg_url = normalize_asset_path(bg_image)

        lines.append(f"""
body {{
    background-image: url('{bg_url}');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
}}
body::before {{
    content: '';
    position: fixed;
    inset: 0;
    background-color: {bg_color};
    opacity: {round(1.0 - opacity, 2)};
    z-index: -1;
    pointer-events: none;
}}""")

    return "\n".join(lines)


def get_style_block(profile: dict) -> str:
    """Return a complete <style>...</style> string ready for <head>."""
    theme = get_theme(profile)
    css   = generate_css(theme)
    return f"<style>\n/* JagDash theme */\n{css}\n</style>"


def preset_names() -> list:
    return list(PRESETS.keys())


def get_preset(name: str) -> dict:
    return dict(PRESETS.get(name, PRESETS["dark"]))
