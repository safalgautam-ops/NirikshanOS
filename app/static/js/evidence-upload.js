/**
 * Resumable S3 multipart evidence upload - drives the dropzone + file table
 * in cases/detail.html's "Upload evidence" dialog.
 *
 * Each file is sliced into S3 parts (size set by the server's /init
 * response) and PUT straight to MinIO via a presigned URL fetched per part
 * - the app never sees the bytes, only issues URLs. Up to
 * MAX_CONCURRENT_PARTS parts are in flight at once via separate
 * XMLHttpRequests (for real xhr.upload.onprogress events fetch() can't give
 * us), which is what makes the upload actually parallel.
 *
 * Pausing aborts every in-flight part PUT and stops handing out new ones;
 * resuming re-fetches /status, which reflects MinIO's own ListParts record,
 * and only re-queues whatever part numbers are still missing - nothing
 * that already landed needs to be re-sent.
 *
 * It takes a huge evidence file the user drops in,
 * cuts it into pieces, uploads those pieces directly to MinIO in parallel,
 * shows live progress, and lets the user pause, resume, or cancel —
 *  without ever sending the file's bytes through the app.
 *
 * XHR request means an HTTP request made from a web page using
 * XMLHttpRequest, a browser API for sending data to or receiving data
 * from a server without reloading the page.
 */

const EVIDENCE_MAX_FILES = 5; /* at most 5 files uploading at once */
// each file sends 4 pieces simultaneously via separate xhr requests
const MAX_CONCURRENT_PARTS = 4; /* at most 4 pieces of one file in flight at once */

// turns 1500000 into "1.4 MB"
function evidenceFormatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / Math.pow(1024, exponent);
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
}

// turns disk.img into "IMG"
function evidenceFormatOf(filename) {
  const dot = filename.lastIndexOf(".");
  return dot === -1 ? "—" : filename.slice(dot + 1).toUpperCase();
}

/* this class handles uploading evidence files to MinIO directly,
  without ever sending the file's bytes through the app.

  this represents one file being uploaded. It holds all the state and logic
  for slicing, sending, paushing, and finishing that single file.
*/
class EvidenceUpload {
  constructor({ file, caseId, csrfToken, onProgress, onStatusChange }) {
    this.file = file;
    this.caseId = caseId;
    this.csrfToken = csrfToken;
    this.onProgress = onProgress;
    this.onStatusChange = onStatusChange;

    this.evidenceId = null;
    this.totalParts = 0; // how many pieces this one file is cut into
    this.partSize = 0; // how big each piece will be
    this.uploadedBytes = 0;
    this.status = "pending";
    this.errorMessage = "";

    this._partBytesDone = new Map(); // for each piece: part_number -> how many bytes uploaded so far
    this._partBytesTotal = new Map(); // for each piece: part_number -> it's full size
    this._pendingParts = []; // pieces still waiting to be sent
    this._activeXhrs = new Map(); // pieces of the file currently being uploaded (in flight)
    this._inFlightCount = 0; // how many uploads are currently happening
    this._pauseRequested = false; // has the user hit pause?
  }

  async start() {
    this.status = "uploading";
    this.onStatusChange(this);

    const form = new FormData();
    form.append("csrf_token", this.csrfToken);
    form.append("filename", this.file.name);
    form.append("size_bytes", String(this.file.size));

    try {
      // tell the server: I want to upload this file
      const res = await fetch(`/cases/${this.caseId}/evidence/init`, {
        method: "POST",
        body: form,
      });
      const body = await res.json();
      if (!res.ok) return this._fail(body.error || "Could not start upload.");
      this.evidenceId = body.evidence_id; // an ID for this upload
      this.totalParts = body.total_parts; // how many pieces to cut into
      this.partSize = body.part_size; // how big each piece will be
    } catch (_err) {
      return this._fail("Could not start upload.");
    }

    for (let partNumber = 1; partNumber <= this.totalParts; partNumber += 1) {
      this._partBytesTotal.set(partNumber, this._sizeOfPart(partNumber));
      this._partBytesDone.set(partNumber, 0);
      this._pendingParts.push(partNumber);
    }
    this._pump(); // the engine actually send pieces
  }

  _sizeOfPart(partNumber) {
    const start = (partNumber - 1) * this.partSize;
    const end = Math.min(start + this.partSize, this.file.size);
    return end - start;
  }

  _recalculateUploadedBytes() {
    let sum = 0;
    for (const bytes of this._partBytesDone.values()) sum += bytes;
    this.uploadedBytes = sum;
    this.onProgress(this, this.uploadedBytes);
  }

  pause() {
    if (this.status !== "uploading") return;
    this._pauseRequested = true;
    for (const xhr of this._activeXhrs.values()) xhr.abort();

    const form = new FormData();
    form.append("csrf_token", this.csrfToken);
    fetch(`/cases/${this.caseId}/evidence/${this.evidenceId}/pause`, {
      method: "POST",
      body: form,
    });
  }

  async resume() {
    if (this.status !== "paused") return;
    this._pauseRequested = false;

    const form = new FormData();
    form.append("csrf_token", this.csrfToken);
    await fetch(`/cases/${this.caseId}/evidence/${this.evidenceId}/resume`, {
      method: "POST",
      body: form,
    });

    // ListParts (via /status) is the ground truth for what's actually
    // landed - only re-queue what's genuinely still missing.
    try {
      const res = await fetch(
        `/cases/${this.caseId}/evidence/${this.evidenceId}/status`,
      );
      const state = await res.json();
      const received = new Set(state.received_part_numbers || []);
      this._pendingParts = [];
      for (let partNumber = 1; partNumber <= this.totalParts; partNumber += 1) {
        if (received.has(partNumber)) {
          this._partBytesDone.set(
            partNumber,
            this._partBytesTotal.get(partNumber),
          );
        } else if (!this._pendingParts.includes(partNumber)) {
          this._pendingParts.push(partNumber);
        }
      }
      this._recalculateUploadedBytes();
    } catch (_err) {
      /* best-effort resync - fall back to whatever was already queued */
    }

    this.status = "uploading";
    this.onStatusChange(this);
    this._pump();
  }

  cancel() {
    this._pauseRequested = true;
    for (const xhr of this._activeXhrs.values()) xhr.abort();
    this.status = "cancelled";
    this.onStatusChange(this);
    if (this.evidenceId) {
      const form = new FormData();
      form.append("csrf_token", this.csrfToken);
      fetch(`/cases/${this.caseId}/evidence/${this.evidenceId}/delete`, {
        method: "POST",
        body: form,
      });
    }
  }

  _pump() {
    if (this._pauseRequested) return;
    while (
      this._inFlightCount < MAX_CONCURRENT_PARTS &&
      this._pendingParts.length
    ) {
      const partNumber = this._pendingParts.shift();
      this._inFlightCount += 1;
      this._uploadPart(partNumber);
    }
    if (
      this.status === "uploading" &&
      this._inFlightCount === 0 &&
      this._pendingParts.length === 0
    ) {
      this._finalize();
    }
  }

  async _uploadPart(partNumber) {
    let url;
    try {
      // ask the server for an upload URL for this piece
      const res = await fetch(
        `/cases/${this.caseId}/evidence/${this.evidenceId}/parts/${partNumber}/url`,
      );
      const body = await res.json();
      if (!res.ok)
        throw new Error(body.error || "Could not get an upload URL.");
      url = body.url;
    } catch (_err) {
      this._inFlightCount -= 1;
      return this._fail("Could not get an upload URL.");
    }

    if (this._pauseRequested) {
      this._inFlightCount -= 1;
      this._pendingParts.push(partNumber);
      return;
    }

    const start = (partNumber - 1) * this.partSize;
    const end = Math.min(start + this.partSize, this.file.size);
    const blob = this.file.slice(start, end);

    const xhr = new XMLHttpRequest();
    this._activeXhrs.set(partNumber, xhr);
    // A presigned S3 PUT expects the raw body, not a multipart/form-data
    // wrapper - this goes straight to MinIO, not through this app.
    xhr.open("PUT", url);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      this._partBytesDone.set(partNumber, event.loaded);
      this._recalculateUploadedBytes();
    };

    xhr.onload = () => {
      this._activeXhrs.delete(partNumber);
      this._inFlightCount -= 1;
      if (xhr.status >= 200 && xhr.status < 300) {
        this._partBytesDone.set(partNumber, blob.size);
        this._recalculateUploadedBytes();
        this._pump();
      } else {
        this._fail("Upload failed.");
      }
    };

    xhr.onerror = () => {
      this._activeXhrs.delete(partNumber);
      this._inFlightCount -= 1;
      this._fail("Network error during upload.");
    };

    xhr.onabort = () => {
      this._activeXhrs.delete(partNumber);
      this._inFlightCount -= 1;
      if (this._pauseRequested) {
        this._partBytesDone.set(partNumber, 0);
        this._pendingParts.push(partNumber);
        if (this._inFlightCount === 0) {
          this._recalculateUploadedBytes();
          this.status = "paused";
          this.onStatusChange(this);
        }
      }
    };

    xhr.send(blob);
  }

  async _finalize() {
    const form = new FormData();
    form.append("csrf_token", this.csrfToken);
    try {
      const res = await fetch(
        `/cases/${this.caseId}/evidence/${this.evidenceId}/finalize`,
        {
          method: "POST",
          body: form,
        },
      );
      const body = await res.json();
      if (!res.ok) return this._fail(body.error || "Could not finish upload.");
    } catch (_err) {
      return this._fail("Could not finish upload.");
    }
    this.status = "completed";
    this.onStatusChange(this);
  }

  _fail(message) {
    this.status = "failed";
    this.errorMessage = message;
    this.onStatusChange(this);
  }
}

function initEvidenceUpload({ caseId, csrfToken }) {
  const root = document.querySelector("[data-evidence-root]");
  const dropzone = document.querySelector("[data-evidence-dropzone]");
  if (!root || !dropzone) return;

  const fileInput = dropzone.querySelector("[data-evidence-file-input]");
  const browseButton = dropzone.querySelector("[data-evidence-browse]");
  const uploadTable = document.querySelector("[data-evidence-upload-table]");
  const uploadRows = document.querySelector("[data-evidence-upload-rows]");
  const persistedTable = document.querySelector("[data-evidence-table]");
  const persistedRows = document.querySelector("[data-evidence-rows]");
  const emptyState = document.querySelector("[data-evidence-empty]");

  const activeUploads = new Map(); // row element -> EvidenceUpload

  function actionButton(label, attrs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors";
    button.setAttribute("aria-label", label);
    Object.entries(attrs).forEach(([key, value]) =>
      button.setAttribute(key, value),
    );
    return button;
  }

  function iconPause() {
    return '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
  }
  function iconPlay() {
    return '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l16 9-16 9V3z"/></svg>';
  }
  function iconTrash() {
    return '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>';
  }

  function addUploadRow(upload) {
    const row = document.createElement("tr");
    row.className = "border-b";
    row.innerHTML = `
      <td class="whitespace-nowrap p-2.5 align-middle"><span data-cell="name" class="truncate"></span></td>
      <td class="whitespace-nowrap p-2.5 align-middle" data-cell="format"></td>
      <td class="whitespace-nowrap p-2.5 align-middle" data-cell="size"></td>
      <td class="p-2.5 align-middle">
        <div class="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div data-cell="bar" class="h-full bg-primary transition-[width]" style="width:0%"></div>
        </div>
        <p data-cell="status" class="mt-1 text-xs text-muted-foreground"></p>
      </td>
      <td class="p-2.5 align-middle text-right"><div class="flex justify-end gap-1" data-cell="actions"></div></td>
    `;
    row.querySelector('[data-cell="name"]').textContent = upload.file.name;
    row.querySelector('[data-cell="format"]').textContent = evidenceFormatOf(
      upload.file.name,
    );
    row.querySelector('[data-cell="size"]').textContent = evidenceFormatBytes(
      upload.file.size,
    );
    uploadRows.appendChild(row);
    uploadTable.classList.remove("hidden");
    return row;
  }

  function renderActions(row, upload) {
    const actions = row.querySelector('[data-cell="actions"]');
    actions.innerHTML = "";
    if (upload.status === "uploading") {
      const pause = actionButton("Pause", {});
      pause.innerHTML = iconPause();
      pause.addEventListener("click", () => upload.pause());
      actions.appendChild(pause);
    } else if (upload.status === "paused") {
      const play = actionButton("Resume", {});
      play.innerHTML = iconPlay();
      play.addEventListener("click", () => upload.resume());
      actions.appendChild(play);
    }
    if (upload.status !== "completed") {
      const del = actionButton("Cancel", { class: "hover:text-destructive" });
      del.innerHTML = iconTrash();
      del.addEventListener("click", () => {
        upload.cancel();
        row.remove();
        activeUploads.delete(row);
      });
      actions.appendChild(del);
    } else {
      const del = actionButton("Remove", {});
      del.innerHTML = iconTrash();
      del.addEventListener("click", () => {
        row.remove();
        activeUploads.delete(row);
      });
      actions.appendChild(del);
    }
  }

  function updateRow(row, upload) {
    const percent = upload.file.size
      ? Math.min(
          100,
          Math.round((upload.uploadedBytes / upload.file.size) * 100),
        )
      : 0;
    row.querySelector('[data-cell="bar"]').style.width = `${percent}%`;
    const statusLabel = {
      pending: "Starting…",
      uploading: `${percent}%`,
      paused: "Paused",
      completed: "Completed",
      failed: upload.errorMessage || "Failed",
      cancelled: "Cancelled",
    }[upload.status];
    row.querySelector('[data-cell="status"]').textContent = statusLabel;
    renderActions(row, upload);
    if (upload.status === "completed") {
      refreshPersistedEvidence();
    }
  }

  function handleFiles(fileList) {
    const remainingSlots = EVIDENCE_MAX_FILES - activeUploads.size;
    const files = Array.from(fileList).slice(0, Math.max(0, remainingSlots));
    files.forEach((file) => {
      const upload = new EvidenceUpload({
        file,
        caseId,
        csrfToken,
        onProgress: (u) => updateRow(row, u),
        onStatusChange: (u) => updateRow(row, u),
      });
      const row = addUploadRow(upload);
      activeUploads.set(row, upload);
      updateRow(row, upload);
      upload.start();
    });
  }

  browseButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    handleFiles(fileInput.files);
    fileInput.value = "";
  });

  ["dragover", "dragenter"].forEach((eventName) =>
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("border-primary");
    }),
  );
  ["dragleave", "dragend"].forEach((eventName) =>
    dropzone.addEventListener(eventName, () =>
      dropzone.classList.remove("border-primary"),
    ),
  );
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("border-primary");
    if (event.dataTransfer && event.dataTransfer.files)
      handleFiles(event.dataTransfer.files);
  });

  function statusLabelFor(status) {
    return (
      {
        uploading: "Uploading",
        paused: "Paused",
        completed: "Completed",
        failed: "Failed",
        cancelled: "Cancelled",
      }[status] || status
    );
  }

  async function refreshPersistedEvidence() {
    try {
      const res = await fetch(`/cases/${caseId}/evidence`);
      if (!res.ok) return;
      const body = await res.json();
      persistedRows.innerHTML = "";
      if (!body.items.length) {
        emptyState.classList.remove("hidden");
        persistedTable.classList.add("hidden");
        return;
      }
      emptyState.classList.add("hidden");
      persistedTable.classList.remove("hidden");
      body.items.forEach((item) => {
        const row = document.createElement("tr");
        row.className = "border-b";
        row.innerHTML = `
          <td class="whitespace-nowrap p-2.5 align-middle truncate">${item.filename}</td>
          <td class="whitespace-nowrap p-2.5 align-middle">${evidenceFormatOf(item.filename)}</td>
          <td class="whitespace-nowrap p-2.5 align-middle">${evidenceFormatBytes(item.size_bytes)}</td>
          <td class="whitespace-nowrap p-2.5 align-middle">${statusLabelFor(item.status)}</td>
          <td class="p-2.5 align-middle text-right"><div class="flex justify-end gap-1" data-cell="actions"></div></td>
        `;
        const del = actionButton("Delete", { class: "hover:text-destructive" });
        del.innerHTML = iconTrash();
        del.addEventListener("click", async () => {
          const form = new FormData();
          form.append("csrf_token", csrfToken);
          await fetch(`/cases/${caseId}/evidence/${item.id}/delete`, {
            method: "POST",
            body: form,
          });
          refreshPersistedEvidence();
        });
        row.querySelector('[data-cell="actions"]').appendChild(del);
        persistedRows.appendChild(row);
      });
    } catch (_err) {
      /* best-effort refresh - leave the table as-is on failure */
    }
  }

  refreshPersistedEvidence();
}
