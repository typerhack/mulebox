import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { startLook } from "./lib/prefs";

startLook();
const root = document.getElementById("root");
if (root) createRoot(root).render(<StrictMode><App /></StrictMode>);
