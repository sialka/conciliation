cp /mnt/c/Users/sidnei/Desktop/CCB/08-2026/*.csv .

python3 conciliar.py extrato.csv siga.csv \
    --col-data Data --col-historico Historico --col-valor Valor \
    --sep "|" --decimal "," \
    --saida nao_conciliacao.csv
