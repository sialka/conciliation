from __future__ import annotations

import io
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import streamlit as st
except ImportError:
    st = None


if st is None or pd is None:
    print("[erro] 'streamlit' e 'pandas' são necessários para executar a interface gráfica.", file=sys.stderr)
    print("Instale as dependências com: pip install -r requirements.txt", file=sys.stderr)
    print("Em seguida execute: streamlit run app.py", file=sys.stderr)
    sys.exit(1)

from conciliar import (
    SEPARADOR_ENTRADA,
    ENCODING_ENTRADA,
    TOLERANCIA_DIAS,
    conciliar_extrato_siga,
)


def formatar_moeda(valor: float) -> str:
    """Formata valor float para formato monetário brasileiro R$ 1.234,56."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_dataframe_upload(uploaded_file, sep: str, encoding: str, origem_padrao: str | None = None) -> pd.DataFrame:
    """Lê arquivo enviado pelo uploader do Streamlit."""
    df = pd.read_csv(uploaded_file, sep=sep, encoding=encoding, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    if origem_padrao and ("Origem" not in df.columns or df["Origem"].isna().all()):
        df["Origem"] = origem_padrao

    for opc in ["Historico", "Documento", "Status"]:
        if opc not in df.columns:
            df[opc] = ""
    return df


def gerar_excel_bytes(df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig) -> bytes:
    """Gera pasta de trabalho Excel (.xlsx) multiabas em memória."""
    output = io.BytesIO()
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

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_resumo.to_excel(writer, sheet_name="Resumo", index=False)
        df_conc.to_excel(writer, sheet_name="Conciliados", index=False)
        df_pend_ext.to_excel(writer, sheet_name="Pendentes_Extrato", index=False)
        df_pend_sig.to_excel(writer, sheet_name="Pendentes_SIGA", index=False)

    return output.getvalue()


# -----------------------------------------------------------------------------
# Configuração da Página
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Conciliação Financeira",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚖️ Conciliação Financeira (EXTRATO x SIGA)")
st.caption("Cruzamento automatizado de lançamentos bancários e registros contábeis por valor, proximidade temporal e documentos.")

# -----------------------------------------------------------------------------
# Barra Lateral de Configurações
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Parâmetros de Conciliação")

    sem_limite = st.checkbox("Sem limite de tolerância temporal", value=True)
    if sem_limite:
        tolerancia_dias = 9999
    else:
        tolerancia_dias = st.slider("Tolerância máxima (em dias):", min_value=0, max_value=60, value=5)

    separador = st.selectbox(
        "Separador de colunas CSV:",
        options=["|", ";", ",", "\\t"],
        index=0,
    )
    if separador == "\\t":
        separador = "\t"

    encoding = st.selectbox(
        "Codificação do arquivo:",
        options=["utf-8", "latin1"],
        index=0,
    )

    st.markdown("---")
    st.markdown("💡 **Dica:** O algoritmo cruza lançamentos de mesmo valor, priorizando pares com menor diferença de dias e mesmo número de documento.")

# -----------------------------------------------------------------------------
# Área de Entrada de Dados
# -----------------------------------------------------------------------------
st.subheader("📂 1. Seleção e Envio dos Arquivos")

tab_dois, tab_unico, tab_exemplo = st.tabs([
    "📁 Dois Arquivos (Extrato + SIGA)",
    "📄 Arquivo Único (dados.csv)",
    "🧪 Carregar Exemplo Prático"
])

df_entrada = None

with tab_dois:
    col_ext, col_sig = st.columns(2)
    with col_ext:
        file_ext = st.file_uploader("Extrato Bancário (CSV):", type=["csv", "txt"], key="upload_extrato")
    with col_sig:
        file_sig = st.file_uploader("Relatório SIGA (CSV):", type=["csv", "txt"], key="upload_siga")

    if file_ext and file_sig:
        try:
            df_e = carregar_dataframe_upload(file_ext, sep=separador, encoding=encoding, origem_padrao="EXTRATO")
            df_s = carregar_dataframe_upload(file_sig, sep=separador, encoding=encoding, origem_padrao="SIGA")
            df_entrada = pd.concat([df_e, df_s], ignore_index=True)
            st.success(f"Arquivos carregados: Extrato ({len(df_e)} registros) e SIGA ({len(df_s)} registros).")
        except Exception as e:
            st.error(f"Erro ao carregar arquivos: {e}")

with tab_unico:
    file_unico = st.file_uploader("Arquivo consolidado com coluna 'Origem' (CSV):", type=["csv", "txt"], key="upload_unico")
    if file_unico:
        try:
            df_entrada = carregar_dataframe_upload(file_unico, sep=separador, encoding=encoding)
            st.success(f"Arquivo consolidado carregado com {len(df_entrada)} registros.")
        except Exception as e:
            st.error(f"Erro ao carregar arquivo consolidado: {e}")

with tab_exemplo:
    st.write("Deseja testar a conciliação imediatamente sem enviar arquivos?")
    if st.button("🧪 Carregar dados de exemplo (dados.exemplo.csv)"):
        exemplo_path = Path("dados.exemplo.csv")
        if exemplo_path.exists():
            df_entrada = pd.read_csv(exemplo_path, sep="|", encoding="utf-8", dtype=str)
            st.success(f"Arquivo de exemplo carregado com {len(df_entrada)} registros.")
        else:
            st.warning("Arquivo 'dados.exemplo.csv' não encontrado no diretório atual.")

# -----------------------------------------------------------------------------
# Processamento e Resultados
# -----------------------------------------------------------------------------
if df_entrada is not None:
    # Validação mínima
    faltantes = [c for c in ["Data", "Valor", "Origem"] if c not in df_entrada.columns]
    if faltantes:
        st.error(f"Colunas obrigatórias ausentes na base: {', '.join(faltantes)}. Colunas encontradas: {list(df_entrada.columns)}")
    else:
        st.markdown("---")
        st.subheader("📊 2. Resumo da Conciliação")

        df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig = conciliar_extrato_siga(
            df_entrada.copy(), tolerancia_dias=tolerancia_dias
        )

        total_ext = df_ext["valor_num"].sum() if "valor_num" in df_ext.columns else 0.0
        total_sig = df_sig["valor_num"].sum() if "valor_num" in df_sig.columns else 0.0
        total_conc = df_conc["valor"].sum() if not df_conc.empty and "valor" in df_conc.columns else 0.0
        total_pend_ext = df_pend_ext["valor"].sum() if not df_pend_ext.empty and "valor" in df_pend_ext.columns else 0.0
        total_pend_sig = df_pend_sig["valor"].sum() if not df_pend_sig.empty and "valor" in df_pend_sig.columns else 0.0
        diferenca_geral = abs(total_ext - total_sig)

        # Cartões de Métricas
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total EXTRATO", formatar_moeda(total_ext), f"{len(df_ext)} registros")
        m2.metric("Total SIGA", formatar_moeda(total_sig), f"{len(df_sig)} registros")
        m3.metric("Conciliado", formatar_moeda(total_conc), f"{len(df_conc)} pares", delta_color="normal")
        m4.metric("Pendente EXTRATO", formatar_moeda(total_pend_ext), f"{len(df_pend_ext)} pendências")
        m5.metric("Pendente SIGA", formatar_moeda(total_pend_sig), f"{len(df_pend_sig)} pendências")

        if diferenca_geral == 0:
            st.success(f"🎉 **Balanço perfeito!** Diferença geral zerada entre EXTRATO e SIGA.")
        else:
            st.warning(f"⚠️ **Diferença líquida geral:** {formatar_moeda(diferenca_geral)}")

        # ---------------------------------------------------------------------
        # Visualização Tabular Interativa
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📋 3. Detalhamento dos Registros")

        tab_r1, tab_r2, tab_r3 = st.tabs([
            f"✅ Conciliados ({len(df_conc)})",
            f"⚠️ Pendentes Extrato ({len(df_pend_ext)})",
            f"⚠️ Pendentes SIGA ({len(df_pend_sig)})"
        ])

        with tab_r1:
            if not df_conc.empty:
                st.dataframe(df_conc, use_container_width=True)
            else:
                st.info("Nenhum lançamento foi conciliado com os critérios atuais.")

        with tab_r2:
            if not df_pend_ext.empty:
                st.dataframe(df_pend_ext, use_container_width=True)
            else:
                st.success("Nenhuma pendência no EXTRATO!")

        with tab_r3:
            if not df_pend_sig.empty:
                st.dataframe(df_pend_sig, use_container_width=True)
            else:
                st.success("Nenhuma pendência no SIGA!")

        # ---------------------------------------------------------------------
        # Área de Exportação / Downloads
        # ---------------------------------------------------------------------
        st.markdown("---")
        st.subheader("📥 4. Exportação dos Relatórios")

        col_d1, col_d2, col_d3, col_d4 = st.columns(4)

        try:
            excel_data = gerar_excel_bytes(df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig)
            col_d1.download_button(
                label="📊 Baixar Excel Completo (.xlsx)",
                data=excel_data,
                file_name="conciliacao_completa.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            col_d1.error(f"Erro ao gerar Excel: {e}")

        # CSVs com formato padrão brasileiro (; e utf-8-sig)
        csv_conc = df_conc.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        col_d2.download_button(
            label="📄 01_conciliados.csv",
            data=csv_conc,
            file_name="01_conciliados.csv",
            mime="text/csv",
        )

        csv_ext = df_pend_ext.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        col_d3.download_button(
            label="📄 02_pendentes_extrato.csv",
            data=csv_ext,
            file_name="02_pendentes_extrato.csv",
            mime="text/csv",
        )

        csv_sig = df_pend_sig.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        col_d4.download_button(
            label="📄 03_pendentes_siga.csv",
            data=csv_sig,
            file_name="03_pendentes_siga.csv",
            mime="text/csv",
        )

