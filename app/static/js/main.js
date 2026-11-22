
document.addEventListener("DOMContentLoaded", function () {
    const sortSelect = document.querySelector(".filter-control select");
    const fieldGrid = document.querySelector(".field-grid");

    if (!sortSelect || !fieldGrid) return;

    sortSelect.addEventListener("change", function () {
        const cards = Array.from(
            fieldGrid.querySelectorAll(".field-card")
        );

        if (sortSelect.value === "lowest") {
            cards.sort((a, b) => {
                return Number(a.dataset.price) - Number(b.dataset.price);
            });
        } else if (sortSelect.value === "highest") {
            cards.sort((a, b) => {
                return Number(b.dataset.price) - Number(a.dataset.price);
            });
        }

        cards.forEach(card => fieldGrid.appendChild(card));
    });
});

document.addEventListener("DOMContentLoaded", function () {
    const navbar = document.querySelector(".navbar");
    if (!navbar) return;

    function updateNavbar() {
        navbar.classList.toggle("scrolled", window.scrollY > 10);
    }

    updateNavbar();
    window.addEventListener("scroll", updateNavbar, { passive: true });
});

document.addEventListener("DOMContentLoaded", function () {
    if (!("IntersectionObserver" in window)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const selector = [
        ".about-text",
        ".schedule-card",
        ".order-step",
        ".field-card",
        ".cta-band .container",
        ".admin-stat",
    ].join(",");

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;

            const el = entry.target;
            observer.unobserve(el);
            el.classList.add("is-visible");

            el.addEventListener("transitionend", function done(event) {
                if (event.target !== el) return;
                el.classList.remove("reveal", "is-visible");
                el.style.transitionDelay = "";
                el.removeEventListener("transitionend", done);
            });
        });
    }, { threshold: 0.12 });

    document.querySelectorAll(selector).forEach(function (el) {
        const siblings = Array.from(el.parentElement.children)
            .filter(function (child) { return child.matches(selector); });
        const index = Math.max(siblings.indexOf(el), 0);

        el.style.transitionDelay = (index * 80) + "ms";
        el.classList.add("reveal");
        observer.observe(el);
    });
});