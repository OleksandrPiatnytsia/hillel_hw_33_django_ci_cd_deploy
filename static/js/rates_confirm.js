// The "NBU rates" page (currencies/rates.html): next to every field a badge
// says how it will be saved. The same rule as the server
// (currencies.services.save_confirmed_rates): the NBU number -> "NBU",
// another number -> "Manual", an empty field -> not saved ("—").
// Only a hint: the server decides by itself, without this script too.
(() => {
  const form = document.querySelector("form[data-rates-form]");
  if (!form) return;

  for (const field of form.querySelectorAll("input[data-nbu]")) {
    const badge = field.parentElement.querySelector("[data-source-badge]");
    const paint = () => {
      const value = field.value.trim().replace(",", ".");
      let label = badge.dataset.labelManual;
      let manual = true;
      if (value === "") {
        label = "—";
        manual = false;
      } else if (field.dataset.nbu !== "" && Number(value) === Number(field.dataset.nbu)) {
        // As numbers: "45.42740" is the NBU's 45.4274
        label = badge.dataset.labelNbu;
        manual = false;
      }
      badge.textContent = label;
      badge.classList.toggle("text-bg-warning", manual);
      badge.classList.toggle("text-bg-secondary", !manual);
    };
    field.addEventListener("input", paint);
    paint();
  }
})();
