// Kelola lapangan (admin): data dasar, status, jam operasional, tarif.
document.addEventListener("DOMContentLoaded", function () {
  const RELOAD_DELAY = 800;

  function messageFor(element) {
    const scope = element.closest("form, .payment-status-card");
    return scope ? scope.querySelector("[data-message]") : null;
  }

  function showMessage(box, text, isError) {
    if (!box) return;

    box.textContent = text;
    box.classList.toggle("error", isError);
    box.classList.toggle("success", !isError);
    box.hidden = false;
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });

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

  // Jalankan satu aksi: kunci tombol, tampilkan pesan, lalu muat ulang.
  async function run(trigger, box, url, body, options) {
    const settings = options || {};
    const buttons = trigger.closest("form, .payment-status-card")
      ? trigger.closest("form, .payment-status-card").querySelectorAll("button")
      : [trigger];

    buttons.forEach(function (button) {
      button.disabled = true;
    });

    if (box) box.hidden = true;

    try {
      const data = await post(url, body);
      showMessage(box, data.message, false);

      if (settings.redirect && data.redirect) {
        window.location.href = data.redirect;
        return;
      }

      if (settings.reload) {
        setTimeout(function () {
          window.location.reload();
        }, RELOAD_DELAY);
        return;
      }
    } catch (error) {
      showMessage(box, error.message || "Aksi gagal diproses.", true);
    }

    buttons.forEach(function (button) {
      button.disabled = false;
    });
  }

  // 1) Data dasar lapangan (buat / ubah)
  const fieldForm = document.getElementById("fieldForm");

  if (fieldForm) {
    fieldForm.addEventListener("submit", function (event) {
      event.preventDefault();

      const isCreate = fieldForm.dataset.mode === "create";

      run(
        fieldForm,
        messageFor(fieldForm),
        fieldForm.dataset.url,
        {
          nama: document.getElementById("fieldName").value,
          luas: document.getElementById("fieldSize").value,
          deskripsi: document.getElementById("fieldDescription").value,
        },
        isCreate ? { redirect: true } : { reload: true },
      );
    });
  }

  // 2) Aktifkan / nonaktifkan
  const statusButton = document.getElementById("statusButton");

  if (statusButton) {
    statusButton.addEventListener("click", function () {
      const next = statusButton.dataset.next;
      const question =
        next === "aktif"
          ? "Aktifkan lapangan ini? Lapangan akan tampil untuk pelanggan."
          : "Nonaktifkan lapangan ini? Pelanggan tidak bisa memesannya lagi.";

      if (!window.confirm(question)) return;

      run(
        statusButton,
        messageFor(statusButton),
        statusButton.dataset.url,
        { status: next },
        { reload: true },
      );
    });
  }

  // 3) Jam operasional (7 hari sekaligus)
  const hoursForm = document.getElementById("hoursForm");

  if (hoursForm) {
    hoursForm.addEventListener("submit", function (event) {
      event.preventDefault();

      const hours = Array.from(hoursForm.querySelectorAll("[data-day]")).map(
        function (row) {
          return {
            hari: Number(row.dataset.day),
            aktif: row.querySelector(".hour-active").checked,
            buka: row.querySelector(".hour-open").value,
            tutup: row.querySelector(".hour-close").value,
          };
        },
      );

      run(
        hoursForm,
        messageFor(hoursForm),
        hoursForm.dataset.url,
        { hours: hours },
        { reload: true },
      );
    });
  }

  // 4) Tambah tarif
  const tariffForm = document.getElementById("tariffForm");

  if (tariffForm) {
    const fromInput = document.getElementById("tariffFrom");

    if (fromInput && !fromInput.value) {
      const now = new Date();
      const pad = function (n) {
        return String(n).padStart(2, "0");
      };

      fromInput.value =
        now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
    }

    tariffForm.addEventListener("submit", function (event) {
      event.preventDefault();

      const days = Array.from(
        tariffForm.querySelectorAll('input[name="hari"]:checked'),
      ).map(function (input) {
        return Number(input.value);
      });

      run(
        tariffForm,
        messageFor(tariffForm),
        tariffForm.dataset.url,
        {
          hari: days,
          jam_mulai: document.getElementById("tariffStart").value,
          jam_selesai: document.getElementById("tariffEnd").value,
          harga: document.getElementById("tariffPrice").value,
          berlaku_mulai: document.getElementById("tariffFrom").value,
          berlaku_sampai: document.getElementById("tariffUntil").value,
        },
        { reload: true },
      );
    });
  }

  // 5) Hapus tarif
  document.querySelectorAll("[data-delete-tariff]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!window.confirm("Hapus tarif ini?")) return;

      const box = document.querySelector('[data-for="tariff-list"]');

      run(button, box, button.dataset.url, {}, { reload: true });
    });
  });
});