import pathlib,re,json,html
root=pathlib.Path(__file__).resolve().parents[1]
data=json.loads((root/'data/journal.json').read_text())
note=html.escape(data['dailyStatus']['note'])
links=' '.join('<a href="'+html.escape(url,quote=True)+'" target="_blank" rel="noopener">'+name+'</a>' for name,url in zip(['Binance','Coinbase','Kraken','BTC-Indikation (USD)','XRP-Indikation (USD)'],data['dailyStatus']['sources']))
notice='<section class="section card"><h2>Tagesstand 04.10.2026</h2><p class="lead">'+note+'</p><p>Geprüfte Quellen: '+links+'</p></section>'
for name in ['index.html','btc.html','xrp.html','journal.html','archiv.html']:
    p=root/name;s=p.read_text()
    s=s.replace('Stand: 03.10.2026','Stand: 04.10.2026').replace('20261003-journal','20261004-journal')
    s=s.replace('<main class="shell">','<main class="shell">'+notice,1)
    if name=='index.html':
        s=s.replace('Samstag · 03.10.2026','Sonntag · 04.10.2026')
        s=re.sub(r'<section class="hero">.*?</section>', '<section class="hero"><div class="card"><h2>Tagesübersicht · 04.10.2026</h2><p class="lead">BTC: aktueller USDT-Kurs nicht verfügbar.<br>XRP: aktueller USDT-Kurs nicht verfügbar.</p><p>Technische Marken und Heatmap-Daten heute nicht verifiziert. Die bisherigen Ansichten stehen unten mit Datenstand 03.10.2026.</p></div><div class="card"><h2>Journal und Downloads</h2><p>Heutige Einträge sind angelegt. Fehlende Werte bleiben ausdrücklich gekennzeichnet; die Historie und originale Excel-Beispielvorlage sind erhalten.</p></div></section>',s,count=1,flags=re.S)
        s=s.replace('crypto-journal-2026-10-03','crypto-journal-2026-10-04')
    if name in ['btc.html','xrp.html']:
        s=s.replace('Aktueller Kurs','Referenzkurs · 03.10.2026').replace('Tagesmarken','Archivmarken · 03.10.2026')
    s=s.replace('Zielzonen heute','Zielzonen vom 03.10.2026').replace('Dashboardgrafik · 30-Minuten-Chart','Datenstand 03.10.2026 · 30-Minuten-Chart').replace('Liquidationszonen als zweite Sicht','Heatmap-Datenstand 03.10.2026').replace('Primäre Trading-Ansicht','Datenstand 03.10.2026').replace('Zusätzliche Liquiditätsansicht','Datenstand 03.10.2026')
    if name=='archiv.html':
        s=s.replace('<h3>Nächster Tag</h3><p>Wird beim nächsten Tagesupdate ergänzt, ohne den 03.10. zu überschreiben.</p>','<h3>04.10.2026</h3><p>Aktuelle Daten nicht verfügbar; Charts vom 03.10. erhalten.</p><a class="btn" href="index.html">Tagesansicht öffnen</a>')
    p.write_text(s)
