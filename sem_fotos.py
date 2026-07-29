"""
Lista perfumes sem foto cadastrada.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python sem_fotos.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("""
    SELECT b.name as brand, p.name, p.gender
    FROM perfumes p JOIN brands b ON p.brand_id = b.id
    WHERE p.active = 1 AND (p.photo_filename IS NULL OR p.photo_filename = '')
    ORDER BY p.gender, b.name, p.name
""")
rows = cur.fetchall()
con.close()

print(f"{len(rows)} perfume(s) sem foto:\n")
for r in rows:
    print(f"  [{r['gender']}] {r['brand']} — {r['name']}")
