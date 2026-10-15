/** "?" button with a side drawer that explains one screen's options. */
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { CLOSE } from "./icons";
import { useWording } from "./useWording";

export type HelpSection = {
  heading: string;
  items: readonly { term: string; text: string; tag?: boolean }[];
};

export function HelpTip({
  title,
  sections,
}: {
  title?: string;
  sections: readonly HelpSection[];
}) {
  const [open, setOpen] = useState(false);
  const { t } = useWording();
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
            <Dialog.Close className="dx" aria-label={t("Close")}>
              {CLOSE}
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
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
