
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
