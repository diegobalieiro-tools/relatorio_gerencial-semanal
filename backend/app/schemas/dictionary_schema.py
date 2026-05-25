from pydantic import BaseModel


class DictionaryOut(BaseModel):
    name: str
    content: str


class DictionaryUpdate(BaseModel):
    content: str
