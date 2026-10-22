"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  function fallback() {
    byId("visual-error").hidden = false;
    byId("text-alternative").open = true;
    byId("evidence-panel").open = true;
    document.querySelectorAll("[data-evidence]").forEach((element) => { element.hidden = false; });
    document.querySelectorAll(".phase-controls button, .navigation button, #copy-step, #show-source, #component-picker")
      .forEach((element) => { element.disabled = true; });
  }
  try {
    const data = JSON.parse(byId("visual-data").textContent);
    const { spec, catalog } = data;
    let phase = "inference";
    let position = 0;
    let selectedNode = null;
    const phaseSteps = () => spec.steps.filter((step) => step.phase === phase);
    const visibleNodes = () => spec.nodes.filter((node) => node.phase === "both" || node.phase === phase);
    const number = (value) => new Intl.NumberFormat("ar-EG").format(value);

    function putRuns(element, runs) {
      element.replaceChildren();
      for (const run of runs) {
        const span = document.createElement("bdi");
        span.dir = run.direction;
        if (run.direction !== "auto") span.lang = run.direction === "rtl" ? "ar-EG" : "en";
        span.textContent = run.text;
        element.append(span);
      }
    }

    function renderState() {
      const steps = phaseSteps();
      const step = steps[position];
      byId("step-heading").textContent = step.heading_ar;
      byId("step-counter").textContent = `الخطوة ${number(position + 1)} من ${number(steps.length)}`;
      putRuns(byId("step-body"), step.body);
      byId("previous").disabled = position === 0;
      byId("next").disabled = position === steps.length - 1;
      const list = byId("step-list");
      if (list.dataset.phase !== phase) {
        list.replaceChildren();
        list.dataset.phase = phase;
        steps.forEach((item, index) => {
          const li = document.createElement("li");
          const button = document.createElement("button");
          button.textContent = item.heading_ar;
          button.addEventListener("click", () => { position = index; selectedNode = null; render(); });
          li.append(button); list.append(li);
        });
      }
      list.querySelectorAll("button").forEach((button, index) => {
        if (position === index) button.setAttribute("aria-current", "step");
        else button.removeAttribute("aria-current");
      });
      document.querySelectorAll("[data-phase]").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.phase === phase));
      });
      for (const candidate of ["inference", "training"]) byId(`figure-${candidate}`).hidden = candidate !== phase;
      const svg = byId(`figure-${phase}`).querySelector("svg");
      if (svg) {
        svg.querySelectorAll("[data-node]").forEach((element) => {
          element.classList.toggle("is-highlighted", step.node_ids.includes(element.dataset.node));
          element.classList.toggle("is-selected", selectedNode === element.dataset.node);
          element.setAttribute("aria-pressed", String(selectedNode === element.dataset.node));
        });
        svg.querySelectorAll("[data-edge]").forEach((element) => {
          element.classList.toggle("is-highlighted", step.edge_ids.includes(element.dataset.edge));
        });
      } else {
        byId("visual-error").textContent = "الرسم مش متاح. تقدر تكمّل التنقل بين الخطوات وفحص المكوّنات والدليل من النص.";
        byId("visual-error").hidden = false;
        byId("text-alternative").open = true;
      }
      const picker = byId("component-picker");
      picker.replaceChildren(new Option("اختار مكوّن من الرسم", ""));
      for (const node of visibleNodes()) picker.append(new Option(node.label_ar, node.id));
      picker.value = selectedNode || "";
      const node = visibleNodes().find((item) => item.id === selectedNode);
      if (node) putRuns(byId("component-details"), node.details);
      else byId("component-details").textContent = "اضغط على مكوّن أو اختاره من القائمة عشان تعرف دوره ودليله.";
      const factIds = new Set([...step.fact_ids, ...(node ? node.fact_ids : [])]);
      const evidenceIds = new Set(catalog.facts.filter((fact) => factIds.has(fact.id)).flatMap((fact) => fact.evidence_ids));
      document.querySelectorAll("[data-evidence]").forEach((element) => {
        element.hidden = !evidenceIds.has(element.dataset.evidence);
      });
      byId("evidence-count").textContent = `${number(evidenceIds.size)} مراجع قصيرة للمصدر`;
      byId("status").textContent = "";
    }

    function render() {
      try { renderState(); } catch { fallback(); }
    }

    function selectNode(id) {
      if (!visibleNodes().some((node) => node.id === id)) return;
      selectedNode = id;
      render();
    }

    byId("previous").addEventListener("click", () => { if (position > 0) { position--; selectedNode = null; render(); } });
    byId("next").addEventListener("click", () => { if (position < phaseSteps().length - 1) { position++; selectedNode = null; render(); } });
    document.querySelectorAll("[data-phase]").forEach((button) => {
      button.addEventListener("click", () => { phase = button.dataset.phase; position = 0; selectedNode = null; render(); });
    });
    byId("component-picker").addEventListener("change", (event) => selectNode(event.target.value));
    document.querySelectorAll(".diagram-scroll").forEach((container) => {
      container.addEventListener("click", (event) => {
        const node = event.target.closest("[data-node]");
        if (node) selectNode(node.dataset.node);
      });
      container.addEventListener("keydown", (event) => {
        const node = event.target.closest("[data-node]");
        if (node && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault(); selectNode(node.dataset.node);
        }
      });
    });
    byId("show-source").addEventListener("click", () => {
      byId("evidence-panel").open = true;
      byId("evidence-summary").focus();
      byId("evidence-panel").scrollIntoView({ block: "nearest", behavior: "instant" });
    });
    byId("copy-step").addEventListener("click", async () => {
      const text = phaseSteps()[position].body.map((run) => run.text).join("");
      try {
        await navigator.clipboard.writeText(text);
        byId("status").textContent = "اتنسخ الشرح بالنص الأصلي من غير علامات اتجاه مخفية.";
      } catch {
        const field = byId("copy-field");
        field.hidden = false; field.value = text; field.focus(); field.select();
        byId("status").textContent = "النص متحدد؛ انسخه بالطريقة المعتادة على جهازك.";
      }
    });
    render();
  } catch { fallback(); }
})();
