#!/usr/bin/env bash
set -e

COMPETENCIA="${1:-08-2026}"
DESTINO_WIN="/mnt/c/Users/sidnei/Desktop/CCB/${COMPETENCIA}"

if [ -d "$DESTINO_WIN" ]; then
    echo "Copiando relatórios para $DESTINO_WIN..."
    cp 01_conciliados.csv 02_pendentes_extrato.csv 03_pendentes_siga.csv "$DESTINO_WIN"/ 2>/dev/null || true
    cp *.xlsx "$DESTINO_WIN"/ 2>/dev/null || true
    echo "Envio concluído com sucesso."
else
    echo "Aviso: Diretório de destino $DESTINO_WIN não acessível. Relatórios mantidos na pasta local."
fi
