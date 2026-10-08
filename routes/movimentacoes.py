from datetime import datetime, timedelta

import pyodbc
from flask import Blueprint, flash, redirect, render_template, request, url_for

from db import conectar

# Todas as rotas deste arquivo começam com /movimentacoes
movimentacoes_bp = Blueprint("movimentacoes", __name__, url_prefix="/movimentacoes")

# Limite por movimentação, para evitar números absurdos
QUANTIDADE_MAXIMA = 1000000

# Quantas movimentações o histórico mostra no máximo
LIMITE_HISTORICO = 500


def buscar_produtos():
    """Devolve a lista de produtos para preencher o campo de seleção."""
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(
            "SELECT id, codigo, nome, quantidade FROM Produtos ORDER BY nome"
        )
        return cursor.fetchall()
    finally:
        conexao.close()


def validar_movimentacao(form):
    """Valida os dados do formulário de movimentação (entrada ou saída).
    Devolve um dicionário com os dados convertidos e uma lista de erros."""
    erros = []

    produto_texto = form.get("produto_id", "").strip()
    quantidade_texto = form.get("quantidade", "").strip()
    observacao = form.get("observacao", "").strip()

    # Produto: precisa ter sido selecionado
    produto_id = None
    if not produto_texto:
        erros.append("Selecione um produto.")
    else:
        try:
            produto_id = int(produto_texto)
        except ValueError:
            erros.append("Produto inválido.")

    # Quantidade: número inteiro maior que zero
    quantidade = None
    if not quantidade_texto:
        erros.append("A quantidade é obrigatória.")
    else:
        try:
            quantidade = int(quantidade_texto)
            if quantidade <= 0:
                erros.append("A quantidade deve ser maior que zero.")
            elif quantidade > QUANTIDADE_MAXIMA:
                limite = f"{QUANTIDADE_MAXIMA:,}".replace(",", ".")
                erros.append(f"A quantidade deve ser no máximo {limite}.")
        except ValueError:
            erros.append("A quantidade deve ser um número inteiro.")

    # Observação: opcional, mas com tamanho máximo
    if len(observacao) > 255:
        erros.append("A observação deve ter no máximo 255 caracteres.")

    dados = {
        "produto_id": produto_id,
        "quantidade": quantidade,
        "observacao": observacao if observacao else None,
    }
    return dados, erros


def converter_data(texto, nome_campo, erros):
    """Converte um texto no formato AAAA-MM-DD (o formato do campo de data
    do navegador) em data. Se for inválido, guarda o erro e devolve None."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        erros.append(f"{nome_campo} inválida.")
        return None


@movimentacoes_bp.route("/")
def historico():
    """Mostra o histórico de movimentações, com filtros opcionais."""

    # 1) Lê os filtros que vieram pela URL
    tipo = request.args.get("tipo", "").strip().upper()
    produto_texto = request.args.get("produto_id", "").strip()
    data_inicial_texto = request.args.get("data_inicial", "").strip()
    data_final_texto = request.args.get("data_final", "").strip()

    # 2) Valida os filtros
    erros = []

    if tipo and tipo not in ("ENTRADA", "SAIDA"):
        erros.append("Tipo de movimentação inválido.")

    produto_id = None
    if produto_texto:
        try:
            produto_id = int(produto_texto)
        except ValueError:
            erros.append("Produto inválido.")

    data_inicial = converter_data(data_inicial_texto, "Data inicial", erros)
    data_final = converter_data(data_final_texto, "Data final", erros)

    if data_inicial and data_final and data_inicial > data_final:
        erros.append("A data inicial não pode ser maior que a data final.")

    # 3) Busca as movimentações (só se os filtros estiverem válidos)
    movimentacoes = []

    if erros:
        for erro in erros:
            flash(erro, "erro")
    else:
        # Monta o WHERE com apenas os filtros preenchidos.
        # Os textos em "condicoes" são fixos (escritos por nós).
        # Os valores digitados pelo usuário vão em "parametros", como "?".
        condicoes = []
        parametros = []

        if tipo:
            condicoes.append("m.tipo = ?")
            parametros.append(tipo)

        if produto_id is not None:
            condicoes.append("m.produto_id = ?")
            parametros.append(produto_id)

        if data_inicial:
            # A partir das 00:00 do dia inicial
            condicoes.append("m.data_movimentacao >= ?")
            parametros.append(data_inicial)

        if data_final:
            # Até o fim do dia final (antes das 00:00 do dia seguinte)
            condicoes.append("m.data_movimentacao < ?")
            parametros.append(data_final + timedelta(days=1))

        where = ""
        if condicoes:
            where = "WHERE " + " AND ".join(condicoes)

        sql = f"""
            SELECT TOP {LIMITE_HISTORICO}
                   m.id, p.codigo, p.nome AS produto, m.tipo,
                   m.quantidade, m.data_movimentacao, m.observacao
            FROM Movimentacoes m
            INNER JOIN Produtos p ON p.id = m.produto_id
            {where}
            ORDER BY m.data_movimentacao DESC, m.id DESC
        """

        conexao = None
        try:
            conexao = conectar()
            cursor = conexao.cursor()
            cursor.execute(sql, tuple(parametros))
            movimentacoes = cursor.fetchall()

        except pyodbc.Error:
            flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

        finally:
            if conexao:
                conexao.close()

    # 4) Carrega os produtos para o campo de seleção do filtro
    try:
        produtos = buscar_produtos()
    except pyodbc.Error:
        produtos = []
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    # 5) Devolve os filtros para a página manter os campos preenchidos
    filtros = {
        "tipo": tipo,
        "produto_id": produto_texto,
        "data_inicial": data_inicial_texto,
        "data_final": data_final_texto,
    }

    return render_template(
        "movimentacoes.html",
        movimentacoes=movimentacoes,
        produtos=produtos,
        filtros=filtros,
        limite=LIMITE_HISTORICO,
    )


@movimentacoes_bp.route("/entrada", methods=["GET", "POST"])
def entrada():
    # Carrega os produtos para o campo de seleção
    try:
        produtos = buscar_produtos()
    except pyodbc.Error:
        produtos = []
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    # GET: o usuário só abriu a página, mostramos o formulário vazio
    if request.method == "GET":
        return render_template("entrada.html", produtos=produtos, form={})

    # POST: o usuário clicou em "Confirmar entrada"
    dados, erros = validar_movimentacao(request.form)

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template("entrada.html", produtos=produtos, form=request.form)

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # 1) Busca o produto para saber o estoque atual
        cursor.execute(
            "SELECT nome, quantidade FROM Produtos WHERE id = ?",
            (dados["produto_id"],),
        )
        produto = cursor.fetchone()

        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("movimentacoes.entrada"))

        estoque_atual = produto.quantidade
        novo_estoque = estoque_atual + dados["quantidade"]

        # 2) Aumenta a quantidade do produto
        cursor.execute(
            "UPDATE Produtos SET quantidade = quantidade + ? WHERE id = ?",
            (dados["quantidade"], dados["produto_id"]),
        )

        # 3) Registra a movimentação no histórico
        #    (a data e a hora são gravadas pelo banco, com GETDATE())
        cursor.execute(
            """
            INSERT INTO Movimentacoes (produto_id, tipo, quantidade, observacao)
            VALUES (?, 'ENTRADA', ?, ?)
            """,
            (dados["produto_id"], dados["quantidade"], dados["observacao"]),
        )

        # 4) Confirma as duas operações juntas (transação)
        conexao.commit()

        flash(
            f"Entrada registrada com sucesso! "
            f"{produto.nome}: estoque de {estoque_atual} para {novo_estoque}.",
            "sucesso",
        )
        return redirect(url_for("movimentacoes.entrada"))

    except pyodbc.Error:
        # Se algo falhou, desfaz tudo: nem o UPDATE nem o INSERT ficam salvos
        if conexao:
            conexao.rollback()
        flash("Erro ao registrar a entrada. Nenhuma alteração foi feita.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template("entrada.html", produtos=produtos, form=request.form)


@movimentacoes_bp.route("/saida", methods=["GET", "POST"])
def saida():
    # Carrega os produtos para o campo de seleção
    try:
        produtos = buscar_produtos()
    except pyodbc.Error:
        produtos = []
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    # GET: o usuário só abriu a página, mostramos o formulário vazio
    if request.method == "GET":
        return render_template("saida.html", produtos=produtos, form={})

    # POST: o usuário clicou em "Confirmar saída"
    dados, erros = validar_movimentacao(request.form)

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template("saida.html", produtos=produtos, form=request.form)

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # 1) Busca o produto para saber o estoque atual
        cursor.execute(
            "SELECT nome, quantidade, estoque_minimo FROM Produtos WHERE id = ?",
            (dados["produto_id"],),
        )
        produto = cursor.fetchone()

        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("movimentacoes.saida"))

        estoque_atual = produto.quantidade

        # 2) REGRA DE NEGÓCIO: não pode sair mais do que existe
        if dados["quantidade"] > estoque_atual:
            flash(
                f"Quantidade insuficiente em estoque. Disponível: {estoque_atual}.",
                "erro",
            )
            return render_template("saida.html", produtos=produtos, form=request.form)

        novo_estoque = estoque_atual - dados["quantidade"]

        # 3) Diminui a quantidade do produto.
        #    O "AND quantidade >= ?" é uma segunda proteção: mesmo que outra pessoa
        #    tenha feito uma saída no mesmo instante, o banco não deixa ficar negativo.
        cursor.execute(
            """
            UPDATE Produtos
            SET quantidade = quantidade - ?
            WHERE id = ? AND quantidade >= ?
            """,
            (dados["quantidade"], dados["produto_id"], dados["quantidade"]),
        )

        # Nenhuma linha alterada = o estoque ficou insuficiente nesse meio tempo
        if cursor.rowcount == 0:
            conexao.rollback()
            flash("Quantidade insuficiente em estoque.", "erro")
            return render_template("saida.html", produtos=produtos, form=request.form)

        # 4) Registra a movimentação no histórico
        cursor.execute(
            """
            INSERT INTO Movimentacoes (produto_id, tipo, quantidade, observacao)
            VALUES (?, 'SAIDA', ?, ?)
            """,
            (dados["produto_id"], dados["quantidade"], dados["observacao"]),
        )

        # 5) Confirma as duas operações juntas (transação)
        conexao.commit()

        mensagem = (
            f"Saída registrada com sucesso! "
            f"{produto.nome}: estoque de {estoque_atual} para {novo_estoque}."
        )

        # Avisa se o produto chegou ao estoque mínimo (ou abaixo dele)
        if novo_estoque <= produto.estoque_minimo:
            mensagem += " Atenção: estoque baixo."

        flash(mensagem, "sucesso")
        return redirect(url_for("movimentacoes.saida"))

    except pyodbc.Error:
        # Se algo falhou, desfaz tudo: nem o UPDATE nem o INSERT ficam salvos
        if conexao:
            conexao.rollback()
        flash("Erro ao registrar a saída. Nenhuma alteração foi feita.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template("saida.html", produtos=produtos, form=request.form)