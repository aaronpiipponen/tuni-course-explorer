/**
 * Lazy PDF.js decoder from one supported Sisu plan PDF to the pure extractor's positioned pages.
 *
 * The module imports PDF.js and its same-version worker only when the profile import accepts a PDF.
 * One array buffer and one text pass per page reach `extractSisuPdfRows`. Pages are never rendered
 * and annotations, scripts, attachments and metadata are never read. Decoder failures become the
 * safe `Invalid Sisu PDF plan` error so no source text reaches a diagnostic.
 */
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { cancellationError } from "../../app/cachedRead";
import {
  extractSisuPdfRows,
  INVALID_SISU_PDF_PLAN,
  type SisuPdfRow,
  type SisuPdfTextItem,
  type SisuPdfTextPage,
} from "./sisuPdfRows";

GlobalWorkerOptions.workerSrc = workerUrl;

/** Read one supported Sisu plan PDF's positioned text and return its ordered plan rows. */
export async function readSisuPdf(
  file: File,
  signal: AbortSignal,
): Promise<readonly SisuPdfRow[]> {
  const buffer = await file.arrayBuffer();
  if (signal.aborted) throw cancellationError(signal);
  const task = getDocument({
    data: new Uint8Array(buffer),
    stopAtErrors: true,
    useWasm: false,
  });
  const abort = () => {
    void task.destroy();
  };
  signal.addEventListener("abort", abort, { once: true });
  try {
    const document = await task.promise;
    if (signal.aborted) throw cancellationError(signal);
    const pages: SisuPdfTextPage[] = [];
    for (let number = 1; number <= document.numPages; number++) {
      if (signal.aborted) throw cancellationError(signal);
      const page = await document.getPage(number);
      try {
        const text = await page.getTextContent();
        const items: SisuPdfTextItem[] = [];
        for (const item of text.items) {
          if (!("str" in item) || !("transform" in item)) continue;
          items.push({
            str: item.str,
            transform: item.transform,
            width: item.width,
            height: item.height,
          });
        }
        pages.push({ page: number, items });
      } finally {
        page.cleanup();
      }
    }
    return extractSisuPdfRows(pages);
  } catch {
    if (signal.aborted) throw cancellationError(signal);
    throw new Error(INVALID_SISU_PDF_PLAN);
  } finally {
    signal.removeEventListener("abort", abort);
    await task.destroy();
  }
}
