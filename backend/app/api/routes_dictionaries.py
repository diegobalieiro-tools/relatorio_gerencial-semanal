from fastapi import APIRouter, HTTPException

from app.schemas.dictionary_schema import DictionaryOut, DictionaryUpdate
from app.services.dictionary_service import read_dictionary, write_dictionary

router = APIRouter(prefix="/api/dictionaries", tags=["Dicionários"])


@router.get("/{kind}", response_model=DictionaryOut)
def get_dictionary(kind: str):
    if kind not in {"ocr", "context"}:
        raise HTTPException(status_code=404, detail="Dicionário não encontrado")
    return DictionaryOut(name=kind, content=read_dictionary(kind))


@router.put("/{kind}", response_model=DictionaryOut)
def update_dictionary(kind: str, payload: DictionaryUpdate):
    if kind not in {"ocr", "context"}:
        raise HTTPException(status_code=404, detail="Dicionário não encontrado")
    write_dictionary(kind, payload.content)
    return DictionaryOut(name=kind, content=payload.content)
