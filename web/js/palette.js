import { h, clear } from "./util.js";

/** Ctrl/Cmd+K command palette. `getCommands()` returns [{label, hint, run}] fresh each time it opens. */
export function initPalette(getCommands) {
  const dlg = document.getElementById("palette");
  const input = document.getElementById("palette-input");
  const list = document.getElementById("palette-list");
  let shown = [], sel = 0;

  function paint() {
    const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    shown = getCommands().filter((c) => terms.every((t) => `${c.label} ${c.hint || ""}`.toLowerCase().includes(t)));
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    clear(list);
    if (!shown.length) { list.append(h("li", { class: "palette-empty", role: "presentation", text: "No match" })); input.removeAttribute("aria-activedescendant"); return; }
    shown.forEach((c, i) => list.append(h("li", { id: `cmd-${i}`, role: "option", "aria-selected": String(i === sel),
      on: { click: () => run(c), pointermove: () => { if (sel !== i) { sel = i; mark(); } } } },
    h("span", { text: c.label }), h("span", { class: "hint", text: c.hint || "" }))));
    input.setAttribute("aria-activedescendant", `cmd-${sel}`);
  }
  function mark() {
    [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === sel)));
    input.setAttribute("aria-activedescendant", `cmd-${sel}`);
    list.children[sel]?.scrollIntoView({ block: "nearest" });
  }
  function run(c) { dlg.close(); c.run(); }
  function open() { if (dlg.open) return; sel = 0; input.value = ""; dlg.showModal(); paint(); input.focus(); }

  input.addEventListener("input", () => { sel = 0; paint(); });
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); mark(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
    else if (ev.key === "Enter" && shown[sel]) { ev.preventDefault(); run(shown[sel]); }
  });
  dlg.addEventListener("click", (ev) => { if (ev.target === dlg) dlg.close(); });
  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); dlg.open ? dlg.close() : open(); }
  });
  document.getElementById("open-palette").addEventListener("click", open);
  return { open };
}
