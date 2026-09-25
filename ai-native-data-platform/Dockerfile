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
# NOTE: .env.example is intentionally not copied into the image as .env.
# Real deployments pass configuration via actual environment variables
# (docker-compose's `environment:`, k8s Secrets) — those always take
# priority over an env_file's values in pydantic-settings, so this never
# changed what a properly configured deployment ran with. But baking a
# dotenv file into every build meant an image run with no environment
# configured at all silently started on mock providers and demo
# credentials instead of failing loudly, and permanently commits whatever
# is in that file to the image's layers.

# Run as a non-root user. bulk-indexing (scripts/run_bulk_index.py) writes
# manifest files under ./data, so the app directory is chowned to this
# user rather than just switching UID.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
  && chown -R app:app /app
USER app

EXPOSE 8000

# Default command runs the FastAPI app; worker can override this CMD.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

