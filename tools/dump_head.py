from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'main.py'
b = p.read_bytes()
print(repr(b[:800]))
print('\n--- as text ---\n')
print(b[:800].decode('utf-8', errors='replace'))
