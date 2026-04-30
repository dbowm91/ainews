#!/usr/bin/env node

/**
 * generate-critical-css.js
 * ─────────────────────────
 *
 * Extracts :root and [data-theme="light"] blocks from variables.css,
 * minifies them, and writes the output to templates/partials/critical_css.html
 *
 * Usage: node build/generate-critical-css.js
 */

const fs = require('fs');
const path = require('path');

const VARIABLES_CSS = path.join(__dirname, '..', 'static', 'css', 'variables.css');
const OUTPUT_HTML = path.join(__dirname, '..', 'templates', 'partials', 'critical_css.html');
const CRITICAL_CSS = path.join(__dirname, '..', 'static', 'css', 'critical.css');

function extractCSSBlocks(content) {
  const blocks = [];

  // Extract :root block
  const rootMatch = content.match(/:root\s*\{([^}]+)\}/);
  if (rootMatch) {
    blocks.push(`:root{${rootMatch[1].trim()}}`);
  }

  // Extract [data-theme="light"] block
  const lightMatch = content.match(/\[data-theme="light"\]\s*\{([^}]+)\}/);
  if (lightMatch) {
    blocks.push(`[data-theme="light"]{${lightMatch[1].trim()}}`);
  }

  return blocks;
}

function minifyCSS(css) {
  return css
    // Remove comments
    .replace(/\/\*[\s\S]*?\*\//g, '')
    // Remove unnecessary whitespace
    .replace(/\s+/g, ' ')
    // Remove spaces around { } ; :
    .replace(/\s*\{\s*/g, '{')
    .replace(/\s*\}\s*/g, '}')
    .replace(/\s*;\s*/g, ';')
    .replace(/\s*:\s*/g, ':')
    .replace(/\s*,\s*/g, ',')
    // Remove trailing semicolons before }
    .replace(/;}/g, '}')
    // Remove remaining whitespace
    .trim();
}

function extractCriticalRules(criticalContent) {
  // Skip the @import line and extract all rules after it
  const lines = criticalContent.split('\n');
  let inImport = false;
  let rulesStart = 0;

  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('@import')) {
      inImport = true;
      continue;
    }
    if (inImport && lines[i].trim() === '') {
      continue;
    }
    if (inImport && lines[i].trim() !== '') {
      rulesStart = i;
      break;
    }
  }

  const rulesSection = lines.slice(rulesStart).join('\n');
  return minifyCSS(rulesSection);
}

function main() {
  try {
    // Read variables.css
    const variablesContent = fs.readFileSync(VARIABLES_CSS, 'utf8');

    // Extract and minify CSS variable blocks
    const variableBlocks = extractCSSBlocks(variablesContent);
    const minifiedVariables = variableBlocks.map(minifyCSS).join('');

    // Read critical.css (excluding @import)
    const criticalContent = fs.readFileSync(CRITICAL_CSS, 'utf8');
    const criticalRules = extractCriticalRules(criticalContent);

    // Combine: variables first, then critical rules
    const output = minifiedVariables + criticalRules;

    // Write to output file
    fs.writeFileSync(OUTPUT_HTML, output + '\n');

    console.log(`✓ Generated ${OUTPUT_HTML}`);
    console.log(`  Variables: ${variableBlocks.length} blocks extracted`);
    console.log(`  Output size: ${output.length} bytes`);
  } catch (err) {
    console.error(`✗ Error: ${err.message}`);
    process.exit(1);
  }
}

main();
