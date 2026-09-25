FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System dependencies for building and running common Python packages (e.g.
# psycopg2), plus poppler-utils: pdf2image (app/ingestion/multimodal.py's
# PDF -> image conversion for /ingest/image) shells out to poppler's
# pdftoppm/pdfinfo binaries and raises PDFInfoNotInstalledError without it —
# PDF ingestion was silently broken in this image despite requirements.txt
# documenting the dependency.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    poppler-utils \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY .env.example ./.env

EXPOSE 8000

# Default command runs the FastAPI app; worker can override this CMD.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

