# CVP · Acompanhamento Semanal

Estrutura inicial do projeto fullstack para a plataforma de acompanhamento semanal de obras da TOOLS.

## Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Observações

- O frontend inicial já possui o layout base das telas `CVP Workspace` e `Nova Obra`.
- O template final do relatório está em `backend/app/templates/relatorio_template.html`.
- Os prompts completos serão colados nos arquivos em `backend/app/prompts/` na próxima etapa.
- A pipeline GPT, persistência inteligente e migrations Alembic completas serão implementadas nas próximas etapas.
