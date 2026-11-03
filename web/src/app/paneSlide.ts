/** Whether the pane around a component is sliding with its tab. */
import { createContext } from "react";

/**
 * True while the surrounding tab pane travels sideways. Content inside a sliding pane rides with
 * it, so a component that would animate its own arrival or position holds still until it stops.
 */
export const PaneSlideContext = createContext(false);
