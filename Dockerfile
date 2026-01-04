# Usa Python Alpine per massima leggerezza
FROM python:3.11-alpine

# Variabili d'ambiente per evitare file .pyc e buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Installa dipendenze
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice e file di configurazione base
COPY src/ ./src/
COPY series.json .
# Non copiamo .env, verrà passato runtime o montato

# Crea cartella data per il volume
RUN mkdir data

# Comando di avvio
CMD ["python", "src/main.py"]