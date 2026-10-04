"""Build the responsive journal and dated PDF from append-only daily records."""
import json, html, datetime, pathlib, re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADERS = ['Datum', 'Coin', 'Kurs (USDT)', 'Trend', 'Support', 'Widerstand', 'Long-Zone', 'Short-Zone', 'Breakout', 'Breakdown', 'Ziele', 'Heatmap-Cluster', 'Heatmap-Dominanz', 'Veränderung zum Vortag']
NOTE = 'Kurs, Einstiegszonen, Breakout, Breakdown und Ziele: bestehende Tagesseiten. Trend, Support, Widerstand und Cluster: separate Heatmap-Ansichten (11:00 Uhr). Die Ansichten haben unterschiedliche Marken. Clusterpreise werden wie in den vorhandenen Grafiken übernommen. Vortagsvergleich nur mit einem Eintrag vom vorherigen Kalendertag; keine Live-Kurse.'

def number(n):
    if n is None: return 'Nicht verfügbar'
    return (f'{n:,.0f}' if n >= 100 else f'{n:.4f}'.rstrip('0').rstrip('.')).replace(',', 'X').replace('.', ',').replace('X', '.')

def rows(records):
    keys = [(r['date'], r['coin']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate daily coin record')
    result = []
    for r in sorted(records, key=lambda r: (r['date'], r['coin']), reverse=True):
        prior = (datetime.date.fromisoformat(r['date']) - datetime.timedelta(days=1)).isoformat()
        prev = next((p for p in records if p['date'] == prior and p['coin'] == r['coin']), None)
        delta = 'Nicht verfügbar' if r['price'] is None or (prev and prev['price'] is None) else ('Kein Vortag' if prev is None or prev['price'] <= 0 else f"{(r['price']/prev['price']-1)*100:+.2f} %".replace('.', ','))
        result.append([datetime.date.fromisoformat(r['date']).strftime('%d.%m.%Y'), r['coin'], number(r['price']), r['trend'], r['support'], r['resistance'], r['longZone'], r['shortZone'], ('> ' if r['breakout'] is not None else '') + number(r['breakout']), ('< ' if r['breakdown'] is not None else '') + number(r['breakdown']), r['targets'], r['clusters'], 'Nicht verfügbar' if r['dominance'] is None else (f"{r['dominance']:.0%} unterhalb" if isinstance(r['dominance'], (int,float)) else r['dominance']), delta])
    return result

def build():
    global NOTE
    dataset = json.loads((ROOT/'data/journal.json').read_text())
    NOTE = dataset.get('dailyStatus', {}).get('note', NOTE)
    records = json.loads((ROOT/'data/journal.json').read_text())['records']
    allrows = rows(records)
    latest = max(r['date'] for r in records)
    downloads = ROOT/'downloads'; downloads.mkdir(exist_ok=True)
    buttons = f'<div class="actions"><a class="btn" href="downloads/crypto-journal-{latest}.pdf" target="_blank" rel="noopener">PDF öffnen</a><a class="btn" href="downloads/crypto-journal-{latest}.xlsx" download>Excel herunterladen</a></div>'
    prefix = (ROOT/'journal.html').read_text().split('<main')[0]
    body = '<main class="shell"><section class="section card"><h2>Excel / Journal</h2><p class="lead muted">BTC und XRP im täglichen Vergleich. Alle Kursmarken in USDT.</p>' + buttons + '<p class="muted">Downloads: Tagesübersicht '+datetime.date.fromisoformat(latest).strftime('%d.%m.%Y')+'. Filter verändern nur die Tabellenansicht.</p></section>'
    body += '<section class="section" aria-labelledby="journal-title"><h2 id="journal-title">Tagesdaten &amp; Historie</h2><div class="journal-filters" role="group" aria-label="Coin filtern"><button type="button" data-coin="Alle" aria-pressed="true">Alle</button><button type="button" data-coin="BTC" aria-pressed="false">BTC</button><button type="button" data-coin="XRP" aria-pressed="false">XRP</button></div><p id="journal-status" role="status" aria-live="polite">'+str(len(allrows))+' Einträge</p><div class="table-wrap journal-wrap" tabindex="0" role="region" aria-label="Journal-Tabelle, horizontal scrollbar"><table class="journal-table"><caption>BTC-/XRP-Journal · neueste Tage zuerst</caption><thead><tr>'
    body += ''.join('<th scope="col">'+h+'</th>' for h in HEADERS)+'</tr></thead><tbody>'
    for row in allrows:
        body += '<tr data-coin="'+row[1]+'">'+''.join('<'+('th scope="row"' if i==1 else 'td')+' data-label="'+h+'">'+html.escape(str(v))+'</'+('th' if i==1 else 'td')+'>' for i,(h,v) in enumerate(zip(HEADERS,row)))+'</tr>'
    body += '</tbody></table></div></section><section class="section card"><h3>Datenstand &amp; Quellen</h3><p class="lead muted">'+NOTE+'</p><div class="actions"><a class="btn secondary" href="btc.html">BTC-Quellen</a><a class="btn secondary" href="xrp.html">XRP-Quellen</a><a class="btn secondary" href="archiv.html">Historie öffnen</a></div></section><div class="footer">Liquidation-Heatmaps zeigen modellierte Zonen. Keine Anlageberatung.</div></main><script src="journal.js" defer></script></body></html>'
    (ROOT/'journal.html').write_text(prefix+body)
    reference_path = ROOT/'excel-reference.html'
    if reference_path.exists():
        reference = reference_path.read_text().replace('id="excel-original"', 'id="journal"', 1)
        reference_block = '<!-- EXCEL REFERENCE START -->' + reference + '<!-- EXCEL REFERENCE END -->'
        journal_page = prefix + body.replace('<main class="shell">', '<main class="shell">' + reference_block, 1)
        if 'href="excel-reference.css' not in journal_page:
            journal_page = journal_page.replace('</head>', '<link rel="stylesheet" href="excel-reference.css?v=20261003-template"></head>')
        journal_page = journal_page.replace('</body>', '<script src="excel-reference.js?v=20261003-template" defer></script></body>')
        (ROOT/'journal.html').write_text(journal_page)
    # Keep the complete journal on the chart dashboard in sync with daily data.
    index_path = ROOT/'index.html'
    index = index_path.read_text()
    embedded = body.split('<main class="shell">', 1)[1].split('<div class="footer">', 1)[0]
    anchor = 'daily-journal' if reference_path.exists() else 'journal'
    embedded = embedded.replace('<section class="section card">', f'<section id="{anchor}" class="section card" style="scroll-margin-top:150px">', 1)
    block = '<!-- JOURNAL START -->\n' + embedded + '\n<!-- JOURNAL END -->'
    if '<!-- JOURNAL START -->' in index:
        index = re.sub(r'<!-- JOURNAL START -->.*?<!-- JOURNAL END -->', lambda _: block, index, flags=re.S)
    else:
        index = index.replace('<div class="footer">', block + '\n<div class="footer">', 1)
    if 'src="journal.js"' not in index:
        index = index.replace('</body>', '<script src="journal.js" defer></script></body>')
    index_path.write_text(index)
    styles = getSampleStyleSheet(); styles['BodyText'].fontSize=10; styles['BodyText'].leading=14
    elements = [Paragraph('CRYPTO - Tagesjournal',styles['Title']),Paragraph(datetime.date.fromisoformat(latest).strftime('%d.%m.%Y')+' | BTC und XRP | Kursmarken in USDT',styles['BodyText']),Spacer(1,16)]
    for idx,row in enumerate(sorted([x for x in allrows if x[0]==datetime.date.fromisoformat(latest).strftime('%d.%m.%Y')],key=lambda x:x[1])):
        if idx: elements += [PageBreak()]
        elements += [Paragraph(row[1],styles['Heading2'])]
        table = Table([[Paragraph(h,styles['BodyText']),Paragraph(html.escape(str(v)),styles['BodyText'])] for h,v in zip(HEADERS,row) if h not in ('Coin','Datum')],colWidths=[145,365])
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#edf3f7')),('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#c5d5e1')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        elements += [table,Spacer(1,14)]
    elements += [Paragraph('Datenherkunft',styles['Heading3']),Paragraph(NOTE,styles['BodyText']),Spacer(1,8),Paragraph('Quelle: z28dgd8phw-cyber.github.io/crypto-dashboard/ (Tagesseiten und vier Chartgrafiken).',styles['BodyText'])]
    def footer(c,d):
        c.setFont('Helvetica',9); c.drawString(42,24,'CRYPTO Journal - '+latest); c.drawRightString(A4[0]-42,24,str(d.page))
    SimpleDocTemplate(str(downloads/f'crypto-journal-{latest}.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=42).build(elements,onFirstPage=footer,onLaterPages=footer)

if __name__ == '__main__': build()
