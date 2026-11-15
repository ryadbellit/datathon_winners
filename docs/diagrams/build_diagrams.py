"""Génère les deux schémas d'architecture (SVG autonomes, fond blanc) : python docs/diagrams/build_diagrams.py"""
import sys
from html import escape
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
INK, MUTED, LINE, FILL = "#1f2328", "#57606a", "#c9d1d9", "#f6f8fa"
LLM_FILL, LLM_LINE = "#eef4ff", "#7aa2e3"   # agents LLM (Bedrock)
CODE_FILL = "#f6f8fa"                        # code déterministe
AWS = "#e8870c"                              # services AWS (contour)
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.parts = w, h, label, []

    def rect(self, x, y, w, h, fill=FILL, stroke=LINE, dash=None, rx=10, sw=1.5):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=13, weight=400, color=INK, anchor="middle"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

    def box(self, x, y, w, h, title, lines=(), fill=FILL, stroke=LINE, dash=None, title_size=14, tag=None, tag_color=MUTED):
        self.rect(x, y, w, h, fill, stroke, dash)
        cx = x + w / 2
        n = len(lines)
        block = 20 + 17 * n
        top = y + (h - block) / 2 + 14
        self.text(cx, top, title, title_size, 600)
        for i, line in enumerate(lines):
            self.text(cx, top + 20 + 17 * i, line, 12, 400, MUTED)
        if tag:
            self.text(x + w - 10, y + 16, tag, 10, 600, tag_color, "end")

    def arrow(self, x1, y1, x2, y2, label=None, dash=None, lx=None, ly=None, anchor="middle", color=INK):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.6" marker-end="url(#arrow)"{d}/>')
        if label:
            self.text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 7, label, 11, 500, MUTED, anchor)

    def path(self, d, label=None, lx=0, ly=0, dash=None, anchor="middle"):
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="1.6" marker-end="url(#arrow)"{ds}/>')
        if label:
            self.text(lx, ly, label, 11, 500, MUTED, anchor)

    def save(self, name):
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.label)}" '
            f'font-family="{FONT}">'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>'
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>' + "".join(self.parts) + "</svg>\n"
        )
        (OUT / name).write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------- 1. Vue d'ensemble (pitch)
s = Svg(1240, 560, "AlphaForge AI : l'investisseur pose une question, six agents sur Amazon Bedrock l'analysent avec des données publiques et rendent une réponse expliquée")
s.text(620, 40, "AlphaForge AI — une question d'investissement, une réponse qui se justifie", 20, 700)

# Investisseur
s.box(40, 170, 220, 190, "Investisseur", ["Profil : risque, horizon, ESG", "Portefeuille fictif", "Une question"])
s.text(150, 392, "Amira · Mateo · Robert", 12, 600, MUTED)
# Interface
s.box(320, 205, 200, 120, "Interface AlphaForge", ["Chat + graphe des agents", "en direct"])
# Données publiques
s.box(600, 72, 380, 86, "Données publiques", ["Jeu de départ PolyFinances · Yahoo Finance", "Banque du Canada · FRED"])
# Équipe d'agents (AWS)
s.rect(600, 200, 380, 250, "#fffaf2", AWS, sw=2)
s.text(790, 226, "Équipe de 6 agents", 15, 700)
s.text(970, 226, "Amazon Bedrock", 11, 700, AWS, "end")
rows = [("Recherche", "rassemble les preuves"), ("Analyse", "événements · portefeuille · complotiste"),
        ("Débat", "l'avocat du diable conteste"), ("Gouvernance", "valide, vérifie le profil"), ("Synthèse", "rédige en citant")]
for i, (a, b) in enumerate(rows):
    y = 244 + 40 * i
    s.rect(620, y, 340, 32, LLM_FILL, LLM_LINE, rx=7, sw=1.2)
    s.text(636, y + 21, a, 13, 600, INK, "start")
    s.text(944, y + 21, b, 12, 400, MUTED, "end")
# Réponse
s.box(1040, 170, 170, 190, "Réponse expliquée", ["✓ ⚠ ✗ contrôles du profil", "faits cités [E1]", "débat et verdict", "limites dites"])

s.arrow(260, 265, 318, 265, "question", ly=255)
s.arrow(520, 265, 598, 265, "analyse", ly=255)
s.arrow(790, 158, 790, 198, "preuves datées et sourcées", lx=800, ly=184, anchor="start")
s.arrow(980, 265, 1038, 265, "rend", ly=255)
s.path("M 1125 360 L 1125 470 L 150 470 L 150 404", "l'investisseur comprend et vérifie ce qui soutient la conclusion", 640, 462)
s.text(620, 528, "Simulation uniquement · aucune transaction · aucun conseil financier personnalisé", 12, 400, MUTED)
s.save("architecture-simple.svg")

# ---------------------------------------------------------------- 2. Architecture technique (documentation)
t = Svg(1400, 1010, "Architecture technique d'AlphaForge AI : collecte déterministe des preuves, agents LLM sur Bedrock, gouvernance par règles et observabilité AWS")
t.text(700, 36, "AlphaForge AI — architecture technique", 20, 700)

# Colonne principale x 40..1000
t.box(300, 60, 400, 64, "Interface React (Vite) — alphaforge-ai/", ["profil · portefeuille · question · graphe des agents · page Debug"])
t.arrow(500, 124, 500, 156, "POST /api/analyze/stream", lx=510, ly=145, anchor="start")
t.box(300, 158, 400, 64, "API Flask — server/src/main.py", ["profil → persona · actifs cités (« Tesla » → TSLA) · ESG"])
t.arrow(500, 222, 500, 254)

# Recherche
t.rect(40, 256, 920, 196, "#ffffff", INK, rx=12, sw=1.6)
t.text(60, 280, "Agent Recherche — collecte déterministe : aucun chiffre n'est produit par un LLM", 14, 700, INK, "start")
srcs = [
    ("Yahoo Finance", ["actualités (éditeur d'origine)", "prix des 10 derniers jours"], False),
    ("Jeu de départ (S3)", ["cours ajustés sur 5 ans", "USD/CAD BdC · taux FRED"], True),
    ("Module quantitatif", ["vol, VaR, bêta, part du risque", "GARCH, Monte Carlo, « et si »"], False),
    ("Contrôles de profil", ["9 règles, seuils documentés", "✓ ⚠ ✗ affichés dans le chat"], False),
]
for i, (title, lines, aws) in enumerate(srcs):
    x = 60 + 222 * i
    t.box(x, 296, 206, 88, title, lines, CODE_FILL, AWS if aws else LINE, title_size=13, tag="S3" if aws else None, tag_color=AWS)
    t.arrow(x + 103, 384, x + 103, 404)
t.rect(60, 406, 880, 34, "#fff8e6", "#e3b341", rx=8, sw=1.2)
t.text(500, 428, "Preuves E1…En : affirmation · source · date · valeur — les seules choses que les agents peuvent citer", 13, 600)

# Sans preuve -> connaissances générales
t.box(1040, 330, 320, 76, "Réponse en connaissances générales", ["1 appel, signalée non vérifiée → rapport"], LLM_FILL, LLM_LINE, dash="6 4", title_size=13)
t.arrow(960, 368, 1038, 368, "aucune preuve", ly=358, dash="6 4")

# Agents en parallèle
t.arrow(500, 452, 500, 482)
for i, (name, role) in enumerate([("Événements", "repère et date"), ("Storyteller", "impact sur ce portefeuille"), ("Complotiste", "théories, toujours non prouvées")]):
    x = 100 + 280 * i
    t.box(x, 484, 240, 64, name, [role], LLM_FILL, LLM_LINE, title_size=13, tag="Haiku", tag_color=LLM_LINE)
t.text(100, 476, "en parallèle", 11, 600, MUTED, "start")
for x in (220, 500, 780):
    t.arrow(x, 548, 500 if x == 500 else (420 if x < 500 else 580), 580)

# Débat
t.box(300, 582, 400, 64, "Avocat du diable", ["conteste ; 6 objections au plus"], LLM_FILL, LLM_LINE, title_size=13, tag="Sonnet", tag_color=LLM_LINE)
t.box(40, 582, 220, 64, "Réponses (tour 2)", ["agents visés, preuves existantes"], LLM_FILL, LLM_LINE, dash="6 4", title_size=13, tag="Haiku", tag_color=LLM_LINE)
t.arrow(298, 614, 262, 614, "si objection sérieuse", lx=280, ly=666, dash="6 4")
t.path("M 140 646 L 140 700 L 298 700", None)
t.arrow(500, 646, 500, 678)

# Gouvernance
t.box(300, 680, 400, 80, "Gouvernance", ["valide / rejette chaque affirmation", "règles en code : chiffre cité, contrôle ✗ ⇒ profil incohérent"], LLM_FILL, LLM_LINE, title_size=13, tag="Sonnet", tag_color=LLM_LINE)
t.arrow(500, 760, 500, 790)
t.box(300, 792, 400, 64, "Synthèse + Bedrock Guardrail", ["6 sections, chaque chiffre cité [E…]"], LLM_FILL, AWS, title_size=13, tag="Sonnet", tag_color=AWS)
t.arrow(500, 856, 500, 886)
t.box(300, 888, 400, 60, "Rapport", ["réponse · preuves · contrôles · débat · verdict"], CODE_FILL, LINE, title_size=13)
t.path("M 300 918 L 18 918 L 18 92 L 298 92", "event: report (SSE)", 28, 790, anchor="start")

# Colonne transverse
t.rect(1040, 460, 320, 488, "#ffffff", LINE, rx=12)
t.text(1200, 486, "Transverse", 14, 700)
side = [
    ("ModelRouter (alphaforge/llm.py)", ["modèle par tâche, repli, coût / appel"], LINE, "Bedrock"),
    ("Événements agent_start / end", ["flux SSE → graphe en direct"], LINE, None),
    ("CloudWatch /alphaforge/app", ["logs JSON + métriques EMF"], AWS, "AWS"),
    ("S3 reports/analyses/", ["rapport complet de chaque analyse"], AWS, "AWS"),
    ("MLflow Tracing", ["un span par agent et par appel"], LINE, None),
]
for i, (title, lines, stroke, tag) in enumerate(side):
    t.box(1060, 500 + 88 * i, 280, 74, title, lines, CODE_FILL, stroke, title_size=13, tag=tag, tag_color=AWS if stroke == AWS else MUTED)

# Légende
ly = 980
t.rect(40, ly - 14, 18, 18, LLM_FILL, LLM_LINE, rx=4, sw=1.2); t.text(66, ly, "agent LLM (Bedrock)", 12, 400, MUTED, "start")
t.rect(230, ly - 14, 18, 18, CODE_FILL, LINE, rx=4, sw=1.2); t.text(256, ly, "code déterministe", 12, 400, MUTED, "start")
t.rect(400, ly - 14, 18, 18, "#ffffff", AWS, rx=4, sw=2); t.text(426, ly, "service AWS", 12, 400, MUTED, "start")
t.parts.append(f'<line x1="540" y1="{ly - 5}" x2="580" y2="{ly - 5}" stroke="{INK}" stroke-width="1.6" stroke-dasharray="6 4"/>')
t.text(588, ly, "chemin conditionnel", 12, 400, MUTED, "start")
t.save("architecture-technique.svg")
print("ok")
