import { mount } from "svelte";
import "./app.css";
import "./live.css";
import App from "./App.svelte";
import LiveApp from "./LiveApp.svelte";
import { detectMode } from "./lib/api";

const target = document.getElementById("app");
if (!target) throw new Error("The app root element is missing.");

// Served by the local companion → live Gmail UI. Served by Vite alone → synthetic demo.
detectMode().then((mode) => {
  if (mode === "demo") mount(App, { target });
  else mount(LiveApp, { target, props: { paired: mode === "live" } });
});
