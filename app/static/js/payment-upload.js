// Logika upload bukti pembayaran yang dipakai bersama oleh
// halaman booking (booking.js) dan halaman detail reservasi.
(function () {
    const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
    const MAX_SIZE = 5 * 1024 * 1024; // 5 MB, sama dengan MAX_CONTENT_LENGTH

    function validate(file) {
        if (!file) {
            return "Pilih file bukti pembayaran terlebih dahulu.";
        }

        if (!ALLOWED_TYPES.includes(file.type)) {
            return "Format file harus JPG, PNG, atau WebP.";
        }

        if (file.size > MAX_SIZE) {
            return "Ukuran file maksimal 5 MB.";
        }

        if (file.size === 0) {
            return "File kosong.";
        }

        return null;
    }

    async function send(reservationId, file) {
        const error = validate(file);

        if (error) {
            throw new Error(error);
        }

        const formData = new FormData();
        formData.append("proof", file);

        // Metode (OVO/GoPay/...) yang dipilih pelanggan di panel QRIS.
        const channel =
            window.PaymentMethods && window.PaymentMethods.selected();

        if (channel) {
            formData.append("channel", channel);
        }

        const response = await fetch(
            "/reservations/" + reservationId + "/payment",
            {
                method: "POST",
                body: formData
            }
        );

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("Respons server tidak dapat dibaca.");
        }

        if (!response.ok || !data.success) {
            throw new Error(
                data.message || "Gagal mengunggah bukti pembayaran."
            );
        }

        return data;
    }

    window.PaymentUpload = { validate, send };
})();