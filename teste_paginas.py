"""Teste rápido do sistema.
Abre cada página (só consultas, sem alterar nada no banco) e confere se o
código de resposta é o esperado. Para executar: python teste_paginas.py
"""

from app import app

# O "cliente de teste" do Flask simula um navegador, sem precisar do servidor ligado
cliente = app.test_client()

# Lista de (endereço, código esperado)
#   200 = página abriu normalmente
#   302 = foi redirecionado (por exemplo, produto que não existe)
#   404 = página não encontrada
TESTES = [
    ("/", 200),
    ("/produtos/", 200),
    ("/produtos/?busca=mouse", 200),
    ("/produtos/novo", 200),
    ("/produtos/1", 200),
    ("/produtos/1/editar", 200),
    ("/produtos/999999", 302),
    ("/produtos/999999/editar", 302),
    ("/produtos/abc", 404),
    ("/movimentacoes/", 200),
    ("/movimentacoes/?tipo=SAIDA", 200),
    ("/movimentacoes/?tipo=INVALIDO", 200),
    ("/movimentacoes/entrada", 200),
    ("/movimentacoes/saida", 200),
    ("/relatorios/", 200),
    ("/relatorios/?data_inicial=2026-01-01&data_final=2026-01-31", 200),
    ("/relatorios/exportar/produtos", 200),
    ("/relatorios/exportar/estoque-baixo", 200),
    ("/relatorios/exportar/movimentacoes", 200),
    ("/relatorios/exportar/movimentacoes?data_inicial=2026-12-31&data_final=2026-01-01", 302),
    ("/pagina-que-nao-existe", 404),
]

falhas = 0

for endereco, esperado in TESTES:
    resposta = cliente.get(endereco)

    if resposta.status_code == esperado:
        print(f"OK      {resposta.status_code}  {endereco}")
    else:
        falhas += 1
        print(f"FALHOU  {resposta.status_code} (esperado {esperado})  {endereco}")

print()
if falhas == 0:
    print(f"Todos os {len(TESTES)} testes passaram!")
else:
    print(f"{falhas} de {len(TESTES)} testes falharam.")