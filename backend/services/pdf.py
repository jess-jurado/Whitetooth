from io import BytesIO
from html import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def budget_pdf(budget, patient, treatments):
    output = BytesIO()
    styles = getSampleStyleSheet()
    body = styles['BodyText']
    rows = [[Paragraph(s, body) for s in ['Tratamiento / piezas FDI', 'Estado', 'Importe']]]
    for t in treatments:
        rows.append([Paragraph(escape(t.name) + '<br/>' + escape(', '.join(map(str, t.teeth)) or 'General') + ' · ' + escape(', '.join(t.surfaces)) + '<br/>' + escape(t.notes), body), Paragraph(escape(t.status), body), f'{t.price_cents / 100:.2f} EUR'])
    table = Table(rows, colWidths=[290, 100, 85], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#deefea')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#dde4e2'))]))
    total = sum(t.price_cents for t in treatments if t.status != 'Cancelado')
    elements = [Paragraph('DENTALIS',styles['Title']), Paragraph('Presupuesto B-%04d · DEMOSTRACIÓN' % budget.id,styles['Heading2']), Paragraph(escape(patient.name),body), Paragraph(escape(budget.title),body), Spacer(1,20),table,Spacer(1,18),Paragraph(f'Total vigente: {total/100:.2f} EUR',styles['Heading2']),Paragraph('Datos ficticios. Importe por línea, con independencia del número de piezas. Las líneas canceladas no se incluyen en el total. Este documento no es una factura.',body)]
    SimpleDocTemplate(output, title='Presupuesto Dentalis', leftMargin=60,rightMargin=60).build(elements)
    return output.getvalue()
