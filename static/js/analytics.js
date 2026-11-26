// The revenue chart of /analytics/ (analytics/templates/analytics/sales.html).
//
// Progressive enhancement: the page has the table of the days already.
// Only when Chart.js has loaded (from the CDN) this script shows the chart
// and folds the table; without JavaScript or without the CDN the table
// stays open and nothing is lost.
//
// The data: {{ chart|json_script:"revenue-chart-data" }}, built by
// SalesAnalyticsView.chart(): labels, revenue (strings), orders, the names
// of the two series in the language of the page.
(function () {
  "use strict";

  const dataElement = document.getElementById("revenue-chart-data");
  const box = document.querySelector("[data-chart-box]");
  if (!dataElement || !box || typeof window.Chart === "undefined") {
    return;
  }
  const data = JSON.parse(dataElement.textContent);
  if (!data) {
    return;
  }

  // The colors of the Bootstrap theme (light and dark)
  const style = getComputedStyle(document.documentElement);
  const primary = style.getPropertyValue("--bs-primary").trim() || "#0d6efd";
  const secondary = style.getPropertyValue("--bs-secondary-color").trim() || "#6c757d";
  const grid = style.getPropertyValue("--bs-border-color").trim() || "#dee2e6";

  box.classList.remove("d-none");
  const table = document.querySelector("[data-chart-table]");
  if (table) {
    table.open = false;
  }

  new window.Chart(box.querySelector("canvas"), {
    data: {
      labels: data.labels,
      datasets: [
        {
          type: "line",
          label: data.revenue_label,
          data: data.revenue.map(Number),
          borderColor: primary,
          backgroundColor: primary,
          tension: 0.25,
          yAxisID: "revenue",
        },
        {
          type: "bar",
          label: data.orders_label,
          data: data.orders,
          backgroundColor: grid,
          yAxisID: "orders",
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: secondary }, grid: { color: grid } },
        revenue: {
          position: "left",
          beginAtZero: true,
          ticks: { color: secondary },
          grid: { color: grid },
        },
        orders: {
          position: "right",
          beginAtZero: true,
          ticks: { color: secondary, precision: 0 },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: { legend: { labels: { color: secondary } } },
    },
  });
})();
