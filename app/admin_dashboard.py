from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "admin_dashboard.html"


def render_admin_dashboard_html() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")
