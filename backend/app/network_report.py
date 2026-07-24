from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import NetworkScan


BRAND = colors.HexColor("#16C79A")
DARK = colors.HexColor("#08202E")
MUTED = colors.HexColor("#587080")
FONT_DIR = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("CyberPME", FONT_DIR / "Vera.ttf"))
pdfmetrics.registerFont(TTFont("CyberPME-Bold", FONT_DIR / "VeraBd.ttf"))


def build_network_scan_pdf(scan: NetworkScan) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Rapport CyberPME - {scan.target}",
        author="CyberPME Africa",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Body", parent=styles["Normal"], fontName="CyberPME", fontSize=9, leading=13))
    styles.add(ParagraphStyle(name="BrandTitle", parent=styles["Title"], fontName="CyberPME-Bold", textColor=DARK, fontSize=22, leading=27, spaceAfter=8))
    styles.add(ParagraphStyle(name="Subtitle", parent=styles["Body"], textColor=MUTED, fontSize=10, leading=14))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="CyberPME-Bold", textColor=DARK, fontSize=15, leading=19, spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle(name="Host", parent=styles["Heading3"], fontName="CyberPME-Bold", textColor=BRAND, fontSize=12, leading=15, spaceAfter=6))
    styles.add(ParagraphStyle(name="Footer", parent=styles["Body"], alignment=TA_CENTER, textColor=MUTED, fontSize=8))

    story = [
        Paragraph("CyberPME Africa", styles["BrandTitle"]),
        Paragraph("Rapport d'audit réseau autorisé", styles["Section"]),
        Paragraph(
            f"Cible : <b>{scan.target}</b><br/>"
            f"Date : {scan.completed_at.strftime('%d/%m/%Y %H:%M UTC') if scan.completed_at else 'Non disponible'}<br/>"
            f"Équipements détectés : <b>{len(scan.results)}</b>",
            styles["Subtitle"],
        ),
        Spacer(1, 10 * mm),
        Paragraph("Synthèse", styles["Section"]),
    ]

    total_ports = sum(len(host.get("ports", [])) for host in scan.results)
    total_recommendations = sum(len(host.get("recommendations", [])) for host in scan.results)
    summary = Table(
        [
            ["Équipements", "Ports ouverts", "Recommandations"],
            [str(len(scan.results)), str(total_ports), str(total_recommendations)],
        ],
        colWidths=[52 * mm, 52 * mm, 52 * mm],
    )
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#EAF8F4")),
                ("TEXTCOLOR", (0, 1), (-1, 1), DARK),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "CyberPME-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "CyberPME"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8D2D8")),
            ]
        )
    )
    story.extend([summary, Spacer(1, 8 * mm), Paragraph("Détails des équipements", styles["Section"])])

    if not scan.results:
        story.append(Paragraph("Aucun équipement actif n'a été détecté sur la cible.", styles["Body"]))

    for host in scan.results:
        host_story = []
        label = host.get("hostname") or host.get("ip_address") or "Équipement inconnu"
        host_story.append(Paragraph(label, styles["Host"]))
        if host.get("hostname"):
            host_story.append(Paragraph(f"Adresse IP : {host.get('ip_address')}", styles["Subtitle"]))
        ports = host.get("ports", [])
        if ports:
            rows = [["Port", "Service", "Produit / version"]]
            for port in ports:
                product_version = " ".join(filter(None, [port.get("product", ""), port.get("version", "")])) or "-"
                rows.append([f"{port.get('port')}/{port.get('protocol')}", port.get("service") or "inconnu", product_version])
            table = Table(rows, colWidths=[30 * mm, 45 * mm, 81 * mm], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDF3ED")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
                        ("FONTNAME", (0, 0), (-1, 0), "CyberPME-Bold"),
                        ("FONTNAME", (0, 1), (-1, -1), "CyberPME"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BCD1D8")),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            host_story.extend([Spacer(1, 3 * mm), table])
        else:
            host_story.append(Paragraph("Aucun port courant ouvert détecté.", styles["Body"]))

        recommendations = host.get("recommendations", [])
        if recommendations:
            host_story.append(Spacer(1, 3 * mm))
            host_story.append(Paragraph("<b>Recommandations</b>", styles["Body"]))
            for recommendation in recommendations:
                host_story.append(Paragraph(f"- {recommendation}", styles["Body"]))
        host_story.append(Spacer(1, 7 * mm))
        if len(ports) <= 10:
            story.append(KeepTogether(host_story))
        else:
            story.extend(host_story)

    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph(
                "Ce rapport présente une observation ponctuelle. Il ne remplace pas un audit de sécurité complet.",
                styles["Footer"],
            ),
        ]
    )
    document.build(story)
    return output.getvalue()
