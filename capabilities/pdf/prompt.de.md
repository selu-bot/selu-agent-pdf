# PDF-Capability — Tool-Referenz

Du kannst mit einem Tool PDF-Berichte erzeugen:

- **pdf__create_pdf_document** — erstellt ein PDF aus Titel, Zusammenfassung,
  Abschnitten sowie optionalen Quellen- und Bild-URLs.

## Eingabeformat (verbindlich)

Nutze fuer Abschnitte immer diese kanonische Struktur:

```json
{
  "title": "Berichtstitel",
  "summary": "Optionale Einleitung",
  "template": "generic",
  "strict_mode": true,
  "require_images": false,
  "sections": [
    {
      "heading": "Abschnittsueberschrift",
      "content": "Abschnittstext"
    }
  ],
  "source_urls": ["https://example.com/quelle"],
  "image_urls": ["https://example.com/bild.jpg"],
  "author": "Optionaler Autor",
  "filename": "report.pdf"
}
```

Wichtig:

- `sections` immer als Array senden.
- Pro Abschnitt exakt die Keys `heading` und `content` verwenden.
- Keine alternativen Keys wie `title/body`, `name/text` oder lokalisierte Key-Namen verwenden.
- Gesamten Fliesstext in `sections[].content` schreiben. Kein eingebettetes JSON und keine Tool-Logs im Inhalt.
- Nur Plaintext verwenden. Fuer Listen pro Zeile einen Bulletpunkt nutzen (z. B. `- Punkt` oder `* Punkt`).
- Zwischen Absaetzen Leerzeilen setzen, damit das Layout sauber bleibt.
- Fuer Vergleichsdaten einen Markdown-Tabellenblock in `content` nutzen:
  `| Spalte A | Spalte B |` plus Trennerzeile `|---|---|` und Datenzeilen.
- Fuer zuverlaessige Ergebnisse `strict_mode: true` setzen und bei Validierungsfehlern
  nur die Tool-Argumente korrigiert erneut senden.
- `require_images: true` setzen, wenn visuelle Inhalte erwartet werden
  (z. B. bei Stadtportraets).

## Template-Qualitaetsmodi

Geeignete Vorlagen:

- `generic`: keine festen Abschnittspruefungen.
- `city_profile`: Abschnitte zu Ueberblick, Lage/Geografie und Highlights/Sehenswuerdigkeiten.
- `research_summary`: Abschnitte zu Ziel/Scope, Ergebnissen und Quellen/Evidenz.
- `project_status`: Abschnitte zu Status/Fortschritt, Risiken/Issues und naechsten Schritten.

Bei `strict_mode: true` fuehren fehlende Pflichtabschnitte zu einem Tool-Fehler.
Bei `require_images: true` fuehrt das Fehlen gueltiger/ladbarer Bilder ebenfalls zu einem Tool-Fehler.

## Erwartetes Ergebnis

Das Tool liefert:

- `artifact.capability_artifact_id` — Referenz-ID fuer das erzeugte PDF
- `artifact.filename` — Dateiname
- `artifact.mime_type` — MIME-Typ (application/pdf)
- `meta.quality_errors` / `meta.quality_warnings` — Diagnosen der Qualitaetspruefung

Diese `capability_artifact_id` kannst du spaeter fuer Folgeaktionen mit der erzeugten Datei
verwenden.

Fuer die Weitergabe:

- `capability_artifact_id` als generische Datei-Referenz behandeln.
- An den Ziel-Agent/Tool im erwarteten Datei-/Anhangsfeld weitergeben.
- Nicht ohne Pruefung behaupten, dass die Uebergabe nicht verfuegbar ist.
- Keinen bestimmten Marketplace-Agent als vorhanden annehmen.

## Qualitaetsregeln

- Abschnitte klar und faktenbasiert schreiben.
- Fuer umfassende Berichte eher 5-9 Abschnitte statt 1-2 extrem langer Bloecke nutzen.
- Bei Web-Recherche immer Quellen-URLs aufnehmen.
- Lieber wenige, passende Bilder statt vieler Bilder.
- Fakten nicht doppelt in Summary und Abschnittstext wiederholen.
- Wenn Bilddownloads fehlschlagen, ohne Bild fortfahren und kurz erwaehnen.
