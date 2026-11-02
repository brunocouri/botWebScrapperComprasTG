"""Prepara runtime Windows a partir de fontes explícitas, sem dados do usuário."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
VERSION = '3.14.5'
SHA256 = 'ba6bd811c4eedb19195cf275770ef127e893d63701e24152606e2cb76f6d876a'
SOURCES = (
    'bot.py', 'rules.py', 'price_parser.py', 'storage.py', 'configuration.py',
    'config_cli.py', 'runtime_safety.py', 'catalog_storage.py', 'catalog_runtime.py',
    'catalog_cli.py', 'etl_worker.py', 'extraction/__init__.py',
)


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 14):
        raise SystemExit('Execute com Python 3.14 em Windows x64.')
    archive = ROOT / 'artifacts' / 'downloads' / f'python-{VERSION}-embed-amd64.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        urllib.request.urlretrieve(f'https://www.python.org/ftp/python/{VERSION}/{archive.name}', archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise SystemExit('Checksum do Python embutido inválido. Preserve o arquivo para inspeção.')
    target = ROOT / 'artifacts' / 'windows-backend'
    # Apagar apenas staging gerado; nunca tocar dados ou diretórios calculados fora de artifacts.
    if target.resolve().parent != (ROOT / 'artifacts').resolve() or target.is_symlink():
        raise SystemExit('Staging fora do diretório autorizado.')
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (target / name).resolve().is_relative_to(target.resolve()):
                raise SystemExit('Caminho inválido no pacote Python.')
        bundle.extractall(target)
    for name in SOURCES:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    (target / 'python314._pth').write_text('python314.zip\n.\nLib/site-packages\n', encoding='ascii')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--isolated', '--no-compile',
                    '--target', str(target / 'Lib' / 'site-packages'),
                    '-r', str(ROOT / 'requirements-windows.txt')], check=True)
    subprocess.run([str(target / 'python.exe'), '-c',
                    'import telethon, dotenv, sqlite3, ssl, config_cli, catalog_runtime, etl_worker; print("EMBEDDED_PYTHON_OK")'],
                   cwd=target, check=True)


if __name__ == '__main__':
    main()
