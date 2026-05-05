import { Ref } from 'vue'

import { WordFormatter } from '@/utils/wordFormatter'

export function insertResult(result: string, insertType: Ref): void {
  const paragraph = result
    .replace(/(\r\n|\n|\r)/g, '\n')
    .replace(/\n+/g, '\n')
    .split('\n')
  switch (insertType.value) {
    case 'replace':
      Word.run(async context => {
        const range = context.document.getSelection()
        range.insertText(paragraph[0], 'Replace')
        for (let i = paragraph.length - 1; i > 0; i--) {
          range.insertParagraph(paragraph[i], 'After')
        }
        await context.sync()
      })
      break
    case 'append':
      Word.run(async context => {
        const range = context.document.getSelection()
        range.insertText(paragraph[0], 'End')
        for (let i = paragraph.length - 1; i > 0; i--) {
          range.insertParagraph(paragraph[i], 'After')
        }
        await context.sync()
      })
      break
    case 'newLine':
      Word.run(async context => {
        const range = context.document.getSelection()
        for (let i = paragraph.length - 1; i >= 0; i--) {
          range.insertParagraph(paragraph[i], 'After')
        }
        await context.sync()
      })
      break
    case 'replaceAll':
      Word.run(async context => {
        const body = context.document.body
        body.select()
        await context.sync()

        const range = context.document.getSelection()
        range.load('text')
        await context.sync()

        if (range.text && range.text.length > 0) {
          range.delete()
        }

        const afterRange = context.document.getSelection()
        afterRange.load('text')
        await context.sync()

        body.insertText(paragraph[0], 'Start')
        for (let i = 1; i < paragraph.length; i++) {
          body.insertParagraph(paragraph[i], 'End')
        }
        await context.sync()
      })
      break
    case 'NoAction':
      break
  }
}

export async function insertFormattedResult(result: string, insertType: Ref): Promise<void> {
  try {
    await WordFormatter.insertFormattedResult(result, insertType)
  } catch (error: any) {
    insertResult(result, insertType)
  }
}
