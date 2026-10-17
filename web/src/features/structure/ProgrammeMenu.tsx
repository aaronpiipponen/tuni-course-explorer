/** One top-level programme's "..." menu: replace, reset and delete that programme. */
import { useRef, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useWording } from "../../shared/useWording";

export function ProgrammeMenu({
  name,
  onReplace,
  onReset,
  onDelete,
}: {
  name: string;
  onReplace(): void;
  onReset(): void;
  onDelete(): void;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const { t } = useWording();
  // The trigger holds focus while the confirmation a menu item opens is displayed.
  const handOff = (action: () => void) => () => {
    trigger.current?.focus();
    action();
  };
  return (
    <DropdownMenu.Root modal={false} open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger ref={trigger} asChild>
        <button
          className="programme-menu-trigger"
          type="button"
          aria-label={t("Programme actions for {name}", { name })}
          aria-expanded={open}
        >
          ⋯
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="course-menu programme-menu"
          side="bottom"
          align="end"
          sideOffset={3}
        >
          <DropdownMenu.Item onSelect={handOff(onReplace)}>
            {t("Replace programme")}
          </DropdownMenu.Item>
          <DropdownMenu.Item onSelect={handOff(onReset)}>
            {t("Reset programme")}
          </DropdownMenu.Item>
          <DropdownMenu.Item className="danger" onSelect={handOff(onDelete)}>
            {t("Delete programme")}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
