from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DICTIONARY_DIR = BASE_DIR / "data" / "dictionaries"

FILES = {
    "ocr": "ocr_common_errors.txt",
    "context": "context_terms.txt",
}


def get_dictionary_path(kind: str) -> Path:
    if kind not in FILES:
        raise KeyError(f"Dicionário inválido: {kind}")
    return DICTIONARY_DIR / FILES[kind]


def read_dictionary(kind: str) -> str:
    path = get_dictionary_path(kind)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_dictionary(kind: str, content: str) -> None:
    path = get_dictionary_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")


def load_dictionaries_context() -> dict[str, str]:
    return {
        "erros_ocr_conhecidos": read_dictionary("ocr"),
        "dicionario_tecnico": read_dictionary("context"),
    }
