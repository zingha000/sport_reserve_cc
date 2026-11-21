// Metode pembayaran QRIS (OVO, GoPay, dll.).
//
// - Langkah 3 (konfirmasi): loadChoices() menampilkan pilihan metode yang WAJIB
//   dipilih sebelum reservasi bisa dikonfirmasi. QR belum ditampilkan.
// - Langkah 4 (pembayaran): renderPayment() menampilkan QR metode yang dipilih.
// - Halaman detail: jika #qrisContainer punya data-channel, QR metode itu yang
//   ditampilkan; reservasi lama tanpa metode memakai pilihan tab (cadangan).
(function () {
  let selected = null;
  let locked = false;

  function create(tag, className, text) {
    const element = document.createElement(tag);

    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;

    return element;
  }

  async function fetchMethods() {
    const response = await fetch("/payments/methods");
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error("gagal");
    }

    return data.methods;
  }

  // ---------- Langkah 3: pilihan metode ----------

  function loadChoices(container, onChange, preselect) {
    if (!container) return;

    fetchMethods()
      .then(function (methods) {
        container.textContent = "";

        if (!methods.length) {
          selected = null;
          container.appendChild(
            create(
              "p",
              "method-empty",
              "Metode pembayaran belum tersedia. Hubungi admin untuk bantuan.",
            ),
          );
          onChange(null);
          return;
        }

        let initial = null;

        methods.forEach(function (method) {
          const label = create("label", "method-choice");
          const input = create("input");
          input.type = "radio";
          input.name = "paymentMethod";
          input.value = method.ewallet;

          input.addEventListener("change", function () {
            if (locked) return;

            selected = method.ewallet;
            onChange(selected);
          });

          const body = create("span", "method-choice-body");
          body.appendChild(create("strong", "", method.ewallet));
          body.appendChild(create("small", "", "a.n. " + method.pemilik));

          label.appendChild(input);
          label.appendChild(body);
          container.appendChild(label);

          if (
            preselect &&
            method.ewallet.toLowerCase() === preselect.toLowerCase()
          ) {
            initial = { input: input, method: method };
          }
        });

        if (initial) {
          initial.input.checked = true;
          selected = initial.method.ewallet;
          onChange(selected);
        } else {
          onChange(null);
        }
      })
      .catch(function () {
        selected = null;
        container.textContent = "";
        container.appendChild(
          create(
            "p",
            "method-empty",
            "Metode pembayaran tidak dapat dimuat. Muat ulang halaman ini.",
          ),
        );
        onChange(null);
      });
  }

  function lock() {
    locked = true;

    document
      .querySelectorAll('input[name="paymentMethod"]')
      .forEach(function (input) {
        input.disabled = true;
      });
  }

  // ---------- Langkah 4 / detail: tampilan QR ----------

  function qrFileName(method) {
    return (
      "qris-" +
      String(method.ewallet || "sportreserve")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-") +
      ".png"
    );
  }

  function qrFileUrl(method) {
    return "/payments/qr/" + method.id + "/file";
  }

  async function shareMethod(method, button) {
    const title = "QRIS " + method.ewallet;
    const text = "Scan QRIS " + method.ewallet + " untuk membayar.";
    const fileUrl = qrFileUrl(method);

    if (navigator.share) {
      try {
        const response = await fetch(fileUrl);

        if (response.ok) {
          const blob = await response.blob();
          const file = new File([blob], qrFileName(method), {
            type: blob.type || "image/png",
          });

          if (!navigator.canShare || navigator.canShare({ files: [file] })) {
            await navigator.share({ files: [file], title: title, text: text });
            return;
          }
        }
      } catch (error) {
        if (error && error.name === "AbortError") return;
      }

      try {
        await navigator.share({ title: title, text: text, url: fileUrl });
        return;
      } catch (error) {
        if (error && error.name === "AbortError") return;
      }
    }

    try {
      await navigator.clipboard.writeText(window.location.href);
      button.textContent = "Tautan disalin";
    } catch {
      button.textContent = "Tidak didukung";
    }

    setTimeout(function () {
      button.textContent = "Bagikan";
    }, 2000);
  }

  function addQrActions(panel, method) {
    const actions = create("div", "payment-qr-actions");
    const fileUrl = qrFileUrl(method);

    const download = create("a", "btn-secondary payment-qr-action", "Unduh QR");
    download.href = fileUrl;
    download.download = qrFileName(method);
    actions.appendChild(download);

    const share = create("button", "btn-secondary payment-qr-action", "Bagikan");
    share.type = "button";
    share.addEventListener("click", function () {
      shareMethod(method, share);
    });
    actions.appendChild(share);

    panel.appendChild(actions);
  }

  function renderPayment(container, method) {
    if (!container) return;

    selected = method.ewallet;
    container.textContent = "";
    container.appendChild(create("h3", "", "Bayar dengan " + method.ewallet));

    const panel = create("div", "payment-qr-panel");

    const image = create("img", "payment-qr-image");
    image.src = method.qr_url;
    image.alt = "QRIS " + method.ewallet;
    panel.appendChild(image);

    const meta = create("div", "payment-qr-meta");
    meta.appendChild(create("strong", "", method.ewallet));
    meta.appendChild(create("span", "", "a.n. " + method.pemilik));

    if (method.nomor) {
      meta.appendChild(create("small", "", method.nomor));
    }

    panel.appendChild(meta);

    if (method.id) addQrActions(panel, method);

    container.appendChild(panel);
    container.appendChild(
      create(
        "p",
        "payment-qr-note",
        "Scan QR, bayar sesuai total, lalu unggah bukti pembayaran.",
      ),
    );
  }

  function renderTabs(container, methods) {
    container.textContent = "";
    container.appendChild(create("h3", "", "Bayar dengan QRIS"));

    if (!methods.length) {
      selected = null;
      container.appendChild(
        create(
          "p",
          "",
          "Metode pembayaran belum tersedia. Hubungi admin untuk bantuan.",
        ),
      );
      return;
    }

    const tabs = create("div", "payment-method-tabs");
    const holder = create("div", "payment-qr-holder");
    const buttons = [];

    methods.forEach(function (method) {
      const button = create("button", "payment-method-tab", method.ewallet);
      button.type = "button";

      button.addEventListener("click", function () {
        buttons.forEach(function (other) {
          other.classList.toggle("active", other === button);
        });

        renderPayment(holder, method);
      });

      buttons.push(button);
      tabs.appendChild(button);
    });

    container.appendChild(tabs);
    container.appendChild(holder);

    buttons[0].classList.add("active");
    renderPayment(holder, methods[0]);
  }

  async function loadForReservation(container) {
    const channel = (container.dataset.channel || "").trim();

    try {
      const methods = await fetchMethods();

      if (!channel) {
        renderTabs(container, methods);
        return;
      }

      const match = methods.find(function (method) {
        return method.ewallet.toLowerCase() === channel.toLowerCase();
      });

      if (match) {
        renderPayment(container, match);
        return;
      }

      selected = channel;
      container.textContent = "";
      container.appendChild(create("h3", "", "Bayar dengan " + channel));
      container.appendChild(
        create(
          "p",
          "",
          "QRIS " + channel + " sedang tidak tersedia. Hubungi admin untuk bantuan.",
        ),
      );
    } catch {
      container.textContent = "";
      container.appendChild(create("h3", "", "Bayar dengan QRIS"));
      container.appendChild(
        create("p", "", "QRIS tidak dapat dimuat. Muat ulang halaman ini."),
      );
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("qrisContainer");

    if (container && container.hasAttribute("data-channel")) {
      loadForReservation(container);
    }
  });

  window.PaymentMethods = {
    selected: function () {
      return selected;
    },
    loadChoices: loadChoices,
    renderPayment: renderPayment,
    lock: lock,
  };
})();
