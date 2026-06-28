#!/bin/bash
cd "$(dirname "$0")"

# Install if needed
if [ ! -d "venv" ]; then
  echo "Primeira execução — instalando dependências..."
  python3 -m venv venv
  ./venv/bin/pip install --quiet flask gunicorn psycopg2-binary
fi

# Load .env if it exists
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Iniciando Poder Olfativo..."
echo "Acesse: http://localhost:8080"
./venv/bin/python app.py
