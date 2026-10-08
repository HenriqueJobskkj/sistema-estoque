import pyodbc
from flask import Flask, flash, render_template

import config
from db import conectar
from routes.movimentacoes import movimentacoes_bp
from routes.produtos import produtos_bp
from routes.relatorios import relatorios_bp

# Cria a aplicação Flask
app = Flask(__name__)

# Chave necessária para o Flask guardar as mensagens (flash) entre páginas
app.secret_key = config.SECRET_KEY

# Registra os grupos de rotas
app.register_blueprint(produtos_bp)
app.register_blueprint(movimentacoes_bp)
app.register_blueprint(relatorios_bp)


@app.route("/")
def index():
    """Dashboard: cards com números e dados para os gráficos."""

    # Valores iniciais (ficam assim se o banco estiver vazio ou der erro)
    resumo = {
        "total_produtos": 0,
        "total_itens": 0,
        "estoque_baixo": 0,
        "entradas_unidades": 0,
        "entradas_movimentacoes": 0,
        "saidas_unidades": 0,
        "saidas_movimentacoes": 0,
    }
    menor_estoque = {"nomes": [], "quantidades": [], "minimos": []}

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # Consulta 1: números gerais dos produtos.
        # COUNT conta as linhas, SUM soma os valores e CASE WHEN conta só os
        # produtos com estoque baixo. O ISNULL troca NULL por 0 (tabela vazia).
        cursor.execute(
            """
            SELECT COUNT(*) AS total_produtos,
                   ISNULL(SUM(quantidade), 0) AS total_itens,
                   ISNULL(SUM(CASE WHEN quantidade <= estoque_minimo
                                   THEN 1 ELSE 0 END), 0) AS estoque_baixo
            FROM Produtos
            """
        )
        linha = cursor.fetchone()
        resumo["total_produtos"] = linha.total_produtos
        resumo["total_itens"] = linha.total_itens
        resumo["estoque_baixo"] = linha.estoque_baixo

        # Consulta 2: totais de entradas e de saídas.
        # O GROUP BY agrupa as movimentações pelo tipo.
        cursor.execute(
            """
            SELECT tipo,
                   COUNT(*) AS movimentacoes,
                   SUM(quantidade) AS unidades
            FROM Movimentacoes
            GROUP BY tipo
            """
        )
        for linha in cursor.fetchall():
            if linha.tipo == "ENTRADA":
                resumo["entradas_unidades"] = linha.unidades
                resumo["entradas_movimentacoes"] = linha.movimentacoes
            elif linha.tipo == "SAIDA":
                resumo["saidas_unidades"] = linha.unidades
                resumo["saidas_movimentacoes"] = linha.movimentacoes

        # Consulta 3: os 5 produtos com menos unidades em estoque
        cursor.execute(
            """
            SELECT TOP 5 nome, quantidade, estoque_minimo
            FROM Produtos
            ORDER BY quantidade ASC, nome
            """
        )
        for linha in cursor.fetchall():
            menor_estoque["nomes"].append(linha.nome)
            menor_estoque["quantidades"].append(linha.quantidade)
            menor_estoque["minimos"].append(linha.estoque_minimo)

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template("index.html", resumo=resumo, menor_estoque=menor_estoque)


# ---------- Páginas de erro ----------

@app.errorhandler(404)
def pagina_nao_encontrada(erro):
    """Aparece quando o endereço digitado não existe."""
    return (
        render_template(
            "erro.html",
            codigo=404,
            titulo="Página não encontrada",
            mensagem="O endereço que você tentou acessar não existe.",
        ),
        404,
    )


@app.errorhandler(500)
def erro_interno(erro):
    """Aparece quando acontece um erro inesperado no sistema."""
    return (
        render_template(
            "erro.html",
            codigo=500,
            titulo="Erro interno",
            mensagem="Algo deu errado no sistema. Tente novamente em instantes.",
        ),
        500,
    )


# Só executa o servidor quando rodamos este arquivo diretamente
if __name__ == "__main__":
    app.run(debug=config.DEBUG)