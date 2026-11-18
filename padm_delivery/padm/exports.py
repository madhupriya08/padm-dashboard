"""Executive-friendly Excel / PDF exports of the signature page (spec 8.2)."""

import html
import io

from padm.ui import is_total_label


def to_excel(frame, title, subtitle):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Signature Page 2"
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = subtitle
    ws["A2"].font = Font(italic=True, color="555555")
    header_fill = PatternFill("solid", fgColor="1F3864")
    total_fill = PatternFill("solid", fgColor="D9E1F2")
    thin = Side(style="thin", color="BFBFBF")
    for c, name in enumerate(frame.columns, start=1):
        cell = ws.cell(row=4, column=c, value=name)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    for r, row in enumerate(frame.itertuples(index=False), start=5):
        total = is_total_label(row[0])
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = Border(bottom=thin)
            if total:
                cell.font = Font(bold=True)
                cell.fill = total_fill
    for c, name in enumerate(frame.columns, start=1):
        width = max([len(str(name))] + [len(str(v)) for v in frame.iloc[:, c - 1]]) + 2
        ws.column_dimensions[get_column_letter(c)].width = min(width, 45)
    ws.freeze_panes = "B5"
    ws.row_dimensions[4].height = 32
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def to_pdf(frame, title, subtitle):
    """Landscape PDF via reportlab; returns None when reportlab isn't installed."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, legal
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return None
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(legal), leftMargin=18, rightMargin=18, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"].clone("cell", fontSize=5.5, leading=6.5)
    head_style = cell_style.clone("head", textColor=colors.white, fontName="Helvetica-Bold")
    data = [[Paragraph(html.escape(str(c)), head_style) for c in frame.columns]]
    data += [[Paragraph(html.escape(str(v)), cell_style) for v in row] for row in frame.itertuples(index=False)]
    table = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFBFBF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, row in enumerate(frame.itertuples(index=False), start=1):
        if is_total_label(row[0]):
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#D9E1F2")))
    table.setStyle(TableStyle(style))
    doc.build([Paragraph(html.escape(title), styles["Title"]), Paragraph(html.escape(subtitle), styles["Normal"]), Spacer(1, 8), table])
    return buffer.getvalue()


def to_html(frame, title, subtitle):
    """Print-to-PDF fallback when reportlab isn't available."""
    rows = "".join(
        f"<tr class='{'t' if is_total_label(r[0]) else ''}'>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r) + "</tr>"
        for r in frame.itertuples(index=False)
    )
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in frame.columns)
    return (f"<html><head><meta charset='utf-8'><style>body{{font-family:Arial;font-size:9px}}"
            f"th{{background:#1F3864;color:#fff}}td,th{{border:1px solid #bbb;padding:2px}}"
            f"tr.t td{{background:#D9E1F2;font-weight:bold}}@page{{size:landscape}}</style></head>"
            f"<body><h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p><table>{head}{rows}</table></body></html>").encode("utf-8")
