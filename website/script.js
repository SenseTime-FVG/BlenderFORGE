(() => {
  "use strict";
  const data = window.BLENDERFORGE_RESULTS.tasks;
  const groupNames = {
    reference: "No-op reference",
    proprietary: "Proprietary Models",
    open: "Open-weight Models",
    ours: "Fine-tuned on BlenderFORGE Datasets",
  };
  const state = {
    task: "placement",
    sort: null,
    direction: "asc",
    query: "",
    group: "all",
  };
  const table = document.querySelector("#leaderboard");
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );
  function rowsForView() {
    return data[state.task].rows
      .filter((row) => {
        const group =
          state.group === "all" ||
          row.group === state.group ||
          (state.group === "open" && ["open", "ours"].includes(row.group));
        return group && row.model.toLowerCase().includes(state.query);
      })
      .sort((a, b) => {
        if (!state.sort) return 0;
        if (a.group === "reference") return 1;
        if (b.group === "reference") return -1;
        const left = state.sort === "model" ? a.model : a.values[state.sort];
        const right = state.sort === "model" ? b.model : b.values[state.sort];
        if (left == null && right == null)
          return a.model.localeCompare(b.model);
        if (left == null) return 1;
        if (right == null) return -1;
        const difference =
          typeof left === "string" ? left.localeCompare(right) : left - right;
        return (
          (state.direction === "asc" ? difference : -difference) ||
          a.model.localeCompare(b.model)
        );
      });
  }
  function renderLeaderboard() {
    const task = data[state.task];
    table.querySelector("caption").innerHTML =
      `<strong>${task.label}.</strong> BlenderFORGE test results.`;
    const header = (metric, model = false) => {
      const selected = metric.key === state.sort;
      const arrow = model
        ? ""
        : metric.direction === "asc"
          ? "&darr;"
          : "&uarr;";
      return `<th scope="col" ${model ? 'rowspan="2" class="model-column"' : ""} aria-sort="${selected ? (state.direction === "asc" ? "ascending" : "descending") : "none"}"><button data-sort="${metric.key}" type="button">${metric.label} ${arrow}</button></th>`;
    };
    const stateHeading =
      state.task === "placement"
        ? "Normalized P-CD"
        : "Normalized ShapeKey L<sub>1</sub>";
    table.querySelector("thead").innerHTML =
      "<tr>" +
      header({ key: "model", label: "Model" }, true) +
      '<th class="metric-group" scope="colgroup" colspan="2">Perceptual</th>' +
      (task.metrics.length > 2
        ? `<th class="metric-group" scope="colgroup" colspan="4">${stateHeading}</th>`
        : "") +
      "</tr><tr>" +
      task.metrics.map((metric) => header(metric)).join("") +
      "</tr>";
    const emphasis = {};
    for (const group of ["proprietary", "open"]) {
      const pool = task.rows.filter((row) =>
        group === "proprietary"
          ? row.group === group
          : ["open", "ours"].includes(row.group),
      );
      emphasis[group] = Object.fromEntries(
        task.metrics.map((metric) => {
          const scores = [
            ...new Set(
              pool.map((row) => row.values[metric.key]).filter(Number.isFinite),
            ),
          ].sort((a, b) => (metric.direction === "asc" ? a - b : b - a));
          return [metric.key, scores.slice(0, 2)];
        }),
      );
    }
    const rows = rowsForView();
    let previousGroup = null;
    const body = [];
    for (const row of rows) {
      if (
        !state.sort &&
        row.group !== "reference" &&
        row.group !== previousGroup
      ) {
        body.push(
          `<tr class="group-heading"><th scope="rowgroup" colspan="${task.metrics.length + 1}">${groupNames[row.group]}</th></tr>`,
        );
      }
      previousGroup = row.group;
      const model =
        row.group === "ours"
          ? escape(row.model).replace(" · BlenderFORGE", "<br>(BlenderFORGE)")
          : escape(row.model);
      body.push(
        `<tr class="${row.group === "ours" ? "model-ours" : row.group}" data-model="${escape(row.model)}"><td class="model-cell"><span class="table-model" title="${row.source || "Table 1"}">${model}</span></td>${task.metrics
          .map((metric) => {
            const value = row.values[metric.key];
            if (!Number.isFinite(value))
              return '<td class="unreported" aria-label="Not reported">&mdash;</td>';
            const scores =
              row.group === "reference"
                ? []
                : emphasis[
                    row.group === "proprietary" ? "proprietary" : "open"
                  ][metric.key];
            const style =
              value === scores[0]
                ? "metric-strong"
                : value === scores[1]
                  ? "metric-second"
                  : "";
            return `<td class="${style}">${value.toFixed(metric.digits)}</td>`;
          })
          .join("")}</tr>`,
      );
    }
    table.querySelector("tbody").innerHTML =
      body.join("") ||
      `<tr><td colspan="${task.metrics.length + 1}" class="empty-results">No models match your search.</td></tr>`;
    document.querySelector("#result-count").textContent =
      `${rows.filter((row) => row.group !== "reference").length} models${rows.some((row) => row.group === "reference") ? " + no-op reference" : ""}`;
    document.querySelector("#metric-note").textContent =
      `PL and N-CLIP: ×10⁻³ (↓).${task.metrics.length > 2 ? " SR: % (↑); Med.: median normalized discrepancy (↓)." : ""} Bold and underline denote the best and second-best distinct scores within proprietary models and the combined open-weight/trained models.`;
  }
  function selectTab(button, selector) {
    document.querySelectorAll(selector).forEach((tab) => {
      const active = tab === button;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
  }
  document.querySelectorAll("[data-task]").forEach((button) =>
    button.addEventListener("click", () => {
      selectTab(button, "[data-task]");
      state.task = button.dataset.task;
      state.sort = null;
      state.direction = "asc";
      document
        .querySelector("#leaderboard-panel")
        .setAttribute("aria-labelledby", button.id);
      renderLeaderboard();
    }),
  );
  document.querySelector("#reset-order").addEventListener("click", () => {
    state.sort = null;
    renderLeaderboard();
  });
  table.querySelector("thead").addEventListener("click", (event) => {
    const button = event.target.closest("[data-sort]");
    if (!button) return;
    const key = button.dataset.sort;
    state.direction =
      state.sort === key
        ? state.direction === "asc"
          ? "desc"
          : "asc"
        : key === "model"
          ? "asc"
          : data[state.task].metrics.find((m) => m.key === key).direction;
    state.sort = key;
    renderLeaderboard();
    table.querySelector(`[data-sort="${key}"]`).focus({ preventScroll: true });
  });
  document.querySelector("#model-search").addEventListener("input", (event) => {
    state.query = event.target.value.toLowerCase().trim();
    renderLeaderboard();
  });
  document.querySelector("#model-group").addEventListener("change", (event) => {
    state.group = event.target.value;
    renderLeaderboard();
  });
  document.querySelector("#export-csv").addEventListener("click", () => {
    const task = data[state.task];
    const quote = (value) => '"' + String(value).replaceAll('"', '""') + '"';
    const lines = [
      [
        "Model",
        "Group",
        "Source",
        ...task.metrics.map(
          (m) => m.label + (m.unit ? " (" + m.unit + ")" : ""),
        ),
      ],
      ...rowsForView().map((row) => [
        row.model,
        groupNames[row.group],
        row.source || "Table 1",
        ...task.metrics.map((m) =>
          Number.isFinite(row.values[m.key])
            ? row.values[m.key].toFixed(m.digits)
            : "",
        ),
      ]),
    ];
    const url = URL.createObjectURL(
      new Blob(
        ["\ufeff" + lines.map((row) => row.map(quote).join(",")).join("\r\n")],
        { type: "text/csv;charset=utf-8" },
      ),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `blenderforge-results-${state.task}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.querySelectorAll("[role=tablist]").forEach((list) =>
    list.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
        return;
      const tabs = [...list.querySelectorAll("[role=tab]")];
      const current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      event.preventDefault();
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? tabs.length - 1
            : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
              tabs.length;
      tabs[next].focus();
      tabs[next].click();
    }),
  );
  const dialog = document.querySelector("#video-dialog");
  const expanded = document.querySelector("#expanded-video");
  let sourceVideo = null;
  const play = (video) =>
    video.play().catch((error) => {
      if (!["NotAllowedError", "AbortError"].includes(error.name))
        console.error(error);
    });
  document.querySelectorAll("[data-expand]").forEach((button) => {
    button.addEventListener("click", () => {
      sourceVideo = document.getElementById(button.dataset.expand);
      const position = sourceVideo.currentTime;
      sourceVideo.pause();
      document.querySelector("#expanded-video-title").textContent =
        sourceVideo.getAttribute("aria-label");
      expanded.src =
        sourceVideo.currentSrc || sourceVideo.querySelector("source").src;
      expanded.poster = sourceVideo.poster;
      expanded.muted = sourceVideo.muted;
      expanded.volume = sourceVideo.volume;
      expanded.currentTime = position;
      dialog.showModal();
      play(expanded);
    });
  });
  document
    .querySelector("#close-video")
    .addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (
        event.clientX < box.left ||
        event.clientX > box.right ||
        event.clientY < box.top ||
        event.clientY > box.bottom
      )
        dialog.close();
    }
  });
  dialog.addEventListener("close", () => {
    expanded.pause();
    if (sourceVideo && Number.isFinite(expanded.currentTime))
      sourceVideo.currentTime = expanded.currentTime;
    expanded.removeAttribute("src");
    expanded.load();
    sourceVideo = null;
  });
  document.querySelector("#fullscreen-video").addEventListener("click", () => {
    if (expanded.requestFullscreen)
      expanded.requestFullscreen().catch((error) => console.error(error));
    else if (expanded.webkitEnterFullscreen) expanded.webkitEnterFullscreen();
  });
  document.querySelectorAll("video").forEach((video) => {
    video.addEventListener("play", () => {
      document.querySelectorAll("video").forEach((other) => {
        if (other !== video) other.pause();
      });
    });
  });
  renderLeaderboard();
})();
