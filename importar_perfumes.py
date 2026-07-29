"""
Script de importação em massa de perfumes.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python importar_perfumes.py
"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), 'estoque.db')

# (marca, nome, concentração, gênero, estilo)
PERFUMES = [
    # ── MASCULINOS ──────────────────────────────────────────────────────────
    ("Armaf",            "Club de Nuit Intense Man",          "EDP",             "Masculino", "Design"),
    ("Azzaro",           "The Most Wanted Parfum",            "Parfum",          "Masculino", "Design"),
    ("Azzaro",           "Wanted",                            "EDP",             "Masculino", "Design"),
    ("Burberry",         "Hero",                              "EDP",             "Masculino", "Design"),
    ("Burberry",         "Touch for Men",                     "EDT",             "Masculino", "Design"),
    ("Bvlgari",          "Man in Black",                      "EDP",             "Masculino", "Design"),
    ("Bvlgari",          "Man Wood Essence",                  "EDP",             "Masculino", "Design"),
    ("Carolina Herrera", "212 VIP Black",                     "EDP",             "Masculino", "Design"),
    ("Carolina Herrera", "Bad Boy Cobalt",                    "EDP",             "Masculino", "Design"),
    ("Carolina Herrera", "CH Men",                            "EDT",             "Masculino", "Design"),
    ("Chanel",           "Allure Homme Sport Eau Extrême",    "EDT",             "Masculino", "Design"),
    ("Chanel",           "Bleu de Chanel",                    "EDP",             "Masculino", "Design"),
    ("Chanel",           "Platinum Égoïste",                  "EDT",             "Masculino", "Design"),
    ("Coach",            "for Men",                           "EDT",             "Masculino", "Design"),
    ("Maison Alhambra",  "World Cup VIP",                     "EDP",             "Masculino", "Árabe"),
    ("Dior",             "Sauvage",                           "EDP",             "Masculino", "Design"),
    ("Dior",             "Homme Intense",                     "EDP",             "Masculino", "Design"),
    ("Dolce & Gabbana",  "K",                                 "EDP",             "Masculino", "Design"),
    ("Dolce & Gabbana",  "Light Blue Pour Homme",             "EDT",             "Masculino", "Design"),
    ("Dolce & Gabbana",  "Pour Homme",                        "EDT",             "Masculino", "Design"),
    ("Dolce & Gabbana",  "The One",                           "EDP",             "Masculino", "Design"),
    ("Emporio Armani",   "Stronger With You",                 "EDT",             "Masculino", "Design"),
    ("Emporio Armani",   "Stronger With You Intensely",       "EDP",             "Masculino", "Design"),
    ("Giorgio Armani",   "Acqua di Giò",                      "EDT",             "Masculino", "Design"),
    ("Giorgio Armani",   "Acqua di Giò Profondo",             "EDP",             "Masculino", "Design"),
    ("Giorgio Armani",   "Armani Code Parfum",                "Parfum",          "Masculino", "Design"),
    ("Givenchy",         "Gentleman Réserve Privée",          "EDP",             "Masculino", "Design"),
    ("Givenchy",         "Gentleman Society",                 "EDP",             "Masculino", "Design"),
    ("Gucci",            "Guilty Pour Homme Parfum",          "Parfum",          "Masculino", "Design"),
    ("Gucci",            "Intense Oud",                       "EDP",             "Masculino", "Design"),
    ("Hermès",           "H24",                               "EDP",             "Masculino", "Design"),
    ("Hermès",           "Terre d'Hermès Intense",            "EDP",             "Masculino", "Design"),
    ("Hermès",           "Terre d'Hermès",                    "EDT",             "Masculino", "Design"),
    ("Hugo Boss",        "Bottled Elixir",                    "Parfum",          "Masculino", "Design"),
    ("Issey Miyake",     "L'Eau d'Issey Pour Homme",          "EDT",             "Masculino", "Design"),
    ("Jean Paul Gaultier","Le Beau Le Parfum",                "Parfum",          "Masculino", "Design"),
    ("Jean Paul Gaultier","Le Male Le Parfum",                "Parfum",          "Masculino", "Design"),
    ("Jean Paul Gaultier","Scandal Pour Homme",               "EDT",             "Masculino", "Design"),
    ("Kenzo",            "Homme",                             "EDP",             "Masculino", "Design"),
    ("Lattafa",          "Asad",                              "EDP",             "Masculino", "Árabe"),
    ("Lattafa",          "Fakhar Black",                      "EDP",             "Masculino", "Árabe"),
    ("Lattafa",          "Fakhar Gold",                       "EDP",             "Masculino", "Árabe"),
    ("Lattafa",          "Fakhar Platinum",                   "EDP",             "Masculino", "Árabe"),
    ("Loewe",            "7 Cobalt",                          "EDP",             "Masculino", "Design"),
    ("Loewe",            "Esencia",                           "EDP",             "Masculino", "Design"),
    ("Maison Alhambra",  "Jean Lowe Vibe",                    "EDP",             "Masculino", "Árabe"),
    ("Mercedes-Benz",    "Club Black",                        "EDT",             "Masculino", "Design"),
    ("Montblanc",        "Explorer",                          "EDP",             "Masculino", "Design"),
    ("Montblanc",        "Explorer Platinum",                 "EDP",             "Masculino", "Design"),
    ("Montblanc",        "Legend",                            "EDP",             "Masculino", "Design"),
    ("Nishane",          "Hacivat",                           "Extrait de Parfum","Unissex",  "Design"),
    ("Prada",            "Luna Rossa Black",                  "EDP",             "Masculino", "Design"),
    ("Prada",            "L'Homme",                           "EDT",             "Masculino", "Design"),
    ("Rabanne",          "1 Million Elixir",                  "Parfum",          "Masculino", "Design"),
    ("Rabanne",          "Invictus Victory Elixir",           "Elixir",          "Masculino", "Design"),
    ("Rabanne",          "Phantom Parfum",                    "Parfum",          "Masculino", "Design"),
    ("Rochas",           "Moustache",                         "EDP",             "Masculino", "Design"),
    ("Valentino",        "Uomo Born in Roma Intense",         "EDP",             "Masculino", "Design"),
    ("Versace",          "Dylan Blue",                        "EDT",             "Masculino", "Design"),
    ("Versace",          "Eros",                              "EDP",             "Masculino", "Design"),
    ("Viktor & Rolf",    "Spicebomb Extreme",                 "EDP",             "Masculino", "Design"),
    ("Yves Saint Laurent","La Nuit de L'Homme",               "EDT",             "Masculino", "Design"),
    ("Yves Saint Laurent","MYSLF",                            "EDP",             "Masculino", "Design"),
    ("Yves Saint Laurent","Y",                                "EDP",             "Masculino", "Design"),

    # ── FEMININOS ───────────────────────────────────────────────────────────
    ("Lattafa",          "Ameerat Al Arab",                   "EDP",             "Feminino",  "Árabe"),
    ("Burberry",         "Goddess",                           "EDP",             "Feminino",  "Design"),
    ("Burberry",         "Her",                               "EDP",             "Feminino",  "Design"),
    ("Bvlgari",          "Omnia Crystalline",                 "EDT",             "Feminino",  "Design"),
    ("Calvin Klein",     "CK IN2U",                           "EDT",             "Feminino",  "Design"),
    ("Calvin Klein",     "Everyone",                          "EDT",             "Unissex",   "Design"),
    ("Carolina Herrera", "CH Feminino",                       "EDP",             "Feminino",  "Design"),
    ("Carolina Herrera", "Good Girl",                         "EDP",             "Feminino",  "Design"),
    ("Carolina Herrera", "Good Girl Blush",                   "EDP",             "Feminino",  "Design"),
    ("Carolina Herrera", "Very Good Girl",                    "EDP",             "Feminino",  "Design"),
    ("Chanel",           "Chance Eau Tendre",                 "EDT",             "Feminino",  "Design"),
    ("Chanel",           "Coco Mademoiselle",                 "EDP",             "Feminino",  "Design"),
    ("Chanel",           "Gabrielle Essence",                 "EDP",             "Feminino",  "Design"),
    ("Chanel",           "N°5 L'Eau",                         "EDT",             "Feminino",  "Design"),
    ("Chloé",            "Eau de Parfum",                     "EDP",             "Feminino",  "Design"),
    ("Coach",            "Dreams Sunset",                     "EDP",             "Feminino",  "Design"),
    ("Coach",            "Floral",                            "EDP",             "Feminino",  "Design"),
    ("Lattafa",          "Durrat Al Aroos",                   "EDP",             "Feminino",  "Árabe"),
    ("Dior",             "Hypnotic Poison",                   "EDT",             "Feminino",  "Design"),
    ("Dior",             "J'adore",                           "EDP",             "Feminino",  "Design"),
    ("Dior",             "Miss Dior",                         "EDP",             "Feminino",  "Design"),
    ("Dolce & Gabbana",  "Devotion",                          "EDP",             "Feminino",  "Design"),
    ("Dolce & Gabbana",  "Light Blue",                        "EDT",             "Feminino",  "Design"),
    ("Dolce & Gabbana",  "Q",                                 "EDP",             "Feminino",  "Design"),
    ("Dolce & Gabbana",  "The Only One",                      "EDP",             "Feminino",  "Design"),
    ("Elie Saab",        "Le Parfum",                         "EDP",             "Feminino",  "Design"),
    ("Giorgio Armani",   "Acqua di Gioia",                    "EDP",             "Feminino",  "Design"),
    ("Giorgio Armani",   "My Way",                            "EDP",             "Feminino",  "Design"),
    ("Giorgio Armani",   "My Way Nectar",                     "EDP",             "Feminino",  "Design"),
    ("Giorgio Armani",   "Sì",                                "EDP",             "Feminino",  "Design"),
    ("Givenchy",         "Irresistible",                      "EDP",             "Feminino",  "Design"),
    ("Givenchy",         "L'Interdit Rouge",                  "EDP",             "Feminino",  "Design"),
    ("Gucci",            "Bloom",                             "EDP",             "Feminino",  "Design"),
    ("Gucci",            "Flora Gorgeous Gardenia",           "EDP",             "Feminino",  "Design"),
    ("Jean Paul Gaultier","La Belle Le Parfum",               "Parfum",          "Feminino",  "Design"),
    ("Jean Paul Gaultier","Scandal",                          "EDP",             "Feminino",  "Design"),
    ("Jimmy Choo",       "I Want Choo",                       "EDP",             "Feminino",  "Design"),
    ("Lancôme",          "Idôle",                             "EDP",             "Feminino",  "Design"),
    ("Lancôme",          "La Vie Est Belle",                  "EDP",             "Feminino",  "Design"),
    ("Lancôme",          "Trésor La Nuit",                    "EDP",             "Feminino",  "Design"),
    ("Lattafa",          "Fakhar Rose",                       "EDP",             "Feminino",  "Árabe"),
    ("Lattafa",          "Sabah Al Ward",                     "EDP",             "Feminino",  "Árabe"),
    ("Lattafa",          "Yara",                              "EDP",             "Feminino",  "Árabe"),
    ("Moschino",         "Toy 2",                             "EDP",             "Feminino",  "Design"),
    ("Mugler",           "Alien",                             "EDP",             "Feminino",  "Design"),
    ("Mugler",           "Angel",                             "EDP",             "Feminino",  "Design"),
    ("Narciso Rodriguez","For Her",                           "EDP",             "Feminino",  "Design"),
    ("Narciso Rodriguez","Musc Noir Rose",                    "EDP",             "Feminino",  "Design"),
    ("Prada",            "Candy",                             "EDP",             "Feminino",  "Design"),
    ("Prada",            "Paradoxe",                          "EDP",             "Feminino",  "Design"),
    ("Valentino",        "Donna Born in Roma",                "EDP",             "Feminino",  "Design"),
    ("Versace",          "Bright Crystal",                    "EDT",             "Feminino",  "Design"),
    ("Versace",          "Crystal Noir",                      "EDT",             "Feminino",  "Design"),
    ("Versace",          "Dylan Purple",                      "EDP",             "Feminino",  "Design"),
    ("Versace",          "Pour Femme Dylan Blue",             "EDP",             "Feminino",  "Design"),
    ("Viktor & Rolf",    "Flowerbomb",                        "EDP",             "Feminino",  "Design"),
    ("Yves Saint Laurent","Libre",                            "EDP",             "Feminino",  "Design"),
    ("Yves Saint Laurent","Libre Intense",                    "EDP",             "Feminino",  "Design"),
    ("Yves Saint Laurent","Mon Paris",                        "EDP",             "Feminino",  "Design"),
    ("Zara",             "Lightly Bloom",                     "EDT",             "Feminino",  "Design"),
]

def run():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    added_brands = 0
    added_perfumes = 0
    skipped = 0

    for brand_name, perf_name, concentration, gender, style in PERFUMES:
        # Garante que a marca existe
        cur.execute("SELECT id FROM brands WHERE name = ?", (brand_name,))
        row = cur.fetchone()
        if row:
            brand_id = row[0]
        else:
            cur.execute("INSERT INTO brands (name) VALUES (?)", (brand_name,))
            brand_id = cur.lastrowid
            added_brands += 1
            print(f"  ✚ Marca: {brand_name}")

        # Verifica duplicidade (mesma marca + mesmo nome)
        cur.execute(
            "SELECT id FROM perfumes WHERE brand_id = ? AND LOWER(name) = LOWER(?)",
            (brand_id, perf_name)
        )
        if cur.fetchone():
            skipped += 1
            continue

        cur.execute(
            """INSERT INTO perfumes (brand_id, name, concentration, gender, family)
               VALUES (?, ?, ?, ?, ?)""",
            (brand_id, perf_name, concentration, gender, style)
        )
        added_perfumes += 1
        print(f"  ✔ {brand_name} — {perf_name} ({concentration}, {gender})")

    con.commit()
    con.close()
    print(f"\nConcluído: {added_perfumes} perfume(s) adicionado(s), "
          f"{added_brands} marca(s) nova(s), {skipped} já existia(m).")

if __name__ == '__main__':
    run()
