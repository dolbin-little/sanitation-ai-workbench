FROM python:3.12-slim-bookworm

WORKDIR /app
ENV IP=0.0.0.0 \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SANITATION_REVIEW_DATADIR=/var/lib/sanitation-review

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY assistant_files.py assistant_imports.py assistant_knowledge.py assistant_service.py server.py ./
COPY assistant_knowledge/ assistant_knowledge/
COPY web/ web/
COPY drive/ drive/
COPY legacy/backend/ legacy/backend/
COPY legacy/web/ legacy/web/
COPY legacy/server.py legacy/server.py
COPY data/bc_model.json data/bc_model.json
COPY evidence/summary.json evidence/summary.json
COPY references/ references/
COPY deploy/review_server.py deploy/review_server.py

EXPOSE 8080
CMD ["python", "deploy/review_server.py"]
