import sqlite3, os
DB = os.path.join(os.path.dirname(__file__), 'estoque.db')
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute("SELECT id FROM brands WHERE name='Prada'")
brand_id = cur.fetchone()['id']

cur.execute("SELECT id FROM perfumes WHERE brand_id=? AND LOWER(name)=LOWER('Paradoxe Intense')", (brand_id,))
if cur.fetchone():
    print("Já existe.")
else:
    cur.execute("INSERT INTO perfumes (brand_id, name, concentration, gender, family) VALUES (?,?,?,?,?)",
                (brand_id, 'Paradoxe Intense', 'EDP', 'Feminino', 'Design'))
    pid = cur.lastrowid

    # Lê config de preço
    cur.execute("SELECT key, value FROM group_settings")
    settings = {r['key']: float(r['value'] or 0) for r in cur.fetchall()}
    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indirect = sum(r['pct'] for r in cur.fetchall())
    denom = (100 - indirect - settings.get('net_margin_pct', 40)) / 100

    cur.execute("INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes) VALUES (?,100,100,100,'Frasco padrão')", (pid,))
    price_per_ml = round((100/100) / denom, 4)
    cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (price_per_ml, pid))
    print(f"✔ Prada — Paradoxe Intense adicionada (id={pid})")

con.commit()
con.close()
