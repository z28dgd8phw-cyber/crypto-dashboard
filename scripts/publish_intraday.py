#!/usr/bin/env python3
"""Source-backed intraday BTC/XRP publisher. Runs in GitHub Actions, not ChatGPT runtime."""
import datetime as dt
import html
import json
import math
import os
import pathlib
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Europe/Berlin")
UTC=dt.timezone.utc
NOW=dt.datetime.now(UTC)
LOCAL=NOW.astimezone(TZ)
DATE=LOCAL.date().isoformat()
DISPLAY=LOCAL.strftime("%d.%m.%Y")
SLOT="16-00" if LOCAL.hour>=16 else "10-00" if LOCAL.hour>=10 else None
if not SLOT:
    print("Outside local 10:00/16:00 reporting window; deploy existing site.")
    sys.exit(0)
PATH=ROOT/"data"/f"binance-report-{DATE}-{SLOT}.json"
if PATH.exists() and os.getenv("FORCE_REFRESH")!="1":
    print(f"Verified snapshot already exists: {PATH.name}; preserve immutable capture.")
    sys.exit(0)

def get_klines(symbol,interval,limit=300):
    query=urllib.parse.urlencode({"symbol":symbol,"interval":interval,"limit":limit})
    errors=[]
    for base in ("https://data-api.binance.vision/api/v3/klines",
                 "https://api.binance.com/api/v3/klines"):
        try:
            req=urllib.request.Request(base+"?"+query,headers={"User-Agent":"CryptoDashboard/1.0 (GitHub Actions)","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=22) as response:
                raw=json.load(response)
            if not isinstance(raw,list) or len(raw)<35 or not isinstance(raw[0],list):
                raise ValueError("Malformed/insufficient kline response")
            if interval=="30m" and (NOW.timestamp()*1000-int(raw[-1][0]))>65*60*1000:
                raise ValueError("Stale 30m candles")
            return raw,base+"?"+query
        except Exception as e:
            errors.append(f"{base}: {e}")
    raise RuntimeError("Could not fetch live OHLC: "+"; ".join(errors))

def closed_bars(bars):
    return [b for b in bars if int(b[6])<int(NOW.timestamp()*1000)-1000]

def ema(values,n):
    if len(values)<n: return []
    a=2/(n+1)
    out=[sum(values[:n])/n]
    for x in values[n:]:
        out.append(a*x+(1-a)*out[-1])
    return out

def rsi(values,n=14):
    if len(values)<=n: return None
    gains=[max(values[i]-values[i-1],0) for i in range(1,len(values))]
    losses=[max(values[i-1]-values[i],0) for i in range(1,len(values))]
    ag=sum(gains[:n])/n;al=sum(losses[:n])/n
    for g,l in zip(gains[n:],losses[n:]):
        ag=(ag*(n-1)+g)/n;al=(al*(n-1)+l)/n
    return 100 if al==0 else 100-100/(1+ag/al)

def macd(values):
    if len(values)<36:return None,None,None
    e12=ema(values,12);e26=ema(values,26)
    diffs=[a-b for a,b in zip(e12[14:],e26)]
    signals=ema(diffs,9)
    if not signals:return None,None,None
    return diffs[-1],signals[-1],diffs[-1]-signals[-1]

def structure(bars):
    if len(bars)<16:return "Nicht genügend Kerzen"
    recent=bars[-16:]
    prev=recent[:8];last=recent[8:]
    h0=max(float(b[2]) for b in prev);h1=max(float(b[2]) for b in last)
    l0=min(float(b[3]) for b in prev);l1=min(float(b[3]) for b in last)
    if h1>h0 and l1>l0:return "Höheres Hoch / höheres Tief"
    if h1<h0 and l1<l0:return "Tieferes Hoch / tieferes Tief"
    return "Seitwärts / gemischte Struktur"

def fmt(value,coin):
    return (f"{value:,.2f}" if coin=="BTC" else f"{value:.5f}").replace(",","_").replace(".",",").replace("_",".")

def point(value,coin):
    return f"{value:.2f}" if coin=="BTC" else f"{value:.5f}"

def fmt_stamp(value):
    return dt.datetime.fromtimestamp(value/1000,UTC).astimezone(TZ).strftime("%d.%m. %H:%M")

def atr(bars,n=14):
    if len(bars)<n+1:return 0
    ranges=[]
    for prev,cur in zip(bars[-n-1:-1],bars[-n:]):
        h=float(cur[2]);l=float(cur[3]);pc=float(prev[4])
        ranges.append(max(h-l,abs(h-pc),abs(l-pc)))
    return statistics.mean(ranges)

def market(symbol,coin):
    candles={};sources={}
    for interval in ("15m","30m","1h","4h","1d"):
        candles[interval],sources[interval]=get_klines(symbol,interval,300 if interval!="1d" else 90)
    daily=candles["1d"]
    yesterday=(NOW.date()-dt.timedelta(days=1)).isoformat()
    prev=next((b for b in daily if dt.datetime.fromtimestamp(int(b[0])/1000,UTC).date().isoformat()==yesterday),None)
    if not prev or int(prev[6])>=int(NOW.timestamp()*1000):
        raise RuntimeError(f"Closed UTC daily candle for {yesterday} unavailable")
    high,low,close=(float(prev[i]) for i in (2,3,4))
    p=(high+low+close)/3
    s1=2*p-high;r1=2*p-low
    s2=p-(high-low);r2=p+(high-low)
    if not(s2<s1<p<r1<r2):raise RuntimeError("Invalid pivot order")
    current=candles["30m"][-1]
    price=float(current[4])
    tf={}
    for interval,bars in candles.items():
        finished=closed_bars(bars)
        if len(finished)<35:raise RuntimeError(f"Not enough completed {interval} candles")
        closes=[float(b[4]) for b in finished]
        m,signal,hist=macd(closes)
        last=finished[-1]
        tf[interval]={
            "close":float(last[4]),"rsi":rsi(closes),
            "macd":m,"signal":signal,"hist":hist,
            "support":min(float(b[3]) for b in finished[-20:]),
            "resistance":max(float(b[2]) for b in finished[-20:]),
            "structure":structure(finished),
            "last_closed":dt.datetime.fromtimestamp(int(last[6])/1000,UTC).astimezone(TZ).isoformat()
        }
    a=atr(closed_bars(candles["30m"]))
    zones={"s2":s2,"s1":s1,"pivot":p,"r1":r1,"r2":r2,
           "long":[s1,p],"neutral":[p,r1],"short":[r1,r2],
           "long_stop":min(s2,s1-a),"short_stop":r2+a,
           "long_targets":[r1,r2],"short_targets":[p,s1]}
    if price<s1:location="Unter S1 – Long erst nach Rückeroberung"
    elif price<p:location="Long-Zone"
    elif price<r1:location="Neutral-Zone"
    elif price<r2:location="Short-Zone"
    else:location="Über R2 – Breakout nur nach Retest"
    return {
        "coin":coin,"symbol":symbol,"price":price,
        "retrieved_at":dt.datetime.now(UTC).astimezone(TZ).isoformat(),
        "source":sources["30m"],"sources":sources,
        "previous_utc_date":yesterday,
        "previous_utc_candle":{"high":high,"low":low,"close":close},
        "timeframes":tf,"zones":zones,"atr30":a,"location":location,
        "trend_summary":" | ".join(f"{k}: {v['structure']}" for k,v in tf.items()),
        "candles":candles["30m"][-100:],
        "scenario_note":"Bedingte Pivot-Szenarien, nicht automatisch bestätigte Einstiege. Long: Rücklauf S1–Pivot und 30m-Halten/Rückeroberung; Short: Ablehnung R1–R2. Breakout über R1 / Breakdown unter S1 jeweils erst nach 30m-Schluss und Retest. Stops als technische Invalidierung, nicht als Garantie."
    }

def svg_chart(row):
    coin=row["coin"];bars=row["candles"][-72:];z=row["zones"]
    lo=min([float(b[3]) for b in bars]+[z["s2"]])
    hi=max([float(b[2]) for b in bars]+[z["r2"]])
    pad=max((hi-lo)*.09, row["atr30"]*.7)
    lo-=pad;hi+=pad
    def y(v):return 695-(v-lo)/(hi-lo)*540
    def esc(s):return html.escape(str(s))
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 850" role="img" aria-label="{coin} echte 30-Minuten-Kerzen mit Pivot-Zielzonen">',
         '<rect width="1600" height="850" fill="#06111c"/>',
         '<g font-family="Arial,Helvetica,sans-serif" fill="#e6f0fa">',
         f'<text x="70" y="47" font-size="29" font-weight="bold">{coin}/USDT · Binance Spot · 30-Minuten-Chart</text>',
         f'<text x="70" y="78" font-size="19">{DISPLAY} · {LOCAL.strftime("%H:%M")} Uhr Europe/Berlin · laufende Kerze offen</text>']
    for i in range(6):
        v=lo+(hi-lo)*i/5;yy=y(v)
        out.append(f'<path d="M70 {yy:.1f} H1420" stroke="#20384b" stroke-width="1"/><text x="1432" y="{yy+5:.1f}" font-size="18">{fmt(v,coin)}</text>')
    zone_specs=[("Short-Zone",z["r1"],z["r2"],"#e85d6a"),
                ("Neutral",z["pivot"],z["r1"],"#7596ba"),
                ("Long-Zone",z["s1"],z["pivot"],"#29c978")]
    for name,bottom,top,color in zone_specs:
        ytop=y(top);height=y(bottom)-ytop
        out.append(f'<rect x="965" y="{ytop:.1f}" width="450" height="{height:.1f}" rx="10" fill="{color}" fill-opacity=".20" stroke="{color}" stroke-opacity=".75" stroke-width="2"/>')
        center=(y(top)+y(bottom))/2
        out.append(f'<rect x="1000" y="{center-16:.1f}" width="390" height="32" rx="6" fill="#071625" fill-opacity=".85"/>')
        out.append(f'<text x="1195" y="{center+7:.1f}" text-anchor="middle" font-size="19" font-weight="bold" fill="{color}">{name}: {fmt(bottom,coin)} – {fmt(top,coin)}</text>')
    for label,value,color in [("S2 / TP2 unten",z["s2"],"#ff9b9b"),("S1 / Breakdown",z["s1"],"#ff8d9b"),("Pivot",z["pivot"],"#f5d977"),("R1 / Breakout",z["r1"],"#83e6b4"),("R2 / TP2 oben",z["r2"],"#83e6b4")]:
        yy=y(value)
        out.append(f'<path d="M70 {yy:.1f} H1415" stroke="{color}" stroke-dasharray="8 6" stroke-width="1.5"/>')
        out.append(f'<text x="76" y="{yy-9:.1f}" fill="{color}" font-size="17">{label}: {fmt(value,coin)}</text>')
    for i,b in enumerate(bars):
        x=92+i*11.8;o,h,l,c=(float(b[k]) for k in (1,2,3,4))
        color="#66d9aa" if c>=o else "#ef788b"
        out.append(f'<path d="M{x:.1f} {y(h):.1f} V{y(l):.1f}" stroke="{color}" stroke-width="2"/>')
        out.append(f'<rect x="{x-3.7:.1f}" y="{min(y(o),y(c)):.1f}" width="7.4" height="{max(2,abs(y(o)-y(c))):.1f}" fill="{color}"/>')
        if i%16==0:
            out.append(f'<text x="{x:.1f}" y="736" text-anchor="middle" font-size="16">{fmt_stamp(int(b[0]))}</text>')
    yy=y(row["price"])
    out.append(f'<path d="M70 {yy:.1f} H930" stroke="#ffffff" stroke-width="2" stroke-dasharray="3 6"/>')
    out.append(f'<rect x="1080" y="94" width="290" height="43" rx="10" fill="#15364b"/><text x="1225" y="123" text-anchor="middle" font-size="22" font-weight="bold">Zielzonen {DISPLAY}</text>')
    out.append(f'<text x="70" y="782" font-size="20">Kurs {fmt(row["price"],coin)} · ATR(14) 30m {fmt(row["atr30"],coin)} · Stop Long {fmt(z["long_stop"],coin)} · Stop Short {fmt(z["short_stop"],coin)}</text>')
    out.append('<text x="70" y="817" font-size="17">Bedingte Pivot-Szenarien · Bestätigung/Retest abwarten · keine Liquidations-Heatmap · keine Anlageberatung</text></g></svg>')
    return "".join(out)

def save_text(path,content):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding="utf-8")

def json_text(obj):
    return json.dumps(obj,ensure_ascii=False,indent=2)+"\n"

def card(row,prior=None):
    c=row["coin"];z=row["zones"];t=row["timeframes"]["30m"]
    comp=""
    if prior:
        delta=row["price"]-prior["price"];pct=delta/prior["price"]*100
        comp=f'<p><strong>Gegen 10 Uhr:</strong> {fmt(delta,c)} USDT ({pct:+.2f} %) · 30m-Struktur: {html.escape(prior["timeframes"]["30m"]["structure"])} → {html.escape(t["structure"])}</p>'
    elif SLOT=="16-00":
        comp='<p>10-Uhr-Vergleich heute nicht verfügbar; keine historischen Kurse erfunden.</p>'
    details="".join(
        f'<tr><th>{name}</th><td>{fmt(row["timeframes"][name]["close"],c)}</td><td>{html.escape(row["timeframes"][name]["structure"])}</td><td>{fmt(row["timeframes"][name]["support"],c)} / {fmt(row["timeframes"][name]["resistance"],c)}</td><td>{row["timeframes"][name]["rsi"]:.1f}</td></tr>'
        for name in ("15m","30m","1h","4h","1d")
    )
    return f'''<article class="card"><h3>{c}/USDT · {fmt(row["price"],c)}</h3>
<p class="lead">{html.escape(row["location"])} · {html.escape(t["structure"])}</p>{comp}
<p><strong>Long:</strong> {fmt(z["s1"],c)}–{fmt(z["pivot"],c)} · <strong>Neutral:</strong> {fmt(z["pivot"],c)}–{fmt(z["r1"],c)} · <strong>Short:</strong> {fmt(z["r1"],c)}–{fmt(z["r2"],c)}</p>
<p>Breakout &gt; {fmt(z["r1"],c)} · Breakdown &lt; {fmt(z["s1"],c)}<br>Long-Ziele TP1 {fmt(z["r1"],c)} / TP2 {fmt(z["r2"],c)} · Short-Ziele TP1 {fmt(z["pivot"],c)} / TP2 {fmt(z["s1"],c)}</p>
<p>Invalidierung Long &lt; {fmt(z["long_stop"],c)} · Short &gt; {fmt(z["short_stop"],c)} · ATR(14) {fmt(row["atr30"],c)}</p>
<details><summary>Zeitebenen 15m / 30m / 1h / 4h / Daily</summary><div class="table-wrap"><table><thead><tr><th>Zeitraum</th><th>Schluss</th><th>Struktur</th><th>Support / Widerstand</th><th>RSI14</th></tr></thead><tbody>{details}</tbody></table></div></details>
<p class="muted">{html.escape(row["scenario_note"])}</p></article>'''

def chart_block(row):
    c=row["coin"];p=f"reports/{c}_{SLOT}_Kaestchen_{DATE}.svg"
    return f'<section class="section"><div class="section-head"><div><h2>{c} · 30-Minuten-Zielzonen</h2><p>Echte Binance-Spotkerzen · Pivot-Szenarien des abgeschlossenen UTC-Vortags</p></div><a class="btn" href="{p}" target="_blank" rel="noopener">Vollbild / Zoom</a></div><div class="chart-card"><img src="{p}" alt="{c} 30-Minuten-Chart mit Long-, Neutral- und Short-Kästchen" style="width:100%;height:auto"></div></section>'

def table_rows(records):
    rows=[]
    for r in sorted(records,key=lambda x:(x["date"],x["slot"],x["coin"]),reverse=True):
        c=r["coin"];z=r["zones"]
        rows.append(f'<tr><td>{r["date"]}</td><td>{r["slot"].replace("-00",":00")}</td><td>{c}</td><td>{fmt(r["price"],c)}</td><td>{html.escape(r["trend"])}</td><td>{fmt(z["s1"],c)}</td><td>{fmt(z["r1"],c)}</td><td>{fmt(z["s1"],c)}–{fmt(z["pivot"],c)}</td><td>{fmt(z["pivot"],c)}–{fmt(z["r1"],c)}</td><td>{fmt(z["r1"],c)}–{fmt(z["r2"],c)}</td><td>{fmt(z["r1"],c)}</td><td>{fmt(z["s1"],c)}</td><td>{fmt(z["r2"],c)} / {fmt(z["s2"],c)}</td><td>{html.escape(r["retrieved_at"])}</td></tr>')
    return "".join(rows)

def journal_block(records):
    headers=("Datum","Zeit","Coin","Kurs","Trend 30m","Support S1","Widerstand R1","Long","Neutral","Short","Breakout","Breakdown","Ziele R2/S2","Abrufzeit")
    return '<section class="section card"><h2>Intraday-Journal · 10 und 16 Uhr</h2><p>Alle verfügbaren Snapshots bleiben erhalten. Pivot-Marken sind bedingte Szenarien; keine Heatmap.</p><div class="table-wrap journal-wrap"><table class="journal-table"><thead><tr>'+''.join(f'<th>{x}</th>' for x in headers)+'</tr></thead><tbody>'+table_rows(records)+'</tbody></table></div></section>'

def exports(rows,records):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    (ROOT/"downloads").mkdir(exist_ok=True)
    for row in rows:
        c=row["coin"];z=row["zones"]
        wb=Workbook();ws=wb.active;ws.title=c+" Tagesstand"
        ws.append([f"{c}/USDT · {DISPLAY} · {SLOT.replace('-00',':00')} Uhr (tatsächlicher Abruf {row['retrieved_at']})"])
        ws.append(["Quelle",row["source"]])
        ws.append(["Pivot-Basis UTC",row["previous_utc_date"]])
        ws.append(["Kurs",row["price"]])
        ws.append(["Long S1–Pivot",z["s1"],z["pivot"]])
        ws.append(["Neutral Pivot–R1",z["pivot"],z["r1"]])
        ws.append(["Short R1–R2",z["r1"],z["r2"]])
        ws.append(["Breakout / Breakdown",z["r1"],z["s1"]])
        ws.append(["TP Long 1/2",*z["long_targets"]])
        ws.append(["TP Short 1/2",*z["short_targets"]])
        ws.append(["Stop Long/Short",z["long_stop"],z["short_stop"]])
        ws.append([])
        ws.append(["Zeitraum","Schluss","Trend","Support","Widerstand","RSI14","MACD","Signal","Histogramm","Letzter Abschluss"])
        for tf in ("15m","30m","1h","4h","1d"):
            x=row["timeframes"][tf]
            ws.append([tf,x["close"],x["structure"],x["support"],x["resistance"],x["rsi"],x["macd"],x["signal"],x["hist"],x["last_closed"]])
        ws.append([]);ws.append(["Szenario",row["scenario_note"]])
        ws.freeze_panes="B14";ws.column_dimensions["A"].width=26
        for col in "BCDEFGHIJ":ws.column_dimensions[col].width=21
        for line in (1,13):
            for cell in ws[line]:
                cell.fill=PatternFill("solid",fgColor="173C56");cell.font=Font(bold=True,color="FFFFFF")
        for cells in ws:
            for cell in cells:cell.alignment=Alignment(wrap_text=True,vertical="top")
        ws.row_dimensions[1].height=32;ws.row_dimensions[19].height=50
        hist=wb.create_sheet("Intraday-Historie")
        hist.append(["Datum","Slot","Coin","Kurs","Trend","S1","Pivot","R1","R2","Abruf"])
        for item in sorted([r for r in records if r["coin"]==c],key=lambda r:(r["date"],r["slot"])):
            q=item["zones"]
            hist.append([item["date"],item["slot"],c,item["price"],item["trend"],q["s1"],q["pivot"],q["r1"],q["r2"],item["retrieved_at"]])
        hist.freeze_panes="A2"
        for col in "ABCDEFGHIJ":hist.column_dimensions[col].width=20
        wb.save(ROOT/"downloads"/f"{c}_Tagesbericht_{DATE}_{SLOT}.xlsx")
    pdf=ROOT/"downloads"/f"BTC_XRP_Tagesuebersicht_{DATE}_{SLOT}.pdf"
    styles=getSampleStyleSheet();elements=[Paragraph("BTC / XRP – Intraday-Marktbericht",styles["Title"]),Paragraph(f"{DISPLAY} · {SLOT.replace('-00',':00')} Uhr · tatsächlicher Datenabruf im Bericht",styles["Normal"]),Spacer(1,14)]
    for i,row in enumerate(rows):
        if i:elements.append(PageBreak())
        c=row["coin"];z=row["zones"]
        elements.extend([Paragraph(f"{c}/USDT · {fmt(row['price'],c)}",styles["Heading2"]),Paragraph(f"Abruf: {html.escape(row['retrieved_at'])} · Binance Spot",styles["Normal"]),Spacer(1,8)])
        fields=[("Trend 30m",row["timeframes"]["30m"]["structure"]),
                ("Long S1–Pivot",fmt(z["s1"],c)+" – "+fmt(z["pivot"],c)),
                ("Neutral Pivot–R1",fmt(z["pivot"],c)+" – "+fmt(z["r1"],c)),
                ("Short R1–R2",fmt(z["r1"],c)+" – "+fmt(z["r2"],c)),
                ("Breakout / Breakdown",fmt(z["r1"],c)+" / "+fmt(z["s1"],c)),
                ("Long TP1 / TP2",fmt(z["r1"],c)+" / "+fmt(z["r2"],c)),
                ("Short TP1 / TP2",fmt(z["pivot"],c)+" / "+fmt(z["s1"],c)),
                ("Invalidierung Long / Short",fmt(z["long_stop"],c)+" / "+fmt(z["short_stop"],c)),
                ("UTC-Vortag",row["previous_utc_date"])]
        t=Table([[Paragraph(html.escape(k),styles["BodyText"]),Paragraph(html.escape(v),styles["BodyText"])] for k,v in fields],colWidths=[170,330])
        t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.whitesmoke,colors.white]),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
        elements.extend([t,Spacer(1,10),Paragraph("Bedingte technische Szenarien, keine Kauf- oder Verkaufsempfehlung. Bestätigung und Retest abwarten.",styles["BodyText"]),Spacer(1,10),Paragraph("Quelle: "+html.escape(row["source"]),styles["BodyText"])])
    SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=42).build(elements)

def main():
    print(f"Generating {DATE} {SLOT} at {LOCAL.isoformat()}",flush=True)
    rows=[market("BTCUSDT","BTC"),market("XRPUSDT","XRP")]
    # Do not write any dashboard files until both coins are fully verified.
    data={r["coin"]:r for r in rows}
    save_text(f"data/binance-report-{DATE}-{SLOT}.json",json_text(data))
    old_path=ROOT/"data/intraday-journal.json"
    history=json.loads(old_path.read_text()) if old_path.exists() else {"records":[]}
    for r in rows:
        record={"date":DATE,"slot":SLOT,"coin":r["coin"],"price":r["price"],
                "trend":r["timeframes"]["30m"]["structure"],"zones":r["zones"],
                "retrieved_at":r["retrieved_at"],"source":r["source"]}
        history["records"]=[x for x in history["records"] if (x["date"],x["slot"],x["coin"])!=(DATE,SLOT,r["coin"])]
        history["records"].append(record)
        svg=svg_chart(r)
        save_text(f"reports/{r['coin']}_{SLOT}_Kaestchen_{DATE}.svg",svg)
        save_text(f"{r['coin'].lower()}-current-{DATE}.svg",svg)
    save_text("data/intraday-journal.json",json_text(history))
    # Preserve older journal entries. The dated daily row shows latest intraday observation;
    # the immutable 10/16-hour records are kept separately above.
    jp=ROOT/"data/journal.json"
    journal=json.loads(jp.read_text())
    for r in rows:
        c=r["coin"];z=r["zones"]
        rec={"date":DATE,"coin":c,"price":r["price"],
             "trend":r["timeframes"]["30m"]["structure"],
             "support":"S1 "+fmt(z["s1"],c)+" / S2 "+fmt(z["s2"],c),
             "resistance":"R1 "+fmt(z["r1"],c)+" / R2 "+fmt(z["r2"],c),
             "longZone":fmt(z["s1"],c)+"–"+fmt(z["pivot"],c),
             "shortZone":fmt(z["r1"],c)+"–"+fmt(z["r2"],c),
             "neutralZone":fmt(z["pivot"],c)+"–"+fmt(z["r1"],c),
             "breakout":z["r1"],"breakdown":z["s1"],
             "targets":"Long R1/R2 "+fmt(z["r1"],c)+" / "+fmt(z["r2"],c)+"; Short Pivot/S1 "+fmt(z["pivot"],c)+" / "+fmt(z["s1"],c),
             "clusters":"Keine Heatmap","dominance":None,
             "previousClose":r["previous_utc_candle"]["close"],
             "source":r["source"],"capturedAt":r["retrieved_at"],"snapshot":SLOT}
        journal["records"]=[x for x in journal["records"] if (x["date"],x["coin"])!=(DATE,c)]
        journal["records"].append(rec)
    journal["dailyStatus"]={"capturedAt":LOCAL.isoformat(),"note":f"Binance Spot · {DISPLAY} {LOCAL.strftime('%H:%M')} Uhr Europe/Berlin; echte Kerzen und Pivot-Szenarien des abgeschlossenen UTC-Vortags. Keine Heatmap.","sources":[r["source"] for r in rows]}
    save_text("data/journal.json",json_text(journal))
    try:
        exports(rows,history["records"])
        download_html=f'<p><a class="btn" href="downloads/BTC_XRP_Tagesuebersicht_{DATE}_{SLOT}.pdf">PDF-Tagesübersicht</a> <a class="btn secondary" href="downloads/BTC_Tagesbericht_{DATE}_{SLOT}.xlsx">BTC Excel</a> <a class="btn secondary" href="downloads/XRP_Tagesbericht_{DATE}_{SLOT}.xlsx">XRP Excel</a></p>'
    except Exception as e:
        print("PDF/XLSX optional export failed: "+str(e),file=sys.stderr)
        download_html='<p class="muted">PDF/Excel derzeit nicht verfügbar; aktuelle HTML-/SVG-Analyse und Journal sind veröffentlicht.</p>'
    prev={}
    ten=ROOT/"data"/f"binance-report-{DATE}-10-00.json"
    if SLOT=="16-00" and ten.exists():
        prev=json.loads(ten.read_text())
    heading=f"{DISPLAY} · {SLOT.replace('-00',':00')} Uhr"
    if SLOT=="10-00" and LOCAL.minute>=10:
        heading+=" (Nachholung)"
    captured=" · ".join(f"{r['coin']}: {dt.datetime.fromisoformat(r['retrieved_at']).strftime('%H:%M:%S')} Uhr" for r in rows)
    top=f'<section class="section card" id="live-snapshot"><h2>Aktuelle BTC-/XRP-Analyse · {heading}</h2><p><strong>Tatsächlicher Abruf:</strong> {captured} (Europe/Berlin). <strong>Quelle:</strong> Binance Spot, echte Kerzen. <strong>Pivot-Basis:</strong> abgeschlossener UTC-Vortag {rows[0]["previous_utc_date"]}. Kein rückdatierter 10:00-Uhr-Kurs.</p><div class="hero">'+''.join(card(r,prev.get(r["coin"])) for r in rows)+'</div>'+download_html+'<p class="muted">30-Minuten-Chart: grüne Long-, blaue Neutral- und rote Short-Zone. 15m/1h/4h/Daily in den Detailtabellen. Alle Szenarien bedingt; keine Anlageberatung.</p></section>'
    charts="".join(chart_block(r) for r in rows)
    intraday=journal_block(history["records"])
    snapshot_html=top+charts+intraday
    for name in ("index.html","btc.html","xrp.html","journal.html","archiv.html"):
        p=ROOT/name;s=p.read_text()
        s=re.sub(r'<section[^>]*id="live-snapshot"[^>]*>.*?</section>','',s,count=1,flags=re.S)
        s=re.sub(r'<section[^>]*id="verified-daily"[^>]*>.*?</section>','',s,count=1,flags=re.S)
        s=re.sub(r'<section class="section"><div class="section-head"><div><h2>(?:BTC|XRP) · aktuelle Zielzonen · 30-Minuten-Chart</h2>.*?</section>','',s,flags=re.S)
        # Remove any previous generated chart section before adding current version.
        s=re.sub(r'<section class="section"><div class="section-head"><div><h2>(?:BTC|XRP) · 30-Minuten-Zielzonen</h2>.*?</section>','',s,flags=re.S)
        s=re.sub(r'<section class="section card"><h2>Intraday-Journal · 10 und 16 Uhr</h2>.*?</section>','',s,flags=re.S)
        s=re.sub(r'<span class="tag">Stand: .*?</span>',f'<span class="tag">Stand: {DISPLAY} · {LOCAL.strftime("%H:%M")} Uhr</span>',s,count=1,flags=re.S)
        if name=="index.html":
            s=re.sub(r'<section class="hero">.*?</section>','',s,count=1,flags=re.S)
            s=s.replace('<main class="shell">','<main class="shell">'+top+charts+intraday,1)
        elif name in ("btc.html","xrp.html"):
            c=name[:3].upper();r=next(r for r in rows if r["coin"]==c)
            single=top.replace('<div class="hero">'+''.join(card(x,prev.get(x["coin"])) for x in rows)+'</div>','<div class="hero">'+card(r,prev.get(c))+'</div>')
            s=s.replace('<main class="shell">','<main class="shell">'+single+chart_block(r),1)
        elif name=="journal.html":
            s=s.replace('<main class="shell">','<main class="shell">'+intraday,1)
        else:
            s=s.replace('<main class="shell">','<main class="shell"><section class="section card"><h2>Aktuelle Snapshots '+DISPLAY+'</h2><a class="btn" href="archive/'+DATE+'/'+SLOT+'/index.html">'+SLOT.replace("-00",":00")+' Uhr · archivierten Stand öffnen</a></section>',1)
        p.write_text(s)
    # Static dated snapshot; links resolve from archive/YYYY-MM-DD/HH-MM/.
    shell='<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BTC/XRP '+heading+'</title><link rel="stylesheet" href="../../../style.css"></head><body><div class="top"><div class="top-inner"><div class="brand"><h1>CRYPTO Dashboard · Archiv</h1></div><div class="nav"><a href="../../../index.html">Heute</a><a href="../../../journal.html">Journal</a><a href="../../../archiv.html">Historie</a></div></div></div><main class="shell">'+snapshot_html.replace('href="reports/','href="../../../reports/').replace('src="reports/','src="../../../reports/').replace('href="downloads/','href="../../../downloads/')+'</main></body></html>'
    save_text(f"archive/{DATE}/{SLOT}/index.html",shell)
    print(json.dumps({"date":DATE,"slot":SLOT,"coins":[{"coin":r["coin"],"price":r["price"],"retrieved_at":r["retrieved_at"],"pivot":r["zones"]["pivot"]} for r in rows]},ensure_ascii=False))

if __name__=="__main__":
    main()
