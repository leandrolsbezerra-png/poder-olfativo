import sqlite3, os
DB = os.path.join(os.path.dirname(__file__), 'estoque.db')
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

cur.execute("SELECT id FROM brands WHERE name='Lattafa'")
brand_id = cur.fetchone()['id']

cur.execute("SELECT id FROM perfumes WHERE brand_id=? AND LOWER(name)=LOWER('Khamrah Waha')", (brand_id,))
if cur.fetchone():
    print("Já existe.")
else:
    foto = "Khamrah Waha Lattafa.png"
    cur.execute("INSERT INTO perfumes (brand_id, name, concentration, gender, family, photo_filename) VALUES (?,?,?,?,?,?)",
                (brand_id, 'Khamrah Waha', 'EDP', 'Unissex', 'Árabe', foto))
    pid = cur.lastrowid

    cur.execute("SELECT key, value FROM group_settings")
    settings = {r['key']: float(r['value'] or 0) for r in cur.fetchall()}
    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indirect = sum(r['pct'] for r in cur.fetchall())
    denom = (100 - indirect - settings.get('net_margin_pct', 40)) / 100

    cur.execute("INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes) VALUES (?,100,100,100,'Frasco padrão')", (pid,))
    cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (round(1/denom, 4), pid))
    print(f"✔ Lattafa — Khamrah Waha adicionado com foto (id={pid})")

con.commit()
con.close()
