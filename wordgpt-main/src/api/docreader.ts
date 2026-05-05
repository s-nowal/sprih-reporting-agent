import { htmlToMarkdown } from "@/utils/mdFormatter";
import { BASE_URL } from './config';

async function getDocumentAsMarkdown(): Promise<string> {
  let markdown = "";
  try {
    markdown = await Word.run(async (context) => {
      const body = context.document.body;
      const htmlResult = body.getHtml();
      await context.sync();

      const html = htmlResult.value;
      const md = htmlToMarkdown(html);
      return md;
    });
  } catch (e) {
    console.error(e);

    markdown = await Word.run(async (context) => {
      const body = context.document.body;
      body.load("text");
      await context.sync();
      return body.text || "";
    });
  }
  return markdown;
}

// export async function getFullDocument(): Promise<string> {
//   return new Promise((resolve, reject) => {
//     Office.context.document.getFileAsync(
//       Office.FileType.Compressed, 
//       { sliceSize: 65536 },       
//       async (result) => {
//         if (result.status !== Office.AsyncResultStatus.Succeeded) {
//           return reject(new Error(`getFileAsync failed: ${result.status}`))
//         }

//         const file = result.value
//         const slices: Uint8Array[] = []

//         try {
//           for (let i = 0; i < file.sliceCount; i++) {
//             const slice = await getSlice(file, i)
//             slices.push(new Uint8Array(slice.data as number[]))
//           }

//           const totalLength = slices.reduce((sum, s) => sum + s.length, 0)
//           const merged = new Uint8Array(totalLength)
//           let offset = 0
//           for (const slice of slices) {
//             merged.set(slice, offset)
//             offset += slice.length
//           }

//           resolve(uint8ArrayToBase64(merged))
//         } catch (err) {
//           reject(err)
//         } finally {
//           file.closeAsync(() => {}) 
//         }
//       }
//     )
//   })
// }

// function getSlice(file: Office.File, index: number): Promise<Office.Slice> {
//   return new Promise((resolve, reject) => {
//     file.getSliceAsync(index, (result) => {
//       if (result.status === Office.AsyncResultStatus.Succeeded) {
//         resolve(result.value)
//       } else {
//         reject(new Error(`getSliceAsync failed on slice ${index}: ${result.status}`))
//       }
//     })
//   })
// }

// function uint8ArrayToBase64(bytes: Uint8Array): string {
//   let binary = ''
//   const chunkSize = 8192
//   for (let i = 0; i < bytes.length; i += chunkSize) {
//     binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
//   }
//   return btoa(binary)
// }

export async function uploadCurrentDocument(): Promise<{ document_id: string; filename: string }> {
  const documentText = await getDocumentAsMarkdown();
  const payload: Record<string, string> = {
    filename: 'output.md',
  };
  if (documentText) {
    payload.document_text = documentText;
  }
  payload.filepath = 'output';

  const response = await fetch(`${BASE_URL}/documents/upload-from-addin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Upload failed (${response.status}): ${detail}`);
  }

  return response.json(); 
}

export async function getCurrentDocument() {
  const response = await fetch(`${BASE_URL}/documents/upload-from-addin`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Upload failed (${response.status}): ${detail}`);
  }

  const data = await response.json();
  const match = data.find((item: any) => item.filename === 'output.md');
  return match.document_text; 
}

export async function getAllDocuments() {
  const response = await fetch(`${BASE_URL}/documents/upload-from-addin`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Upload failed (${response.status}): ${detail}`);
  }

  const data = await response.json();
  return data; 
}

export async function downloadDocument(
  payload: { filename: string; document_base64: string },
  directoryHandle?: FileSystemDirectoryHandle,
): Promise<void> {
  const { filename, document_base64 } = payload
  const byteArray = new Uint8Array(
    Array.from(atob(document_base64), c => c.charCodeAt(0))
  )
  const blob = new Blob([byteArray])

  if (directoryHandle) {
    const fileHandle = await directoryHandle.getFileHandle(filename, { create: true })
    const writable = await fileHandle.createWritable()
    await writable.write(blob)
    await writable.close()
    return
  }

  if ('showSaveFilePicker' in window) {
    try {
      const ext = filename.split('.').pop()
      const fileHandle = await (window as any).showSaveFilePicker({
        suggestedName: filename,
        types: ext ? [{ description: 'File', accept: { '*/*': [`.${ext}`] } }] : undefined,
      })
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      return
    } catch (e: any) {
      if (e.name === 'AbortError') return
    }
  }

  // Legacy fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function uploadInputDocument(payload) {
  const response = await fetch(`${BASE_URL}/documents/upload-from-addin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Upload failed (${response.status}): ${detail}`);
  }
  
  return response.json(); 
}