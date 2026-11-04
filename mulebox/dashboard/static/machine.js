// The load boxes for the machine the dashboard runs on: CPU (history graph of the average,
// a meter per core), memory (meter and history) and disk (meters), plus Docker, the
// dashboard's own overhead and the viewer count. Current values are always text too.
// Nothing is drawn while the tab is hidden; the next sample after it returns redraws.

import { LineChart } from "./charts.js";
import { bytes, el, fill, meter } from "./format.js";

const WINDOW_S = 300;  // the server keeps 5 minutes of samples
const MAX_SAMPLES = 150;
const DISK_WARN = 90;

const percent = (v) => `${v.toFixed(0)}%`;

function graph(format, scale) {
  const canvas = el("canvas", { role: "img" });
  const tip = el("div", { class: "tip", hidden: "" });
  const chart = new LineChart(canvas, tip, { windowS: WINDOW_S, format });
  const note = el("span", { class: "scale", text: scale });
  return { chart, canvas, box: el("div", { class: "graph" }, canvas, note, tip) };
}

function stat(label) {
  const value = el("span", { class: "value num", text: "-" });
  return { value, node: el("p", { class: "stat" }, el("span", { class: "muted", text: label }), value) };
}

export class Machine {
  constructor(boxes) {
    this.boxes = boxes;
    this.samples = [];
    this.cores = [];
    this.coreGrid = el("div", { class: "cores" });
    this.cpuNote = el("span", { text: "waiting for the first sample" });
    this.cpu = graph(percent, "last 5 min, 0 to 100%");
    this.memNote = el("span", { text: "-" });
    this.memMeter = meter({ "aria-label": "Memory used" });
    this.memory = graph(bytes, "last 5 min, 0 to total");
    this.disks = el("div", {});
    this.docker = stat("docker containers");
    this.self = stat("overhead");
    this.viewers = stat("viewers");
    fill(boxes.cpu, "CPU", this.cpuNote, this.cpu.box, this.coreGrid);
    fill(boxes.mem, "Memory", this.memNote, this.memMeter.node, this.memory.box);
    fill(boxes.disk, "Disk", null, this.disks,
         el("div", { class: "facts-line" }, this.docker.node, this.self.node, this.viewers.node));
    document.addEventListener("visibilitychange", () => { if (!document.hidden) this.render(); });
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
    if (!last || document.hidden) return;
    this.renderCores(last);
    const memory = last.memory;
    this.memNote.textContent = memory ? `${bytes(memory.used)} of ${bytes(memory.total)}`
      : "not available";
    this.memMeter.set(memory ? memory.used / memory.total : 0);
    this.memMeter.node.setAttribute("aria-label", `Memory used: ${this.memNote.textContent}`);
    this.memory.chart.update(this.samples.map((s) => ({ t: s.t, v: s.memory?.used ?? null })),
                             memory?.total);
    this.memory.canvas.setAttribute("aria-label", `Memory used, last 5 minutes`);
    this.renderDisks(last.disk ?? []);
    this.docker.value.textContent = last.docker ?? "not available";
    const own = last.self;
    this.self.value.textContent = own ? `${own.cpu.toFixed(1)}% cpu, ${bytes(own.rss)}` : "-";
    this.viewers.value.textContent = String(last.viewers ?? "-");
  }

  renderCores(last) {
    const cpu = last.cpu ?? this.samples.findLast((s) => s.cpu)?.cpu;
    if (!cpu) return;
    const average = (s) => (s.cpu ? s.cpu.reduce((a, b) => a + b, 0) / s.cpu.length : null);
    const now = average(last);
    this.cpuNote.textContent = `${cpu.length} cores, average ${percent(now)}`;
    this.cpu.chart.update(this.samples.map((s) => ({ t: s.t, v: average(s) })), 100);
    this.cpu.canvas.setAttribute("aria-label", `Average CPU, last 5 minutes: ${percent(now)}`);
    while (this.cores.length < cpu.length) {
      const index = this.cores.length;
      const bar = meter({ "aria-label": `Core ${index}` });
      const value = el("span", { class: "value num", text: "-" });
      this.coreGrid.append(el("div", { class: "core" },
        el("span", { class: "label", text: `c${index}` }), bar.node, value));
      this.cores.push({ bar, value });
    }
    this.cores.forEach((core, index) => {
      const share = cpu[index];
      core.value.textContent = share === undefined ? "-" : percent(share);
      core.bar.set((share ?? 0) / 100);
      core.bar.node.setAttribute("aria-label", `Core ${index}: ${core.value.textContent}`);
    });
  }

  renderDisks(disks) {
    this.disks.replaceChildren(...disks.map((disk) => {
      const used = disk.total ? disk.used / disk.total : 0;
      const low = used * 100 >= DISK_WARN;
      const bar = meter({ "aria-label": `Disk ${disk.roots.join(", ")}` });
      bar.set(used);
      if (low) bar.node.dataset.low = "1";
      return el("div", { class: "disk-row" },
        el("span", { class: "roots", text: disk.roots.join(", ") }),
        el("div", { class: "row" }, bar.node,
           el("span", { class: "value num",
                        text: `${bytes(disk.used)} of ${bytes(disk.total)}${low ? ", low" : ""}` })));
    }));
    if (!disks.length) this.disks.append(el("p", { class: "empty", text: "Not measured yet." }));
  }
}
