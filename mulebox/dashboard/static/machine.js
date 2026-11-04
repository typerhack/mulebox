// The machine panel: CPU per core, memory, disk, Docker and the dashboard's own overhead.
// Current values are always written as text beside the graphs.

import { LineChart } from "./charts.js";
import { bytes, el } from "./format.js";

const WINDOW_S = 300;  // the server keeps 5 minutes of samples
const MAX_SAMPLES = 150;
const DISK_WARN = 90;

const percent = (v) => `${v.toFixed(0)}%`;

function plot(format) {
  const canvas = el("canvas", { role: "img" });
  const tip = el("div", { class: "tip", hidden: "" });
  const chart = new LineChart(canvas, tip, { windowS: WINDOW_S, format });
  return { chart, canvas, box: el("div", { class: "plot" }, canvas, tip) };
}

function stat(label) {
  const value = el("dd", { text: "-" });
  return { value, nodes: [el("dt", { text: label }), value] };
}

export class Machine {
  constructor(root) {
    this.samples = [];
    this.cores = [];
    this.coreGrid = el("div", { class: "cores" });
    this.cpuNote = el("p", { class: "muted", text: "Waiting for the first sample." });
    this.memoryText = el("span", { class: "value", text: "-" });
    this.memory = plot(bytes);
    this.disks = el("div", {});
    this.docker = stat("Docker containers");
    this.self = stat("Dashboard overhead");
    this.viewers = stat("Viewers");
    root.replaceChildren(
      el("h2", { text: "CPU per core" }), this.cpuNote, this.coreGrid,
      el("h2", {}, "Memory ", this.memoryText), this.memory.box,
      el("p", { class: "muted scale", text: "Last 5 minutes, 0 to total" }),
      el("h2", { text: "Disk" }), this.disks,
      el("dl", { class: "facts" }, ...this.docker.nodes, ...this.self.nodes,
         ...this.viewers.nodes));
  }

  reset(history) {
    this.samples = history.slice(-MAX_SAMPLES);
    this.render();
  }

  add(sample) {
    this.samples.push(sample);
    if (this.samples.length > MAX_SAMPLES) this.samples.shift();
    this.render();
  }

  render() {
    const last = this.samples.at(-1);
    if (!last) return;
    this.renderCores(last);
    const memory = last.memory;
    this.memoryText.textContent = memory ? `${bytes(memory.used)} of ${bytes(memory.total)}`
      : "not available";
    this.memory.chart.update(this.samples.map((s) => ({ t: s.t, v: s.memory?.used ?? null })),
                             memory?.total);
    this.memory.canvas.setAttribute("aria-label", `Memory used: ${this.memoryText.textContent}`);
    this.renderDisks(last.disk ?? []);
    this.docker.value.textContent = last.docker ?? "not available";
    const own = last.self;
    this.self.value.textContent = own ? `${own.cpu.toFixed(1)}% CPU, ${bytes(own.rss)}` : "-";
    this.viewers.value.textContent = String(last.viewers ?? "-");
  }

  renderCores(last) {
    const cpu = last.cpu ?? this.samples.findLast((s) => s.cpu)?.cpu;
    if (!cpu) return;
    this.cpuNote.textContent = "Last 5 minutes, 0 to 100%";
    while (this.cores.length < cpu.length) {
      const index = this.cores.length;
      const parts = plot(percent);
      const value = el("span", { class: "value", text: "-" });
      this.coreGrid.append(el("div", { class: "core" },
        el("div", { class: "core-head" }, el("span", { text: `Core ${index}` }), value),
        parts.box));
      this.cores.push({ ...parts, value });
    }
    this.cores.forEach((core, index) => {
      const now = cpu[index];
      core.value.textContent = now === undefined ? "-" : percent(now);
      core.canvas.setAttribute("aria-label", `Core ${index}: ${core.value.textContent}`);
      core.chart.update(this.samples.map((s) => ({ t: s.t, v: s.cpu?.[index] ?? null })), 100);
    });
  }

  renderDisks(disks) {
    this.disks.replaceChildren(...disks.map((disk) => {
      const used = disk.total ? (disk.used / disk.total) * 100 : 0;
      const bar = el("div", { class: "fill" });
      bar.style.width = `${used.toFixed(1)}%`;
      const low = used >= DISK_WARN ? ", low on space" : "";
      return el("div", { class: "disk" },
        el("p", {}, el("span", { text: disk.roots.join(", ") }),
           el("span", { class: "value",
                        text: `${bytes(disk.used)} of ${bytes(disk.total)}${low}` })),
        el("div", { class: "meter", "data-low": low ? "1" : null }, bar));
    }));
    if (!disks.length) this.disks.append(el("p", { class: "muted", text: "Not measured yet." }));
  }
}
