# PDF-Capability — Tool-Referenz

Du kannst mit einem Tool ansprechend gestaltete PDF-Berichte erzeugen:

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
  "cover_image_url": "https://example.com/hero.jpg",
  "author": "Optionaler Autor",
  "filename": "report.pdf"
}
```

Wichtig:

- `sections` immer als Array senden.
- Pro Abschnitt exakt die Keys `heading` und `content` verwenden.
- Keine alternativen Keys wie `title/body`, `name/text` oder lokalisierte Key-Namen verwenden.
- Gesamten Fliesstext in `sections[].content` schreiben. Kein eingebettetes JSON und keine Tool-Logs im Inhalt.
- Fuer zuverlaessige Ergebnisse `strict_mode: true` setzen und bei Validierungsfehlern
  nur die Tool-Argumente korrigiert erneut senden.
- `require_images: true` setzen, wenn visuelle Inhalte erwartet werden
  (z. B. bei Stadtportraets).

## Reichhaltige Inhaltsformatierung

Abschnittsinhalte unterstuetzen diese Formatierungen fuer visuell ansprechende Ausgaben:

- **Absaetze**: Klartext mit Leerzeilen zwischen Absaetzen.
- **Listen**: Pro Zeile ein Aufzaehlungspunkt mit `- Punkt` oder `* Punkt`. Nummerierte Listen mit `1. Punkt`.
- **Fett/Kursiv**: `**fetter Text**` und `*kursiver Text*` fuer Hervorhebungen bei Kennzahlen und Begriffen.
- **Zitat-Hervorhebungen**: Zeilen mit `> ` am Anfang werden als farbige Infoboxen dargestellt.
  Nutze diese fuer Kernfakten, bemerkenswerte Zahlen oder wichtige Erkenntnisse.
  Beispiel: `> Mit rund 48.000 Einwohnern ist Duelmen die groesste Stadt im Kreis Coesfeld.`
- **Markdown-Tabellen**: `| Spalte A | Spalte B |` plus Trennerzeile `|---|---|` und Datenzeilen.
- **Bilder**: Ueber `image_urls` Fotos einbinden. Das erste Bild wird als grosses Titelbild genutzt;
  weitere Bilder werden inline ueber die Abschnitte verteilt.
- **Titelbild**: Ueber `cover_image_url` ein bestimmtes Hero-Bild fuer Seite 1 festlegen.

## Template-Qualitaetsmodi

Geeignete Vorlagen:

- `generic`: keine festen Abschnittspruefungen. Tuerkises Farbschema.
- `city_profile`: Abschnitte zu Ueberblick, Lage/Geografie und Highlights/Sehenswuerdigkeiten. Warmes Bernstein-Farbschema.
- `research_summary`: Abschnitte zu Ziel/Scope, Ergebnissen und Quellen/Evidenz. Blaues akademisches Farbschema.
- `project_status`: Abschnitte zu Status/Fortschritt, Risiken/Issues und naechsten Schritten. Indigo-Farbschema.

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
- Pro Bericht 2-4 `> Zitat`-Hervorhebungen fuer Kernfakten nutzen — das schafft visuelle Abwechslung.
- `**Fett**` fuer wichtige Zahlen, Namen und Begriffe in Absaetzen verwenden.
- Bei Web-Recherche immer Quellen-URLs aufnehmen.
- Lieber wenige, passende Bilder statt vieler Bilder.
- Fakten nicht doppelt in Summary und Abschnittstext wiederholen.
- Wenn Bilddownloads fehlschlagen, ohne Bild fortfahren und kurz erwaehnen.
