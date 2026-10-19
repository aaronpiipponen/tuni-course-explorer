/**
 * Browser bootstrap: mount the console application over the page root.
 */
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles/admin.css";

createRoot(document.getElementById("root")!).render(<App />);
