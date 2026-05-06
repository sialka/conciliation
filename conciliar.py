"""














"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def carregar_csv(
    caminho: Path,
    col_data: str,
    col_valor: str,
    sep: str,
    decimal: str,
    formato_data: str | None,
) -> pd.DataFrame:    
    df = pd.read_csv(caminho, sep=sep, decimal=decimal, dtype=str)
    
    faltantes = [c for c in (col_data, col_valor) if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Arquivo '{caminho}' não contém as colunas obrigatórias: {', '.join(faltantes)}"
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Normaliza data e valor, tratando erros como NaT/NaN
    df[col_data] = pd.to_datetime(
        df[col_data], format=formato_data, errors='coerce', dayfirst=formato_data is None
    ).dt.date

    # Normaliza valor, removendo espaços e convertendo para numérico, tratando erros como NaN
    valores = (
        df[col_valor]
        .astype(str)
        .str.strip()
        .str.replace(" ", "", regex=False)
    )
    if decimal == ",":
        valores = valores.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    df[col_valor] = pd.to_numeric(valores, errors='coerce').round(2)

    invalidos = df[df[col_data].isna() | df[col_valor].isna()]
    if not invalidos.empty:
        print(
            f"[aviso] {len(invalidos)} linha(s) de '{caminho.name}' foram descartadas."
            f"por data/valor inválidos.", 
            file=sys.stderr
        )
        df = df.dropna(subset=[col_data, col_valor]).reset_index(drop=True)

    return df


def conciliar(
    df_a: pd.DataFrame, 
    df_b: pd.DataFrame, 
    col_data: str, 
    col_valor: str
)-> pd.DataFrame:
    """
    Faz
    é
    indicado
    """
    chave = [col_data, col_valor]

    contagem_a = df_a.groupby(chave).size().rename('qtd_a')
    contagem_b = df_b.groupby(chave).size().rename('qtd_b')
   
    junto = pd.concat([contagem_a, contagem_b], axis=1).fillna(0).astype(int)
    junto['sobra_a'] = (junto['qtd_a'] - junto['qtd_b']).clip(lower=0)
    junto['sobra_b'] = (junto['qtd_b'] - junto['qtd_a']).clip(lower=0)

    sobras_a = junto.loc[junto['sobra_a'] > 0, ['sobra_a']].reset_index()
    sobras_b = junto.loc[junto['sobra_b'] > 0, ['sobra_b']].reset_index()

    nao_conc_a = sobras_a.loc[
       sobras_a.index.repeat(sobras_a['sobra_a'])
    ][chave].assign(origem='A')

    nao_conc_b = sobras_b.loc[
        sobras_b.index.repeat(sobras_b['sobra_b'])
    ][chave].assign(origem='B')

    resultado = pd.concat([nao_conc_a, nao_conc_b], ignore_index=True)
    resultado = resultado.sort_values(by=[col_data, col_valor, "origem"]).reset_index(drop=True)
    return resultado


def main() -> init:
    parser = argparse.ArgumentParser(description="Conciliar 2 CSVs por (data, valor).")
    parser.add_argument("arquivo_a", type=Path, help="Caminho para o primeiro arquivo CSV.")
    parser.add_argument("arquivo_b", type=Path, help="Caminho para o segundo arquivo CSV.")
    parser.add_argument("--col-data", default="data", help="Nome da coluna de data nos arquivos CSV.") 
    parser.add_argument("--col-valor",default="valor", help="Nome da coluna de valor nos arquivos CSV.")  
    parser.add_argument("--sep", default=",", help="Separador do CSV (default: ',').")
    parser.add_argument("--decimal",  default=".",  help="Separador decimal (default: '.').")
    parser.add_argument(
        "--formato-data", 
        default=None, 
        help="Formato da data (default: '%%d/%%m/%%Y'). Se omitido, tenta detectar."    
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("nao_conciliação.csv"),
        help="Arquivo de saída (default: nao_conciliacao.csv).",
    )
    args = parser.parse_args()

    try:
        df_a = carregar_csv(args.arquivo_a, args.col_data, args.col_valor, args.sep, args.decimal, args.formato_data)
        df_b = carregar_csv(args.arquivo_b, args.col_data, args.col_valor, args.sep, args.decimal, args.formato_data)
    except (FileNotFoundError, ValueError) as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 1
    
    resultado = conciliar(df_a, df_b, args.col_data, args.col_valor)    

    resultado.to_csv(args.saida, sep=args.sep, index=False)

    total_a = (resultado['origem'] == 'A').sum()
    total_b = (resultado['origem'] == 'B').sum()
    print(f"Registros em A: {len(df_a)} | Registros em B: {len(df_b)}")
    print(f"Não conciliados em A: {total_a}")
    print(f"Não conciliados em B: {total_b}")
    print(f"Total não conciliados: {len(resultado)}")
    print(f"Arquivo gerado: {args.saida.resolve()}")
    return 0
    

if __name__ == "__main__":
    raise SystemExit(main())