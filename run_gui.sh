#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  ⚖️  Iniciando Interface Gráfica da Conciliação Financeira"
echo "=========================================================="
echo ""
echo "A interface será aberta automaticamente no seu navegador."
echo "Caso não abra, acesse no Chrome ou Edge: http://localhost:8501"
echo ""

# Verifica se streamlit está instalado
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "[aviso] Streamlit não encontrado. Instalando dependências necessárias..."
    pip install -r requirements.txt || python3 -m pip install -r requirements.txt
fi

exec streamlit run app.py --server.headless=true

