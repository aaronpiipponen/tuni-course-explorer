/** "?" button with a side drawer that explains one screen's options through inline links. */
import { useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useWording } from "./useWording";
import { usePhoneTabsOnClose } from "./usePhoneTabsOnClose";
import type { UiTextKey } from "./wording";

/** One explained group of options: its heading and its term entries. */
export type HelpSection = {
  heading: ReactNode;
  items: readonly { term: ReactNode; text: ReactNode; tag?: boolean }[];
};

/** Render a native in-tab link inside help text or a help term. */
export function HelpLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a className="help-link" href={href}>
      {children}
    </a>
  );
}

/** Render the help button that opens one screen's explanation drawer. */
export function HelpTip({
  title,
  explain = "Explain these options",
  sections,
  onOpenChange,
  keepOpenOnOutside,
}: {
  title?: string;
  /** The trigger's accessible name. */
  explain?: UiTextKey;
  sections: readonly HelpSection[];
  /** Report the drawer's open state to the surface that makes room for it. */
  onOpenChange?: (open: boolean) => void;
  /** Return whether one outside interaction keeps the drawer open, such as a drag press. */
  keepOpenOnOutside?: (target: EventTarget | null) => boolean;
}) {
  const [open, setOpen] = useState(false);
  const { t } = useWording();
  usePhoneTabsOnClose(open);
  return (
    <Dialog.Root
      open={open}
      modal={false}
      onOpenChange={(value) => {
        setOpen(value);
        onOpenChange?.(value);
      }}
    >
      <Dialog.Trigger asChild>
        <button
          className="help-tip"
          type="button"
          aria-label={t(explain)}
          aria-expanded={open}
        >
          ?
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Content
          className="help-drawer"
          aria-describedby={undefined}
          onInteractOutside={(event) => {
            if (keepOpenOnOutside?.(event.target)) event.preventDefault();
          }}
        >
          <header className="dh">
            <Dialog.Title className="dt">
              {title ?? t("About these options")}
            </Dialog.Title>
            <Dialog.Close className="pill-btn" aria-label={t("Close")}>
              {t("Close")}
            </Dialog.Close>
          </header>
          <div className="help-body thin-scrollbar">
            {sections.map((section, index) => (
              <section key={index}>
                <h3>{section.heading}</h3>
                <dl>
                  {section.items.map((item, itemIndex) => (
                    <div key={itemIndex}>
                      <dt className={item.tag ? "help-tag" : undefined}>
                        {item.term}
                      </dt>
                      <dd>{item.text}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
