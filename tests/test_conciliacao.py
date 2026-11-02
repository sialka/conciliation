import unittest
import os
import sys

# Adiciona o diretório raiz ao path para importar conciliar
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conciliar import parse_valor, calcular_similaridade, criar_parser

try:
    import pandas as pd
    from conciliar import parse_data, conciliar_extrato_siga
    TEM_PANDAS = True
except ImportError:
    TEM_PANDAS = False


class TestConciliacaoBasico(unittest.TestCase):
    def test_parse_valor_padrao_brasileiro(self):
        self.assertEqual(parse_valor("1.234,56"), 1234.56)
        self.assertEqual(parse_valor("24,70"), 24.70)
        self.assertEqual(parse_valor("10.000.500,25"), 10000500.25)

    def test_parse_valor_com_moeda_e_espacos(self):
        self.assertEqual(parse_valor("R$ 1.500,00"), 1500.00)
        self.assertEqual(parse_valor("  R$  320,50 "), 320.50)

    def test_parse_valor_negativo_contabil(self):
        self.assertEqual(parse_valor("(350,00)"), -350.00)
        self.assertEqual(parse_valor("- 120,00"), -120.00)
        self.assertEqual(parse_valor("120,00-"), -120.00)
        self.assertEqual(parse_valor("(R$ 1.000,00)"), -1000.00)

    def test_parse_valor_nulo_e_invalido(self):
        self.assertEqual(parse_valor(None), 0.0)
        self.assertEqual(parse_valor(""), 0.0)
        self.assertEqual(parse_valor("     "), 0.0)
        self.assertEqual(parse_valor("NAO_NUMERICO"), 0.0)

    def test_calcular_similaridade(self):
        # Strings idênticas
        self.assertEqual(calcular_similaridade("TED FORNECEDOR", "ted fornecedor"), 1.0)
        # Strings vazias
        self.assertEqual(calcular_similaridade("", "teste"), 0.0)
        # Similaridade razoável
        sim = calcular_similaridade("TED RECEBIDA CLIENTE A", "RECEBIMENTO NOTA CLIENTE A")
        self.assertGreater(sim, 0.4)

    def test_parser_cli_argumentos_padrao(self):
        parser = criar_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.arquivo)
        self.assertIsNone(args.extrato)
        self.assertIsNone(args.siga)
        self.assertEqual(args.tolerancia, 9999)
        self.assertEqual(args.sep, "|")
        self.assertEqual(args.encoding, "utf-8")

    def test_parser_cli_argumentos_customizados(self):
        parser = criar_parser()
        args = parser.parse_args([
            "--extrato", "banco.csv",
            "--siga", "sistema.csv",
            "--tolerancia", "5",
            "--excel", "relatorio.xlsx"
        ])
        self.assertEqual(args.extrato, "banco.csv")
        self.assertEqual(args.siga, "sistema.csv")
        self.assertEqual(args.tolerancia, 5)
        self.assertEqual(args.excel, "relatorio.xlsx")


@unittest.skipUnless(TEM_PANDAS, "Pandas não disponível no ambiente atual")
class TestConciliacaoPandas(unittest.TestCase):
    def test_parse_data(self):
        dt = parse_data("01/08/2026")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 1)

    def test_conciliacao_logica(self):
        dados = pd.DataFrame([
            {"Data": "01/08/2026", "Valor": "100,00", "Origem": "EXTRATO", "Historico": "PAGTO A", "Documento": "101", "Status": "OK"},
            {"Data": "02/08/2026", "Valor": "100,00", "Origem": "SIGA", "Historico": "PAGTO A", "Documento": "101", "Status": "OK"},
            {"Data": "03/08/2026", "Valor": "50,00", "Origem": "EXTRATO", "Historico": "TAXA", "Documento": "102", "Status": "OK"},
        ])
        df_conc, df_pend_ext, df_pend_sig, df_ext, df_sig = conciliar_extrato_siga(dados, tolerancia_dias=5)
        self.assertEqual(len(df_conc), 1)
        self.assertEqual(len(df_pend_ext), 1)
        self.assertEqual(len(df_pend_sig), 0)
        self.assertEqual(df_conc.loc[0, "diferenca_dias"], 1)


if __name__ == "__main__":
    unittest.main()

