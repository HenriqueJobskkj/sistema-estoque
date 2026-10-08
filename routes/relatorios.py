import csv
import io
from datetime import datetime, timedelta

import pyodbc
from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from db import conectar

# Todas as rotas deste arquivo começam com /relatorios
relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

# Quantas movimentações a tabela da página mostra no máximo
LIMITE_TABELA = 500

# Maior período permitido, em dias (evita gráficos gigantes)
DIAS_MAXIMOS = 366


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def ler_periodo():
    """Lê a data inicial e a final da URL.
    Se não vierem (ou forem inválidas), usa os últimos 30 dias.
    Devolve: data_inicial, data_final, lista de erros."""
    erros = []

    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    padrao_inicial = hoje - timedelta(days=29)

    texto_inicial = request.args.get("data_inicial", "").strip()
    texto_final = request.args.get("data_final", "").strip()

    data_inicial = padrao_inicial
    data_final = hoje

    if texto_inicial:
        try:
            data_inicial = datetime.strptime(texto_inicial, "%Y-%m-%d")
        except ValueError:
            erros.append("Data inicial inválida.")

    if texto_final:
        try:
            data_final = datetime.strptime(texto_final, "%Y-%m-%d")
        except ValueError:
            erros.append("Data final inválida.")

    if not erros:
        if data_inicial > data_final:
            erros.append("A data inicial não pode ser maior que a data final.")
        elif (data_final - data_inicial).days >= DIAS_MAXIMOS:
            erros.append(f"O período máximo é de {DIAS_MAXIMOS} dias.")

    # Se algo estiver errado, volta para o período padrão
    if erros:
        data_inicial = padrao_inicial
        data_final = hoje

    return data_inicial, data_final, erros


def buscar_lista_produtos(cursor, apenas_estoque_baixo=False):
    """Busca os produtos (todos ou só os de estoque baixo)."""
    if apenas_estoque_baixo:
        cursor.execute(
            """
            SELECT id, codigo, nome, categoria, preco, quantidade, estoque_minimo
            FROM Produtos
            WHERE quantidade <= estoque_minimo
            ORDER BY quantidade ASC, nome
            """
        )
    else:
        cursor.execute(
            """
            SELECT id, codigo, nome, categoria, preco, quantidade, estoque_minimo
            FROM Produtos
            ORDER BY nome
            """
        )
    return cursor.fetchall()


def buscar_movimentacoes(cursor, data_inicial, data_final, limite=None):
    """Busca as movimentações do período (do início do dia inicial até o
    fim do dia final). Se 'limite' for informado, traz só as mais recentes."""
    topo = f"TOP {int(limite)}" if limite else ""

    cursor.execute(
        f"""
        SELECT {topo} m.id, p.codigo, p.nome AS produto, m.tipo,
               m.quantidade, m.data_movimentacao, m.observacao
        FROM Movimentacoes m
        INNER JOIN Produtos p ON p.id = m.produto_id
        WHERE m.data_movimentacao >= ? AND m.data_movimentacao < ?
        ORDER BY m.data_movimentacao DESC, m.id DESC
        """,
        (data_inicial, data_final + timedelta(days=1)),
    )
    return cursor.fetchall()


def executar_consulta(funcao, *argumentos):
    """Abre a conexão, executa a função de consulta recebida e fecha a conexão."""
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        return funcao(cursor, *argumentos)
    finally:
        conexao.close()


def proteger_celula(valor):
    """Evita 'injeção de fórmulas' no Excel: textos que começam com
    = + - ou @ ganham um apóstrofo na frente."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@"):
        return "'" + valor
    return valor


def status_do_produto(produto):
    if produto.quantidade <= produto.estoque_minimo:
        return "ESTOQUE BAIXO"
    return "ESTOQUE NORMAL"


def linha_csv_produto(p):
    return [
        proteger_celula(p.codigo),
        proteger_celula(p.nome),
        proteger_celula(p.categoria),
        str(p.preco).replace(".", ","),  # 59.90 vira 59,90
        p.quantidade,
        p.estoque_minimo,
        status_do_produto(p),
    ]


def linha_csv_movimentacao(m):
    return [
        m.id,
        proteger_celula(m.codigo),
        proteger_celula(m.produto),
        "Entrada" if m.tipo == "ENTRADA" else "Saída",
        m.quantidade,
        m.data_movimentacao.strftime("%d/%m/%Y %H:%M"),
        proteger_celula(m.observacao or ""),
    ]


def gerar_csv(prefixo_arquivo, cabecalho, linhas):
    """Monta o arquivo CSV na memória e devolve como download."""
    saida = io.StringIO()

    # ponto e vírgula como separador, que é o padrão do Excel em português
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)

    # "\ufeff" é a marca que faz o Excel mostrar os acentos corretamente
    conteudo = "\ufeff" + saida.getvalue()

    nome_arquivo = f"{prefixo_arquivo}_{datetime.now():%Y%m%d}.csv"

    return Response(
        conteudo,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------------------------------------------------------------------------
# Página de relatórios
# ---------------------------------------------------------------------------

@relatorios_bp.route("/")
def index():
    data_inicial, data_final, erros = ler_periodo()
    for erro in erros:
        flash(erro, "erro")

    # Valores iniciais (ficam assim se o banco estiver vazio ou der erro)
    resumo = {
        "total_produtos": 0,
        "estoque_baixo": 0,
        "entradas_unidades": 0,
        "entradas_movimentacoes": 0,
        "saidas_unidades": 0,
        "saidas_movimentacoes": 0,
    }
    grafico_dias = {"rotulos": [], "entradas": [], "saidas": []}
    grafico_categorias = {"nomes": [], "unidades": []}
    produtos = []
    produtos_baixo = []
    movimentacoes = []

    # O fim do período é "antes das 00:00 do dia seguinte", para incluir o dia final inteiro
    fim = data_final + timedelta(days=1)

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # Cards: produtos cadastrados e produtos com estoque baixo (situação atual)
        cursor.execute(
            """
            SELECT COUNT(*) AS total_produtos,
                   ISNULL(SUM(CASE WHEN quantidade <= estoque_minimo
                                   THEN 1 ELSE 0 END), 0) AS estoque_baixo
            FROM Produtos
            """
        )
        linha = cursor.fetchone()
        resumo["total_produtos"] = linha.total_produtos
        resumo["estoque_baixo"] = linha.estoque_baixo

        # Cards: entradas e saídas dentro do período
        cursor.execute(
            """
            SELECT tipo, COUNT(*) AS movimentacoes, SUM(quantidade) AS unidades
            FROM Movimentacoes
            WHERE data_movimentacao >= ? AND data_movimentacao < ?
            GROUP BY tipo
            """,
            (data_inicial, fim),
        )
        for linha in cursor.fetchall():
            if linha.tipo == "ENTRADA":
                resumo["entradas_unidades"] = linha.unidades
                resumo["entradas_movimentacoes"] = linha.movimentacoes
            elif linha.tipo == "SAIDA":
                resumo["saidas_unidades"] = linha.unidades
                resumo["saidas_movimentacoes"] = linha.movimentacoes

        # Gráfico 1: unidades por dia e por tipo
        cursor.execute(
            """
            SELECT CAST(data_movimentacao AS DATE) AS dia,
                   tipo,
                   SUM(quantidade) AS unidades
            FROM Movimentacoes
            WHERE data_movimentacao >= ? AND data_movimentacao < ?
            GROUP BY CAST(data_movimentacao AS DATE), tipo
            """,
            (data_inicial, fim),
        )
        por_dia = {}
        for linha in cursor.fetchall():
            por_dia[(linha.dia, linha.tipo)] = linha.unidades

        # O banco só devolve os dias que tiveram movimentação.
        # Aqui percorremos todos os dias do período e usamos 0 nos dias vazios.
        dia = data_inicial.date()
        ultimo_dia = data_final.date()
        while dia <= ultimo_dia:
            grafico_dias["rotulos"].append(dia.strftime("%d/%m"))
            grafico_dias["entradas"].append(por_dia.get((dia, "ENTRADA"), 0))
            grafico_dias["saidas"].append(por_dia.get((dia, "SAIDA"), 0))
            dia += timedelta(days=1)

        # Gráfico 2: unidades em estoque por categoria
        cursor.execute(
            """
            SELECT categoria, SUM(quantidade) AS unidades
            FROM Produtos
            GROUP BY categoria
            ORDER BY unidades DESC, categoria
            """
        )
        for linha in cursor.fetchall():
            grafico_categorias["nomes"].append(linha.categoria)
            grafico_categorias["unidades"].append(linha.unidades)

        # Tabelas
        produtos_baixo = buscar_lista_produtos(cursor, apenas_estoque_baixo=True)
        movimentacoes = buscar_movimentacoes(
            cursor, data_inicial, data_final, LIMITE_TABELA
        )
        produtos = buscar_lista_produtos(cursor)

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template(
        "relatorios.html",
        data_inicial=data_inicial,
        data_final=data_final,
        resumo=resumo,
        grafico_dias=grafico_dias,
        grafico_categorias=grafico_categorias,
        produtos=produtos,
        produtos_baixo=produtos_baixo,
        movimentacoes=movimentacoes,
        limite=LIMITE_TABELA,
    )


# ---------------------------------------------------------------------------
# Exportação para CSV
# ---------------------------------------------------------------------------

@relatorios_bp.route("/exportar/produtos")
def exportar_produtos():
    try:
        produtos = executar_consulta(buscar_lista_produtos)
    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")
        return redirect(url_for("relatorios.index"))

    cabecalho = [
        "Código", "Nome", "Categoria", "Preço",
        "Quantidade", "Estoque mínimo", "Status",
    ]
    linhas = [linha_csv_produto(p) for p in produtos]
    return gerar_csv("produtos", cabecalho, linhas)


@relatorios_bp.route("/exportar/estoque-baixo")
def exportar_estoque_baixo():
    try:
        produtos = executar_consulta(buscar_lista_produtos, True)
    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")
        return redirect(url_for("relatorios.index"))

    cabecalho = [
        "Código", "Nome", "Categoria", "Preço",
        "Quantidade", "Estoque mínimo", "Status",
    ]
    linhas = [linha_csv_produto(p) for p in produtos]
    return gerar_csv("estoque_baixo", cabecalho, linhas)


@relatorios_bp.route("/exportar/movimentacoes")
def exportar_movimentacoes():
    data_inicial, data_final, erros = ler_periodo()

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return redirect(url_for("relatorios.index"))

    try:
        movimentacoes = executar_consulta(
            buscar_movimentacoes, data_inicial, data_final
        )
    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")
        return redirect(url_for("relatorios.index"))

    cabecalho = [
        "ID", "Código", "Produto", "Tipo",
        "Quantidade", "Data", "Observação",
    ]
    linhas = [linha_csv_movimentacao(m) for m in movimentacoes]
    return gerar_csv("movimentacoes", cabecalho, linhas)