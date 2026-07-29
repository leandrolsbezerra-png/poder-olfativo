"""
Vincula as fotos .avif aos perfumes no banco de dados.
Execute no PythonAnywhere:
  cd ~/poder-olfativo && python vincular_fotos.py
"""
import sqlite3, os, unicodedata, re

DB     = os.path.join(os.path.dirname(__file__), 'estoque.db')
FOTOS  = os.path.join(os.path.dirname(__file__), 'static', 'perfume_photos')

def normalizar(s):
    """Remove acentos, pontuação e deixa minúsculo para comparação."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r"[^a-z0-9 ]", ' ', s.lower())
    return re.sub(r'\s+', ' ', s).strip()

# Mapa manual: nome_do_arquivo (sem extensão, normalizado) → (brand, name) no BD
# Só precisamos dos casos que não casam automaticamente.
MANUAL = {
    # femininos
    "armani acqua di gioia":          ("Giorgio Armani",    "Acqua di Gioia"),
    "armani my way":                  ("Giorgio Armani",    "My Way"),
    "armani si edp":                  ("Giorgio Armani",    "Sì"),
    "chloe eau de parfum":            ("Chloé",             "Eau de Parfum"),
    "chanel no 5 l eau":              ("Chanel",            "N°5 L'Eau"),
    "dior j adore":                   ("Dior",              "J'adore"),
    "dolce gabbana devotion":         ("Dolce & Gabbana",   "Devotion"),
    "dolce gabbana light blue feminino":("Dolce & Gabbana", "Light Blue"),
    "dolce gabbana q":                ("Dolce & Gabbana",   "Q"),
    "dolce gabbana the only one":     ("Dolce & Gabbana",   "The Only One"),
    "givenchy l interdit rouge":      ("Givenchy",          "L'Interdit Rouge"),
    "jean paul gaultier la belle le parfum":("Jean Paul Gaultier","La Belle Le Parfum"),
    "jean paul gaultier scandal":     ("Jean Paul Gaultier","Scandal"),
    "lancome idole":                  ("Lancôme",           "Idôle"),
    "lancome la nuit tresor":         ("Lancôme",           "Trésor La Nuit"),
    "lancome la vie est belle":       ("Lancôme",           "La Vie Est Belle"),
    "miss dior eau de parfum":        ("Dior",              "Miss Dior"),
    "narciso rodriguez for her edp":  ("Narciso Rodriguez", "For Her"),
    "valentino donna born in roma":   ("Valentino",         "Donna Born in Roma"),
    "versace bright crystal edt":     ("Versace",           "Bright Crystal"),
    "versace crystal noir edt":       ("Versace",           "Crystal Noir"),
    "versace dylan blue pour femme":  ("Versace",           "Pour Femme Dylan Blue"),
    "viktor rolf flowerbomb":         ("Viktor & Rolf",     "Flowerbomb"),
    "ysl libre intense":              ("Yves Saint Laurent","Libre Intense"),
    "ysl mon paris":                  ("Yves Saint Laurent","Mon Paris"),
    # masculinos
    "acqua di gio profondo edp":      ("Giorgio Armani",    "Acqua di Giò Profondo"),
    "armani code parfum":             ("Giorgio Armani",    "Armani Code Parfum"),
    "bleu de chanel edp":             ("Chanel",            "Bleu de Chanel"),
    "chanel allure homme sport eau extreme":("Chanel",      "Allure Homme Sport Eau Extrême"),
    "chanel platinum egoiste":        ("Chanel",            "Platinum Égoïste"),
    "dolce gabbana k edp":            ("Dolce & Gabbana",   "K"),
    "dolce & gabbana k edp":          ("Dolce & Gabbana",   "K"),
    "dolce gabbana light blue pour homme":("Dolce & Gabbana","Light Blue Pour Homme"),
    "dolce & gabbana light blue pour homme":("Dolce & Gabbana","Light Blue Pour Homme"),
    "dolce gabbana the one edp":      ("Dolce & Gabbana",   "The One"),
    "dolce & gabbana the one edp":    ("Dolce & Gabbana",   "The One"),
    "givenchy gentleman reserve privee":("Givenchy",        "Gentleman Réserve Privée"),
    "hermes h24 edp":                 ("Hermès",            "H24"),
    "hermes terre d hermes edt":      ("Hermès",            "Terre d'Hermès"),
    "issey miyake l eau d issey pour homme":("Issey Miyake","L'Eau d'Issey Pour Homme"),
    "jean paul gaultier le beau le parfum":("Jean Paul Gaultier","Le Beau Le Parfum"),
    "jean paul gaultier le male le parfum":("Jean Paul Gaultier","Le Male Le Parfum"),
    "jean paul gaultier scandal pour homme":("Jean Paul Gaultier","Scandal Pour Homme"),
    "kenzo homme eau de parfum":      ("Kenzo",             "Homme"),
    "loewe esencia pour homme eau de parfum":("Loewe",      "Esencia"),
    "mercedes benz club black edt":   ("Mercedes-Benz",     "Club Black"),
    "prada l'homme":                  ("Prada",             "L'Homme"),
    "rochas moustache eau de parfum": ("Rochas",            "Moustache"),
    "stronger with you intensely":    ("Emporio Armani",    "Stronger With You Intensely"),
    "viktor rolf spicebomb extreme":  ("Viktor & Rolf",     "Spicebomb Extreme"),
    "ysl la nuit de l'homme":         ("Yves Saint Laurent","La Nuit de L'Homme"),
    "ysl myslf eau de parfum":        ("Yves Saint Laurent","MYSLF"),
    "ysl y eau de parfum":            ("Yves Saint Laurent","Y"),
}

def run():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Monta índice do BD: (norm_brand + ' ' + norm_name) → id
    cur.execute("""
        SELECT p.id, b.name as brand, p.name
        FROM perfumes p JOIN brands b ON p.brand_id = b.id
    """)
    db_index = {}
    for r in cur.fetchall():
        chave = normalizar(r['brand'] + ' ' + r['name'])
        db_index[chave] = r['id']
        # também indexa só pelo nome do perfume
        db_index.setdefault(normalizar(r['name']), r['id'])

    fotos = [f for f in os.listdir(FOTOS) if f.lower().endswith('.avif')]
    vinculados = 0
    nao_encontrados = []

    for foto in sorted(fotos):
        stem = normalizar(os.path.splitext(foto)[0])

        perf_id = None

        # 1. mapa manual
        if stem in MANUAL:
            brand, name = MANUAL[stem]
            cur.execute("""
                SELECT p.id FROM perfumes p JOIN brands b ON p.brand_id=b.id
                WHERE LOWER(b.name)=LOWER(?) AND LOWER(p.name)=LOWER(?)
            """, (brand, name))
            row = cur.fetchone()
            if row:
                perf_id = row['id']

        # 2. chave composta no índice
        if not perf_id:
            perf_id = db_index.get(stem)

        if perf_id:
            cur.execute("UPDATE perfumes SET photo_filename=? WHERE id=?", (foto, perf_id))
            vinculados += 1
            print(f"  ✔ {foto}")
        else:
            nao_encontrados.append(foto)

    con.commit()
    con.close()

    print(f"\n✅ {vinculados} foto(s) vinculada(s).")
    if nao_encontrados:
        print(f"⚠️  {len(nao_encontrados)} não encontrada(s) no banco:")
        for f in nao_encontrados:
            print(f"    • {f}")

if __name__ == '__main__':
    run()
