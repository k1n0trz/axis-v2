(function () {
  function enhancePasswordField(input) {
    if (!input || input.dataset.axisPasswordToggle === "1") return;
    input.dataset.axisPasswordToggle = "1";

    var wrapper = document.createElement("span");
    wrapper.className = "axis-password-toggle-wrap";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "axis-password-toggle";
    button.setAttribute("aria-label", "Mostrar contrasena");
    button.setAttribute("title", "Mostrar contrasena");
    button.innerHTML = '<span aria-hidden="true">&#128065;</span>';

    button.addEventListener("click", function () {
      var shouldShow = input.type === "password";
      input.type = shouldShow ? "text" : "password";
      button.setAttribute("aria-label", shouldShow ? "Ocultar contrasena" : "Mostrar contrasena");
      button.setAttribute("title", shouldShow ? "Ocultar contrasena" : "Mostrar contrasena");
      button.classList.toggle("is-visible", shouldShow);
    });

    wrapper.appendChild(button);
  }

  function init() {
    document.querySelectorAll('input[type="password"]').forEach(enhancePasswordField);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
