"""Keep protected page templates in the function bundle, apart from CDN assets."""
from pathlib import Path
import shutil
from cloud_verify import main as verify

root = Path(__file__).resolve().parent
shutil.copytree(root / 'public', root / 'server_assets', dirs_exist_ok=True)
verify()
