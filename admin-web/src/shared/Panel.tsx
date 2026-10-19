/**
 * The console's shared panel layout: a panel box, its measured body, its row list, its data table
 * and its failure notice. Feature panels compose these primitives and own no layout of their own.
 */
import type { ReactNode } from "react";
import { AnimatedPanelBody } from "./AnimatedPanelBody";

/**
 * Render one panel box with its heading, its automatic-read marker and its measured body.
 *
 * The default span places two panels in one desktop row.
 */
export function Panel({
  title,
  marker,
  children,
  span = 6,
}: {
  title: string;
  marker?: ReactNode;
  children: ReactNode;
  span?: 4 | 6 | 12;
}) {
  return (
    <section className={`panel w${span}`}>
      <div className="ph">
        <h3>{title}</h3>
        <span className="sp" />
        {marker}
      </div>
      <AnimatedPanelBody>{children}</AnimatedPanelBody>
    </section>
  );
}

/** Render one labelled row of a panel, optionally closing it with an accent rule. */
export function Row({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={accent ? "row accent" : "row"}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

/** Render the row list of one panel. */
export function Rows({ children }: { children: ReactNode }) {
  return <div className="rows">{children}</div>;
}

/** Render one data table with its header row, its aligned cells and its optional scroll class. */
export function DataTable({
  head,
  rows,
  align = [],
  scrollClassName = "",
}: {
  head: string[];
  rows: ReactNode[][];
  align?: string[];
  scrollClassName?: string;
}) {
  return (
    <div className={["scroll", scrollClassName].filter(Boolean).join(" ")}>
      <table className="tbl">
        <thead>
          <tr>
            {head.map((title, index) => (
              <th key={title} className={align[index]}>
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            // A table row's identity is its position in the reported order.
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className={align[cellIndex]}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Render one visible command or read failure inside the panel it belongs to. */
export function FailureNotice({ text }: { text: string | null }) {
  if (text === null) {
    return null;
  }
  return (
    <p className="failure" role="alert">
      {text}
    </p>
  );
}
