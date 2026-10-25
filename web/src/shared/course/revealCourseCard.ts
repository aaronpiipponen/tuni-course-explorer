/** Scroll a course card under the visible header and reserve room below it for its menu. */
export function revealCourseCard(
  card: HTMLElement,
  reducedMotion: boolean,
  menuTop: number,
  containerOverride?: HTMLElement | null,
): () => void {
  let container = containerOverride ?? card.parentElement;
  if (!containerOverride)
    while (container && !isScrollContainer(container))
      container = container.parentElement;
  if (!container) return () => {};
  const scroller = container;
  const containerRect = scroller.getBoundingClientRect();
  const cardRect = card.getBoundingClientRect();
  const header = scroller.querySelector<HTMLElement>(".discover-phone-head");
  const headerBottom = header
    ? Math.max(0, header.getBoundingClientRect().bottom - containerRect.top)
    : 0;
  const headerTop = containerRect.top + headerBottom;
  const visibleBottom = Math.min(menuTop, containerRect.bottom);
  const available = Math.max(0, visibleBottom - headerTop);
  const desiredTop =
    available >= cardRect.height + 8
      ? headerTop + (available - cardRect.height) / 2
      : headerTop + 8;
  const target = Math.max(0, scroller.scrollTop + cardRect.top - desiredTop);
  const maximum = scroller.scrollHeight - scroller.clientHeight;
  const deficit = Math.max(0, target - maximum);
  const previousPadding = scroller.style.paddingBottom;
  if (deficit > 0) {
    const current = Number.parseFloat(getComputedStyle(scroller).paddingBottom);
    scroller.style.paddingBottom = `${(Number.isFinite(current) ? current : 0) + deficit + 8}px`;
  }
  let frame = 0;
  const timers: number[] = [];
  const animateTo = (top: number, duration: number) => {
    cancelAnimationFrame(frame);
    const from = scroller.scrollTop;
    if (reducedMotion || duration <= 0) {
      scroller.scrollTop = top;
      return;
    }
    const began = performance.now();
    const step = (now: number) => {
      const progress = Math.min(1, (now - began) / duration);
      const eased = 1 - (1 - progress) ** 3;
      scroller.scrollTop = from + (top - from) * eased;
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
  };
  const align = () => {
    const rect = card.getBoundingClientRect();
    const scrollerRect = scroller.getBoundingClientRect();
    const top = scrollerRect.top + headerBottom;
    const bottom = Math.min(menuTop, scrollerRect.bottom);
    const available = Math.max(0, bottom - top);
    const wanted =
      available >= rect.height + 8
        ? top + (available - rect.height) / 2
        : top + 8;
    const delta = rect.top - wanted;
    if (Math.abs(delta) > 1) animateTo(scroller.scrollTop + delta, 120);
  };
  const distance = Math.abs(target - scroller.scrollTop);
  const duration = reducedMotion ? 0 : Math.min(360, 160 + distance * 0.35);
  animateTo(target, duration);
  timers.push(window.setTimeout(align, duration + 80));
  timers.push(window.setTimeout(align, duration + 260));
  return () => {
    cancelAnimationFrame(frame);
    for (const timer of timers) window.clearTimeout(timer);
    scroller.style.paddingBottom = previousPadding;
    const nextMaximum = scroller.scrollHeight - scroller.clientHeight;
    if (scroller.scrollTop > nextMaximum) scroller.scrollTop = nextMaximum;
  };
}

function isScrollContainer(element: HTMLElement): boolean {
  const { overflowY } = getComputedStyle(element);
  return (
    (overflowY === "auto" || overflowY === "scroll") &&
    element.scrollHeight > element.clientHeight
  );
}
