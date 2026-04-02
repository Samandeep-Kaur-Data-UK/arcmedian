const revealElements = document.querySelectorAll(".reveal");
const animatedCharts = document.querySelectorAll("[data-bars]");

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      entry.target.classList.add("visible");
      revealObserver.unobserve(entry.target);
    });
  },
  {
    threshold: 0.18,
  },
);

revealElements.forEach((element) => {
  revealObserver.observe(element);
});

const chartObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      entry.target.classList.add("in-view");
      chartObserver.unobserve(entry.target);
    });
  },
  {
    threshold: 0.35,
  },
);

animatedCharts.forEach((chart) => {
  chartObserver.observe(chart);
});

const year = document.getElementById("year");
if (year) {
  year.textContent = new Date().getFullYear();
}
