#!/bin/bash
cd "$(dirname "$0")"

# Install if needed
if [ ! -d "venv" ]; then
  echo "Primeira execução — instalando dependências..."
  python3 -m venv venv
  ./venv/bin/pip install --quiet flask
fi

echo "Iniciando Sistema de Estoque Pro..."
echo "Acesse: http://localhost:8080"
echo "(Feche esta janela para encerrar o sistema)"
./venv/bin/python app.py
