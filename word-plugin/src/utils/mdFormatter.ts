// ── Markdown → HTML renderer ─────────────────────────────────────────────
// Tiny CommonMark-ish subset, sufficient for what an LLM emits in chat:
// headings, bold/italic/code/links, fenced code, lists, tables, blockquotes,
// rules. Output is plugged in via v-html, so all user-supplied substrings
// MUST flow through escapeHtml() before concatenation.

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInline(text: string): string {
  // Ordered longest-match first: *** > ** > *, ___ > __ > _.
  const pattern =
    /\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|___(.+?)___|__(.+?)__|_(.+?)_|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/g
  let result = ''
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex)
      result += escapeHtml(text.slice(lastIndex, match.index))
    const [, bi1, b1, i1, bi2, b2, i2, code, linkText, linkHref] = match
    if (bi1 !== undefined) result += `<strong><em>${escapeHtml(bi1)}</em></strong>`
    else if (b1 !== undefined) result += `<strong>${escapeHtml(b1)}</strong>`
    else if (i1 !== undefined) result += `<em>${escapeHtml(i1)}</em>`
    else if (bi2 !== undefined) result += `<strong><em>${escapeHtml(bi2)}</em></strong>`
    else if (b2 !== undefined) result += `<strong>${escapeHtml(b2)}</strong>`
    else if (i2 !== undefined) result += `<em>${escapeHtml(i2)}</em>`
    else if (code !== undefined) result += `<code>${escapeHtml(code)}</code>`
    else if (linkText !== undefined)
      result += `<a href="${escapeHtml(linkHref)}" target="_blank" rel="noopener noreferrer">${escapeHtml(linkText)}</a>`
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) result += escapeHtml(text.slice(lastIndex))
  return result
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim())
}

export function markdownToHtml(markdown: string): string {
  const lines = markdown.trim().split('\n')
  const parts: string[] = []
  let i = 0
  let openList: '' | 'ul' | 'ol' = ''

  const closeList = () => {
    if (openList) {
      parts.push(`</${openList}>`)
      openList = ''
    }
  }

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    if (line.trim().startsWith('```')) {
      closeList()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(escapeHtml(lines[i]))
        i++
      }
      i++
      parts.push(`<pre><code>${codeLines.join('\n')}</code></pre>`)
      continue
    }

    // Heading
    const hm = line.match(/^(#{1,6})\s+(.+?)(?:\s+#+)?$/)
    if (hm) {
      closeList()
      const tag = `h${hm[1].length}`
      parts.push(`<${tag}>${renderInline(hm[2])}</${tag}>`)
      i++
      continue
    }

    // Blockquote
    if (line.trimStart().startsWith('>')) {
      closeList()
      parts.push(
        `<blockquote>${renderInline(line.replace(/^\s*>\s?/, ''))}</blockquote>`,
      )
      i++
      continue
    }

    // Bullet list
    const bm = line.match(/^(\s*)[-*+]\s+(.+)/)
    if (bm) {
      if (openList !== 'ul') {
        closeList()
        parts.push('<ul>')
        openList = 'ul'
      }
      parts.push(`<li>${renderInline(bm[2])}</li>`)
      i++
      continue
    }

    // Numbered list
    const nm = line.match(/^(\s*)\d+\.\s+(.+)/)
    if (nm) {
      if (openList !== 'ol') {
        closeList()
        parts.push('<ol>')
        openList = 'ol'
      }
      parts.push(`<li>${renderInline(nm[2])}</li>`)
      i++
      continue
    }

    // Table (header row followed by | --- | --- | separator)
    if (line.trim().startsWith('|')) {
      const nextLine = lines[i + 1]?.trim() ?? ''
      if (nextLine.match(/^\|[-:\s|]+\|/)) {
        closeList()
        const headers = parseTableRow(line)
        i += 2
        const rows: string[][] = []
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          rows.push(parseTableRow(lines[i]))
          i++
        }
        const headerHtml = headers
          .map((h) => `<th>${renderInline(h)}</th>`)
          .join('')
        const bodyHtml = rows
          .map(
            (row) =>
              `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`,
          )
          .join('')
        parts.push(
          `<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`,
        )
        continue
      }
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(line.trim())) {
      closeList()
      parts.push('<hr/>')
      i++
      continue
    }

    // Blank line
    if (!line.trim()) {
      closeList()
      i++
      continue
    }

    // Paragraph
    closeList()
    parts.push(`<p>${renderInline(line)}</p>`)
    i++
  }

  closeList()
  return parts.join('')
}

// ── HTML → Markdown converter ────────────────────────────────────────────

export function htmlToMarkdown(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const TEXT_NODE    = 3;
  const ELEMENT_NODE = 1;
 
  doc.querySelectorAll("script, style, head, meta, link").forEach(n => n.remove());
 
  function meaningfulDescendants(el) {
    const result = [];
    for (const n of el.childNodes) {
      if (n.nodeType === TEXT_NODE) {
        if (n.textContent.trim()) result.push(n); 
      } else if (n.nodeType === ELEMENT_NODE) {
        const t = n.tagName.toLowerCase();
        if (t === "span") {
          result.push(...meaningfulDescendants(n)); 
        } else {
          result.push(n);
        }
      }
    }
    return result;
  }
 
  doc.querySelectorAll("div, p").forEach(wrapper => {
    if (!wrapper.parentNode) return;
    const mc = meaningfulDescendants(wrapper);
    if (
      mc.length === 1 &&
      mc[0].nodeType === ELEMENT_NODE &&
      mc[0].tagName.toLowerCase() === "hr"
    ) {
      const hr = doc.createElement("hr");
      wrapper.parentNode.replaceChild(hr, wrapper);
    }
  });
 
  function collapse(str) {
    return str.replace(/[ \t]*\n[ \t]*/g, " ").replace(/  +/g, " ").trim();
  }
 
  const TOC_RE = /^\s*\(.*?table\s+of\s+contents.*?\)\s*$/i;

  function convert(node) {
    if (node.nodeType === TEXT_NODE) {
      return node.textContent.replace(/\n/g, " ");
    }
    if (node.nodeType !== ELEMENT_NODE) return "";
 
    const tag = node.tagName.toLowerCase();
    const children = () => Array.from(node.childNodes).map(convert).join("");
 
    switch (tag) {
      case "h1": return `\n# ${collapse(children())}\n`;
      case "h2": return `\n## ${collapse(children())}\n`;
      case "h3": return `\n### ${collapse(children())}\n`;
      case "h4": return `\n#### ${collapse(children())}\n`;
      case "h5": return `\n##### ${collapse(children())}\n`;
      case "h6": return `\n###### ${collapse(children())}\n`;
      case "strong":
      case "b": {
        const inner = collapse(children());
        return inner ? `**${inner}**` : "";
      }
      case "em":
      case "i": {
        const inner = collapse(children());
        return inner ? `*${inner}*` : "";
      }
      case "code":  return `\`${children()}\``;
      case "mark":  return children();
      case "s":
      case "del":   return `~~${children()}~~`;
      case "sup":   return `^${children()}`;
      case "sub":   return `~${children()}~`;
      case "a": {
        const href = node.getAttribute("href") || "";
        const text = children().trim();
        if (!href || href === text) return text;
        return `[${text}](${href})`;
      }
      case "img": {
        const src = node.getAttribute("src") || "";
        const alt = node.getAttribute("alt") || "";
        return `![${alt}](${src})`;
      }
      case "p": {
        const text = collapse(children());
        if (!text) return "";                             
        if (TOC_RE.test(text)) return "\n<!-- TOC -->\n";
        return `\n${text}\n`;
      }
      case "br": return "  \n";
      case "hr": return "\n\n---\n\n";
      case "blockquote": {
        const lines = children().trim().split("\n");
        return "\n" + lines.map(l => `> ${l}`).join("\n") + "\n";
      }
      case "ul": return convertList(node, false);
      case "ol": return convertList(node, true);
      case "li": return children();
      case "table": return convertTable(node);
      case "pre": {
        const code = node.querySelector("code");
        const lang = code ? (code.className.replace("language-", "") || "") : "";
        const content = code ? code.textContent : node.textContent;
        return `\n\`\`\`${lang}\n${content}\n\`\`\`\n`;
      }
      case "div":
      case "section":
      case "article":
      case "main":
      case "header":
      case "footer":
      case "span":
      case "body":
      case "html": return children();
      case "xml":
      case "o:p":
      case "w:sdt":
        return "";
      default: return children();
    }
  }

  function convertList(listNode, ordered, depth = 0) {
    const indent = "  ".repeat(depth);
    let index = 1;
    let result = "\n";
 
    for (const child of listNode.childNodes) {        
      if (child.nodeType !== ELEMENT_NODE) continue;
      if (child.tagName.toLowerCase() !== "li") continue;
 
      const nestedList = Array.from(child.childNodes).find(
        n => n.nodeType === ELEMENT_NODE &&
             (n.tagName.toLowerCase() === "ul" || n.tagName.toLowerCase() === "ol")
      );
 
      let text = "";
      for (const n of child.childNodes) {
        if (n.nodeType === ELEMENT_NODE) {
          const t = n.tagName.toLowerCase();
          if (t === "ul" || t === "ol") continue;
        }
        text += convert(n);
      }
      text = collapse(text);
 
      const bullet = ordered ? `${index++}.` : "-";
      result += `${indent}${bullet} ${text}\n`;
 
      if (nestedList) {
        const isOrdered = nestedList.tagName.toLowerCase() === "ol";
        result += convertList(nestedList, isOrdered, depth + 1);
      }
    }
    return result;
  }

  function convertTable(tableNode) {
    const rows = Array.from(tableNode.querySelectorAll("tr"));
    if (!rows.length) return "";
 
    const md = [];
    rows.forEach((row, rowIdx) => {
      const cells = Array.from(row.querySelectorAll("th, td"));
      const cellTexts = cells.map(c =>
        c.textContent.replace(/\s*\n\s*/g, " ").trim()
      );
      md.push("| " + cellTexts.join(" | ") + " |");
      if (rowIdx === 0) {
        md.push("| " + cells.map(() => "---").join(" | ") + " |");
      }
    });
    return "\n" + md.join("\n") + "\n";
  }
 
  const root = doc.body || doc.documentElement;
  let markdown = convert(root);
 
  markdown = markdown
    .replace(/^[ \t]+$/gm, "")     
    .replace(/\n{3,}/g, "\n\n")      
    .replace(/^\s*\u00a0\s*$/gm, "") 
    .trim();
 
  return markdown;
}