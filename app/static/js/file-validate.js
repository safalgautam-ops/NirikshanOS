// Client-side mirror of the size limits enforced server-side in
// app/core/storage.py (MAX_LOGO_SIZE_BYTES / MAX_DOCUMENT_SIZE_BYTES).
// The backend check is what actually matters - this only saves the user
// from waiting through a full upload just to get rejected at the end.
// Inputs opt in via data-max-size-bytes + data-max-size-label (see
// components/ui/input.html callers); CSP rules out inline <script>, so
// this lives in its own file like toast-runtime.js.
(function () {
  function formatMB(bytes) {
    return `${(bytes / (1024 * 1024)).toFixed(0)}MB`;
  }

  function validate(input) {
    const max = Number(input.dataset.maxSizeBytes);
    if (!max || !input.files) return true;
    const label = input.dataset.maxSizeLabel || formatMB(max);
    for (const file of input.files) {
      if (file.size > max) {
        window.toast.error(`"${file.name}" is ${formatMB(file.size)} - max is ${label}.`);
        input.value = "";
        return false;
      }
    }
    return true;
  }

  document.addEventListener(
    "change",
    (event) => {
      const input = event.target;
      if (input.matches && input.matches('input[type="file"][data-max-size-bytes]')) {
        validate(input);
      }
    },
    true
  );

  document.addEventListener(
    "submit",
    (event) => {
      const inputs = event.target.querySelectorAll('input[type="file"][data-max-size-bytes]');
      for (const input of inputs) {
        if (!validate(input)) {
          event.preventDefault();
          return;
        }
      }
    },
    true
  );
})();
