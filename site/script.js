// Optional mobile navigation only. No storage, analytics, network requests or tracking.
(() => {
  "use strict";
  const button = document.querySelector(".menu-button");
  const navigation = document.querySelector("#site-nav");
  if (!button || !navigation) return;

  const closeMenu = () => {
    navigation.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
  };

  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    navigation.classList.toggle("is-open", !expanded);
    button.setAttribute("aria-expanded", String(!expanded));
  });

  navigation.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("a")) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
      closeMenu();
      button.focus();
    }
  });
})();
