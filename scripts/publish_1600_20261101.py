#!/usr/bin/env python3
"""BTC/XRP 16-Uhr-Bericht. Kraken Spot XBTUSDT/XRPUSDT; alte Daten bleiben erhalten."""
import json, os, math, time, shutil, html, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
BERLIN=ZoneInfo("Europe/Berlin")
ROOT=Path(".")
DATE=datetime.now(BERLIN).date().isoformat()
SLOT="16-00"
API="https://api.kraken.com/0/public/"
def fetch(endpoint, params):
    url=API+endpoint+"?"+urllib.parse.urlencode(params)
    error=None
    for attempt in range(6):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"CryptoDashboard/2.0 (public market research)"})
            with urllib.request.urlopen(req,timeout=25) as r: data=json.load(r)
            if data.get("error"): raise RuntimeError(str(data["error"]))
            return data["result"],url
        except Exception as exc:
            error=exc
            time.sleep(min(2**attempt,15))
    raise RuntimeError("Market source unavailable: "+url+" / "+str(error))
def pricefmt(v,coin):
    return f"{v:,.2f}".replace(",","X").replace(".",",").replace("X",".") if coin=="BTC" else f"{v:.5f}".replace(".",",")
def esc(s): return html.escape(str(s),quote=True)
def pct(v): return ("+" if v>=0 else "")+f"{v:.2f}%".replace(".",",")
def fnum(v): return f"{v:.6f}".rstrip("0").rstrip(".")
def get_candles(pair,interval):
    res,url=fetch("OHLC",{"pair":pair,"interval":interval})
    key=next(k for k in res if k!="last")
    a=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[6])] for x in res[key]]
    now=int(datetime.now(timezone.utc).timestamp())
    # Current incomplete candle excluded from structural analysis.
    completed=[x for x in a if x[0]+interval*60<=now]
    if len(completed)<30: raise RuntimeError(f"Insufficient {pair}/{interval} OHLC bars")
    return completed,url
def trend(a):
    if len(a)<14: return "Seitwärts"
    recent=a[-6:]; previous=a[-12:-6]
    rh=max(x[2] for x in recent); ph=max(x[2] for x in previous)
    rl=min(x[3] for x in recent); pl=min(x[3] for x in previous)
    if rh>ph and rl>pl: return "Steigend (HH/HL)"
    if rh<ph and rl<pl: return "Fallend (LH/LL)"
    return "Seitwärts / gemischt"
def rsi(a):
    closes=[x[4] for x in a[-16:]]
    changes=[closes[i]-closes[i-1] for i in range(1,len(closes))]
    gains=sum(max(x,0) for x in changes)/len(changes)
    losses=sum(max(-x,0) for x in changes)/len(changes)
    return 100 if losses==0 else 100-100/(1+gains/losses)
def atr(a):
    vals=[]
    for i in range(max(1,len(a)-14),len(a)):
        x=a[i]; pc=a[i-1][4]
        vals.append(max(x[2]-x[3],abs(x[2]-pc),abs(x[3]-pc)))
    return sum(vals)/len(vals)
def pivots(a,day):
    target=int(datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc).timestamp())
    matches=[x for x in a if x[0]==target]
    if not matches: raise RuntimeError("Previous UTC daily candle missing")
    c=matches[-1]; h,l,close=c[2],c[3],c[4]
    p=(h+l+close)/3
    return {"high":h,"low":l,"close":close,"pivot":p,"s1":2*p-h,"r1":2*p-l,"s2":p-(h-l),"r2":p+(h-l)}
def svg_chart(coin,price,at,series,z,trend30):
    W,H=1280,680
    left,right,top,bottom=88,930,85,588
    a=series[-75:]
    levels=[price,z["s2"],z["s1"],z["pivot"],z["r1"],z["r2"]]
    lo=min([x[3] for x in a]+levels); hi=max([x[2] for x in a]+levels)
    pad=(hi-lo)*0.09 or 1
    lo-=pad;hi+=pad
    def y(v):return top+(hi-v)/(hi-lo)*(bottom-top)
    def label(v):return pricefmt(v,coin)
    colors={"Long":"#198754","Neutral":"#2678d4","Short":"#c94958"}
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{coin} 30 Minuten mit Pivot-Zonen">',
       '<rect width="1280" height="680" fill="#091724"/>',
       f'<text x="90" y="38" fill="#f2f5fa" font-size="25" font-family="Arial" font-weight="bold">{coin}/USDT · 30 Minuten · {DATE} 16:00</text>',
       f'<text x="90" y="65" fill="#a9c0d0" font-size="15" font-family="Arial">Kraken Spot · Abruf {esc(at)} · Kurs {label(price)} · {esc(trend30)}</text>',
       '<rect x="86" y="82" width="846" height="509" rx="9" fill="#0c2030" stroke="#335064"/>']
    for i in range(6):
        v=lo+(hi-lo)*i/5; yy=y(v)
        s.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#2c4052" stroke-dasharray="3,5"/>')
        s.append(f'<text x="8" y="{yy+5:.1f}" fill="#a9bfce" font-size="13" font-family="Arial">{label(v)}</text>')
    cw=(right-left)/len(a)
    for i,x in enumerate(a):
        cx=left+(i+0.5)*cw
        op,high,low,close=x[1],x[2],x[3],x[4]
        color="#3dd6a0" if close>=op else "#ff7585"
        s.append(f'<line x1="{cx:.1f}" y1="{y(high):.1f}" x2="{cx:.1f}" y2="{y(low):.1f}" stroke="{color}" stroke-width="1.4"/>')
        ry=min(y(op),y(close)); rh=max(1.5,abs(y(op)-y(close)))
        s.append(f'<rect x="{cx-cw*.31:.1f}" y="{ry:.1f}" width="{max(2,cw*.62):.1f}" height="{rh:.1f}" fill="{color}"/>')
    for k,col in [("s2","#e4b76b"),("s1","#58c99a"),("pivot","#77b9ff"),("r1","#ff9d9d"),("r2","#e4b76b")]:
        yy=y(z[k]);s.append(f'<line x1="{left}" y1="{yy:.1f}" x2="1230" y2="{yy:.1f}" stroke="{col}" stroke-width="1.1" stroke-dasharray="6,5" opacity=".75"/>')
    py=y(price)
    s.append(f'<line x1="{left}" y1="{py:.1f}" x2="1230" y2="{py:.1f}" stroke="#ffffff" stroke-width="2"/>')
    s.append(f'<rect x="940" y="{max(82,min(560,py-13)):.1f}" width="280" height="26" rx="5" fill="#253d50"/>')
    s.append(f'<text x="952" y="{max(101,min(579,py+5)):.1f}" font-size="14" fill="white" font-family="Arial">Live-Kurs {label(price)}</text>')
    # Beschriftete, gefüllte Boxen exakt an den Pivot-Grenzen im Chart.
    for name,lower,upper in [("Long",z["s1"],z["pivot"]),("Neutral",z["pivot"],z["r1"]),("Short",z["r1"],z["r2"])]:
        yy=y(upper); hh=max(3,y(lower)-yy)
        s.append(f'<rect x="942" y="{yy:.1f}" width="280" height="{hh:.1f}" rx="4" fill="{colors[name]}" fill-opacity=".52" stroke="{colors[name]}" stroke-width="1.5"/>')
        mid=yy+hh/2
        if hh>28:
            s.append(f'<text x="950" y="{mid+4:.1f}" font-size="13" font-family="Arial" fill="#ffffff" font-weight="bold">{name}: {label(lower)}–{label(upper)}</text>')
    s.append(f'<text x="942" y="620" font-family="Arial" font-size="14" fill="#b9d2e0">Breakout &gt; R1 {label(z["r1"])}</text>')
    s.append(f'<text x="942" y="642" font-family="Arial" font-size="14" fill="#b9d2e0">Breakdown &lt; S1 {label(z["s1"])}</text>')
    s.append('<text x="90" y="641" fill="#9ab0bf" font-family="Arial" font-size="14">Bestätigung: 30m-Schluss + Retest · Ziele R2/S2 · keine Heatmap</text></svg>')
    return "\n".join(s)
def render_table(coin,tf):
    rows="".join(f"<tr><td>{esc(k)}</td><td>{esc(v['trend'])}</td><td>{pricefmt(v['support'],coin)}</td><td>{pricefmt(v['resistance'],coin)}</td><td>{v['rsi']:.1f}</td></tr>" for k,v in tf.items())
    return "<table><thead><tr><th>Zeitraum</th><th>Struktur</th><th>Support</th><th>Widerstand</th><th>RSI14</th></tr></thead><tbody>"+rows+"</tbody></table>"
def card(coin,d):
    z=d["zones"]; p=d["price"]; diff=d["change"];pc=d["change_pct"]
    if p<z["s1"]: pos="Unter S1"
    elif p<z["pivot"]:pos="Long-Zone"
    elif p<z["r1"]:pos="Neutral-Zone"
    elif p<=z["r2"]:pos="Short-Zone"
    else:pos="Über R2"
    def v(k):return pricefmt(z[k],coin)
    return f'''<article class="card"><h2>{coin}/USDT · {pricefmt(p,coin)}</h2>
    <p class="lead">{esc(pos)} · 30m {esc(d["timeframes"]["30m"]["trend"])}</p>
    <p><strong>16:00 gegenüber 10:00:</strong> {("+" if diff>=0 else "")+pricefmt(diff,coin)} USDT ({pct(pc)}) · 10:00 {pricefmt(d["previous_price"],coin)}</p>
    <p><strong>Abruf:</strong> {esc(d["retrieved_at"])} · Kraken Spot {coin}/USDT</p>
    <p><strong>Long S1–Pivot:</strong> {v("s1")}–{v("pivot")} · <strong>Neutral Pivot–R1:</strong> {v("pivot")}–{v("r1")} · <strong>Short R1–R2:</strong> {v("r1")}–{v("r2")}</p>
    <p><strong>Breakout:</strong> über {v("r1")} · <strong>Breakdown:</strong> unter {v("s1")}</p>
    <p><strong>Long-Ziele:</strong> R1 {v("r1")} / R2 {v("r2")} · <strong>Short-Ziele:</strong> S1 {v("s1")} / S2 {v("s2")}</p>
    <p><strong>Invalidierung/Stop Long:</strong> unter {v("s2")} · <strong>Short:</strong> über {pricefmt(d["short_stop"],coin)}</p>
    <p><strong>Trigger/Bestätigung:</strong> 30-Minuten-Schlusskurs über R1 bzw. unter S1 mit Retest. Long-Zone nur bei Stabilisierung/Rückeroberung; Short-Zone nur bei bestätigter Ablehnung.</p>
    <details><summary>Alle fünf Zeitebenen (15m, 30m, 1h, 4h, Daily)</summary><div class="table-wrap">{render_table(coin,d["timeframes"])}</div></details></article>'''
def page(title,body,active):
    nav="".join(f'<a class="{("active" if active==name else "")}" href="{link}">{name}</a>' for name,link in [("Heute","index.html"),("BTC","btc.html"),("XRP","xrp.html"),("Journal","journal.html"),("Historie","archiv.html")])
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · CRYPTO Dashboard</title><link rel="stylesheet" href="style.css?v=20261101-1600"></head><body><div class="top"><div class="top-inner"><div class="brand"><div class="logo">CR</div><div><h1>CRYPTO Dashboard</h1><p>BTC & XRP · 30-Minuten-Fokus</p></div></div><span class="tag">Stand: {DATE} · 16:00 Uhr</span></div><div class="nav">{nav}</div></div><main class="shell">{body}<div class="footer">Bedingte technische Szenarien; keine pauschale Kauf- oder Verkaufsempfehlung. Keine neuen Liquidations-Heatmaps.</div></main></body></html>'''
def main():
    # Nicht vor dem vereinbarten Laufzeitpunkt abrufen.
    while datetime.now(BERLIN).hour<16 and datetime.now(BERLIN).date().isoformat()==DATE:
        time.sleep(5)
    now=datetime.now(BERLIN)
    if now.date().isoformat()!=DATE:raise RuntimeError("Wrong date")
    data={}
    intrapath=Path("data/intraday-journal.json")
    intraj=json.loads(intrapath.read_text()) if intrapath.exists() else {"records":[]}
    old_records=intraj["records"]
    for coin,pair in [("BTC","XBTUSDT"),("XRP","XRPUSDT")]:
        candles={};urls={}
        for label,iv in [("15m",15),("30m",30),("1h",60),("4h",240),("Daily",1440)]:
            candles[label],urls[label]=get_candles(pair,iv)
            time.sleep(.35)
        ticks,tickerurl=fetch("Ticker",{"pair":pair})
        tick=next(iter(ticks.values()))
        price=float(tick["c"][0])
        at=datetime.now(BERLIN).isoformat(timespec="seconds")
        yesterday=datetime.now(timezone.utc).date()-timedelta(days=1)
        z=pivots(candles["Daily"],yesterday)
        tf={}
        for label,a in candles.items():
            recent=a[-20:]
            tf[label]={"trend":trend(a),"support":min(x[3] for x in recent),"resistance":max(x[2] for x in recent),"rsi":rsi(a),"close":a[-1][4]}
        prior=[x for x in old_records if x.get("coin")==coin and x.get("date")==DATE and x.get("slot")=="10-00"]
        if not prior:raise RuntimeError("10:00 snapshot absent for "+coin+"; do not fabricate comparison")
        previous=float(prior[-1]["price"])
        d={"coin":coin,"pair":pair,"date":DATE,"slot":SLOT,"price":price,"previous_price":previous,
           "change":price-previous,"change_pct":100*(price/previous-1),"retrieved_at":at,
           "source":tickerurl,"ohlc_sources":urls,"pivot_utc_date":str(yesterday),
           "zones":z,"timeframes":tf,"short_stop":z["r2"]+max(atr(candles["30m"])*.5,(z["r2"]-z["r1"])*.12),
           "trigger":"30m close beyond R1/S1 and subsequent retest",
           "candles_30m":candles["30m"][-100:]}
        data[coin]=d
        rec={"date":DATE,"slot":SLOT,"coin":coin,"price":price,"trend":tf["30m"]["trend"],
             "support":tf["30m"]["support"],"resistance":tf["30m"]["resistance"],
             "zones":{**z,"long":[z["s1"],z["pivot"]],"neutral":[z["pivot"],z["r1"]],"short":[z["r1"],z["r2"]],
                      "long_stop":z["s2"],"short_stop":d["short_stop"],"long_targets":[z["r1"],z["r2"]],
                      "short_targets":[z["s1"],z["s2"]]},
             "change":d["change"],"change_pct":d["change_pct"],"previous_price":previous,
             "retrieved_at":at,"source":tickerurl}
        old_records=[x for x in old_records if not (x.get("date")==DATE and x.get("slot")==SLOT and x.get("coin")==coin)]
        old_records.append(rec)
    intraj["records"]=old_records
    intrapath.write_text(json.dumps(intraj,ensure_ascii=False,indent=2)+"\n")
    # Alte 11:11-Ansicht separat archivieren; 10:00 bleibt unverändert.
    arc=Path("archive")/DATE/"11-11"
    arc.mkdir(parents=True,exist_ok=True)
    for name in ["index.html","btc.html","xrp.html","journal.html"]:
        if Path(name).exists() and not (arc/name).exists():
            content=Path(name).read_text()
            content=content.replace('href="style.css','href="../../../style.css')
            content=content.replace('src="btc-kraken-','src="../../../btc-kraken-').replace('src="xrp-kraken-','src="../../../xrp-kraken-')
            (arc/name).write_text(content)
    Path("reports").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    Path("downloads").mkdir(exist_ok=True)
    for coin,d in data.items():
        fn=f"reports/{coin}_{SLOT}_Kaestchen_{DATE}.svg"
        Path(fn).write_text(svg_chart(coin,d["price"],d["retrieved_at"],d["candles_30m"],d["zones"],d["timeframes"]["30m"]["trend"]))
    Path(f"data/kraken-report-{DATE}-{SLOT}.json").write_text(json.dumps({"date":DATE,"slot":SLOT,"data":data},ensure_ascii=False,indent=2)+"\n")
    intro=f'''<section class="section card"><h2>BTC / XRP · {DATE} · 16:00 Uhr</h2><p><strong>Live-Snapshot 16:00 Uhr.</strong> Tatsächliche Abrufzeiten: BTC {esc(data["BTC"]["retrieved_at"])} · XRP {esc(data["XRP"]["retrieved_at"])}. Kraken Spot BTC/USDT und XRP/USDT. Pivot-Basis: abgeschlossener UTC-Vortag {data["BTC"]["pivot_utc_date"]}.</p><p>Beide 10-Uhr-Snapshots bleiben im Journal und unter Historie erhalten. 16:00 gegenüber 10:00 ist je Coin ausgewiesen. Die Charts verwenden echte abgeschlossene Kraken-30-Minuten-Kerzen; der aktuelle Tickerkurs ist separat markiert.</p></section>'''
    charts="".join(f'''<section class="section"><div class="section-head"><h2>{coin} · 30-Minuten-Chart mit gefüllten Zonen</h2><a class="btn" href="reports/{coin}_{SLOT}_Kaestchen_{DATE}.svg">Vollbild / Zoom</a></div><div class="chart-card"><img style="width:100%;height:auto" src="reports/{coin}_{SLOT}_Kaestchen_{DATE}.svg" alt="{coin} 30m mit Long-, Neutral- und Short-Kästchen"></div></section>''' for coin in ["BTC","XRP"])
    cards='<section class="section hero">'+card("BTC",data["BTC"])+card("XRP",data["XRP"])+'</section>'
    dl=f'<section class="section card"><h2>Downloads</h2><a class="btn" href="downloads/BTC_XRP_Tagesuebersicht_{DATE}_{SLOT}.pdf">PDF</a> <a class="btn" href="downloads/BTC_Tagesbericht_{DATE}_{SLOT}.xlsx">BTC Excel</a> <a class="btn" href="downloads/XRP_Tagesbericht_{DATE}_{SLOT}.xlsx">XRP Excel</a></section>'
    links=f'<section class="section card"><h2>Frühere Snapshots</h2><a class="btn" href="archive/{DATE}/10-00/index.html">10:00 Uhr</a> <a class="btn secondary" href="archive/{DATE}/11-11/index.html">11:11 Uhr</a> <a class="btn secondary" href="archiv.html">Historie</a></section>'
    Path("index.html").write_text(page("Heute",intro+cards+charts+dl+links,"Heute"))
    for coin in ["BTC","XRP"]:
        Path(coin.lower()+".html").write_text(page(coin,intro+card(coin,data[coin])+next(s for s in [f'<section class="section"><img style="width:100%" src="reports/{coin}_{SLOT}_Kaestchen_{DATE}.svg" alt="{coin} 30m"></section>'])+dl+links,coin))
    # Journal: neueste Einträge zuerst, alle früheren Einträge unverändert im JSON.
    rows=[]
    for r in sorted(old_records,key=lambda x:(x.get("date",""),x.get("slot",""),x.get("coin","")),reverse=True):
        c=r.get("coin","BTC"); z=r.get("zones",{})
        def zv(k):return pricefmt(z[k],c) if k in z else "–"
        delta=r.get("change"); delta_text=(("+" if delta>=0 else "")+pricefmt(delta,c)) if isinstance(delta,(float,int)) else "–"
        rows.append("<tr>"+"".join("<td>"+esc(v)+"</td>" for v in [r.get("date",""),r.get("slot","").replace("-",":"),c,pricefmt(r.get("price",0),c),r.get("trend",""),zv("s1"),zv("r1"),zv("s1")+"–"+zv("pivot"),zv("pivot")+"–"+zv("r1"),zv("r1")+"–"+zv("r2"),zv("r1"),zv("s1"),zv("r2")+" / "+zv("s2"),delta_text,r.get("retrieved_at","")])+"</tr>")
    journal='<section class="section card"><h2>Journal · BTC/XRP · 10:00 und 16:00 Uhr</h2><p>Alle vorhandenen Snapshots. Quelle und Abrufzeit pro Zeile. Keine neuen Heatmaps.</p><div class="table-wrap journal-wrap"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ["Datum","Snapshot","Coin","Kurs","Trend 30m","S1","R1","Long","Neutral","Short","Breakout","Breakdown","Ziele R2/S2","Änderung","Abrufzeit"])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'
    Path("journal.html").write_text(page("Journal",journal,"Journal"))
    ap=Path("archiv.html")
    old=ap.read_text() if ap.exists() else page("Historie","","Historie")
    entry=f'<section class="section card"><h2>01.11.2026 · 16:00 Uhr</h2><a class="btn" href="archive/{DATE}/{SLOT}/index.html">16:00-Snapshot öffnen</a> · <a href="archive/{DATE}/10-00/index.html">10:00-Snapshot</a></section>'
    if f'archive/{DATE}/{SLOT}/index.html' not in old:
        old=old.replace('<main class="shell">','<main class="shell">'+entry,1)
        ap.write_text(old)
    snap=Path("archive")/DATE/SLOT
    snap.mkdir(parents=True,exist_ok=True)
    (snap/"index.html").write_text(f'<!doctype html><html lang="de"><meta charset="utf-8"><title>{DATE} 16:00</title><link rel="stylesheet" href="../../../style.css"><main class="shell"><p><a href="../../../index.html">Heute</a> · <a href="../../../archiv.html">Historie</a></p>'+intro+cards+''.join(f'<section><img style="width:100%" src="../../../reports/{c}_{SLOT}_Kaestchen_{DATE}.svg"></section>' for c in ["BTC","XRP"])+'</main></html>')
    # Historisches data/journal.json nur ergänzen, nie bestehende Einträge verändern.
    jp=Path("data/journal.json")
    if jp.exists():
        j=json.loads(jp.read_text())
        if isinstance(j,dict) and isinstance(j.get("records"),list):
            for coin,d in data.items():
                if not any(x.get("date")==DATE and x.get("coin")==coin and x.get("slot")==SLOT for x in j["records"]):
                    z=d["zones"]
                    j["records"].append({"date":DATE,"slot":SLOT,"coin":coin,"price":d["price"],"trend":d["timeframes"]["30m"]["trend"],"support":pricefmt(d["timeframes"]["30m"]["support"],coin),"resistance":pricefmt(d["timeframes"]["30m"]["resistance"],coin),"longZone":pricefmt(z["s1"],coin)+"–"+pricefmt(z["pivot"],coin),"neutralZone":pricefmt(z["pivot"],coin)+"–"+pricefmt(z["r1"],coin),"shortZone":pricefmt(z["r1"],coin)+"–"+pricefmt(z["r2"],coin),"breakout":z["r1"],"breakdown":z["s1"],"targets":"R2 "+pricefmt(z["r2"],coin)+" / S2 "+pricefmt(z["s2"],coin),"change":d["change"],"changePct":d["change_pct"],"retrieved_at":d["retrieved_at"],"source":d["source"]})
            jp.write_text(json.dumps(j,ensure_ascii=False,indent=2)+"\n")
    # PDF/XLSX sind optionale Downloads, kein Veröffentlichungs-Blocker.
    try:
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        pdf=f"downloads/BTC_XRP_Tagesuebersicht_{DATE}_{SLOT}.pdf"
        doc=SimpleDocTemplate(pdf)
        styles=getSampleStyleSheet()
        story=[Paragraph(f"BTC/XRP Marktbericht {DATE} 16:00 Uhr",styles["Title"]),Spacer(1,12)]
        for coin,d in data.items():
            z=d["zones"]
            story.append(Paragraph(f"{coin}/USDT {pricefmt(d['price'],coin)} | {pct(d['change_pct'])} seit 10 Uhr",styles["Heading2"]))
            for line in [f"Abruf {d['retrieved_at']} | Kraken Spot",f"S1 {pricefmt(z['s1'],coin)} / Pivot {pricefmt(z['pivot'],coin)} / R1 {pricefmt(z['r1'],coin)}",f"R2 {pricefmt(z['r2'],coin)} / S2 {pricefmt(z['s2'],coin)}",f"Breakout > R1, Breakdown < S1; 30m-Schluss und Retest"]:
                story.append(Paragraph(esc(line),styles["Normal"]))
            story.append(Spacer(1,12))
        doc.build(story)
    except Exception as exc: print("PDF optional failed:",repr(exc),flush=True)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill
        for coin,d in data.items():
            wb=Workbook(); ws=wb.active;ws.title="Analyse"
            ws.append(["Datum","Slot","Coin","Kurs USDT","10 Uhr","Differenz","Prozent","Abrufzeit","Quelle"])
            ws.append([DATE,"16:00",coin,d["price"],d["previous_price"],d["change"],d["change_pct"],d["retrieved_at"],d["source"]])
            ws.append([])
            ws.append(["Zeitebene","Struktur","Support","Widerstand","RSI14"])
            for name,t in d["timeframes"].items():ws.append([name,t["trend"],t["support"],t["resistance"],t["rsi"]])
            ws.append([])
            ws.append(["S2","S1","Pivot","R1","R2","Long Stop","Short Stop"])
            z=d["zones"];ws.append([z["s2"],z["s1"],z["pivot"],z["r1"],z["r2"],z["s2"],d["short_stop"]])
            for cell in ws[1]+ws[4]+ws[12]:cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="243746")
            for col in "ABCDEFGHI":ws.column_dimensions[col].width=23
            wb.save(f"downloads/{coin}_Tagesbericht_{DATE}_{SLOT}.xlsx")
    except Exception as exc:print("XLSX optional failed:",repr(exc),flush=True)
    print("PUBLISHED_CONTENT_READY",DATE,{k:(v["price"],v["retrieved_at"]) for k,v in data.items()},flush=True)
if __name__=="__main__":main()
