"""
Adiciona um frasco padrão (100ml, R$100) para cada perfume sem frasco
e recalcula o price_per_ml para aparecer na tela de etiquetas.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python adicionar_frascos.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

def get_denom(cur):
    """Lê margem e custos indiretos e devolve o denominador de precificação."""
    cur.execute("SELECT key, value FROM group_settings")
    settings = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    net_margin_pct = settings.get('net_margin_pct', 40)

    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indirect_total = sum(r[0] for r in cur.fetchall())

    total = indirect_total + net_margin_pct
    if total >= 100:
        return None  # configuração inválida
    return (100 - total) / 100

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    denom = get_denom(cur)
    if not denom:
        print("⚠️  Configuração de margem inválida — ajuste em Configurações antes de continuar.")
        con.close()
        return

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

    VOLUME = 100.0
    CUSTO  = 100.0
    price_per_ml = round((CUSTO / VOLUME) / denom, 4)

    added = 0
    for p in perfumes:
        cur.execute("""
            INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes)
            VALUES (?, ?, ?, ?, 'Frasco padrão — atualize o valor e ml reais depois')
        """, (p['id'], VOLUME, CUSTO, VOLUME))

        cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (price_per_ml, p['id']))

        # APC: metade do volume
        apc_size = VOLUME / 2
        apc_price = round((CUSTO / VOLUME * apc_size) / denom)
        cur.execute("SELECT id FROM apc_products WHERE perfume_id=? AND size_ml=?", (p['id'], apc_size))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE apc_products SET group_price=?, active=1 WHERE id=?", (apc_price, existing['id']))
        else:
            cur.execute("INSERT INTO apc_products(perfume_id,size_ml,group_price,active) VALUES(?,?,?,1)",
                        (p['id'], apc_size, apc_price))
        cur.execute("UPDATE apc_products SET active=0 WHERE perfume_id=? AND size_ml!=?", (p['id'], apc_size))

        added += 1
        print(f"  ✔ {p['brand']} — {p['name']}  (R${price_per_ml:.4f}/ml)")

    con.commit()
    con.close()
    print(f"\nConcluído: {added} frasco(s) e preço(s) calculado(s).")

if __name__ == '__main__':
    run()
