// Aksi verifikasi / tolak pembayaran di halaman detail reservasi admin.
document.addEventListener("DOMContentLoaded", function () {
  const openProof = document.getElementById("openProof");
  const proofModal = document.getElementById("proofModal");

  if (openProof && proofModal) {
    const closeProof = document.getElementById("closeProof");

    function hideProof() {
      proofModal.hidden = true;
      document.body.style.overflow = "";
    }

    openProof.addEventListener("click", function () {
      proofModal.hidden = false;
      document.body.style.overflow = "hidden";
    });

    closeProof.addEventListener("click", hideProof);

    proofModal.addEventListener("click", function (event) {
      if (event.target === proofModal) hideProof();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !proofModal.hidden) hideProof();
    });
  }

  const panel = document.getElementById("reviewPanel");
  if (!panel) return;

  const reservationId = Number(panel.dataset.reservationId);
  const approveButton = document.getElementById("approveButton");
  const rejectButton = document.getElementById("rejectButton");
  const rejectNote = document.getElementById("rejectNote");
  const message = document.getElementById("reviewMessage");
  const checks = Array.from(panel.querySelectorAll(".review-check"));

  let busy = false;

  // Dialog konfirmasi kustom, menggantikan window.confirm bawaan browser.
  function askConfirm(title, text) {
    return new Promise(function (resolve) {
      const modal = document.getElementById("confirmModal");
      const titleEl = document.getElementById("confirmTitle");
      const textEl = document.getElementById("confirmText");
      const yes = document.getElementById("confirmYes");
      const no = document.getElementById("confirmNo");

      function cleanup(result) {
        modal.hidden = true;
        document.body.style.overflow = "";
        yes.removeEventListener("click", onYes);
        no.removeEventListener("click", onNo);
        modal.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(result);
      }

      function onYes() {
        cleanup(true);
      }

      function onNo() {
        cleanup(false);
      }

      function onBackdrop(event) {
        if (event.target === modal) cleanup(false);
      }

      function onKey(event) {
        if (event.key === "Escape") cleanup(false);
      }

      titleEl.textContent = title;
      textEl.textContent = text;
      modal.hidden = false;
      document.body.style.overflow = "hidden";

      yes.addEventListener("click", onYes);
      no.addEventListener("click", onNo);
      modal.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKey);
    });
  }

  // Verifikasi baru bisa ditekan setelah semua pemeriksaan dicentang.
  function syncApprove() {
    const allChecked = checks.every(function (box) {
      return box.checked;
    });

    approveButton.disabled = busy || !allChecked;
  }

  checks.forEach(function (box) {
    box.addEventListener("change", syncApprove);
  });

  syncApprove();

  function showMessage(text, isError) {
    message.textContent = text;
    message.classList.toggle("error", isError);
    message.classList.toggle("success", !isError);
    message.hidden = false;
  }

  function setBusy(value) {
    busy = value;
    rejectButton.disabled = value;
    syncApprove();
  }

  async function send(action, body) {
    const response = await fetch(
      "/admin/reservations/" + reservationId + "/" + action,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      },
    );

    let data;

    try {
      data = await response.json();
    } catch {
      throw new Error("Respons server tidak dapat dibaca.");
    }

    if (!response.ok || !data.success) {
      throw new Error(data.message || "Aksi gagal diproses.");
    }

    return data;
  }

  async function run(action, body) {
    if (busy) return;

    setBusy(true);
    message.hidden = true;

    try {
      const data = await send(action, body);
      showMessage(data.message, false);

      setTimeout(function () {
        window.location.reload();
      }, 900);
    } catch (error) {
      showMessage(error.message || "Aksi gagal diproses.", true);
      setBusy(false);
    }
  }

  approveButton.addEventListener("click", async function () {
    const ok = await askConfirm(
      "Verifikasi pembayaran",
      "Verifikasi pembayaran ini dan konfirmasi reservasi?",
    );

    if (!ok) return;

    run("verify");
  });

  rejectButton.addEventListener("click", async function () {
    const note = rejectNote.value.trim();

    if (!note) {
      showMessage("Isi alasan penolakan terlebih dahulu.", true);
      rejectNote.focus();
      return;
    }

    const ok = await askConfirm(
      "Tolak pembayaran",
      "Tolak pembayaran ini? Reservasi akan dibatalkan dan jadwal dilepas.",
    );

    if (!ok) return;

    run("reject", { note: note });
  });
});
