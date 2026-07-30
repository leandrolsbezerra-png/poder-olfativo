"""
Remove duplicatas identificadas manualmente pelo ver_duplicatas.py.
Mantém sempre o que tem foto; inativa o duplicado sem foto.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python corrigir_duplicatas.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

# (id a inativar, motivo)
REMOVER = [
    (58,  "Emporio Armani — Stronger With You (sem foto, duplicata do id 4)"),
    (60,  "Giorgio Armani — Acqua di Giò (sem foto, duplicata do id 15)"),
    (117, "Giorgio Armani — My Way Nectar (sem foto, duplicata do id 5)"),
    (56,  "Dolce & Gabbana — Pour Homme (sem foto, duplicata do id 7)"),
    (138, "Yves Saint Laurent — Libre (sem foto, duplicata do id 10)"),
    (73,  "Lattafa — Fakhar Platinum (sem foto, duplicata do id 27 Fakhar Platin)"),
    (106, "Lattafa — Durrat Al Aroos (sem foto, duplicata do id 30 Al Wataniah)"),
    (127, "Lattafa — Sabah Al Ward (sem foto, duplicata do id 31 Al Wataniah)"),
    (2,   "Dolce Gabbana — Light Blue (duplicata do id 111 Dolce & Gabbana)"),
]

con = sqlite3.connect(DB)
cur = con.cursor()

for pid, motivo in REMOVER:
    cur.execute("UPDATE perfumes SET active=0 WHERE id=?", (pid,))
    print(f"  ✖ inativado id={pid}: {motivo}")

con.commit()
con.close()
print(f"\nConcluído: {len(REMOVER)} duplicata(s) removida(s).")
