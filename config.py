import os

from dotenv import load_dotenv

# Lê as configurações do arquivo .env (se ele existir).
# O .env fica só no seu computador e não vai para o GitHub.
load_dotenv()

# Nome do servidor SQL Server (o mesmo que você usa para conectar no SSMS)
SERVIDOR = os.environ.get("DB_SERVIDOR", "localhost")

# Nome do banco de dados que criamos
BANCO = os.environ.get("DB_BANCO", "SistemaEstoque")

# Driver ODBC instalado no computador
DRIVER = os.environ.get("DB_DRIVER", "ODBC Driver 17 for SQL Server")

# Chave usada pelo Flask para as mensagens de sucesso/erro da tela
SECRET_KEY = os.environ.get("SECRET_KEY", "chave-de-desenvolvimento")

# Modo de desenvolvimento do Flask (1 = ligado, 0 = desligado)
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"