from decimal import Decimal, InvalidOperation

import pyodbc
from flask import Blueprint, flash, redirect, render_template, request, url_for

from db import conectar

# Um Blueprint agrupa todas as rotas relacionadas a produtos.
# O url_prefix faz todas elas começarem com /produtos
produtos_bp = Blueprint("produtos", __name__, url_prefix="/produtos")


def validar_produto(form, editando=False):
    """Valida os dados do formulário.
    Devolve um dicionário com os dados já convertidos e uma lista de erros.
    Na edição (editando=True) a quantidade não é validada, pois ela só
    muda por meio de entradas e saídas."""
    erros = []

    codigo = form.get("codigo", "").strip()
    nome = form.get("nome", "").strip()
    categoria = form.get("categoria", "").strip()
    descricao = form.get("descricao", "").strip()
    preco_texto = form.get("preco", "").strip().replace(",", ".")
    quantidade_texto = form.get("quantidade", "").strip()
    minimo_texto = form.get("estoque_minimo", "").strip()

    # Campos de texto obrigatórios
    if not codigo:
        erros.append("O código é obrigatório.")
    elif len(codigo) > 30:
        erros.append("O código deve ter no máximo 30 caracteres.")

    if not nome:
        erros.append("O nome é obrigatório.")
    elif len(nome) > 100:
        erros.append("O nome deve ter no máximo 100 caracteres.")

    if not categoria:
        erros.append("A categoria é obrigatória.")
    elif len(categoria) > 50:
        erros.append("A categoria deve ter no máximo 50 caracteres.")

    if len(descricao) > 500:
        erros.append("A descrição deve ter no máximo 500 caracteres.")

    # Preço: número com no máximo 2 casas decimais, maior ou igual a zero
    preco = None
    if not preco_texto:
        erros.append("O preço é obrigatório.")
    else:
        try:
            preco = Decimal(preco_texto)
            if not preco.is_finite() or preco < 0:
                erros.append("O preço deve ser um número maior ou igual a zero.")
            elif preco != preco.quantize(Decimal("0.01")):
                erros.append("O preço deve ter no máximo 2 casas decimais.")
        except InvalidOperation:
            erros.append("O preço deve ser um número válido.")

    # Quantidade inicial: só existe no cadastro
    quantidade = None
    if not editando:
        if not quantidade_texto:
            erros.append("A quantidade inicial é obrigatória.")
        else:
            try:
                quantidade = int(quantidade_texto)
                if quantidade < 0:
                    erros.append("A quantidade não pode ser negativa.")
            except ValueError:
                erros.append("A quantidade deve ser um número inteiro.")

    # Estoque mínimo: número inteiro, maior ou igual a zero
    estoque_minimo = None
    if not minimo_texto:
        erros.append("O estoque mínimo é obrigatório.")
    else:
        try:
            estoque_minimo = int(minimo_texto)
            if estoque_minimo < 0:
                erros.append("O estoque mínimo não pode ser negativo.")
        except ValueError:
            erros.append("O estoque mínimo deve ser um número inteiro.")

    dados = {
        "codigo": codigo,
        "nome": nome,
        "categoria": categoria,
        "descricao": descricao if descricao else None,
        "preco": preco,
        "quantidade": quantidade,
        "estoque_minimo": estoque_minimo,
    }
    return dados, erros


def buscar_produto(produto_id):
    """Busca um produto pelo id. Devolve a linha do banco ou None."""
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(
            """
            SELECT id, codigo, nome, categoria, descricao,
                   preco, quantidade, estoque_minimo, data_cadastro
            FROM Produtos
            WHERE id = ?
            """,
            (produto_id,),
        )
        return cursor.fetchone()
    finally:
        conexao.close()


@produtos_bp.route("/")
def listar():
    """Mostra a tabela de produtos, com pesquisa opcional."""
    # Lê o texto digitado na pesquisa (vem pela URL: ?busca=mouse)
    busca = request.args.get("busca", "").strip()
    produtos = []

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        if busca:
            # Procura o texto no código, no nome ou na categoria.
            # Os "%" significam "qualquer coisa antes e depois".
            termo = f"%{busca}%"
            cursor.execute(
                """
                SELECT id, codigo, nome, categoria, preco, quantidade, estoque_minimo
                FROM Produtos
                WHERE codigo LIKE ? OR nome LIKE ? OR categoria LIKE ?
                ORDER BY nome
                """,
                (termo, termo, termo),
            )
        else:
            cursor.execute(
                """
                SELECT id, codigo, nome, categoria, preco, quantidade, estoque_minimo
                FROM Produtos
                ORDER BY nome
                """
            )

        produtos = cursor.fetchall()

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template("produtos.html", produtos=produtos, busca=busca)


@produtos_bp.route("/novo", methods=["GET", "POST"])
def novo():
    # GET: o usuário só abriu a página, mostramos o formulário vazio
    if request.method == "GET":
        return render_template("produto_form.html", produto={})

    # POST: o usuário clicou em "Salvar produto"
    dados, erros = validar_produto(request.form)

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template("produto_form.html", produto=request.form)

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # Os "?" são parâmetros: o pyodbc coloca os valores com segurança.
        # É isso que protege contra SQL Injection.
        # O "OUTPUT INSERTED.id" devolve o id que o banco gerou para o produto novo.
        cursor.execute(
            """
            INSERT INTO Produtos
                (codigo, nome, categoria, descricao, preco, quantidade, estoque_minimo)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["codigo"],
                dados["nome"],
                dados["categoria"],
                dados["descricao"],
                dados["preco"],
                dados["quantidade"],
                dados["estoque_minimo"],
            ),
        )
        novo_id = cursor.fetchone()[0]

        # Se o produto já nasce com estoque, registramos isso no histórico
        # como uma ENTRADA. Assim, o saldo do histórico sempre bate com o estoque.
        if dados["quantidade"] > 0:
            cursor.execute(
                """
                INSERT INTO Movimentacoes (produto_id, tipo, quantidade, observacao)
                VALUES (?, 'ENTRADA', ?, ?)
                """,
                (novo_id, dados["quantidade"], "Estoque inicial"),
            )

        # Um único commit confirma o produto e a movimentação juntos
        conexao.commit()

        flash("Produto cadastrado com sucesso!", "sucesso")
        # Agora o usuário volta para a lista e já vê o produto novo
        return redirect(url_for("produtos.listar"))

    except pyodbc.IntegrityError:
        # Acontece quando o código já existe (regra UNIQUE do banco)
        if conexao:
            conexao.rollback()
        flash("Já existe um produto com este código.", "erro")

    except pyodbc.Error:
        if conexao:
            conexao.rollback()
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    finally:
        # Sempre fecha a conexão, deu certo ou não
        if conexao:
            conexao.close()

    return render_template("produto_form.html", produto=request.form)


@produtos_bp.route("/<int:produto_id>")
def detalhes(produto_id):
    """Mostra todos os dados de um produto e as últimas movimentações dele."""
    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute(
            """
            SELECT id, codigo, nome, categoria, descricao,
                   preco, quantidade, estoque_minimo, data_cadastro
            FROM Produtos
            WHERE id = ?
            """,
            (produto_id,),
        )
        produto = cursor.fetchone()

        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos.listar"))

        # TOP 10 traz só as 10 movimentações mais recentes
        cursor.execute(
            """
            SELECT TOP 10 tipo, quantidade, data_movimentacao, observacao
            FROM Movimentacoes
            WHERE produto_id = ?
            ORDER BY data_movimentacao DESC, id DESC
            """,
            (produto_id,),
        )
        movimentacoes = cursor.fetchall()

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")
        return redirect(url_for("produtos.listar"))

    finally:
        if conexao:
            conexao.close()

    return render_template(
        "produto_detalhes.html", produto=produto, movimentacoes=movimentacoes
    )


@produtos_bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
def editar(produto_id):
    # GET: busca o produto e mostra o formulário já preenchido
    if request.method == "GET":
        try:
            produto = buscar_produto(produto_id)
        except pyodbc.Error:
            flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")
            return redirect(url_for("produtos.listar"))

        if produto is None:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos.listar"))

        return render_template(
            "produto_form.html", produto=produto, editando=True, produto_id=produto_id
        )

    # POST: o usuário clicou em "Salvar alterações"
    dados, erros = validar_produto(request.form, editando=True)

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template(
            "produto_form.html",
            produto=request.form,
            editando=True,
            produto_id=produto_id,
        )

    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        # A quantidade NÃO entra no UPDATE: ela só muda por entrada e saída
        cursor.execute(
            """
            UPDATE Produtos
            SET codigo = ?, nome = ?, categoria = ?, descricao = ?,
                preco = ?, estoque_minimo = ?
            WHERE id = ?
            """,
            (
                dados["codigo"],
                dados["nome"],
                dados["categoria"],
                dados["descricao"],
                dados["preco"],
                dados["estoque_minimo"],
                produto_id,
            ),
        )

        # rowcount diz quantas linhas foram alteradas. Zero = o produto não existe
        if cursor.rowcount == 0:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos.listar"))

        conexao.commit()

        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("produtos.listar"))

    except pyodbc.IntegrityError:
        # Acontece quando o novo código já pertence a outro produto
        flash("Já existe outro produto com este código.", "erro")

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.", "erro")

    finally:
        if conexao:
            conexao.close()

    return render_template(
        "produto_form.html", produto=request.form, editando=True, produto_id=produto_id
    )


@produtos_bp.route("/<int:produto_id>/excluir", methods=["POST"])
def excluir(produto_id):
    # Só aceita POST: excluir por link (GET) seria perigoso
    conexao = None
    try:
        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("DELETE FROM Produtos WHERE id = ?", (produto_id,))

        if cursor.rowcount == 0:
            flash("Produto não encontrado.", "erro")
        else:
            conexao.commit()
            flash("Produto excluído com sucesso!", "sucesso")

    except pyodbc.IntegrityError:
        # A chave estrangeira impede apagar produtos que têm movimentações
        flash(
            "Não é possível excluir este produto, "
            "pois ele possui movimentações no histórico.",
            "erro",
        )

    except pyodbc.Error:
        flash("Erro ao acessar o banco de dados. Tente novamente.","erro")