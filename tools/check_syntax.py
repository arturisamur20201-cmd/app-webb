import py_compile, traceback
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'main.py'
try:
    py_compile.compile(str(p), doraise=True)
    print('OK')
except Exception:
    traceback.print_exc()
