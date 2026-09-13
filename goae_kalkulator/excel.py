"""Excel-Export (.xlsx) ohne externe Abhaengigkeiten.

Eine .xlsx-Datei ist ein ZIP-Archiv mit XML-Dateien.  Der Schreiber hier
erzeugt genau die Teile, die Excel, LibreOffice und Numbers zum Oeffnen
benoetigen - dadurch laeuft der Export ohne Installation zusaetzlicher
Pakete.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape

from . import angaben, farben
from .modelle import Angebot

# Formatvorlagen -> Index in cellXfs (siehe _STYLES_XML)
STIL = {
    "normal": 0,
    "titel": 1,
    "kopf": 2,
    "euro": 3,
    "faktor": 4,
    "fett": 5,
    "euro_summe": 6,
    "hinweis": 7,
    "zahl": 8,
    "untertitel": 9,
    "euro_hell": 10,
}

# Die Farben stammen aus farben.py; der erzeugte Text ist Zeichen fuer Zeichen
# derselbe wie in der Smartphone-App (app/js/xlsx.js) - siehe Testfaelle.
_STYLES_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;EUR&quot;"/>
<numFmt numFmtId="165" formatCode="0.00#"/>
</numFmts>
<fonts count="6">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="15"/><color rgb="{farben.excel(farben.GRUEN)}"/><name val="Calibri"/></font>
<font><i/><sz val="9"/><color rgb="{farben.excel(farben.GRAU)}"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="{farben.excel(farben.WEISS)}"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="{farben.excel(farben.GRAU)}"/><name val="Calibri"/></font>
</fonts>
<fills count="4">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="{farben.excel(farben.GRUEN)}"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="{farben.excel(farben.GRUEN_TON)}"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="{farben.excel(farben.GRUEN)}"/></top><bottom/><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="11">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="4" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="1" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="5" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


@dataclass
class Zelle:
    wert: object = None
    stil: str = "normal"


@dataclass
class Blatt:
    name: str
    zeilen: list[list[Zelle]]
    breiten: Sequence[float] = ()


def _spaltenname(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _zelle_xml(spalte: int, zeile: int, zelle: Zelle) -> str:
    ref = f"{_spaltenname(spalte)}{zeile}"
    stil = STIL.get(zelle.stil, 0)
    wert = zelle.wert
    if wert is None or wert == "":
        return f'<c r="{ref}" s="{stil}"/>'
    if isinstance(wert, bool):
        wert = "ja" if wert else "nein"
    if isinstance(wert, (int, float, Decimal)):
        return f'<c r="{ref}" s="{stil}"><v>{wert}</v></c>'
    text = escape(str(wert))
    return f'<c r="{ref}" s="{stil}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _blatt_xml(blatt: Blatt) -> str:
    teile = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    ]
    if blatt.breiten:
        cols = "".join(
            f'<col min="{i + 1}" max="{i + 1}" width="{b}" customWidth="1"/>'
            for i, b in enumerate(blatt.breiten)
        )
        teile.append(f"<cols>{cols}</cols>")
    teile.append("<sheetData>")
    for nr, zeile in enumerate(blatt.zeilen, start=1):
        zellen = "".join(_zelle_xml(s, nr, z) for s, z in enumerate(zeile) if z is not None)
        teile.append(f'<row r="{nr}">{zellen}</row>' if zellen else f'<row r="{nr}"/>')
    teile.append("</sheetData></worksheet>")
    return "".join(teile)


def _blattname(name: str, vergeben: set[str]) -> str:
    sauber = "".join(" " if z in "[]:*?/\\" else z for z in name).strip() or "Blatt"
    sauber = sauber[:31]
    kandidat, zaehler = sauber, 2
    while kandidat.lower() in vergeben:
        endung = f" ({zaehler})"
        kandidat = sauber[: 31 - len(endung)] + endung
        zaehler += 1
    vergeben.add(kandidat.lower())
    return kandidat


def schreibe_arbeitsmappe(pfad: Path | str, blaetter: Sequence[Blatt]) -> Path:
    """Schreibt die Blaetter als .xlsx-Datei."""
    pfad = Path(pfad)
    if pfad.suffix.lower() != ".xlsx":
        pfad = pfad.with_suffix(".xlsx")
    pfad.parent.mkdir(parents=True, exist_ok=True)

    vergeben: set[str] = set()
    namen = [_blattname(b.name, vergeben) for b in blaetter]

    typen = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(len(blaetter))
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{typen}"
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, name in enumerate(namen)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets></workbook>"
    )
    beziehungen = "".join(
        f'<Relationship Id="rId{i + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(len(blaetter))
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{beziehungen}"
        f'<Relationship Id="rId{len(blaetter) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )

    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as archiv:
        archiv.writestr("[Content_Types].xml", content_types)
        archiv.writestr("_rels/.rels", root_rels)
        archiv.writestr("xl/workbook.xml", workbook)
        archiv.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archiv.writestr("xl/styles.xml", _STYLES_XML)
        for i, blatt in enumerate(blaetter):
            archiv.writestr(f"xl/worksheets/sheet{i + 1}.xml", _blatt_xml(blatt))
    return pfad


# -- Aufbereitung der Angebote -------------------------------------------

KOPFZEILE = [
    "Ziffer", "Leistung", "Anz.", "Punkte",
    "1,0-fach", "2,3-fach", "3,5-fach",
    "Faktor", "Betrag", "Begruendung / Hinweis",
]
BREITEN = (10, 46, 6, 8, 12, 12, 12, 9, 13, 34)


def _f(wert: Decimal) -> float:
    return float(wert)


def angebot_blatt(angebot: Angebot, name: str | None = None) -> Blatt:
    """Baut ein Tabellenblatt fuer ein einzelnes Angebot."""
    z: list[list[Zelle]] = []
    z.append([Zelle(angebot.name or "Angebot", "titel")])
    kopf = []
    if angebot.patient:
        kopf.append(f"Patient/in: {angebot.patient}")
    if angebot.beschreibung:
        kopf.append(angebot.beschreibung)
    kopf.append(f"Stand: {angebot.geaendert}")
    z.append([Zelle(" | ".join(kopf), "untertitel")])
    z.append([])
    z.append([Zelle(t, "kopf") for t in KOPFZEILE])

    for p in angebot.positionen:
        z.append([
            Zelle(p.nummer),
            Zelle(p.leistungstext),
            Zelle(p.anzahl, "zahl"),
            Zelle(p.punktzahl * p.anzahl, "zahl"),
            Zelle(_f(p.einfachsatz), "euro_hell"),
            Zelle(_f(p.satz_2_3), "euro_hell"),
            Zelle(_f(p.satz_3_5), "euro_hell"),
            Zelle(_f(p.faktor), "faktor"),
            Zelle(_f(p.betrag), "euro"),
            Zelle(p.begruendung or p.hinweis(), "hinweis"),
        ])

    z.append([
        Zelle("Summe", "fett"),
        Zelle(f"{len(angebot.positionen)} Position(en)", "fett"),
        Zelle(None), Zelle(angebot.punkte, "zahl"),
        Zelle(_f(angebot.summe_einfach), "euro_summe"),
        Zelle(_f(angebot.summe_2_3), "euro_summe"),
        Zelle(_f(angebot.summe_3_5), "euro_summe"),
        Zelle(None),
        Zelle(_f(angebot.summe), "euro_summe"),
        Zelle(None),
    ])
    z.append([])
    if angebot.zielbetrag is not None:
        z.append([
            Zelle("Zielbetrag", "fett"), Zelle(None), Zelle(None), Zelle(None),
            Zelle(None), Zelle(None), Zelle(None), Zelle(None),
            Zelle(_f(angebot.zielbetrag), "euro"),
        ])
        z.append([
            Zelle("Abweichung", "fett"), Zelle(None), Zelle(None), Zelle(None),
            Zelle(None), Zelle(None), Zelle(None), Zelle(None),
            Zelle(_f(angebot.summe - angebot.zielbetrag), "euro"),
        ])
        z.append([])
    for hinweis in angebot.hinweise():
        z.append([Zelle(hinweis, "hinweis")])
    z.append([Zelle(
        "Berechnung nach GOAE: Punktzahl x Punktwert (0,0582873 EUR) x Faktor. "
        "Faktoren oberhalb des Regelsatzes sind schriftlich zu begruenden (§ 12 GOAE). "
        "Angaben ohne Gewaehr.",
        "hinweis",
    )])
    z.append([Zelle(f"{angaben.IMPRESSUM['praxis']}  ·  {angaben.COPYRIGHT}", "hinweis")])
    return Blatt(name=name or angebot.name or "Angebot", zeilen=z, breiten=BREITEN)


def uebersicht_blatt(angebote: Sequence[Angebot], blattnamen: Sequence[str]) -> Blatt:
    z: list[list[Zelle]] = [
        [Zelle("Angebotsuebersicht", "titel")],
        [Zelle(f"Export vom {datetime.now():%d.%m.%Y %H:%M}", "untertitel")],
        [],
        [Zelle(t, "kopf") for t in
         ("Angebot", "Patient/in", "Positionen", "Punkte", "1,0-fach", "2,3-fach", "3,5-fach",
          "Kalkuliert", "Zuletzt geaendert")],
    ]
    for angebot in angebote:
        z.append([
            Zelle(angebot.name),
            Zelle(angebot.patient),
            Zelle(len(angebot.positionen), "zahl"),
            Zelle(angebot.punkte, "zahl"),
            Zelle(_f(angebot.summe_einfach), "euro_hell"),
            Zelle(_f(angebot.summe_2_3), "euro_hell"),
            Zelle(_f(angebot.summe_3_5), "euro_hell"),
            Zelle(_f(angebot.summe), "euro"),
            Zelle(angebot.geaendert),
        ])
    z.append([
        Zelle("Gesamt", "fett"), Zelle(None), Zelle(None), Zelle(None),
        Zelle(_f(sum((a.summe_einfach for a in angebote), Decimal("0.00"))), "euro_summe"),
        Zelle(_f(sum((a.summe_2_3 for a in angebote), Decimal("0.00"))), "euro_summe"),
        Zelle(_f(sum((a.summe_3_5 for a in angebote), Decimal("0.00"))), "euro_summe"),
        Zelle(_f(sum((a.summe for a in angebote), Decimal("0.00"))), "euro_summe"),
    ])
    return Blatt(name="Uebersicht", zeilen=z, breiten=(34, 22, 11, 9, 12, 12, 12, 13, 20))


def exportiere(angebote: Angebot | Sequence[Angebot], pfad: Path | str) -> Path:
    """Exportiert ein Angebot oder mehrere Angebote als .xlsx-Datei."""
    if isinstance(angebote, Angebot):
        return schreibe_arbeitsmappe(pfad, [angebot_blatt(angebote)])
    angebote = list(angebote)
    if not angebote:
        raise ValueError("Es wurden keine Angebote zum Export uebergeben.")
    if len(angebote) == 1:
        return schreibe_arbeitsmappe(pfad, [angebot_blatt(angebote[0])])
    namen = [a.name for a in angebote]
    blaetter = [uebersicht_blatt(angebote, namen)]
    blaetter += [angebot_blatt(a) for a in angebote]
    return schreibe_arbeitsmappe(pfad, blaetter)
