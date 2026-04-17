# PDF Capability — Tool Reference

You can generate beautifully designed report-style PDFs with one tool:

- **pdf__create_pdf_document** — creates a PDF from title, summary, sections,
  optional source links, and optional image URLs.

## Input contract (strict)

Use this canonical structure for sections:

```json
{
  "title": "Report title",
  "summary": "Optional intro paragraph",
  "template": "generic",
  "strict_mode": true,
  "require_images": false,
  "sections": [
    {
      "heading": "Section heading",
      "content": "Section body text"
    }
  ],
  "source_urls": ["https://example.com/source"],
  "image_urls": ["https://example.com/image.jpg"],
  "cover_image_url": "https://example.com/hero.jpg",
  "author": "Optional author",
  "filename": "report.pdf"
}
```

Important:

- Always send `sections` as an array.
- For every section, use keys `heading` and `content` exactly.
- Do not substitute alternate keys such as `title/body`, `name/text`, or localized key names.
- Put all prose into `sections[].content`. Do not embed JSON or tool traces inside content.
- Use `strict_mode: true` for reliable outputs and retry with corrected arguments if the tool rejects quality.
- Set `require_images: true` when visual coverage is expected (for example city profiles).

## Rich content formatting

Section content supports these formatting options for visually rich output:

- **Paragraphs**: Plain text separated by blank lines.
- **Lists**: One bullet per line using `- item` or `* item`. Numbered lists with `1. item`.
- **Bold/italic**: Use `**bold text**` and `*italic text*` for emphasis on key terms and figures.
- **Blockquote callouts**: Lines starting with `> ` become highlighted callout boxes.
  Use these for key facts, notable figures, or important takeaways.
  Example: `> With 48,000 residents, Duelmen is the largest city in the Kreis Coesfeld.`
- **Markdown tables**: `| Col A | Col B |` + separator row `|---|---|` + data rows.
- **Images**: Use `image_urls` to include photos. The first image becomes a cover hero;
  remaining images are distributed inline across sections.
- **Cover image**: Use `cover_image_url` for a specific hero image at the top of page 1.

## Template quality modes

Choose a template when appropriate:

- `generic`: no template heading checks. Teal accent theme.
- `city_profile`: include sections that cover overview, location/geography, and highlights/attractions. Warm amber theme.
- `research_summary`: include scope/objective, findings, and sources/evidence. Blue academic theme.
- `project_status`: include status/progress, risks/issues, and next steps/actions. Indigo professional theme.

When `strict_mode` is `true`, missing required template sections causes a tool error.
When `require_images` is `true`, the tool fails if no image URL is provided or no image can be downloaded.

## Expected output

The tool returns:

- `artifact.capability_artifact_id` — reference ID for the generated PDF
- `artifact.filename` — output filename
- `artifact.mime_type` — MIME type (application/pdf)
- `meta.quality_errors` / `meta.quality_warnings` — quality gate diagnostics

Use this `capability_artifact_id` when asking another agent/tool to perform follow-up
actions with the generated file.

For downstream handoff:

- Treat `capability_artifact_id` as a generic file reference.
- Pass it to the receiving tool/agent using its expected attachment/file field.
- Do not say handoff is unavailable without checking available tools first.
- Do not assume a specific marketplace agent name is installed.

## Content quality rules

- Keep sections factual and well-structured.
- Prefer 5-9 sections for comprehensive reports instead of 1-2 very long sections.
- Use `> blockquote` callouts to highlight 2-4 key facts per report — this creates visual variety.
- Use `**bold**` for important numbers, names, and terms within paragraphs.
- Include source URLs when the content comes from web research.
- Prefer a small number of relevant images over many images.
- Avoid repeating the same facts in summary and sections.
- If some images fail to download, continue and mention that briefly.
