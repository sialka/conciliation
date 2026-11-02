#!/usr/bin/env bash
set -e

COMPETENCIA="${1:-08-2026}"
ORIGEM_WIN="/mnt/c/Users/sidnei/Desktop/CCB/${COMPETENCIA}"

if [ -d "$ORIGEM_WIN" ]; then
    echo "Copiando arquivos da competência $COMPETENCIA de $ORIGEM_WIN..."
    cp "$ORIGEM_WIN"/*.csv . 2>/dev/null || true
else
    echo "Aviso: Diretório $ORIGEM_WIN não acessível. Utilizando arquivos locais."
fi

if [ -f "extrato.csv" ] && [ -f "siga.csv" ]; then
    echo "Executando conciliação com extrato.csv e siga.csv..."
    python3 conciliar.py --extrato extrato.csv --siga siga.csv --excel conciliacao_resultado.xlsx
elif [ -f "dados.csv" ]; then
    echo "Executando conciliação com dados.csv..."
    python3 conciliar.py dados.csv --excel conciliacao_resultado.xlsx
else
    python3 conciliar.py --excel conciliacao_resultado.xlsx
fi
