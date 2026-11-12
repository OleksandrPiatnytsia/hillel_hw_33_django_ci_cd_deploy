// Light / dark theme of the site (Bootstrap 5.3 colour modes).
//
// Loaded in <head> WITHOUT defer: the first part runs before the page is
// drawn and puts data-bs-theme on <html>, so a dark page never flashes white.
// The second part waits for the page and wires the navbar switcher.
//
// The choice is kept in localStorage (this browser only, guests too, no
// request to the server): "light", "dark" or "auto" (= the theme of the
// operating system, also the default when nothing is saved).
(() => {
  const STORAGE_KEY = "theme";
  const CHOICES = ["light", "dark", "auto"];
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function storedChoice() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return CHOICES.includes(value) ? value : "auto";
    } catch {
      // localStorage can be blocked (privacy settings): just follow the system
      return "auto";
    }
  }

  function apply(choice) {
    const theme = choice === "auto" ? (systemDark.matches ? "dark" : "light") : choice;
    document.documentElement.setAttribute("data-bs-theme", theme);
  }

  // 1. Right now, before the page is drawn
  apply(storedChoice());

  // "Auto": follow the system when it switches (e.g. at sunset)
  systemDark.addEventListener("change", () => {
    if (storedChoice() === "auto") apply("auto");
  });

  // 2. The switcher in the navbar: buttons with data-theme-value
  function showChoice(switcher, choice) {
    for (const button of switcher.querySelectorAll("[data-theme-value]")) {
      const current = button.dataset.themeValue === choice;
      button.classList.toggle("active", current);
      button.setAttribute("aria-pressed", current);
      // The icon of the chosen item goes to the toggle in the navbar
      if (current) {
        switcher.querySelector("[data-theme-icon]").textContent = button.dataset.themeIcon;
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const switcher = document.querySelector("[data-theme-switcher]");
    if (!switcher) return;
    showChoice(switcher, storedChoice());

    switcher.addEventListener("click", (event) => {
      const button = event.target.closest("[data-theme-value]");
      if (!button) return;
      const choice = button.dataset.themeValue;
      try {
        localStorage.setItem(STORAGE_KEY, choice);
      } catch {
        // Not saved: the theme still changes until the next page
      }
      apply(choice);
      showChoice(switcher, choice);
    });
  });
})();
