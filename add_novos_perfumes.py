"""
Cadastra os 21 novos perfumes e vincula as fotos da pasta NOVOS.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python add_novos_perfumes.py
"""
import sqlite3, os

DB    = os.path.join(os.path.dirname(__file__), 'estoque.db')
FOTOS = os.path.join(os.path.dirname(__file__), 'static', 'perfume_photos')

# (marca, nome, concentração, gênero, estilo, arquivo_foto)
NOVOS = [
    # Masculinos
    ("Rabanne",          "1 Million Parfum",                          "Parfum",          "Masculino", "Design", "1 Million Parfum Rabanne .png"),
    ("Rabanne",          "Invictus",                                  "EDT",             "Masculino", "Design", "Invictus Rabanne.png"),
    ("Rabanne",          "Invictus Victory Elixir",                   "Elixir",          "Masculino", "Design", "Invictus Victory Elixir Rabanne.png"),
    ("Jean Paul Gaultier","Le Male Elixir",                           "Parfum",          "Masculino", "Design", "Le Male Elixir Jean Paul Gaultier.png"),
    ("Chanel",           "Bleu de Chanel Parfum",                     "Parfum",          "Masculino", "Design", "Bleu de Chanel Parfum Chanel.png"),
    ("Carolina Herrera", "212 Men",                                   "EDT",             "Masculino", "Design", "212 Men Carolina Herrera.png"),
    # Femininos
    ("Carolina Herrera", "212 VIP Rosé",                              "EDP",             "Feminino",  "Design", "212 VIP Rosé Carolina Herrera.png"),
    ("Calvin Klein",     "Euphoria",                                  "EDP",             "Feminino",  "Design", "Euphoria Calvin Klein.png"),
    ("Carolina Herrera", "La Bomba",                                  "EDP",             "Feminino",  "Design", "La Bomba Carolina Herrera.png"),
    # Árabes
    ("Orientica",        "Royal Amber",                               "EDP",             "Unissex",   "Árabe",  "Royal Amber Orientica.png"),
    ("Lattafa",          "Asad Bourbon",                              "EDP",             "Masculino", "Árabe",  "Asad Bourbon Lattafa.png"),
    ("French Avenue",    "Liquid Brun",                               "EDP",             "Unissex",   "Árabe",  "Liquid Brun French Avenue.png"),
    ("French Avenue",    "Vulcan Feu",                                "EDP",             "Masculino", "Árabe",  "Vulcan Feu French Avenue.png"),
    ("Rasasi",           "Hawas Black",                               "EDP",             "Masculino", "Árabe",  "Hawas Black Rasasi.png"),
    ("Afnan",            "Supremacy Collector's Edition",             "EDP",             "Unissex",   "Árabe",  "Supremacy Collector's Edition Afnan.png"),
    ("Armaf",            "Club de Nuit Intense Man Limited Edition",  "Parfum",          "Masculino", "Árabe",  "Club de Nuit Intense Man Limited Edition Parfum Armaf.png"),
    ("Lattafa",          "Asad Elixir",                               "EDP",             "Masculino", "Árabe",  "Asad Elixir Lattafa.png"),
    ("Lattafa",          "Atheeri",                                   "EDP",             "Unissex",   "Árabe",  "Atheeri Lattafa.png"),
    ("French Avenue",    "Spectre Ghost",                             "EDP",             "Masculino", "Árabe",  "Spectre Ghost French Avenue.png"),
    ("Al Wataniah",      "Attar Al Wesal Gold",                       "EDP",             "Unissex",   "Árabe",  "Attar Al Wesal Gold Al Wataniah.png"),
    ("Bidaya",           "Gris",                                      "EDP",             "Unissex",   "Árabe",  "Gris Bidaya.png"),
]

def get_denom(cur):
    cur.execute("SELECT key, value FROM group_settings")
    settings = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    cur.execute("SELECT pct FROM group_indirect_costs WHERE active=1")
    indirect = sum(r[0] for r in cur.fetchall())
    total = indirect + settings.get('net_margin_pct', 40)
    return (100 - total) / 100 if total < 100 else None

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    denom = get_denom(cur)
    price_per_ml = round((100 / 100) / denom, 4) if denom else 0

    added = 0
    for brand_name, perf_name, conc, gender, style, foto in NOVOS:
        # Marca
        cur.execute("SELECT id FROM brands WHERE name=?", (brand_name,))
        row = cur.fetchone()
        if row:
            brand_id = row['id']
        else:
            cur.execute("INSERT INTO brands (name) VALUES (?)", (brand_name,))
            brand_id = cur.lastrowid
            print(f"  ✚ Marca: {brand_name}")

        # Verifica duplicidade
        cur.execute("SELECT id FROM perfumes WHERE brand_id=? AND LOWER(name)=LOWER(?)", (brand_id, perf_name))
        if cur.fetchone():
            print(f"  ⚠ Já existe: {brand_name} — {perf_name}")
            continue

        # Insere perfume
        cur.execute(
            "INSERT INTO perfumes (brand_id, name, concentration, gender, family, photo_filename) VALUES (?,?,?,?,?,?)",
            (brand_id, perf_name, conc, gender, style, foto)
        )
        pid = cur.lastrowid

        # Frasco padrão + preço
        cur.execute("INSERT INTO bottles (perfume_id, volume_ml, cost_price, remaining_ml, notes) VALUES (?,100,100,100,'Frasco padrão')", (pid,))
        cur.execute("UPDATE perfumes SET price_per_ml=? WHERE id=?", (price_per_ml, pid))

        added += 1
        print(f"  ✔ {brand_name} — {perf_name} ({conc}, {gender})")

    con.commit()
    con.close()
    print(f"\nConcluído: {added} perfume(s) adicionado(s).")

if __name__ == '__main__':
    run()
