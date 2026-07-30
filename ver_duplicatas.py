"""
Mostra todos os perfumes agrupados por marca para identificar duplicatas manualmente.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python ver_duplicatas.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("""
    SELECT p.id, b.name as brand, p.name, p.gender,
           CASE WHEN p.photo_filename IS NOT NULL AND p.photo_filename != '' THEN '✔' ELSE '✖' END as foto
    FROM perfumes p JOIN brands b ON p.brand_id = b.id
    WHERE p.active = 1
    ORDER BY b.name, p.name
""")
rows = cur.fetchall()
con.close()

brand = None
for r in rows:
    if r['brand'] != brand:
        brand = r['brand']
        print(f"\n{brand}")
    print(f"  [{r['id']:3d}] {r['foto']} {r['name']}  ({r['gender']})")
