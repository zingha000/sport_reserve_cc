// Kelola foto lapangan (admin): daftar, unggah, jadikan foto utama, hapus.
document.addEventListener("DOMContentLoaded", function () {
  const root = document.querySelector("[data-photos-root]");
  if (!root) return;

  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
  const MAX_BYTES = 5 * 1024 * 1024;
  const MAX_ORIGINAL_BYTES = 25 * 1024 * 1024;
  const MAX_SIDE = 1600;
  const QUALITY = 0.82;

  // Kecilkan gambar di browser agar unggahan cepat dan halaman pelanggan ringan.
  async function compressImage(file) {
    if (!window.createImageBitmap) return file;

    try {
      const bitmap = await createImageBitmap(file);
      const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();

      const blob = await new Promise(function (resolve) {
        canvas.toBlob(resolve, "image/webp", QUALITY);
      });

      // Pakai hasil kompres hanya bila benar WebP dan lebih kecil dari aslinya.
      if (!blob || blob.type !== "image/webp" || blob.size >= file.size) {
        return file;
      }

      const name = file.name.replace(/\.[^.]+$/, "") + ".webp";
      return new File([blob], name, { type: "image/webp" });
    } catch {
      return file;
    }
  }

  const grid = root.querySelector("[data-photos-grid]");
  const input = root.querySelector("#photoInput");
  const uploadButton = root.querySelector("[data-photo-upload]");
  const box = root.querySelector("[data-photos-message]");
  const listUrl = root.dataset.listUrl;
  const uploadUrl = root.dataset.uploadUrl;

  let busy = false;

  function show(text, isError) {
    box.textContent = text;
    box.classList.toggle("error", isError);
    box.classList.toggle("success", !isError);
    box.hidden = false;
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    let data = {};

    try {
      data = await response.json();
    } catch {
      // Respons bukan JSON (mis. 413 dari server).
    }

    if (!response.ok || data.success === false) {
      throw new Error(
        data.message ||
          (response.status === 413
            ? "Ukuran foto maksimal 5 MB."
            : "Terjadi kesalahan. Coba lagi."),
      );
    }

    return data;
  }

  function setBusy(value) {
    busy = value;
    uploadButton.disabled = value;
    root.querySelectorAll("button[data-action]").forEach(function (button) {
      button.disabled = value;
    });
  }

  function actionButton(label, action, handler, danger) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      "btn-secondary admin-btn-small" + (danger ? " admin-danger" : "");
    button.dataset.action = action;
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function render(photos) {
    grid.replaceChildren();

    if (!photos.length) {
      const empty = document.createElement("p");
      empty.className = "admin-note";
      empty.textContent = "Belum ada foto.";
      grid.appendChild(empty);
      return;
    }

    photos.forEach(function (photo) {
      const card = document.createElement("div");
      card.className = "field-photo-card";

      const image = document.createElement("img");
      image.src = photo.url;
      image.alt = photo.name || "Foto lapangan";
      image.loading = "lazy";
      card.appendChild(image);

      if (photo.is_thumbnail) {
        const badge = document.createElement("span");
        badge.className = "field-photo-badge";
        badge.textContent = "Foto utama";
        card.appendChild(badge);
      }

      const actions = document.createElement("div");
      actions.className = "field-photo-actions";

      if (!photo.is_thumbnail) {
        actions.appendChild(
          actionButton("Jadikan utama", "thumb", function () {
            act(
              uploadUrl + "/" + photo.id + "/thumbnail",
              "Foto utama diubah.",
            );
          }),
        );
      }

      actions.appendChild(
        actionButton(
          "Hapus",
          "delete",
          function () {
            if (!window.confirm("Hapus foto ini?")) return;
            act(uploadUrl + "/" + photo.id + "/delete", "Foto dihapus.");
          },
          true,
        ),
      );

      card.appendChild(actions);
      grid.appendChild(card);
    });
  }

  async function refresh() {
    const data = await request(listUrl);
    render(data.photos);
  }

  async function act(url, okText) {
    if (busy) return;
    setBusy(true);

    try {
      await request(url, { method: "POST" });
      await refresh();
      show(okText, false);
    } catch (error) {
      show(error.message, true);
    } finally {
      setBusy(false);
    }
  }

  uploadButton.addEventListener("click", async function () {
    if (busy) return;

    const file = input.files && input.files[0];

    if (!file) return show("Pilih foto terlebih dahulu.", true);
    if (ALLOWED_TYPES.indexOf(file.type) === -1)
      return show("Format foto harus JPG, PNG, atau WebP.", true);
    if (file.size > MAX_ORIGINAL_BYTES)
      return show("Ukuran foto terlalu besar (maksimal 25 MB).", true);

    setBusy(true);
    uploadButton.textContent = "Memproses...";

    try {
      const prepared = await compressImage(file);

      if (prepared.size > MAX_BYTES) {
        throw new Error("Ukuran foto maksimal 5 MB setelah dikecilkan.");
      }

      const form = new FormData();
      form.append("photo", prepared);

      uploadButton.textContent = "Mengunggah...";
      await request(uploadUrl, { method: "POST", body: form });
      input.value = "";
      await refresh();
      show("Foto berhasil diunggah.", false);
    } catch (error) {
      show(error.message, true);
    } finally {
      uploadButton.textContent = "Unggah Foto";
      setBusy(false);
    }
  });

  refresh().catch(function (error) {
    show(error.message, true);
  });
});