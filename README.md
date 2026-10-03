# CRYPTO Dashboard

GitHub Pages: https://z28dgd8phw-cyber.github.io/crypto-dashboard/

Das Journal zeigt BTC/XRP mit Filtern und einer Kartenansicht auf schmalen Bildschirmen. PDF und XLSX enthalten den neuesten gespeicherten Tagesstand. Charts bleiben in ihrer bisherigen Qualität erhalten.

Das Hauptdashboard enthält zusätzlich die originale BTC-Excel-Vorlage als echte Webtabellen mit den Arbeitsblättern Dashboard, Tagesanalyse, Trading Journal und Einstellungen. Farben und Werte stammen aus der bereitgestellten Datei; Beispielwerte werden getrennt von den Tagesdaten gekennzeichnet. Die Originaldatei steht unverändert als Download bereit. `scripts/build_reference.py <xlsx-Datei>` erzeugt die Webansicht (read-only mit openpyxl) und integriert sie auf der Haupt- und Journalseite. Das Journal-Update erhält diese Ansicht.

## Tagesdaten ergänzen

`data/journal.json` enthält einen Datensatz je Datum und Coin. Neue Tage anhängen, alte Tage erhalten. Kurse und Prozentwerte sind Zahlen. Die Veränderung wird nur gegen denselben Coin am vorherigen Kalendertag berechnet. Fehlt dieser, erscheint „Kein Vortag“.

Die Werte vom 03.10.2026 stammen aus den bestehenden HTML-Tagesseiten und Chartgrafiken. Trend, Support, Widerstand und Cluster stammen aus den Heatmap-Grafiken von 11:00 Uhr. Die Heatmap- und Chartansichten verwenden teilweise verschiedene Kursmarken. BTC-Cluster liegen laut Beschriftung außerhalb des genannten ±5%-Bereichs; diese Angaben wurden unverändert übernommen. Es gibt keinen automatischen Marktdatenabruf.

`scripts/build_journal.py` (Python mit ReportLab) erzeugt die Journal-Seite und datierte PDF. `scripts/build_excel.mjs` erzeugt die XLSX mit dem Codex Artifact-Tool. Beide lesen dieselbe JSON-Datei. Generierte Downloads mit dem jeweiligen Datum einchecken und die Downloadlinks auf der Startseite aktualisieren.

Vor jedem weiteren Tagesupdate die bisherigen HTML-Seiten und vier SVG-Grafiken unter `archive/YYYY-MM-DD/` sichern, sofern noch nicht vorhanden. Relative Links zu globalem CSS und Downloads auf `../../` anpassen. Bereits archivierte Tagesstände nicht überschreiben. Die Historienseite auf den gesicherten Tagesstand verlinken.

Ein Push auf `main` veröffentlicht den eingecheckten Stand durch den vorhandenen GitHub-Pages-Workflow.
