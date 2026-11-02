from __future__ import annotations

import argparse
import difflib
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

# =============================================================================
# CONFIGURAÇÕES PADRÃO (podem ser sobrescritas via linha de comando CLI)
# =============================================================================
ARQUIVO_ENTRADA = "dados.csv"          # <-- ajuste o nome do seu arquivo consolidado
SEPARADOR_ENTRADA = "|"
ENCODING_ENTRADA = "utf-8"             # mude para 'latin1' se der erro de encoding

# Se quiser restringir o pareamento a registros com datas próximas,
# altere a tolerância (ex: 5 = só pareia se a diferença for <= 5 dias).
# 9999 significa "sem limite".
TOLERANCIA_DIAS = 9999
# =============================================================================


def parse_valor(valor_str: object) -> float:
    """
    Converte valor brasileiro ou contábil para float com precisão de 2 casas decimais.
    Exemplos:
      '1.234,56'     -> 1234.56
      '24,70'        -> 24.70
      'R$ 1.500,00'  -> 1500.00
      '(350,00)'     -> -350.00
      '- 120,00'     -> -120.00
    """
    if valor_str is None or (pd is not None and pd.isna(valor_str)):
        return 0.0
    s = str(valor_str).strip()
    if not s:
        return 0.0

    # Trata parênteses de notação contábil negativa: (100,00) -> -100.00
    eh_negativo = False
    if s.startswith("(") and s.endswith(")"):
        eh_negativo = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        eh_negativo = True
        s = s[1:].strip()
    elif s.endswith("-"):
        eh_negativo = True
        s = s[:-1].strip()

    # Remove símbolos de moeda e caracteres que não sejam dígitos, vírgula ou ponto
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return 0.0

    # Normalização de pontuação
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # Padrão brasileiro: 1.234,56 -> remove '.' de milhar e troca vírgula decimal por ponto
            s = s.replace(".", "").replace(",", ".")
        else:
            # Padrão internacional: 1,234.56 -> remove ',' de milhar
            s = s.replace(",", "")
    elif "," in s:
        # Apenas vírgula: decimal brasileiro (ex: 24,70 -> 24.70)
        s = s.replace(",", ".")

    try:
        num = float(s)
        if eh_negativo:
            num = -num
        return round(num, 2)
    except ValueError:
        return 0.0


def parse_data(data_str: object) -> pd.Timestamp:
    """
    Converte dd/mm/yyyy para pd.Timestamp normalizado (sem horas residuais).
    Suporta formatos DD/MM/YYYY, YYYY-MM-DD e com timestamps de hora.
    """
    if pd.isna(data_str):
        return pd.NaT
    if isinstance(data_str, (pd.Timestamp, datetime)):
        return pd.Timestamp(data_str).normalize()

    s = str(data_str).strip()
    if not s:
        return pd.NaT

    # Tenta padrão brasileiro DD/MM/YYYY primeiro
    ts = pd.to_datetime(s, format="%d/%m/%Y", dayfirst=True, errors="coerce")
    if pd.isna(ts):
        # Fallback genérico para outros formatos (ISO YYYY-MM-DD, etc.)
        ts = pd.to_datetime(s, dayfirst=True, errors="coerce")

    if pd.notna(ts):
        return ts.normalize()
    return pd.NaT


def calcular_similaridade(texto_a: str, texto_b: str) -> float:
    """
    Calcula razão de similaridade textual entre 0.0 e 1.0 (usada para desempate).
    """
    a = (texto_a or "").strip().lower()
    b = (texto_b or "").strip().lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def carregar_arquivo_individual(
    caminho: str | Path,
    sep: str = SEPARADOR_ENTRADA,
    encoding: str = ENCODING_ENTRADA,
    origem_padrao: str | None = None,
) -> pd.DataFrame:
    """Lê um CSV individual e faz limpeza básica de espaços."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    df = pd.read_csv(
        caminho,
        sep=sep,
        dtype=str,
        encoding=encoding,
    )
    # Limpa espaços em branco dos nomes de colunas e dados
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    # Se uma origem padrão for informada e a coluna não existir, define
    if origem_padrao and ("Origem" not in df.columns or df["Origem"].isna().all()):
        df["Origem"] = origem_padrao

    return df


def carregar_dados(
    caminho: str | Path | None = None,
    extrato_path: str | Path | None = None,
    siga_path: str | Path | None = None,
    sep: str = SEPARADOR_ENTRADA,
    encoding: str = ENCODING_ENTRADA,
) -> pd.DataFrame:
    """
    Carrega os dados de entrada suportando:
    1. Arquivo único consolidado (contendo a coluna 'Origem').
    2. Dois arquivos separados (Extrato e SIGA).
    """
    if extrato_path and siga_path:
        print(f"Lendo arquivos separados:\n  - Extrato: {extrato_path}\n  - SIGA:    {siga_path}")
        df_ext = carregar_arquivo_individual(extrato_path, sep=sep, encoding=encoding, origem_padrao="EXTRATO")
        df_sig = carregar_arquivo_individual(siga_path, sep=sep, encoding=encoding, origem_padrao="SIGA")
        df = pd.concat([df_ext, df_sig], ignore_index=True)
    elif caminho:
        print(f"Lendo arquivo consolidado: {caminho}")
        df = carregar_arquivo_individual(caminho, sep=sep, encoding=encoding)
    else:
        print(f"Lendo arquivo padrão: {ARQUIVO_ENTRADA}")
        df = carregar_arquivo_individual(ARQUIVO_ENTRADA, sep=sep, encoding=encoding)

    # Validação de colunas obrigatórias
    colunas_obrigatorias = ["Data", "Valor", "Origem"]
    faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"O arquivo não contém as colunas obrigatórias: {', '.join(faltantes)}.\n"
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Garante a existência das colunas opcionais úteis
    for col_opc in ["Historico", "Documento", "Status"]:
        if col_opc not in df.columns:
            df[col_opc] = ""

    return df


def conciliar_extrato_siga(df: pd.DataFrame, tolerancia_dias: int = TOLERANCIA_DIAS):
    """
    Executa a conciliação entre EXTRATO e SIGA.
    Critérios de pareamento:
    1. Igualdade exata de valor monetário (valor_num).
    2. Menor diferença em dias entre lançamentos (<= tolerancia_dias).
    3. Desempate inteligente: coincidência de número de Documento e maior similaridade de Histórico.
    """
    # -------------------------------------------------------------------------
    # Normalização
    # -------------------------------------------------------------------------
    df["data_dt"] = df["Data"].apply(parse_data)
    df["valor_num"] = df["Valor"].apply(parse_valor)

    # Descarta linhas com data nula ou inválida
    linhas_sem_data = df["data_dt"].isna().sum()
    if linhas_sem_data > 0:
        print(f"[aviso] {linhas_sem_data} linha(s) com data inválida foram ignoradas.", file=sys.stderr)
        df = df.dropna(subset=["data_dt"]).copy()

    # Separa as origens
    df_ext = df[df["Origem"].str.upper() == "EXTRATO"].copy().reset_index(drop=True)
    df_sig = df[df["Origem"].str.upper() == "SIGA"].copy().reset_index(drop=True)

    # IDs internos para rastreamento
    df_ext["id_int"] = [f"EXT_{i:05d}" for i in range(len(df_ext))]
    df_sig["id_int"] = [f"SIG_{i:05d}" for i in range(len(df_sig))]

    # -------------------------------------------------------------------------
    # Conciliação por valor + proximidade de data + desempate
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

        # Monta todos os candidatos possíveis
        candidatos = []
        for e in ext_idx:
            d_e = sub_ext.loc[e, "data_dt"]
            doc_e = str(sub_ext.loc[e, "Documento"]).strip().lower()
            hist_e = str(sub_ext.loc[e, "Historico"]).strip()

            for s in sig_idx:
                d_s = sub_sig.loc[s, "data_dt"]
                diff = abs((d_e - d_s).days)
                if diff <= tolerancia_dias:
                    doc_s = str(sub_sig.loc[s, "Documento"]).strip().lower()
                    hist_s = str(sub_sig.loc[s, "Historico"]).strip()

                    # Desempate 1: Documento coincidente não vazio tem prioridade (0 = match, 1 = sem match)
                    tem_match_doc = 0 if (doc_e and doc_s and doc_e == doc_s) else 1

                    # Desempate 2: Maior similaridade de texto no histórico (invertido para ordenação crescente)
                    sim_hist = calcular_similaridade(hist_e, hist_s)

                    candidatos.append((diff, tem_match_doc, -sim_hist, e, s))

        # Ordena: 1º menor delta de dias, 2º documento coincidente, 3º maior similaridade de histórico
        candidatos.sort(key=lambda x: (x[0], x[1], x[2]))

        usados_e = set()
        usados_s = set()
        pares_formados = []

        for diff, _, _, e, s in candidatos:
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
                "documento_extrato": row_e["Documento"],
                "valor": row_e["valor_num"],
                "data_siga": row_s["Data"],
                "historico_siga": row_s["Historico"],
                "documento_siga": row_s["Documento"],
                "diferenca_dias": diff,
                "status": "CONCILIADO",
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
                    "status_original": row["Status"],
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
                    "status_original": row["Status"],
                })

    df_conc = pd.DataFrame(registros_conciliados)
    df_pend_ext = pd.DataFrame(pendentes_ext)
    df_pend_sig = pd.DataFrame(pendentes_sig)

    return df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig


def exportar_excel(
    df_conc: pd.DataFrame,
    df_pend_ext: pd.DataFrame,
    df_pend_sig: pd.DataFrame,
    df_ext: pd.DataFrame,
    df_sig: pd.DataFrame,
    caminho_excel: str,
):
    """
    Gera uma pasta de trabalho Excel consolidada (.xlsx) com múltiplas abas:
    Resumo, Conciliados, Pendentes Extrato e Pendentes SIGA.
    """
    try:
        total_ext = df_ext["valor_num"].sum() if "valor_num" in df_ext.columns else 0.0
        total_sig = df_sig["valor_num"].sum() if "valor_num" in df_sig.columns else 0.0
        total_conc = df_conc["valor"].sum() if not df_conc.empty and "valor" in df_conc.columns else 0.0
        total_pend_ext = df_pend_ext["valor"].sum() if not df_pend_ext.empty and "valor" in df_pend_ext.columns else 0.0
        total_pend_sig = df_pend_sig["valor"].sum() if not df_pend_sig.empty and "valor" in df_pend_sig.columns else 0.0

        df_resumo = pd.DataFrame([
            {"Indicador": "Total EXTRATO", "Quantidade": len(df_ext), "Valor Total (R$)": total_ext},
            {"Indicador": "Total SIGA", "Quantidade": len(df_sig), "Valor Total (R$)": total_sig},
            {"Indicador": "Conciliado (Pares)", "Quantidade": len(df_conc), "Valor Total (R$)": total_conc},
            {"Indicador": "Pendente no EXTRATO", "Quantidade": len(df_pend_ext), "Valor Total (R$)": total_pend_ext},
            {"Indicador": "Pendente no SIGA", "Quantidade": len(df_pend_sig), "Valor Total (R$)": total_pend_sig},
            {"Indicador": "Diferença Geral (Extrato - SIGA)", "Quantidade": abs(len(df_ext) - len(df_sig)), "Valor Total (R$)": abs(total_ext - total_sig)},
        ])

        with pd.ExcelWriter(caminho_excel, engine="openpyxl") as writer:
            df_resumo.to_excel(writer, sheet_name="Resumo", index=False)
            df_conc.to_excel(writer, sheet_name="Conciliados", index=False)
            df_pend_ext.to_excel(writer, sheet_name="Pendentes_Extrato", index=False)
            df_pend_sig.to_excel(writer, sheet_name="Pendentes_SIGA", index=False)

        print(f"  • Planilha Excel consolidada: {caminho_excel}")
    except ImportError:
        print("  [aviso] Biblioteca openpyxl não encontrada. Instale com 'pip install openpyxl' para gerar arquivo .xlsx.")
    except Exception as e:
        print(f"  [aviso] Não foi possível exportar Excel (.xlsx): {e}")


def criar_parser() -> argparse.ArgumentParser:
    """Configura e retorna os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Conciliação Financeira automatizada entre EXTRATO bancário e sistema SIGA.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Entrada de arquivos
    parser.add_argument(
        "arquivo",
        nargs="?",
        default=None,
        help="Caminho do arquivo CSV consolidado de entrada (ex: dados.csv).",
    )
    parser.add_argument(
        "--extrato",
        type=str,
        default=None,
        help="Caminho do arquivo do EXTRATO bancário (usado em conjunto com --siga).",
    )
    parser.add_argument(
        "--siga",
        type=str,
        default=None,
        help="Caminho do arquivo do sistema SIGA (usado em conjunto com --extrato).",
    )
    parser.add_argument(
        "--sep",
        type=str,
        default=SEPARADOR_ENTRADA,
        help="Separador/delimitador de colunas dos arquivos de entrada.",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default=ENCODING_ENTRADA,
        help="Codificação dos arquivos de entrada ('utf-8', 'latin1', etc.).",
    )
    parser.add_argument(
        "--tolerancia",
        type=int,
        default=TOLERANCIA_DIAS,
        help="Tolerância máxima de diferença de dias para conciliação (9999 = sem limite).",
    )
    # Saídas
    parser.add_argument(
        "--excel",
        type=str,
        default=None,
        help="Caminho opcional para gerar pasta de trabalho Excel (.xlsx) com múltiplas abas.",
    )
    parser.add_argument(
        "--prefixo-saida",
        type=str,
        default="",
        help="Prefixo customizado para os arquivos CSV gerados (ex: 'agosto_').",
    )
    return parser


def main(argv=None):
    parser = criar_parser()
    args = parser.parse_args(argv)

    if pd is None:
        print("[erro] A biblioteca 'pandas' é obrigatória para processar a conciliação.", file=sys.stderr)
        print("Instale as dependências executando: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    # Identifica fonte de dados
    caminho_arquivo = args.arquivo
    # Se nenhum arquivo foi passado e não há --extrato e --siga, verifica se existe dados.csv ou extrato.csv/siga.csv
    if not caminho_arquivo and not (args.extrato and args.siga):
        if Path("extrato.csv").exists() and Path("siga.csv").exists():
            args.extrato = "extrato.csv"
            args.siga = "siga.csv"
        else:
            caminho_arquivo = ARQUIVO_ENTRADA

    df = carregar_dados(
        caminho=caminho_arquivo,
        extrato_path=args.extrato,
        siga_path=args.siga,
        sep=args.sep,
        encoding=args.encoding,
    )

    print(f"Processando conciliação (Tolerância: {args.tolerancia} dias)...")
    df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig = conciliar_extrato_siga(
        df, tolerancia_dias=args.tolerancia
    )

    # -------------------------------------------------------------------------
    # Exportação CSV
    # -------------------------------------------------------------------------
    pfx = args.prefixo_saida
    arq_conc = f"{pfx}01_conciliados.csv"
    arq_pend_ext = f"{pfx}02_pendentes_extrato.csv"
    arq_pend_sig = f"{pfx}03_pendentes_siga.csv"

    # Usa ; como separador e , como decimal para abrir direto no Excel BR
    df_conc.to_csv(arq_conc, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    df_pend_ext.to_csv(arq_pend_ext, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    df_pend_sig.to_csv(arq_pend_sig, index=False, sep=";", decimal=",", encoding="utf-8-sig")

    # -------------------------------------------------------------------------
    # Exportação Excel (.xlsx) opcional
    # -------------------------------------------------------------------------
    if args.excel:
        exportar_excel(df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig, args.excel)

    # -------------------------------------------------------------------------
    # Resumo no console
    # -------------------------------------------------------------------------
    total_ext = df_ext["valor_num"].sum() if "valor_num" in df_ext.columns else 0.0
    total_sig = df_sig["valor_num"].sum() if "valor_num" in df_sig.columns else 0.0
    total_conc = df_conc["valor"].sum() if not df_conc.empty and "valor" in df_conc.columns else 0.0
    total_pend_ext = df_pend_ext["valor"].sum() if not df_pend_ext.empty and "valor" in df_pend_ext.columns else 0.0
    total_pend_sig = df_pend_sig["valor"].sum() if not df_pend_sig.empty and "valor" in df_pend_sig.columns else 0.0

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
    print(f"  • {arq_conc}")
    print(f"  • {arq_pend_ext}")
    print(f"  • {arq_pend_sig}")


if __name__ == "__main__":
    main()
