#!/bin/bash
echo "======================================"
echo "  Instalando Sistema de Estoque Pro"
echo "======================================"

# Check Python 3
if ! command -v python3 &>/dev/null; then
  echo "ERRO: Python 3 não encontrado. Instale em https://python.org"
  exit 1
fi

echo "Python encontrado: $(python3 --version)"

# Create virtual environment
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv venv
fi

# Install dependencies
echo "Instalando dependências..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet flask

echo ""
echo "✓ Instalação concluída!"
echo ""
echo "Para iniciar o sistema, execute: ./iniciar.sh"
echo "Ou clique duas vezes no arquivo 'iniciar.sh'"
