/** Shared immutable SVG marks for interface controls. */

/** The delete mark: a bin outline with two vertical strokes. */
export const TRASH = (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9h6.6L12 4M6.8 6.5v4M9.2 6.5v4" />
  </svg>
);
/** The swap mark: two opposed horizontal arrows. */
export const SWAP_ICON = (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3 5h8M9 3l2 2-2 2M13 11H5M7 9l-2 2 2 2" />
  </svg>
);
/** GitHub's Octicons mark (`mark-github`), drawn in the text color. */
export const GITHUB_MARK = (
  <svg className="github-mark" viewBox="0 0 16 16" aria-hidden="true">
    <metadata>{`MIT License

Copyright (c) 2026 GitHub Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`}</metadata>
    <path
      fill="currentColor"
      d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"
    />
  </svg>
);
/** The document mark: a page outline with three text lines. */
export const DOCUMENT = (
  <svg className="doc" viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3.5 2h7l2 2v10h-9z M5.5 6h5 M5.5 8.5h5 M5.5 11h3" />
  </svg>
);
/** The search mark: a magnifier with a handle. */
export const SEARCH_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <circle cx="10.5" cy="10.5" r="6" />
    <path d="m15 15 4.5 4.5" />
  </svg>
);
/** The comparison mark: two opposed horizontal arrows. */
export const COMPARE_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <path d="M4 8.5h13m-3.5-4 4 4-4 4" />
    <path d="M20 15.5H7m3.5-4-4 4 4 4" />
  </svg>
);
/** The prerequisite graph mark: one box above two boxes. */
export const GRAPH_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <rect x="8.5" y="3" width="7" height="5" rx="1.2" />
    <rect x="2.5" y="16" width="7" height="5" rx="1.2" />
    <rect x="14.5" y="16" width="7" height="5" rx="1.2" />
    <path d="M12 8v4M6 16v-4h12v4" />
  </svg>
);
/** The discovery mark: a compass needle inside a circle. */
export const DISCOVER_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="8.5" />
    <path d="m15.5 8.5-2 5-5 2 2-5z" />
  </svg>
);
/** The structure mark: one box above three boxes. */
export const STRUCTURE_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <rect x="9" y="3" width="6" height="4.5" rx="1" />
    <path d="M12 7.5v4.5M5 21v-6h14v6" />
    <rect x="2.5" y="17" width="5" height="4" rx="1" />
    <rect x="9.5" y="17" width="5" height="4" rx="1" />
    <rect x="16.5" y="17" width="5" height="4" rx="1" />
  </svg>
);
/** The menu mark: three 12-unit horizontal lines. */
export const MORE_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <path d="M6 8h12M6 12h12M6 16h12" />
  </svg>
);
/** The recenter mark: a circle with four outward ticks. */
export const RECENTER_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4" />
  </svg>
);
/** The sliders mark: three rows with one knob each. */
export const SLIDERS_ICON = (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    aria-hidden="true"
  >
    <path d="M4 7h5M13 7h7M4 12h10M18 12h2M4 17h2M10 17h10" />
    <circle cx="11" cy="7" r="1.8" />
    <circle cx="16" cy="12" r="1.8" />
    <circle cx="8" cy="17" r="1.8" />
  </svg>
);
