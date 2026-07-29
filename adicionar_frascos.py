"""
Adiciona um frasco padrão (100ml, R$100) para cada perfume sem frasco.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python adicionar_frascos.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("""
        SELECT p.id, b.name as brand, p.name
        FROM perfumes p
        JOIN brands b ON p.brand_id = b.id
        WHERE p.active = 1
          AND NOT EXISTS (
              SELECT 1 FROM bottles bt WHERE bt.perfume_id = p.id AND bt.active = 1
          )
        ORDER BY b.name, p.name
    """)
    perfumes = cur.fetchall()

    added = 0
    for p in perfumes:
        cur.execute("""
            INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes)
            VALUES (?, 100, 100, 100, 'Frasco padrão — atualize o valor e ml reais depois')
        """, (p['id'],))
        added += 1
        print(f"  ✔ {p['brand']} — {p['name']}")

    con.commit()
    con.close()
    print(f"\nConcluído: {added} frasco(s) adicionado(s).")

if __name__ == '__main__':
    run()
