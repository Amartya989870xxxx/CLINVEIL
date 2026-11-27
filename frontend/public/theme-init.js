// Applies the saved or system theme before first paint (avoids a flash). No storage of anything else.
(function () {
  try {
    var pref = localStorage.getItem("clinveil.theme") || "system";
    var dark = pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  } catch (e) {
    document.documentElement.setAttribute("data-theme", "light");
  }
})();
