from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_settings

settings = get_settings()
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
TEMPLATE_NAME = "relatorio_template.html"


def _replace_inline_data(template: str, report_json: dict[str, Any]) -> str:
    data = json.dumps(report_json, ensure_ascii=False, separators=(",", ":"))
    pattern = r"const\s+DATA\s*=\s*\{.*?\};"
    replacement = f"const DATA = {data};"
    rendered, count = re.subn(pattern, replacement, template, count=1, flags=re.DOTALL)
    if count:
        return rendered
    return template.replace("</script>", f"\nconst DATA = {data};\n</script>", 1)


def render_report_html(relatorio_id: int, report_json: dict[str, Any]) -> str:
    template_path = TEMPLATES_DIR / TEMPLATE_NAME
    if not template_path.exists():
        raise FileNotFoundError(f"Template de relatório não encontrado: {template_path}")

    template_text = template_path.read_text(encoding="utf-8")

    if "const DATA" in template_text:
        html = _replace_inline_data(template_text, report_json)
    else:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        html = env.get_template(TEMPLATE_NAME).render(report=report_json)

    relative_dir = Path("reports") / str(relatorio_id)
    output_dir = settings.output_path / relative_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "relatorio_semanal_obra.html"
    output_file.write_text(html, encoding="utf-8")

    return str(relative_dir / output_file.name)
