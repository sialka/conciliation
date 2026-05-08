import pandas as pd
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
ARQUIVO_ENTRADA = "dados.csv"          # <-- ajuste o nome do seu arquivo
SEPARADOR_ENTRADA = "|"
ENCODING_ENTRADA = "utf-8"             # mude para 'latin1' se der erro de encoding

# Se quiser restringir o pareamento a registros com datas próximas,
# altere a tolerância (ex: 5 = só pareia se a diferença for <= 5 dias).
# 9999 significa "sem limite".
TOLERANCIA_DIAS = 9999
# =============================================================================


def parse_valor(valor_str: str) -> float:
    """
    Converte valor brasileiro para float.
    Exemplos: '1.234,56' -> 1234.56 | '24,70' -> 24.70
    """
    if pd.isna(valor_str):
        return 0.0
    s = str(valor_str).strip()
    # remove pontos de milhar, troca vírgula decimal por ponto
    s = s.replace(".", "").replace(",", ".")
    return float(s)


def parse_data(data_str: str) -> pd.Timestamp:
    """Converte dd/mm/yyyy para datetime."""
    return pd.to_datetime(data_str, format="%d/%m/%Y", dayfirst=True)


def carregar_dados(caminho: str) -> pd.DataFrame:
    """Lê o CSV e faz limpeza básica."""
    df = pd.read_csv(
        caminho,
        sep=SEPARADOR_ENTRADA,
        dtype=str,
        encoding=ENCODING_ENTRADA
    )
    # limpa espaços das colunas e strings
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    return df


def conciliar_extrato_siga(df: pd.DataFrame):
    """
    Executa a conciliação entre EXTRATO e SIGA.
    Retorna 4 DataFrames: conciliados, pendentes_ext, pendentes_sig,
    além dos dados brutos parseados.
    """
    # -------------------------------------------------------------------------
    # Normalização
    # -------------------------------------------------------------------------
    df["data_dt"] = df["Data"].apply(parse_data)
    df["valor_num"] = df["Valor"].apply(parse_valor)

    # Separa as origens
    df_ext = df[df["Origem"].str.upper() == "EXTRATO"].copy().reset_index(drop=True)
    df_sig = df[df["Origem"].str.upper() == "SIGA"].copy().reset_index(drop=True)

    # IDs internos para rastreamento
    df_ext["id_int"] = [f"EXT_{i:05d}" for i in range(len(df_ext))]
    df_sig["id_int"] = [f"SIG_{i:05d}" for i in range(len(df_sig))]

    # -------------------------------------------------------------------------
    # Conciliação por valor + proximidade de data
    # -------------------------------------------------------------------------
    registros_conciliados = []
    pendentes_ext = []
    pendentes_sig = []

    # Valores distintos presentes em uma ou outra origem
    valores = set(df_ext["valor_num"].unique()) | set(df_sig["valor_num"].unique())

    for valor in valores:
        sub_ext = df_ext[df_ext["valor_num"] == valor]
        sub_sig = df_sig[df_sig["valor_num"] == valor]

        ext_idx = sub_ext.index.tolist()
        sig_idx = sub_sig.index.tolist()

        # Monta todos os candidatos possíveis (diff de datas)
        candidatos = []
        for e in ext_idx:
            d_e = sub_ext.loc[e, "data_dt"]
            for s in sig_idx:
                d_s = sub_sig.loc[s, "data_dt"]
                diff = abs((d_e - d_s).days)
                if diff <= TOLERANCIA_DIAS:
                    candidatos.append((diff, e, s))

        # Ordena do menor para o maior delta de dias
        candidatos.sort(key=lambda x: x[0])

        usados_e = set()
        usados_s = set()
        pares_formados = []

        for diff, e, s in candidatos:
            if e not in usados_e and s not in usados_s:
                pares_formados.append((e, s, diff))
                usados_e.add(e)
                usados_s.add(s)

        # Registra conciliados
        for e, s, diff in pares_formados:
            row_e = sub_ext.loc[e]
            row_s = sub_sig.loc[s]
            registros_conciliados.append({
                "id_par": f"PAR_{len(registros_conciliados):05d}",
                "data_extrato": row_e["Data"],
                "historico_extrato": row_e["Historico"],
                "valor": row_e["valor_num"],
                "data_siga": row_s["Data"],
                "historico_siga": row_s["Historico"],
                "diferenca_dias": diff,
                "status": "CONCILIADO"
            })

        # Registra pendentes do EXTRATO
        for e in ext_idx:
            if e not in usados_e:
                row = sub_ext.loc[e]
                pendentes_ext.append({
                    "id": row["id_int"],
                    "data": row["Data"],
                    "historico": row["Historico"],
                    "documento": row["Documento"],
                    "valor": row["valor_num"],
                    "status_original": row["Status"]
                })

        # Registra pendentes do SIGA
        for s in sig_idx:
            if s not in usados_s:
                row = sub_sig.loc[s]
                pendentes_sig.append({
                    "id": row["id_int"],
                    "data": row["Data"],
                    "historico": row["Historico"],
                    "documento": row["Documento"],
                    "valor": row["valor_num"],
                    "status_original": row["Status"]
                })

    df_conc = pd.DataFrame(registros_conciliados)
    df_pend_ext = pd.DataFrame(pendentes_ext)
    df_pend_sig = pd.DataFrame(pendentes_sig)

    return df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig


def main():
    print(f"Lendo arquivo: {ARQUIVO_ENTRADA}")
    df = carregar_dados(ARQUIVO_ENTRADA)

    print("Processando conciliação...")
    df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig = conciliar_extrato_siga(df)

    # -------------------------------------------------------------------------
    # Exportação
    # -------------------------------------------------------------------------
    # Usa ; como separador e , como decimal para abrir direto no Excel BR
    df_conc.to_csv("01_conciliados.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
    df_pend_ext.to_csv("02_pendentes_extrato.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
    df_pend_sig.to_csv("03_pendentes_siga.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")

    # -------------------------------------------------------------------------
    # Resumo no console
    # -------------------------------------------------------------------------
    total_ext = df_ext["valor_num"].sum()
    total_sig = df_sig["valor_num"].sum()
    total_conc = df_conc["valor"].sum() if not df_conc.empty else 0.0
    total_pend_ext = df_pend_ext["valor"].sum() if not df_pend_ext.empty else 0.0
    total_pend_sig = df_pend_sig["valor"].sum() if not df_pend_sig.empty else 0.0

    print("\n" + "=" * 60)
    print("RESUMO DA CONCILIAÇÃO")
    print("=" * 60)
    print(f"Total EXTRATO        : R$ {total_ext:>15,.2f}  ({len(df_ext)} regs)")
    print(f"Total SIGA           : R$ {total_sig:>15,.2f}  ({len(df_sig)} regs)")
    print("-" * 60)
    print(f"Conciliado           : R$ {total_conc:>15,.2f}  ({len(df_conc)} pares)")
    print(f"Pendente no EXTRATO  : R$ {total_pend_ext:>15,.2f}  ({len(df_pend_ext)} regs)")
    print(f"Pendente no SIGA     : R$ {total_pend_sig:>15,.2f}  ({len(df_pend_sig)} regs)")
    print("-" * 60)
    print(f"Diferença geral      : R$ {abs(total_ext - total_sig):>15,.2f}")
    print("=" * 60)
    print("\nArquivos gerados:")
    print("  • 01_conciliados.csv")
    print("  • 02_pendentes_extrato.csv")
    print("  • 03_pendentes_siga.csv")


if __name__ == "__main__":
    main()
