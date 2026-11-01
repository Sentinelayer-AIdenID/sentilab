// SentiLab Package view: the one way a door temperature becomes text (CAD/3D freeze PL-2). Pure; the node tests run it.
// A value is formatted only together with its label, and only a label that IS one of the shared rule's frozen LABELS
// objects (temperature-label.mjs: identity, not shape) is accepted. Labels never come from the data: the caller resolves
// them with labelFor() from a verified evaluator identity (PL-6), and a value with no verified identity is labelled by
// labelFor(undefined), which is "unvalidated". The number is rounded for display only; comparisons use the value given.
import { LABELS } from "../../temperature-label.mjs";

const SHARED = new Set(Object.values(LABELS));

// -> { text, qualifier, title, state, notice }, or a throw for a label that is not shared or a value that is not finite.
export function formatTemp(valueC, label, { digits = 1 } = {}) {
  if (!SHARED.has(label)) throw new TypeError("formatTemp: the label must be one of temperature-label.mjs LABELS");
  if (typeof valueC !== "number" || !Number.isFinite(valueC)) throw new TypeError("formatTemp: not a finite temperature");
  const f = 10 ** digits;
  const text = `${(Math.round(valueC * f + Math.sign(valueC) * 1e-7) / f).toFixed(digits)} °C`;
  return Object.freeze({ text, qualifier: label.short, title: label.title, state: label.state, notice: label.notice });
}

// The value and its qualifier in ONE element: <span class="t s-<state>" title>115.94 °C <em class="q">unvalidated</em></span>.
// h: the page's element helper (tag, props, ...children).
export function tempNode(h, valueC, label, opts = {}) {
  const t = formatTemp(valueC, label, opts);
  return h("span", { class: `t s-${t.state}`, title: t.title }, t.text, " ", h("em", { class: "q" }, t.qualifier));
}
