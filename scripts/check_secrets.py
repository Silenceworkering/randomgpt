"""Scan tracked project text, never print matched secrets."""

import pathlib
import re
import subprocess

PATTERNS = [
    re.compile(rb"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{25,}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
files = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
failed = []
for file in files:
    if not file:
        continue
    path = pathlib.Path(file.decode())
    if path.is_file() and any(pattern.search(path.read_bytes()) for pattern in PATTERNS):
        failed.append(str(path))
if failed:
    raise SystemExit("Возможный секрет в файлах: " + ", ".join(failed))
print("Проверка известных форматов секретов: OK")
