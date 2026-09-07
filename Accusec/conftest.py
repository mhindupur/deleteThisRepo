import os
import tempfile

os.environ.setdefault("ACCUSEC_MYSQL_DATABASE", "accusec_test")
os.environ.setdefault("ACCUSEC_USE_FIXTURES", "1")

_secrets = tempfile.NamedTemporaryFile(prefix="accusec-secrets-", suffix=".json", delete=False)
_secrets.write(b"{}")
_secrets.close()
os.environ.setdefault("ACCUSEC_SECRETS_PATH", _secrets.name)
