import pytest

import bpaye.pdf as pdf
from bpaye.codes import ALL_CODES
from bpaye.pdf import ecart_totaux, ecarts_colonnes, extract_bulletin, find_pdfs, parse_amount

# Un faux bulletin PAY18E, tel que pdf._pages le rend : des morceaux de texte (x, y, texte)
# dans l'ordre du flux. Montants fictifs.
ENTETE = [(560.0, 300.0, c) for c in "PAY18E-V4.2"]
PIED = [
    (450.0, 625.0, "1 000,00"),  # total des retenues
    (520.0, 625.0, "2 000,00"),  # total patronal
    (420.0, 640.0, "4 000,00 €"),  # net à payer
    (120.0, 710.0, "3 900,00"),  # montant imposable du mois
]


def _ligne(code, libelle, montant, y, apres=None):
    """Une ligne de paye ; ``apres`` : la mention écrite après le montant (« RAPPEL… »)."""
    spans = [(16.0, y, f"{code} {libelle}"), (361.0, y, "€"), (385.0, y, montant)]
    return spans + ([(420.0, y, apres), (361.0, y + 4, "€")] if apres else [])


def _montant(texte):
    return parse_amount(texte) or 0.0


@pytest.fixture
def bulletin(monkeypatch):
    """Un faux bulletin des ``lignes`` ; TOTAUX DU MOIS vaut la somme des lignes de revenu
    plus ``decompte`` (le rappel sur décompte), sauf ``totaux`` donné."""

    def faux(lignes, decompte=None, totaux=None):
        corps = [s for i, ligne in enumerate(lignes) for s in _ligne(*ligne[:3], 130.0 + 9 * i, *ligne[3:])]
        if totaux is None:
            revenus = sum(
                _montant(m) for c, _, m, *_ in lignes if ALL_CODES.get(c, {}).get("cat") == "revenu"
            )
            totaux = f"{revenus + (_montant(decompte) if decompte else 0.0):.2f}".replace(".", ",")
        pied = [(380.0, 625.0, totaux), *PIED]
        if decompte:
            pied.append((374.0, 601.0, decompte))
        spans = ENTETE + corps + pied
        monkeypatch.setattr(pdf, "_pages", lambda chemin: [spans])
        return extract_bulletin("2026_01_BP_janvier.pdf")

    return faux


@pytest.mark.parametrize(("texte", "attendu"), [("3962,84", 3962.84), ("4 110,52", 4110.52), ("x", None)])
def test_parse_amount_virgule_et_espaces(texte, attendu):
    assert parse_amount(texte) == attendu


def test_extract_bulletin_lit_codes_et_pied(bulletin):
    lu = bulletin([("101000", "TRAITEMENT BRUT", "3000,00"), ("102000", "INDEMNITE DE RESIDENCE", "90,00")])
    assert (lu["101000"], lu["102000"]) == (3000.0, 90.0)
    assert (lu["_totaux_mois"], lu["_total_ret"], lu["_total_pat"]) == (3090.0, 1000.0, 2000.0)
    assert (lu["_net_payer"], lu["_montant_imp"]) == (4000.0, 3900.0)


HSA = "HEURES ANNEES ENSEIGNT"
COLLES = "HEURES D INTERROGATION"


@pytest.mark.parametrize(
    "rappel",
    [
        ("200205", f"{HSA}    RAPPEL ANNEE COURANTE", "50,00"),  # mention fondue dans le libellé
        ("200205", HSA, "50,00", "RAPPEL ANNEE COURANTE"),  # mention après le montant
        ("200205", HSA, "50,00", "RAPPEL ANNEES ANTER"),  # rappel d'une année passée, tronqué
    ],
)
def test_extract_bulletin_rappel_selon_la_mention(bulletin, rappel):
    lu = bulletin([("200205", HSA, "300,00"), rappel])
    assert (lu["200205"], lu["200205_R"]) == (300.0, 50.0)


def test_extract_bulletin_rappels_d_un_meme_code_additionnes(bulletin):
    # Deux mois de colles rattrapés le même mois.
    rappels = [
        ("200207", COLLES, "400,00", "RAPPEL ANNEE COURANTE"),
        ("200207", COLLES, "250,00", "RAPPEL ANNEE COURAN"),
    ]
    lu = bulletin(rappels)
    assert "200207" not in lu
    assert lu["200207_R"] == 650.0


def test_extract_bulletin_lignes_d_un_meme_code_additionnees(bulletin):
    jury = "IND.JURY.CONC.EXAM.- SUP."
    lu = bulletin([("201357", jury, "120,00"), ("201357", jury, "80,00")])
    assert lu["201357"] == 200.0


def test_extract_bulletin_rappel_sur_decompte_dans_les_totaux(bulletin):
    lu = bulletin([("101000", "TRAITEMENT BRUT", "3000,00")], decompte="436,06")
    assert lu["_rappel_decompte"] == 436.06
    assert ecart_totaux(lu) == 0.0


def test_extract_bulletin_ligne_manquee_signalee(bulletin):
    with pytest.warns(UserWarning, match="TOTAUX DU MOIS"):
        lu = bulletin([("101000", "TRAITEMENT BRUT", "3000,00")], totaux="3100,00")
    assert ecart_totaux(lu) == 100.0


def test_extract_bulletin_code_inconnu_signale(bulletin):
    with pytest.warns(UserWarning, match="code 999123 inconnu"):
        lu = bulletin([("999123", "PRIME NOUVELLE", "12,34")])
    assert lu["_unknown"] == [("999123", "PRIME NOUVELLE", 12.34)]


def test_extract_bulletin_version_inconnue_signalee(monkeypatch):
    spans = _ligne("101000", "TRAITEMENT BRUT", "3000,00", 130.0)
    monkeypatch.setattr(pdf, "_pages", lambda chemin: [spans])
    with pytest.warns(UserWarning, match="version PAY18E non reconnue"):
        extract_bulletin("2026_01_BP_janvier.pdf")


def test_extract_bulletin_sur_un_vrai_pdf(tmp_path, faux_bulletin_pdf):
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    faux_bulletin_pdf(chemin)
    lu = extract_bulletin(chemin)
    assert (lu["101000"], lu["200205"], lu["200205_R"]) == (3000.0, 300.0, 50.0)
    assert (lu["_totaux_mois"], lu["_total_ret"], lu["_total_pat"]) == (3350.0, 1000.0, 2000.0)
    assert (lu["_net_payer"], lu["_montant_imp"]) == (2350.0, 2600.0)


def test_extract_bulletin_reprise_sans_mention_d_un_code_rappelable(bulletin):
    lu = bulletin([("200205", HSA, "300,00"), ("200205", HSA, "300,00")])
    assert (lu["200205"], lu["200205_R"]) == (300.0, 300.0)


def test_find_pdfs_trouve_aussi_les_bulletins_d_un_sous_dossier(tmp_path, faux_bulletin_pdf):
    (tmp_path / "autre_employeur").mkdir()
    faux_bulletin_pdf(tmp_path / "autre_employeur" / "2026_01_BP_janvier.pdf")
    assert [p.name for p in find_pdfs(tmp_path, 2026)[1]] == ["2026_01_BP_janvier.pdf"]


def test_bulletin_lu_se_lit_comme_un_dict_sans_se_modifier(tmp_path, faux_bulletin_pdf):
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    faux_bulletin_pdf(chemin)
    lu = extract_bulletin(chemin)
    assert lu.totaux_mois == lu["_totaux_mois"] == 3350.0
    assert lu.montants["200205_R"] == 50.0 and "200205_R" in lu
    with pytest.raises(TypeError):
        lu["101000"] = 0.0


def test_colonne_de_chaque_montant_lue(tmp_path, faux_bulletin_pdf):
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    faux_bulletin_pdf(chemin)
    colonnes = {(ligne.code, ligne.colonne) for ligne in extract_bulletin(chemin).lignes}
    assert colonnes == {
        ("101000", "payer"),
        ("200205", "payer"),
        ("401301", "deduire"),
        ("404001", "information"),
    }


def test_traitement_repris_a_deduire_compte_en_moins(tmp_path, faux_bulletin_pdf):
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    lignes = [
        ("101000", "TRAITEMENT BRUT", "3000,00"),
        ("101000", "TRAITEMENT BRUT", "100,00", 457.4),  # un trop-perçu repris
    ]
    faux_bulletin_pdf(chemin, lignes, "3000,00")
    lu = extract_bulletin(chemin)
    assert lu["101000"] == 2900.0
    assert ecarts_colonnes(lu) == {"payer": 0.0, "deduire": 0.0, "information": 0.0}


def test_retenue_manquee_signalee(tmp_path, faux_bulletin_pdf):
    chemin = tmp_path / "2026_01_BP_janvier.pdf"
    lignes = [("101000", "TRAITEMENT BRUT", "3000,00"), ("999999", "CODE INCONNU", "50,00", 457.4)]
    faux_bulletin_pdf(chemin, lignes, "3000,00")
    with pytest.warns(UserWarning, match="« à déduire » \\(écart de 50.0 €\\)"):
        extract_bulletin(chemin)


def test_decompte_lit_toute_ligne_d_un_code_connu():
    from bpaye.pdf import DR_ROW_CODES

    assert DR_ROW_CODES["TRAITEMENT BRUT"] == "101000"
    assert DR_ROW_CODES[ALL_CODES["101070"]["libelle"].upper()] == "101070"  # NBI


def test_find_pdfs_ecarte_un_scan_sans_texte(tmp_path, faux_bulletin_pdf):
    from reportlab_layout import PDFMaker

    faux_bulletin_pdf(tmp_path / "2026_01_BP_janvier.pdf")
    (tmp_path / "Scans").mkdir()
    with PDFMaker(str(tmp_path / "Scans" / "2026_02_BP_fevrier.pdf"), pagesize=(595.0, 842.0)) as doc:
        doc.canvas.rect(50, 50, 400, 600, fill=1)  # une image seule, sans caractère
    assert {mois: [p.name for p in chemins] for mois, chemins in find_pdfs(tmp_path, 2026).items()} == {
        1: ["2026_01_BP_janvier.pdf"]
    }


def test_montant_simule_du_pas_hors_du_total_pour_information():
    # Décembre 2018 : le montant simulé du prélèvement, imprimé pour information, n'entre
    # pas dans le total pour information, que les seules cotisations patronales retrouvent.
    lu = pdf.BulletinLu(
        lignes=(
            pdf.LigneLue("403301", "COTIS PATRON. ALLOC FAMIL", "information", 170.98, False),
            pdf.LigneLue(
                "558001", "MONTANT SIMULE DU PRELEVEMENT A LA SOURCE", "information", 1136.22, False
            ),
        ),
        total_pat=170.98,
    )
    assert ecarts_colonnes(lu)["information"] == 0.0
