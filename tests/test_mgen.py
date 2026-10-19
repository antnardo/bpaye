import datetime as dt

from bpaye.mgen import mgen_charges, mgen_part_employeur

MAI_2026 = dt.date(2026, 6, 30)


def test_part_solidaire_de_l_exemple_de_la_documentation():
    # docs/mgen.md : 22,62 × (min(4 100 ; 4 005 + 32,42) + 32,42) / 3 107 = 29,63 €.
    lignes = {ligne.code: ligne.valeur for ligne in mgen_charges(4100.0, MAI_2026)}
    assert (lignes[720576], lignes[720577]) == (-15.08, -29.63)


def test_contributions_variables_sur_la_somme_des_deux_parts():
    lignes = {ligne.code: ligne.valeur for ligne in mgen_charges(4100.0, MAI_2026)}
    base = 15.08 + 29.63
    assert (lignes[720578], lignes[720579]) == (-round(0.02 * base / 1.1327, 2), -round(0.03 * base / 1.1327, 2))


def test_rien_avant_le_contrat_de_mai_2026():
    assert mgen_charges(4100.0, dt.date(2026, 4, 30)) == []
    assert (mgen_part_employeur(dt.date(2026, 4, 30)), mgen_part_employeur(MAI_2026)) == (0.0, 37.70)
