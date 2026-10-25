/** "?" button with a side drawer that explains one screen's options and links its guide. */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "./useWording";
import { usePhoneTabsOnClose } from "./usePhoneTabsOnClose";

/** One explained group of options: its heading and its term entries. */
export type HelpSection = {
  heading: string;
  items: readonly { term: string; text: string; tag?: boolean }[];
};

/** Render the help button that opens one screen's explanation drawer. */
export function HelpTip({
  title,
  sections,
  guide,
}: {
  title?: string;
  sections: readonly HelpSection[];
  /** One native link to the guide of the explained screen, opened in the current tab. */
  guide?: { href: string; label: string };
}) {
  const [open, setOpen] = useState(false);
  const { t } = useWording();
  usePhoneTabsOnClose(open);
  return (
    <Dialog.Root open={open} modal={false} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          className="help-tip"
          type="button"
          aria-label={t("Explain these options")}
          aria-expanded={open}
        >
          ?
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Content className="help-drawer" aria-describedby={undefined}>
          <header className="dh">
            <Dialog.Title className="dt">
              {title ?? t("About these options")}
            </Dialog.Title>
            <Dialog.Close className="pill-btn" aria-label={t("Close")}>
              {t("Close")}
            </Dialog.Close>
          </header>
          <div className="help-body">
            {sections.map((section) => (
              <section key={section.heading}>
                <h3>{section.heading}</h3>
                <dl>
                  {section.items.map((item) => (
                    <div key={item.term}>
                      <dt className={item.tag ? "help-tag" : undefined}>
                        {item.term}
                      </dt>
                      <dd>{item.text}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
            {guide && (
              <a className="help-guide" href={guide.href}>
                {guide.label}
              </a>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
