"""Importar o runtime nos testes não cria logs nem carrega credenciais reais."""
import os
import tempfile

_data = tempfile.TemporaryDirectory(prefix='comprastg-tests-')
os.environ['COMPRAS_DATA_DIR'] = _data.name
