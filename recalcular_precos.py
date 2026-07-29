"""
Recalcula price_per_ml para todos os perfumes que têm frasco
mas ainda estão com price_per_ml = 0 (ou nulo).
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python recalcular_precos.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Lê configuração de margem
    cur.execute("SELECT key, value FROM group_settings")
    settings = {r['key']: float(r['value'] or 0) for r in cur.fetchall()}
    net_margin_pct = settings.get('net_margin_pct', 40)

    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indirect_total = sum(r['pct'] for r in cur.fetchall())

    total = indirect_total + net_margin_pct
    if total >= 100:
        print("⚠️  Configuração inválida: margem + custos indiretos >= 100%")
        con.close()
        return
    denom = (100 - total) / 100

    # Todos os perfumes com frasco ativo mas sem price_per_ml
    cur.execute("""
        SELECT p.id, b.name as brand, p.name,
               bt.volume_ml, bt.cost_price
        FROM perfumes p
        JOIN brands b ON p.brand_id = b.id
        JOIN bottles bt ON bt.perfume_id = p.id AND bt.active = 1
        WHERE p.active = 1 AND (p.price_per_ml IS NULL OR p.price_per_ml = 0)
        ORDER BY b.name, p.name
    """)
    perfumes = cur.fetchall()

    updated = 0
    for p in perfumes:
        price_per_ml = round((p['cost_price'] / p['volume_ml']) / denom, 4)
        cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (price_per_ml, p['id']))

        # APC
        apc_size = p['volume_ml'] / 2
        apc_price = round((p['cost_price'] / p['volume_ml'] * apc_size) / denom)
        cur.execute("SELECT id FROM apc_products WHERE perfume_id=? AND size_ml=?", (p['id'], apc_size))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE apc_products SET group_price=?, active=1 WHERE id=?", (apc_price, existing['id']))
        else:
            cur.execute("INSERT INTO apc_products(perfume_id,size_ml,group_price,active) VALUES(?,?,?,1)",
                        (p['id'], apc_size, apc_price))
        cur.execute("UPDATE apc_products SET active=0 WHERE perfume_id=? AND size_ml!=?", (p['id'], apc_size))

        updated += 1
        print(f"  ✔ {p['brand']} — {p['name']}  R${price_per_ml:.4f}/ml")

    con.commit()
    con.close()
    print(f"\nConcluído: {updated} perfume(s) com preço recalculado.")

if __name__ == '__main__':
    run()
