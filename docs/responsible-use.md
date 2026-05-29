# Responsible Use

ainews is an AI-powered news aggregation tool. Please use it responsibly.

## Source Rights and Attribution

- **Prefer RSS/API sources** with clear reuse rights over scraping web pages
- **Respect `robots.txt`** and publisher terms of service where applicable
- **Link and attribute original sources** — generated articles include source URLs
- **Configure source allowlists intentionally** in `sources.yaml`

## AI-Generated Content

- Generated summaries are **not original reporting** — they are AI-distilled versions of source material
- **Human editorial review is recommended** before publishing or distributing generated content
- Quality gates catch degenerate outputs, but they do not guarantee factual accuracy
- Consider adding a disclaimer to newsletters (e.g., "This newsletter is AI-generated")

## Publication and Distribution

- Use the `review` pipeline stage to inspect articles before publication
- The `done` status means the article is published — ensure you've reviewed it
- Newsletter delivery is final — test with a small subscriber list first
- Webhook events include source attribution for audit trails

## Privacy

- Subscriber emails are stored only for newsletter delivery
- Double opt-in verification is required for new subscribers
- One-click unsubscribe is included in every newsletter
- Search queries are logged for analytics but not sold or shared

## Legal Considerations

- You are responsible for compliance with applicable laws in your jurisdiction
- Copyright and fair use laws vary by country — consult legal counsel if unsure
- The maintainers of ainews are not responsible for how the software is used
