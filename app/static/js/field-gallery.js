// Galeri foto detail lapangan: panah, penghitung, dan klik thumbnail.
document.addEventListener("DOMContentLoaded", function () {
  const gallery = document.querySelector("[data-gallery]");
  if (!gallery) return;

  const stage = gallery.querySelector(".detail-image");
  const main = gallery.querySelector("[data-gallery-main]");
  const thumbs = Array.from(gallery.querySelectorAll("[data-gallery-src]"));

  if (!stage || !main || thumbs.length === 0) return;

  const sources = thumbs.map(function (thumb) {
    return thumb.dataset.gallerySrc;
  });
  let current = 0;

  function show(index) {
    current = (index + sources.length) % sources.length;
    main.src = sources[current];

    thumbs.forEach(function (thumb, thumbIndex) {
      thumb.classList.toggle("active", thumbIndex === current);
    });

    if (counter) {
      counter.textContent = (current + 1) + " / " + sources.length;
    }
  }

  let counter = null;

  if (sources.length > 1) {
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "gallery-nav gallery-nav-prev";
    prev.setAttribute("aria-label", "Foto sebelumnya");
    prev.textContent = "\u2039";

    const next = document.createElement("button");
    next.type = "button";
    next.className = "gallery-nav gallery-nav-next";
    next.setAttribute("aria-label", "Foto berikutnya");
    next.textContent = "\u203a";

    counter = document.createElement("span");
    counter.className = "gallery-counter";

    prev.addEventListener("click", function () {
      show(current - 1);
    });

    next.addEventListener("click", function () {
      show(current + 1);
    });

    stage.appendChild(prev);
    stage.appendChild(next);
    stage.appendChild(counter);
  }

  thumbs.forEach(function (thumb, index) {
    thumb.addEventListener("click", function () {
      show(index);
    });
  });

  show(0);
});
