// Notifikasi pelanggan: lonceng di pojok kanan bawah + pop-up saat ada kabar baru.
(function () {
  const POLL_MS = 30000;
  const TOAST_MS = 9000;

  let unread = 0;
  let toastedId = 0;
  let panelOpen = false;
  let closeTimer = null;
  let bell, badge, panel, list;

  function create(tag, className, text) {
    const element = document.createElement(tag);

    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;

    return element;
  }

  function build() {
    bell = create("button", "notif-bell");
    bell.type = "button";
    bell.setAttribute("aria-label", "Notifikasi");
    bell.setAttribute("aria-expanded", "false");
    bell.appendChild(create("span", "notif-bell-icon", "🔔"));

    badge = create("span", "notif-badge");
    badge.hidden = true;
    bell.appendChild(badge);

    panel = create("div", "notif-panel");
    panel.hidden = true;
    panel.appendChild(create("div", "notif-panel-title", "Notifikasi"));

    list = create("div", "notif-list");
    panel.appendChild(list);

    bell.addEventListener("click", togglePanel);

    document.addEventListener("click", function (event) {
      if (
        panelOpen &&
        !panel.contains(event.target) &&
        !bell.contains(event.target)
      ) {
        closePanel();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && panelOpen) closePanel();
    });

    document.body.appendChild(panel);
    document.body.appendChild(bell);
  }

  function setBadge(count) {
    unread = count;
    badge.textContent = count > 9 ? "9+" : String(count);
    badge.hidden = count === 0;
    bell.classList.toggle("has-unread", count > 0);
  }

  function renderList(items) {
    list.textContent = "";

    if (!items.length) {
      list.appendChild(create("p", "notif-empty", "Belum ada notifikasi."));
      return;
    }

    items.forEach(function (item) {
      const row = create(
        item.url ? "a" : "div",
        "notif-item notif-" + item.jenis + (item.dibaca ? "" : " unread"),
      );

      if (item.url) row.href = item.url;

      row.appendChild(create("strong", "", item.judul));
      row.appendChild(create("span", "", item.pesan));
      row.appendChild(create("small", "", item.waktu + " WIB"));
      list.appendChild(row);
    });
  }

  function showToast(item) {
    const toast = create(item.url ? "a" : "div", "notif-toast notif-" + item.jenis);

    if (item.url) toast.href = item.url;

    toast.appendChild(create("strong", "", item.judul));
    toast.appendChild(create("span", "", item.pesan));
    document.body.appendChild(toast);

    requestAnimationFrame(function () {
      toast.classList.add("show");
    });

    setTimeout(function () {
      toast.classList.remove("show");
      setTimeout(function () {
        toast.remove();
      }, 400);
    }, TOAST_MS);
  }

  async function load() {
    try {
      const response = await fetch("/notifications");

      if (!response.ok) return;

      const data = await response.json();

      if (!data.success) return;

      renderList(data.items);
      setBadge(data.unread);

      // Pop-up hanya untuk notifikasi belum dibaca yang belum pernah ditampilkan.
      const fresh = data.items.find(function (item) {
        return !item.dibaca && item.id > toastedId;
      });

      if (fresh && !panelOpen) {
        showToast(fresh);
      }

      data.items.forEach(function (item) {
        if (!item.dibaca && item.id > toastedId) toastedId = item.id;
      });
    } catch {
      // Gagal sementara (jaringan): coba lagi pada polling berikutnya.
    }
  }

  async function markRead() {
    try {
      await fetch("/notifications/read", { method: "POST" });
      setBadge(0);
    } catch {
      // abaikan; akan dicoba lagi saat panel dibuka berikutnya
    }
  }

  function openPanel() {
    panelOpen = true;
    clearTimeout(closeTimer);
    panel.hidden = false;
    bell.setAttribute("aria-expanded", "true");

    requestAnimationFrame(function () {
      panel.classList.add("open");
    });

    if (unread > 0) markRead();
  }

  function closePanel() {
    panelOpen = false;
    panel.classList.remove("open");
    bell.setAttribute("aria-expanded", "false");

    clearTimeout(closeTimer);
    closeTimer = setTimeout(function () {
      if (!panelOpen) panel.hidden = true;
    }, 230);

    // Tandai item sebagai terbaca di tampilan setelah panel ditutup.
    list.querySelectorAll(".unread").forEach(function (row) {
      row.classList.remove("unread");
    });
  }

  function togglePanel() {
    if (panelOpen) closePanel();
    else openPanel();
  }

  function updateOffset() {
    const footer = document.querySelector(".footer");

    if (!footer) return;

    const overlap = window.innerHeight - footer.getBoundingClientRect().top;
    const offset =
      overlap > 0
        ? Math.max(
            24,
            Math.min(Math.round(overlap) + 24, window.innerHeight - 90),
          )
        : 24;

    document.documentElement.style.setProperty(
      "--notif-bottom",
      offset + "px",
    );
  }

  let offsetFrame = 0;

  function scheduleOffset() {
    cancelAnimationFrame(offsetFrame);

    offsetFrame = requestAnimationFrame(updateOffset);
  }

  document.addEventListener("DOMContentLoaded", function () {
    build();
    updateOffset();
    window.addEventListener("scroll", scheduleOffset, { passive: true });
    window.addEventListener("resize", scheduleOffset);
    load();
    setInterval(load, POLL_MS);
  });
})();
