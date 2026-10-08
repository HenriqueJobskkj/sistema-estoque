import pyodbc
import config


def conectar():
    """Abre e devolve uma conexão com o banco SistemaEstoque."""
    string_conexao = (
        f"DRIVER={{{config.DRIVER}}};"
        f"SERVER={config.SERVIDOR};"
        f"DATABASE={config.BANCO};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(string_conexao)