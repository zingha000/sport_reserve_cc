// Kelola QRIS (admin): tambah, aktif/nonaktif, hapus.
document.addEventListener("DOMContentLoaded", function () {
  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
  const MAX_SIZE = 5 * 1024 * 1024;
  const RELOAD_DELAY = 700;

  function showMessage(box, text, isError) {
    if (!box) return;

    box.textContent = text;
    box.classList.toggle("error", isError);
    box.classList.toggle("success", !isError);
    box.hidden = false;
  }

  async function post(url, body) {
    const response = await fetch(url, { method: "POST", body: body });

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

  const form = document.getElementById("methodForm");

  if (form) {
    const box = form.querySelector("[data-message]");
    const submit = form.querySelector('button[type="submit"]');

    form.addEventListener("submit", async function (event) {
      event.preventDefault();

      const file = document.getElementById("methodQr").files[0];

      if (!file) {
        showMessage(box, "Pilih gambar QRIS terlebih dahulu.", true);
        return;
      }

      if (!ALLOWED_TYPES.includes(file.type)) {
        showMessage(box, "Format gambar harus JPG, PNG, atau WebP.", true);
        return;
      }

      if (file.size > MAX_SIZE) {
        showMessage(box, "Ukuran gambar maksimal 5 MB.", true);
        return;
      }

      const body = new FormData();
      body.append("ewallet", document.getElementById("methodWallet").value);
      body.append("pemilik", document.getElementById("methodOwner").value);
      body.append("nomor", document.getElementById("methodNumber").value);
      body.append("qr", file);

      submit.disabled = true;
      submit.textContent = "Mengunggah...";
      box.hidden = true;

      try {
        const data = await post(form.dataset.url, body);
        showMessage(box, data.message, false);

        setTimeout(function () {
          window.location.reload();
        }, RELOAD_DELAY);
      } catch (error) {
        showMessage(box, error.message || "Gagal menambah QRIS.", true);
        submit.disabled = false;
        submit.textContent = "Tambah QRIS";
      }
    });
  }

  const listBox = document.getElementById("listMessage");

  async function act(button, question) {
    if (question && !window.confirm(question)) return;

    button.disabled = true;

    try {
      const data = await post(button.dataset.url, new FormData());
      showMessage(listBox, data.message, false);

      setTimeout(function () {
        window.location.reload();
      }, RELOAD_DELAY);
    } catch (error) {
      showMessage(listBox, error.message || "Aksi gagal diproses.", true);
      button.disabled = false;
    }
  }

  document.querySelectorAll("[data-toggle-method]").forEach(function (button) {
    button.addEventListener("click", function () {
      act(button, null);
    });
  });

  document.querySelectorAll("[data-delete-method]").forEach(function (button) {
    button.addEventListener("click", function () {
      act(button, "Hapus QRIS ini? Gambarnya juga dihapus dari cloud storage.");
    });
  });
});
