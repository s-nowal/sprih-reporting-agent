import { Ref } from 'vue'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inlineToHtml(text: string): string {
  let s = escapeHtml(text)
  s = s.replace(/\*\*\*([\s\S]+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  s = s.replace(/___(.+?)___/g, '<strong><em>$1</em></strong>')
  s = s.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>')
  s = s.replace(/\*([\s\S]+?)\*/g, '<em>$1</em>')
  s = s.replace(/_([^_\s][^_]*)_/g, '<em>$1</em>')
  s = s.replace(/~~([\s\S]+?)~~/g, '<del>$1</del>')
  s = s.replace(/`([^`]+)`/g, '<code style="font-family:Courier New,monospace;">$1</code>')
  return s
}

type BlockType =
  | 'heading'
  | 'paragraph'
  | 'blockquote'
  | 'code_block'
  | 'hr'
  | 'table'
  | 'li'
  | 'oli'
  | 'empty'

interface Block {
  type: BlockType
  content: string
  rows?: string[][]
  level?: number
}

function parseTableRow(row: string): string[] {
  const cells = row.split('|')
  if (cells[0].trim() === '') cells.shift()
  if (cells.length > 0 && cells[cells.length - 1].trim() === '') cells.pop()
  return cells.map(c => c.trim())
}

function isTableSeparator(line: string): boolean {
  return /^\|?[\s:|-]+\|[\s:|-]*$/.test(line)
}

function parseMarkdown(md: string): Block[] {
  const lines = md.replace(/\r/g, '').split('\n')
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    if (/^```/.test(line)) {
      const codeLines: string[] = []
      i++
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i])
        i++
      }
      i++ 
      blocks.push({ type: 'code_block', content: codeLines.join('\n') })
      continue
    }

    const hm = line.match(/^(#{1,6})\s+(.+)$/)
    if (hm) {
      blocks.push({ type: 'heading', level: hm[1].length, content: hm[2].trim() })
      i++
      continue
    }

    if (line.startsWith('>')) {
      const qLines = [line.replace(/^>\s?/, '')]
      while (i + 1 < lines.length && lines[i + 1].startsWith('>')) {
        i++
        qLines.push(lines[i].replace(/^>\s?/, ''))
      }
      blocks.push({ type: 'blockquote', content: qLines.join('\n') })
      i++
      continue
    }

    if (/^(---+|\*\*\*+|___+)\s*$/.test(line.trim())) {
      blocks.push({ type: 'hr', content: '' })
      i++
      continue
    }

    if (line.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const rows: string[][] = [parseTableRow(line)]
      i += 2 // skip header + separator
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(parseTableRow(lines[i]))
        i++
      }
      blocks.push({ type: 'table', content: '', rows })
      continue
    }

    if (/^[\*\-\+]\s+/.test(line)) {
      blocks.push({ type: 'li', content: line.replace(/^[\*\-\+]\s+/, '') })
      i++
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      blocks.push({ type: 'oli', content: line.replace(/^\d+\.\s+/, '') })
      i++
      continue
    }

    if (line.trim() === '') {
      blocks.push({ type: 'empty', content: '' })
      i++
      continue
    }

    blocks.push({ type: 'paragraph', content: line })
    i++
  }

  return blocks
}

const TABLE_STYLE = 'border-collapse:collapse;width:100%;'
const CELL_STYLE = 'border:1px solid #000;padding:4px 8px;vertical-align:top;'
const TH_STYLE = `${CELL_STYLE}font-weight:bold;background:#f0f0f0;`
const BLOCKQUOTE_STYLE =
  'margin:0 0 0 1em;padding-left:0.75em;border-left:3px solid #ccc;color:#555;'
const CODE_BLOCK_STYLE =
  'font-family:Courier New,monospace;background:#f5f5f5;padding:0.75em;white-space:pre-wrap;'

function blocksToHtml(blocks: Block[]): string {
  const parts: string[] = []
  let inUl = false
  let inOl = false

  const closeList = () => {
    if (inUl) {
      parts.push('</ul>')
      inUl = false
    }
    if (inOl) {
      parts.push('</ol>')
      inOl = false
    }
  }

  for (const block of blocks) {
    if (block.type === 'li') {
      if (!inUl) {
        closeList()
        parts.push('<ul>')
        inUl = true
      }
      parts.push(`<li>${inlineToHtml(block.content)}</li>`)
      continue
    }
    if (block.type === 'oli') {
      if (!inOl) {
        closeList()
        parts.push('<ol>')
        inOl = true
      }
      parts.push(`<li>${inlineToHtml(block.content)}</li>`)
      continue
    }
    closeList()

    switch (block.type) {
      case 'heading':
        parts.push(`<h${block.level}>${inlineToHtml(block.content)}</h${block.level}>`)
        break

      case 'paragraph':
        parts.push(`<p>${inlineToHtml(block.content)}</p>`)
        break

      case 'blockquote': {
        const inner = block.content
          .split('\n')
          .map(l => inlineToHtml(l))
          .join('<br/>')
        parts.push(`<blockquote style="${BLOCKQUOTE_STYLE}">${inner}</blockquote>`)
        break
      }

      case 'code_block':
        parts.push(
          `<pre style="${CODE_BLOCK_STYLE}"><code>${escapeHtml(block.content)}</code></pre>`
        )
        break

      case 'hr':
        parts.push('<hr style="border:none;border-top:1px solid #999;margin:0.5em 0;"/>')
        break

      case 'table': {
        if (!block.rows?.length) break
        const maxCols = Math.max(...block.rows.map(r => r.length))
        parts.push(`<table style="${TABLE_STYLE}">`)
        block.rows.forEach((row, ri) => {
          parts.push('<tr>')
          const padded = [...row]
          while (padded.length < maxCols) padded.push('')
          padded.forEach(cell => {
            const tag = ri === 0 ? 'th' : 'td'
            const style = ri === 0 ? TH_STYLE : CELL_STYLE
            parts.push(`<${tag} style="${style}">${inlineToHtml(cell)}</${tag}>`)
          })
          parts.push('</tr>')
        })
        parts.push('</table>')
        break
      }

      case 'empty':
        break
    }
  }

  closeList()
  return parts.join('')
}

const BLOCKS_PER_CHUNK = 100

function chunkBlocks(blocks: Block[]): Block[][] {
  const chunks: Block[][] = []
  for (let i = 0; i < blocks.length; i += BLOCKS_PER_CHUNK) {
    chunks.push(blocks.slice(i, i + BLOCKS_PER_CHUNK))
  }
  return chunks
}

async function insertChunksAtSelection(
  htmlChunks: string[],
  firstLocation: Word.InsertLocation | 'Replace' | 'Start' | 'End' | 'Before' | 'After'
): Promise<void> {
  if (htmlChunks.length === 0) return

  await Word.run(async context => {
    const range = context.document.getSelection()
    range.insertHtml(htmlChunks[0], firstLocation)
    await context.sync()
  })

  for (let ci = 1; ci < htmlChunks.length; ci++) {
    const html = htmlChunks[ci]
    await Word.run(async context => {
      context.document.body.insertHtml(html, 'End')
      await context.sync()
    })
  }
}

export class WordFormatter {
  static async insertFormattedResult(result: string, insertType: Ref): Promise<void> {
    if (insertType.value === 'NoAction') return

    const blocks = parseMarkdown(result)
    const chunks = chunkBlocks(blocks)
    const htmlChunks = chunks.map(blocksToHtml)

    switch (insertType.value) {
      case 'replace':
        await insertChunksAtSelection(htmlChunks, 'Replace')
        break

      case 'append':
        await insertChunksAtSelection(htmlChunks, 'End')
        break

      case 'newLine':
        await insertChunksAtSelection(htmlChunks, 'After')
        break

      case 'replaceAll': {
        await Word.run(async context => {
          context.document.body.insertHtml(htmlChunks[0] ?? '', 'Replace')
          await context.sync()
        })
        for (let ci = 1; ci < htmlChunks.length; ci++) {
          const html = htmlChunks[ci]
          await Word.run(async context => {
            context.document.body.insertHtml(html, 'End')
            await context.sync()
          })
        }
        break
      }
    }
  }

  static async insertPlainResult(result: string, insertType: Ref): Promise<void> {
    const paragraphs = result.replace(/\r/g, '').split('\n')

    await Word.run(async context => {
      switch (insertType.value) {
        case 'replace': {
          const range = context.document.getSelection()
          range.insertText(paragraphs[0], 'Replace')
          for (let i = paragraphs.length - 1; i > 0; i--) range.insertParagraph(paragraphs[i], 'After')
          break
        }
        case 'append': {
          const range = context.document.getSelection()
          range.insertText(paragraphs[0], 'End')
          for (let i = paragraphs.length - 1; i > 0; i--) range.insertParagraph(paragraphs[i], 'After')
          break
        }
        case 'newLine': {
          const range = context.document.getSelection()
          for (let i = paragraphs.length - 1; i >= 0; i--) range.insertParagraph(paragraphs[i], 'After')
          break
        }
      }
      await context.sync()
    })
  }
}
