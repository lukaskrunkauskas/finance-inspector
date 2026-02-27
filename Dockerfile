#  1. Starts from python:3.11-slim (a lightweight Python base image)           2. Installs libgomp1 — a native dependency required by pdfplumber/pdfminer
 #  3. Installs Python dependencies from requirements-docker.txt
 #  4. Copies and installs the project itself (pip install -e . using
 #  pyproject.toml)
 #  5. Copies app.py and creates the data/statements/ directory
 #  6. Exposes port 8501 and starts Streamlit on container launch
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

COPY app.py .

RUN mkdir -p data/statements

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]