from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = APP_DIR / "templates" / "relatorio_template.html"
OUTPUT_ROOT = APP_DIR / "outputs" / "reports"


def _json_for_script(value: dict[str, Any] | None) -> str:
    """Serializa JSON para uso seguro dentro de <script>.

    O erro do relatório 7 ocorreu porque quebras de linha reais foram inseridas
    dentro de strings JavaScript, quebrando o `const DATA = ...` e impedindo a
    renderização. `json.dumps` mantém as quebras como `\\n` e também escapamos
    `</` para evitar fechamento acidental de script.
    """
    return json.dumps(value or {}, ensure_ascii=False, default=str).replace("</", "<\\/")


def render_report_html(relatorio_id: int, report_json: dict[str, Any]) -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template do relatório não encontrado: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_js = _json_for_script(report_json)

    if "const DATA = {};" in template:
        html = template.replace("const DATA = {};", f"const DATA = {data_js};", 1)
    else:
        html = re.sub(
            r"const\s+DATA\s*=\s*.*?;\s*(?=const\s+TABS)",
            f"const DATA = {data_js};\n\n",
            template,
            count=1,
            flags=re.DOTALL,
        )

    output_dir = OUTPUT_ROOT / str(relatorio_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "relatorio_semanal_obra.html"
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)
