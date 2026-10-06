"""Build one source-backed daily snapshot from captured Kraken responses."""
import json,pathlib,datetime,html,re,statistics,sys
from zoneinfo import ZoneInfo
R=pathlib.Path(__file__).resolve().parents[1]
DATE=sys.argv[1] if len(sys.argv)>1 else datetime.datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
PREVIOUS=(datetime.date.fromisoformat(DATE)-datetime.timedelta(days=1)).isoformat()
DISPLAY=datetime.date.fromisoformat(DATE).strftime('%d.%m.%Y')
PREVDISPLAY=datetime.date.fromisoformat(PREVIOUS).strftime('%d.%m.%Y')
def load(name):
    data=json.loads((R/'data'/name).read_text());assert not data['error'],data['error'];return data['result']
stamp=load('kraken-time-'+DATE+'.json')['unixtime']
when=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc)
assert when.date().isoformat()==DATE
captured=when.astimezone(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y, %H:%M Uhr')
tick=load('kraken-ticker-'+DATE+'.json')
dataset=json.loads((R/'data/journal.json').read_text())
last_date=max(r['date'] for r in dataset['records'])
archive=R/'archive'/last_date/'final'
if not archive.exists():
    archive.mkdir(parents=True)
    for name in ['index.html','journal.html','btc.html','xrp.html']:
        s=(R/name).read_text()
        s=re.sub(r'(href|src)="(?!https?:|#)([^"/][^"]*)"',lambda m:m[1]+'="../../../'+m[2]+'"',s)
        for chart in ['btc_chart.svg','btc_heatmap.svg','xrp_chart.svg','xrp_heatmap.svg']:
            s=s.replace('../../../'+chart,chart)
        (archive/name).write_text(s)
    (archive/'journal.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2))
def fmt(v,coin): return (f'{v:,.1f}' if coin=='BTC' else f'{v:.4f}').replace(',','X').replace('.',',').replace('X','.')
summary=[]
for coin,pair in [('BTC','XBTUSDT'),('XRP','XRPUSDT')]:
    name='kraken-'+coin.lower()+'-daily-'+DATE+'.json';response=load(name)
    key=next(k for k in response if k!='last');candles=response[key]
    assert len(candles)>=21
    previous=[c for c in candles if datetime.datetime.fromtimestamp(c[0],datetime.timezone.utc).date().isoformat()==PREVIOUS]
    assert len(previous)==1
    prev=previous[0];high,low,close=map(float,[prev[2],prev[3],prev[4]])
    pivot=(high+low+close)/3;s1=2*pivot-high;r1=2*pivot-low;s2=pivot-(high-low);r2=pivot+(high-low)
    price=float(tick[pair]['c'][0]);change=price/close-1
    completed=[c for c in candles if c[0]<int(when.replace(hour=0,minute=0,second=0,microsecond=0).timestamp())]
    sma=statistics.mean(float(c[4]) for c in completed[-20:])
    trend=('Über' if price>sma else 'Unter')+' SMA20 ('+fmt(sma,coin)+'); '+('über' if price>pivot else 'unter')+' Tagespivot '+fmt(pivot,coin)
    row=dict(date=DATE,coin=coin,price=price,trend=trend,support='S1 '+fmt(s1,coin)+' / S2 '+fmt(s2,coin),resistance='R1 '+fmt(r1,coin)+' / R2 '+fmt(r2,coin),longZone=fmt(s1,coin)+'–'+fmt(pivot,coin)+' (Pivot-Rücklauf; Bestätigung abwarten)',shortZone=fmt(r1,coin)+'–'+fmt(r2,coin)+' (nur bei Ablehnung)',breakout=r1,breakdown=s1,targets='Oberseite R1/R2: '+fmt(r1,coin)+' / '+fmt(r2,coin)+'; Unterseite S1/S2: '+fmt(s1,coin)+' / '+fmt(s2,coin),clusters='Keine aktuelle Liquidationsquelle; alte Heatmap: 03.10.2026',dominance=None,previousClose=close,changePct=change,comparisonBasis='Kraken-Schlusskurs '+PREVDISPLAY+', UTC-Tageskerze',source='https://api.kraken.com/0/public/Ticker?pair=XBTUSDT,XRPUSDT',capturedAt=when.isoformat(),pivot=pivot,sma20=sma,dayHigh=float(tick[pair]['h'][0]),dayLow=float(tick[pair]['l'][0]))
    dataset['records']=[r for r in dataset['records'] if not (r['date']==DATE and r['coin']==coin)]+[row]
    summary.append(row)
    # Publish the exact inspected source window needed to reproduce these calculations.
    response[key]=candles[-90:];(R/'data'/name).write_text(json.dumps({'error':[],'result':response}))
    mname='kraken-'+coin.lower()+'-30m-'+DATE+'.json';intraday=load(mname);ikey=next(k for k in intraday if k!='last');bars=intraday[ikey][-96:]
    intraday[ikey]=bars;(R/'data'/mname).write_text(json.dumps({'error':[],'result':intraday}))
    bottom=min(min(float(c[3]) for c in bars),s2);top=max(max(float(c[2]) for c in bars),r2);pad=(top-bottom)*.08;bottom-=pad;top+=pad
    def y(n):return 650-(float(n)-bottom)/(top-bottom)*520
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 780" role="img" aria-label="'+coin+' 30-Minuten-Kerzen von Kraken"><rect width="1600" height="780" fill="#06111c"/><g font-family="Arial" fill="#e6f0fa"><text x="70" y="50" font-size="30">'+coin+'/USDT · Kraken · 30 Minuten</text><text x="70" y="85" font-size="19">'+captured+' Europe/Berlin · letzte Kerze noch offen</text>']
    for i in range(6):
        value=bottom+(top-bottom)*i/5;yy=y(value);svg.append(f'<path d="M70 {yy} H1410" stroke="#22384c"/><text x="1420" y="{yy+6}" font-size="18">{fmt(value,coin)}</text>')
    for label,value,color in [('S2',s2,'#ff8b8b'),('S1',s1,'#ff8b8b'),('Pivot',pivot,'#f6dc72'),('R1',r1,'#73ddb3'),('R2',r2,'#73ddb3')]:
        yy=y(value);svg.append(f'<path d="M70 {yy} H1410" stroke="{color}" stroke-dasharray="8 6"/><text x="75" y="{yy-7}" fill="{color}" font-size="17">{label} {fmt(value,coin)}</text>')
    for i,c in enumerate(bars):
        x=95+i*13.6;o,h,l,cl=map(float,c[1:5]);color='#6bdcb0' if cl>=o else '#ef7e91';yy=min(y(o),y(cl));height=max(2,abs(y(o)-y(cl)))
        svg.append(f'<path d="M{x} {y(h)} V{y(l)}" stroke="{color}"/><rect x="{x-4}" y="{yy}" width="8" height="{height}" fill="{color}"/>')
        if i%24==0:
            label=datetime.datetime.fromtimestamp(c[0],ZoneInfo('Europe/Berlin')).strftime('%d.%m. %H:%M');svg.append(f'<text x="{x}" y="700" text-anchor="middle" font-size="17">{label}</text>')
    svg.append('<text x="70" y="750" font-size="17">Pivot-Linien aus dem abgeschlossenen UTC-Vortag · Spotmarkt · keine Liquidations-Heatmap</text></g></svg>')
    (R/(coin.lower()+'-current-'+DATE+'.svg')).write_text(''.join(svg))
note='Kraken Spot BTC/USDT und XRP/USDT. Abruf '+captured+' Europe/Berlin; Börsenzeit bestätigt. Veränderung: aktueller letzter Handel gegen Kraken-Schlusskurs des '+PREVDISPLAY+' (UTC), nicht gegen den älteren Journal-Screenshot. Trend: Kurs gegen SMA20 der abgeschlossenen UTC-Tage. Klassische Tagespivots: P=(Vortagshoch+Vortagstief+Vortagsschluss)/3; S1=2P-H, R1=2P-L, S2=P-(H-L), R2=P+(H-L). Zonen und Ziele sind daraus abgeleitete Szenarien; keine unabhängig bestätigten Chart-Signale. Aktuelle Liquidations-Heatmap fehlt; Grafikstand 03.10.2026 bleibt separat erhalten.'
dataset['dailyStatus']={'capturedAt':when.isoformat(),'note':note,'sources':['https://api.kraken.com/0/public/Ticker?pair=XBTUSDT,XRPUSDT','https://api.kraken.com/0/public/OHLC?pair=XBTUSDT&interval=1440','https://api.kraken.com/0/public/OHLC?pair=XRPUSDT&interval=1440','https://api.kraken.com/0/public/Time']}
(R/'data/journal.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2))
notice='<section class="section card" id="verified-daily"><h2>Tagesstand '+DISPLAY+' · '+captured+'</h2><p>Aktuelle Kraken-Spotkurse und echte 30-Minuten-Kerzen. Technische Marken aus dem abgeschlossenen Vortag. Die ältere Heatmap steht separat unten.</p></section>'
cards=''
for row in summary:
    c=row['coin'];cards+='<div class="card"><h2>'+c+'/USDT · '+fmt(row['price'],c)+'</h2><p class="lead">'+f"{row['changePct']*100:+.2f}".replace('.',',')+' % zum Vortagsschluss</p><p>Tagesbereich (UTC): '+fmt(row['dayLow'],c)+'–'+fmt(row['dayHigh'],c)+'</p><p>'+html.escape(row['trend'])+'</p><p>Support: '+row['support']+'<br>Widerstand: '+row['resistance']+'</p></div>'
charts=''
for row in summary:
    c=row['coin'];file=c.lower()+'-current-'+DATE+'.svg';charts+='<section class="section"><div class="section-head"><div><h2>'+c+' · aktueller 30-Minuten-Chart</h2><p>Kraken Spot · echte Kerzen · Pivot-Marken aus dem UTC-Vortag</p></div><a class="btn" href="'+file+'" target="_blank">Vollbild / Zoom</a></div><div class="chart-card"><img src="'+file+'" alt="'+c+' aktueller Kraken-Chart" style="width:100%;height:auto"></div></section>'
for name in ['index.html','btc.html','xrp.html','journal.html','archiv.html']:
    p=R/name;s=p.read_text()
    s=re.sub(r'<section[^>]*id="verified-daily"[^>]*>.*?</section>','',s,flags=re.S)
    s=re.sub(r'<section class="section"><div class="section-head"><div><h2>(?:BTC|XRP) · (?:aktueller 30-Minuten-Chart|30-Minuten-Chart \(10-Uhr-Snapshot\))</h2>.*?</section>','',s,flags=re.S)
    s=re.sub(r'<section class="section card" id="report-(\d{4}-\d{2}-\d{2})">.*?</section>', lambda m: m[0] if m[1]==DATE else '', s, flags=re.S)
    s=re.sub(r'Stand: \d{2}\.\d{2}\.\d{4}[^<]*', 'Stand: '+DISPLAY+' · Kraken '+when.astimezone(ZoneInfo('Europe/Berlin')).strftime('%H:%M'), s)
    s=re.sub(r'crypto-journal-\d{4}-\d{2}-\d{2}', 'crypto-journal-'+DATE, s)
    s=s.replace('<main class="shell">','<main class="shell">'+notice,1).replace('20261004-journal','20261004-verified')
    if name=='index.html':
        s=re.sub(r'<section class="hero">.*?</section>','<section class="hero">'+cards+'</section>'+charts,s,count=1,flags=re.S)
        s=s.replace('BTC · Chart ohne Heatmap','BTC · bisherige Chartanalyse vom 03.10.').replace('XRP · Chart ohne Heatmap','XRP · bisherige Chartanalyse vom 03.10.')
    if name in ['btc.html','xrp.html']:
        c=name[:3].upper();row=next(r for r in summary if r['coin']==c)
        s=re.sub(r'<section class="hero">.*?</section>','<section class="hero">'+cards.split('</div>')[0]+'</div></section>' if c=='BTC' else '<section class="hero">'+cards.split('</div>')[1]+'</div></section>',s,count=1,flags=re.S)
        chart=charts.split('</section>')[0 if c=='BTC' else 1]+'</section>';s=s.replace(notice,notice+chart,1)
    if name=='archiv.html':
        s=re.sub(r'<div class="day"><h3>'+PREVDISPLAY+r'</h3>.*?</div>', '<div class="day"><h3>'+PREVDISPLAY+'</h3><a class="btn" href="archive/'+last_date+'/final/index.html">Gesicherten Tagesstand öffnen</a></div>', s, flags=re.S)
        s=s.replace('<div class="archive">','<div class="archive"><div class="day"><h3>'+DISPLAY+'</h3><p>Kraken-Tagesdaten und aktuelle Charts.</p><a class="btn" href="index.html">Tagesansicht öffnen</a></div>',1)
    p.write_text(s)
print(json.dumps([{'coin':r['coin'],'price':r['price'],'previousClose':r['previousClose'],'changePct':r['changePct'],'pivot':r['pivot']} for r in summary]))
