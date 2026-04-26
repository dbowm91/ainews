# Badge System

The ainews badge system provides visual categorization and status indicators for articles and content.

## Category Badges

Category badges identify the topic area of an article. They use semantic colors to aid quick scanning.

```html
<span class="badge cat-ai">AI</span>
<span class="badge cat-privacy">Privacy</span>
<span class="badge cat-security">Security</span>
<span class="badge cat-programming">Programming</span>
<span class="badge cat-hardware">Hardware</span>
<span class="badge cat-other">Other</span>
```

### Categories

| Class | Color | Use Case |
|-------|-------|----------|
| `.cat-ai` | Purple (#bc8cff) | Artificial Intelligence, ML, NLP |
| `.cat-privacy` | Orange (#d29922) | Privacy, data protection, surveillance |
| `.cat-security` | Red (#f85149) | Security vulnerabilities, breaches |
| `.cat-programming` | Green (#3fb950) | Programming languages, frameworks |
| `.cat-hardware` | Blue (#58a6ff) | Hardware, chips, devices |
| `.cat-other` | Gray | Miscellaneous topics |

## Pipeline Status Badges

Used in admin views to show article processing status.

```html
<span class="pipeline-badge pipeline-done">Done</span>
<span class="pipeline-badge pipeline-active">Active</span>
<span class="pipeline-badge pipeline-skipped">Skipped</span>
<span class="pipeline-badge pipeline-error">Error</span>
```

## Impact Score Badges

Shows relative importance of articles on the dashboard.

```html
<span class="impact-score impact-high">9</span>
<span class="impact-score impact-mid">6</span>
<span class="impact-score impact-low">3</span>
<span class="impact-score impact-minor">1</span>
```

## Confidence Labels

Indicates LLM confidence in article analysis.

```html
<span class="impact-score impact-high">High</span>
<span class="impact-score impact-mid">Medium</span>
<span class="impact-score impact-low">Low</span>
```

## CSS Structure

```css
.badge,
.category-badge {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-weight: 600;
  display: inline-block;
}

.cat-ai {
  color: var(--purple);
  background: var(--purple-alpha-10);
  border: 1px solid var(--purple-alpha-25);
}
```

## Variables Used

- `--purple`, `--purple-alpha-10`, `--purple-alpha-25`
- `--orange`, `--orange-alpha-10`, `--orange-alpha-25`
- `--red`, `--red-alpha-10`, `--red-alpha-25`
- `--green`, `--green-alpha-10`, `--green-alpha-25`
- `--accent`, `--accent-alpha-10`, `--accent-alpha-25`
- `--text-muted`, `--bg-tertiary`, `--border`
