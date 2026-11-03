# Shared interface components

The shared interface components provide the help drawer, the notices, the disclosure and slide motion, the phone sheet, the scrollbar, the brand mark and the course menu.

## Help and the help drawer

`HelpTip` in `web/src/shared/HelpTip.tsx` renders the **?** button and the side drawer that explains one screen's options. A caller passes the drawer title, the trigger's accessible name through `explain`, one `HelpSection` per explained group, and optional `onOpenChange` and `keepOpenOnOutside` callbacks. The structure drawer keeps itself open when its `keepOpenOnOutside` check reports that the press landed inside the structure tree, so a desktop course drag can start there.

The trigger is a `.help-tip` button with `aria-expanded`. The drawer is one Radix dialog with `modal={false}`, so the page behind it accepts ordinary input. Its header holds the title and the **Close** control, and its `.help-body` scrolls with the shared thin accent scrollbar. Each section renders an H3 heading and a definition list of terms and explanations. `usePhoneTabsOnClose(open)` restores the phone bottom bar when the drawer closes.

`HelpLink` renders one in-tab link inside a heading, a term or an explanation. The link stays in the same browser tab. `HelpTip.test.ts` proves that a heading link, a term link and a text link all render inside the drawer in their owner element.

## Notices

`web/src/shared/noticeContext.ts` holds the notice types and the two contexts. `NoticeAction` is an optional button with a localized label and a run function, and `NoticeLink` is one phrase inside the message with the same pair. `NoticeOptions` carries a stable `key`, a `persistent` flag and a `link`. `NoticeApi` exposes `show(text, action?, options?)` and `dismiss(key)`, where `text` is a `(language) => string` formatter so one notice reads in the profile language at render time. `useNotice` reads the API and raises `Notice provider is missing` when no provider is mounted.

`NoticeProvider` in `NoticeProvider.tsx` owns the list, the identity counter and the timers. It records the tab that showed the notice from `getActiveTab()` at `show` time. A transient notice closes after 2200 milliseconds. A notice shown with a key that a visible notice already carries updates that notice in place and keeps its identity, so its running lifetime does not restart. A persistent notice carries no timer, and `dismiss` clears it by key.

`NoticeStack` in `NoticeStack.tsx` renders the notices of its own tab in one `.toast-stack`. Each row animates its height and opacity, and a message whose text changes fades the old words out, resizes the pill, and fades the incoming words in. A linked phrase appears as a `.toast-link` button inside the words, and an action appears beside them. Each action and each linked phrase runs inside `useAction`, so a navigation failure reaches `ErrorNotice`.

The stack measures its place against the bottom surfaces of the phone shell: the course, programme and profile menus, the phone sheets and any open menu, plus the pane's `.route-stack` and `.routebox`. A surface that appears or leaves hands over through the shared rise, and a surface that animates its own height is followed frame by frame. The stack sits above a scrim at `z-index` 40 and above an open picker, an open help drawer or a full-screen panel at 50, and it rides the tab slide of the pane that owns it. A stack that is leaving with its tab is `inert` and hidden from assistive technology.

`App` mounts `NoticeProvider` around the app shell with the current profile identity as its key, so a profile switch clears the list. `CourseMenu.test.ts` mounts the provider and the stack and proves that the menu's removal notice reaches the stack with the course code.

## Height and disclosure

`AnimatedHeight` in `AnimatedHeight.tsx` renders `.animated-height` around one content block and sets its height from the content's measured `offsetHeight`. A `ResizeObserver` reports each following measurement, and the CSS height transition runs over 0.3 seconds. The first measurement applies without animation because no earlier pixel height exists. The picker result areas and the feedback page use it.

`Disclosure` in `Disclosure.tsx` renders `.disclosure` with a `.panelclip` child and animates `grid-template-rows` between `0fr` and `1fr` over the shared phone rise of 240 milliseconds. A closed disclosure is `inert`. The component marks an open or close change as animating and clears that flag when the `grid-template-rows` transition ends, because a suppressed transition fires no event. With reduced motion the flag clears at once and the panel takes its final height. `disclosure.css` releases the clip of a settled open panel so its content can overflow.

## The phone sheet

`PhoneSheet` in `PhoneSheet.tsx` renders one bottom sheet above the phone tab bar through a portal into `document.body`, so the fixed surface is independent of the tab pane's transform. Nothing renders while the sheet is closed.

The sheet carries a scrim that closes it on a press and a `.phone-sheet` section with `role="dialog"` and the title as its accessible name. Its header holds the title and the **Close** control. The sheet owns one document Escape listener and closes unless a nested layer handled the key first. `usePhoneTabsOnClose` restores the bottom bar, and `usePhoneSurfaceClosing` marks the body as closing for one 240-millisecond rise, so the notice stack makes room back in step.

`web/src/shared/phoneMotion.ts` holds the shared values: `PHONE_RISE_SECONDS` 0.24, `PHONE_RISE_EASE` as `cubic-bezier(0.22, 0.8, 0.2, 1)`, the closing class and its reader.

## Tab panes and their slide

`web/src/app/tabSlide.ts` holds the one horizontal slide. A `TabDirection` is `-1` or `1`. `tabSlideVariants(reducedMotion)` moves a pane from `travel * 100vw` to zero and out to `-travel * 100vw`, and `tabSlideTransition` runs it over 0.65 seconds with the shared ease. With reduced motion every variant is zero and the duration is zero.

`AnimatedTabPane` renders one `motion.section` with the `tab-pane` class. A pane that is not present also carries `exiting`, `aria-hidden` and `inert`, so it takes no input and is hidden from assistive technology while it moves. The component publishes `PaneSlideContext` as true while the pane is leaving or animating.

`web/src/app/paneSlide.ts` exports that context. A component that would animate its own arrival, position or meter holds that motion while the context is true, so nothing inside a travelling pane moves at its own speed. The Discover result row and meter, the structure node row, the structure drawer and the add-programme row are its consumers.

## Reduced motion

`useReducedMotion` in `web/src/shared/useReducedMotion.ts` reads `(prefers-reduced-motion: reduce)` through one module-local `MediaQueryList` shared by every caller, using `useSyncExternalStore`. Its server snapshot is false. `prefersReducedMotion()` answers the same query outside a component. A component that supplies a duration of zero with reduced motion reads this hook, and `theme.css` additionally removes every CSS animation, transition and smooth scroll under the same preference.

## Scrollbars

`scrollbar.css` defines `.thin-scrollbar`: an 18 px scrollbar, a 5 px inset, a transparent track, and a rounded accent thumb of at least 40 px on each axis. The thumb is drawn through the WebKit pseudo-elements, and the standard `scrollbar-width` and `scrollbar-color` apply only where those pseudo-elements are unavailable. A panel can set `--scrollbar-size` and `--scrollbar-inset` to fit its own padding.

`useScrollbarShift(scroll, active)` in `useScrollbarShift.ts` animates the width of a scroll container's first element child when a classic scrollbar takes or releases space. It starts the 180-millisecond transition only for that shift, applies a real panel resize at once, and throws `A scroll container holds no content element` when the container has no element child. `ProfilePanel` uses it on the profile list and `ProfileButton` on the profile menu while the menu is open.

## The brand mark

`BrandMark` in `BrandMark.tsx` renders the product name from the `course-explorer` wording entry. With the `site` prop it adds a slash and the `tuni` entry, which names the site instance. The app top bar passes `site`, and the documentation header renders the bare product mark.

## The course menu

`CourseMenu` in `web/src/shared/course/CourseMenu.tsx` renders one course action menu and its dialogs. It receives the course summary, the trigger element, the open state and its setter, an optional `onInteractionChange`, and a `structureSurface` flag for a card inside the structure of studies.

The menu is one Radix dropdown with `modal={false}` and the `.course-menu` class. Its trigger suppresses the pointer-down default, so a scroll gesture that starts on the card stays a scroll. The title entry shows the course code, its credits and its active or inactive state, then the full name. The actions are those of the [course menu](/docs/reference/glossary.md#browser-app), which [Shared course state](/docs/guides/README.md#shared-course-state) states, and **Open in Sisu** is an anchor to the official page.

The Unplaced studies action comes from the course state and the saved holder in `state.structure.courseHolders`: an unselected course offers **Add to Unplaced studies**, a selected course with no place offers **Remove from Unplaced studies**, and a placed course offers **Move to Unplaced studies** beside **Remove from {name}**. Each action shows its notice through `useNotice`.

The component owns three dialogs. `ComparisonReplaceDialog` appears when both comparison slots are full. `CompletedCourseDeselectDialog` appears for a completed course that would leave the selection. `ConfirmDialog` asks the move question outside the structure surface. Every dialog returns focus to the menu trigger, and the menu never restores focus after a pointer press on another card. The component also renders the action's `ErrorNotice`. `CourseMenu.test.ts` proves that a card outside Structure names its holder in the removal action, clears the placement, forgets the holder and shows the notice.

`CourseLookupBox` in the same folder is the shared substring picker. It holds the magnifier, the query field and the loading, error, empty and result states in one animated block. `ActivitySwitch` sits inside the control row above 680 px and in its own `.course-lookup-filters` row at 680 px and below. `CourseLookupBox.test.ts` proves both placements and that each control reports its change.

## Where a change belongs

- A help entry belongs in the `sections` of the owning `HelpTip` call site, and a link inside it belongs in `HelpLink`.
- A notice lifetime, a key rule or a placement rule belongs in `NoticeProvider` or `NoticeStack`.
- A tab slide value belongs in `tabSlide.ts`, and a phone rise value belongs in `phoneMotion.ts`.
- A panel's scrollbar appearance belongs in `scrollbar.css`, and its shift motion belongs in `useScrollbarShift`.
- A menu action belongs in `CourseMenu.tsx` and in the store action it calls.

| Test file | Covers |
|---|---|
| `web/src/shared/HelpTip.test.ts` | A heading link, a term link and a text link inside the open drawer |
| `web/src/shared/course/CourseMenu.test.ts` | A holder-named removal outside the structure surface, with the placement cleared, the holder forgotten and the notice shown |
| `web/src/shared/course/CourseLookupBox.test.ts` | The activity control inside the bar on desktop and below it at a phone width, and its reported change |
