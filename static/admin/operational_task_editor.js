(function () {
  function bindEditor() {
    var field = document.querySelector("#id_employee_response");
    if (!field || field.dataset.richBound === "1") return;

    var wrapper = document.createElement("div");
    wrapper.className = "axis-rich-editor";

    var toolbar = document.createElement("div");
    toolbar.className = "axis-rich-toolbar";
    [
      ["bold", "B", "Negrita"],
      ["italic", "I", "Cursiva"],
      ["insertUnorderedList", "•", "Lista"],
      ["createLink", "↗", "Enlace"],
    ].forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      button.dataset.command = item[0];
      button.textContent = item[1];
      button.title = item[2];
      toolbar.appendChild(button);
    });

    var editor = document.createElement("div");
    editor.className = "axis-rich-editor-surface";
    editor.contentEditable = "true";
    editor.innerHTML = field.value || "";

    field.parentNode.insertBefore(wrapper, field);
    wrapper.appendChild(toolbar);
    wrapper.appendChild(editor);
    field.classList.add("axis-rich-hidden-source");

    toolbar.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-command]");
      if (!button) return;
      editor.focus();
      if (button.dataset.command === "createLink") {
        var url = window.prompt("Pega el enlace");
        if (!url) return;
        document.execCommand("createLink", false, url);
      } else {
        document.execCommand(button.dataset.command, false, null);
      }
      field.value = editor.innerHTML;
    });

    editor.addEventListener("input", function () {
      field.value = editor.innerHTML;
    });

    var form = field.closest("form");
    if (form) {
      form.addEventListener("submit", function () {
        field.value = editor.innerHTML;
      });
    }
    field.dataset.richBound = "1";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindEditor);
  } else {
    bindEditor();
  }
})();
