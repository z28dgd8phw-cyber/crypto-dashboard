"""Render the supplied Excel example as native, styled web tables. Read-only XLSX input."""
import datetime
import html
import pathlib
import sys
import re
import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = pathlib.Path(sys.argv[1])
book = openpyxl.load_workbook(SOURCE, data_only=True)

def escape(value):
    return html.escape(str(value), quote=True)

def display(cell):
    value = cell.value
    if value is None: return ''
    if isinstance(value, (datetime.date, datetime.datetime)): return value.strftime('%d.%m.%Y')
    if isinstance(value, (int, float)):
        text = f'{value:,.0f}'.replace(',', '.') if '#,##0' in cell.number_format else str(value).replace('.', ',')
        return text + (' USDT' if 'USDT' in cell.number_format else '')
    return str(value)

def style(cell):
    background = '#ffffff'
    if cell.fill.patternType == 'solid' and cell.fill.fgColor.type == 'rgb':
        background = '#' + cell.fill.fgColor.rgb[-6:]
    color = '#252525'
    if cell.font.color is not None and cell.font.color.type == 'rgb': color = '#' + cell.font.color.rgb[-6:]
    return f'background:{background};color:{color};font-weight:{700 if cell.font.bold else 400};text-align:{cell.alignment.horizontal or ("right" if isinstance(cell.value,(int,float,datetime.date)) else "left")}'

def table(sheet, bounds, caption, omit_blank=False):
    cells=list(sheet.iter_rows(min_row=bounds[0],max_row=bounds[1],min_col=bounds[2],max_col=bounds[3]))
    widths=[min(300,max(95,sheet.column_dimensions[openpyxl.utils.get_column_letter(i)].width * 7)) for i in range(bounds[2],bounds[3]+1)]
    out='<div class="excel-scroll" tabindex="0" role="region" aria-label="'+escape(caption)+'"><table class="excel-table"><caption>'+escape(caption)+'</caption><colgroup>'+''.join(f'<col style="width:{w}px">' for w in widths)+'</colgroup>'
    for idx,row in enumerate(cells):
        if omit_blank and idx and all(c.value is None for c in row): continue
        if idx==0: out+='<thead>'
        elif idx==1: out+='</thead><tbody>'
        out+='<tr>'
        for cell in row:
            tag='th' if idx==0 else 'td'
            out+='<'+tag+(' scope="col"' if idx==0 else '')+' style="'+style(cell)+'">'+escape(display(cell))+'</'+tag+'>'
        out+='</tr>'
    out+='</tbody></table></div>'
    return out

def level_chart(sheet):
    labels=[sheet.cell(r,1).value for r in range(13,20)]
    values=[sheet.cell(r,2).value for r in range(13,20)]
    baseline=83000; maximum=86000; x0=190; width=390
    svg='<svg class="excel-chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 330" role="img" aria-labelledby="level-chart-title level-chart-desc"><title id="level-chart-title">Wichtige BTC-Kursmarken</title><desc id="level-chart-desc">'+escape('; '.join(f'{l}: {v} USDT' for l,v in zip(labels,values)))+'</desc><rect width="660" height="330" rx="12" fill="white"/><text x="22" y="29" font-size="18" font-weight="700" fill="#252525">Wichtige BTC-Kursmarken (USDT)</text>'
    for tick in range(83000,86001,1000):
        x=x0+(tick-baseline)/(maximum-baseline)*width
        svg+=f'<line x1="{x}" y1="46" x2="{x}" y2="288" stroke="#e2e2e2"/><text x="{x}" y="313" text-anchor="middle" font-size="12" fill="#555">{tick:,.0f}</text>'.replace(',', '.')
    for i,(label,value) in enumerate(zip(labels,values)):
        y=53+i*33; w=(value-baseline)/(maximum-baseline)*width
        color='#db8f95' if 'Short' in label else '#79af85' if 'Long' in label else '#dfba50' if 'Ziel' in label else '#9ea5ad'
        svg+=f'<text x="180" y="{y+17}" text-anchor="end" font-size="13" fill="#252525">{escape(label)}</text><rect x="{x0}" y="{y}" width="{w}" height="23" fill="{color}"/><text x="{x0+w+8}" y="{y+17}" font-size="12" fill="#252525">{value:,.0f}</text>'.replace(',', '.')
    return svg+'</svg>'

dashboard=book['Dashboard']
content='<section id="excel-original" class="section excel-example" aria-labelledby="excel-example-title" style="scroll-margin-top:150px"><div class="section-head"><div><h2 id="excel-example-title">Excel-Dashboard wie in deiner Vorlage</h2><p>BTC · Originalwerte der Startvorlage vom 03.10.2026</p></div><a class="btn" href="downloads/BTC_Trading_Journal_Dashboard.xlsx" download>Original-Excel herunterladen</a></div><p class="excel-source-note">Beispielwerte aus deiner Excel-Datei, keine Live-Daten. Referenzkurs: 84.600 USDT. Die aktuellen BTC-/XRP-Tagesdaten stehen im Journal darunter.</p><div class="excel-tabs" role="tablist" aria-label="Excel-Arbeitsblätter">'
names=['Dashboard','Tagesanalyse','Trading Journal','Einstellungen']
for i,name in enumerate(names):
    content+=f'<button type="button" role="tab" id="excel-tab-{i}" aria-controls="excel-panel-{i}" aria-selected="{"true" if i==0 else "false"}" tabindex="{0 if i==0 else -1}">{escape(name)}</button>'
content+='</div>'
for i,name in enumerate(names):
    sheet=book[name]
    content+=f'<div role="tabpanel" id="excel-panel-{i}" aria-labelledby="excel-tab-{i}" class="excel-panel"'+(' hidden' if i else '')+'>'
    content+='<h3 class="excel-title">'+escape(sheet['A1'].value)+'</h3>'
    if sheet['A2'].value: content+='<p class="excel-subtitle">'+escape(sheet['A2'].value)+'</p>'
    if i==0:
        content+='<div class="excel-dashboard-grid">'+table(sheet,(4,9,1,2),'Kennzahlen')+table(sheet,(4,10,4,6),'Signale & Zonen')+'</div>'
        content+='<div class="excel-dashboard-grid">'+table(sheet,(12,19,1,2),'Kursmarken')+level_chart(sheet)+'</div>'
        content+=table(sheet,(21,27,1,6),'Zeitebenen')
    elif i==1:
        content+=table(sheet,(4,9,1,17),'Tagesanalyse · alle Zeitebenen')+table(sheet,(12,17,1,4),'Tagesfazit')
    elif i==2:
        content+=table(sheet,(4,40,1,21),'Trading Journal · Entry, Stop-Loss und Take-Profit',omit_blank=True)
        content+='<div class="excel-history-chart"><h4>BTC-Referenzkurs im Journal</h4><div class="excel-point"><span class="excel-dot"></span><strong>84.600 USDT</strong><span>03.10.2026</span></div><p>Ein Tagespunkt vorhanden. Eine Verlaufslinie entsteht mit weiteren Einträgen.</p></div>'
    else:
        content+=table(sheet,(3,9,1,2),'Einstellungen & Quellen')+table(sheet,(11,16,1,2),'Farblogik')
    content+='</div>'
content+='</section>'
(ROOT/'excel-reference.html').write_text(content)
(ROOT/'downloads/BTC_Trading_Journal_Dashboard.xlsx').write_bytes(SOURCE.read_bytes())
for name in ('index.html','journal.html'):
    path=ROOT/name
    page=path.read_text()
    fragment=content.replace('id="excel-original"','id="journal"',1)
    block='<!-- EXCEL REFERENCE START -->'+fragment+'<!-- EXCEL REFERENCE END -->'
    page=page.replace('<section id="journal" class="section card"','<section id="daily-journal" class="section card"')
    if '<!-- EXCEL REFERENCE START -->' in page:
        page=re.sub(r'<!-- EXCEL REFERENCE START -->.*?<!-- EXCEL REFERENCE END -->',lambda _:block,page,flags=re.S)
    elif name=='index.html':
        page=page.replace('<!-- JOURNAL START -->',block+'\n<!-- JOURNAL START -->',1)
    else:
        page=page.replace('<main class="shell">','<main class="shell">'+block,1)
    if 'href="excel-reference.css' not in page:
        page=page.replace('</head>','<link rel="stylesheet" href="excel-reference.css?v=20261003-template"></head>')
    if 'src="excel-reference.js' not in page:
        page=page.replace('</body>','<script src="excel-reference.js?v=20261003-template" defer></script></body>')
    path.write_text(page)
print('Original workbook rendered: four sheet panels, seven tables, source values unchanged.')
