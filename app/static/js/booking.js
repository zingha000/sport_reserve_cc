
document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("bookingForm");
    if (!form) return;

    // ==========================================
    // ELEMEN JADWAL
    // ==========================================

    const bookingDate = document.getElementById("bookingDate");
    const duration = document.getElementById("duration");
    const startTime = document.getElementById("startTime");
    const endTime = document.getElementById("endTime");

    const timeSlots = document.getElementById("timeSlots");
    const scheduleMessage = document.getElementById("scheduleMessage");
    const scheduleDateLabel = document.getElementById("scheduleDateLabel");

    const summaryDate = document.getElementById("summaryDate");
    const summaryTime = document.getElementById("summaryTime");
    const summaryDuration = document.getElementById("summaryDuration");
    const summaryTotal = document.getElementById("summaryTotal");

    const bookingButton = document.getElementById("nextToStage2");

    const availabilityUrl = form.dataset.availabilityUrl;
    const fieldId = Number(form.dataset.fieldId);
    const pricePerHour = Number(form.dataset.price || 0);

    // ==========================================
    // ELEMEN TAHAP 2
    // ==========================================

    const activityType = document.getElementById("activityType");

    const trainingFields = document.getElementById("trainingFields");
    const friendlyFields = document.getElementById("friendlyFields");

    const trainingTeamName = document.getElementById("trainingTeamName");
    const trainingPlayers = document.getElementById("trainingPlayers");

    const teamAName = document.getElementById("teamAName");
    const teamAPlayers = document.getElementById("teamAPlayers");
    const teamBName = document.getElementById("teamBName");
    const teamBPlayers = document.getElementById("teamBPlayers");

    const bookingNotes = document.getElementById("bookingNotes");

    // ==========================================
    // ELEMEN TAHAP 3
    // ==========================================

    const confirmDate = document.getElementById("confirmDate");
    const confirmTime = document.getElementById("confirmTime");
    const confirmDuration = document.getElementById("confirmDuration");
    const confirmActivity = document.getElementById("confirmActivity");
    const confirmTeamDetails = document.getElementById("confirmTeamDetails");
    const confirmNotes = document.getElementById("confirmNotes");
    const confirmTotal = document.getElementById("confirmTotal");

    const confirmButton = document.getElementById("confirmBooking");

    // ==========================================
    // ELEMEN TAHAP 4
    // ==========================================

    const paymentTransactionCode = document.getElementById(
        "paymentTransactionCode"
    );

    const paymentReservationStatus = document.getElementById(
        "paymentReservationStatus"
    );

    const paymentStatus = document.getElementById("paymentStatus");
    const paymentFieldName = document.getElementById("paymentFieldName");
    const paymentDate = document.getElementById("paymentDate");
    const paymentTime = document.getElementById("paymentTime");
    const paymentTotal = document.getElementById("paymentTotal");
    const paymentCountdown = document.getElementById("paymentCountdown");

    const paymentProof = document.getElementById("paymentProof");
    const submitPayment = document.getElementById("submitPayment");
    const paymentMessage = document.getElementById("paymentMessage");

    // ==========================================
    // NAVIGASI TAHAP
    // ==========================================

    const stages = [
        document.getElementById("stage1"),
        document.getElementById("stage2"),
        document.getElementById("stage3"),
        document.getElementById("stage4")
    ];

    const progressSteps = document.querySelectorAll(".progress-step");
    const progressLines = document.querySelectorAll(".progress-line");

    let currentStage = 1;
    let operational = null;
    let reservations = [];
    let selectedSlot = null;
    let loading = false;
    let requestNumber = 0;
    let countdownInterval = null;
    let reservationCreated = false;

    // ==========================================
    // UTILITAS
    // ==========================================

    const now = new Date();

    const localDate = new Date(
        now.getTime() - now.getTimezoneOffset() * 60000
    ).toISOString().split("T")[0];

    bookingDate.min = localDate;

    function formatRupiah(amount) {
        return new Intl.NumberFormat("id-ID", {
            style: "currency",
            currency: "IDR",
            maximumFractionDigits: 0
        }).format(amount);
    }

    function formatDate(value) {
        if (!value) return "-";

        return new Date(value + "T00:00:00").toLocaleDateString(
            "id-ID",
            {
                day: "numeric",
                month: "long",
                year: "numeric"
            }
        );
    }

    function toMinutes(time) {
        const [hour, minute] = time.split(":").map(Number);
        return hour * 60 + minute;
    }

    function toTime(minutes) {
        const hour = Math.floor(minutes / 60);
        const minute = minutes % 60;

        return (
            String(hour).padStart(2, "0") +
            ":" +
            String(minute).padStart(2, "0")
        );
    }

    function overlaps(start, end, reservedStart, reservedEnd) {
        return start < reservedEnd && end > reservedStart;
    }

    function isPastSlot(start) {
        if (bookingDate.value < localDate) return true;
        if (bookingDate.value > localDate) return false;

        const current = new Date();
        const currentMinutes =
            current.getHours() * 60 + current.getMinutes();

        return start <= currentMinutes;
    }

    async function readResponse(response) {
        try {
            return await response.json();
        } catch {
            throw new Error("Respons server tidak dapat dibaca.");
        }
    }

    // ==========================================
    // NAVIGASI TAHAP
    // ==========================================

    function showStage(stageNumber) {
        currentStage = stageNumber;

        stages.forEach((stage, index) => {
            const active = index + 1 === stageNumber;

            stage.hidden = !active;
            stage.classList.toggle("active", active);
        });

        progressSteps.forEach((step, index) => {
            step.classList.toggle(
                "active",
                index + 1 === stageNumber
            );

            step.classList.toggle(
                "completed",
                index + 1 < stageNumber
            );
        });

        progressLines.forEach((line, index) => {
            line.classList.toggle(
                "completed",
                index + 1 < stageNumber
            );
        });

        window.scrollTo({
            top: 0,
            behavior: "smooth"
        });
    }

    // ==========================================
    // RINGKASAN JADWAL
    // ==========================================

    function updateSummary() {
        const selectedDuration = Number(duration.value);

        summaryDate.textContent = formatDate(bookingDate.value);

        summaryTime.textContent = selectedSlot
            ? `${selectedSlot.start} - ${selectedSlot.end}`
            : "-";

        summaryDuration.textContent = selectedDuration
            ? `${selectedDuration} Jam`
            : "-";

        summaryTotal.textContent = selectedDuration
            ? formatRupiah(pricePerHour * selectedDuration)
            : formatRupiah(0);
    }

    function resetSelection() {
        selectedSlot = null;
        startTime.value = "";
        endTime.value = "";
        bookingButton.disabled = true;

        updateSummary();
    }

    // ==========================================
    // RENDER JADWAL
    // ==========================================

    function renderSlots() {
        timeSlots.innerHTML = "";
        resetSelection();

        if (!operational || !duration.value) return;

        const open = toMinutes(operational.open);
        const close = toMinutes(operational.close);
        const selectedDuration = Number(duration.value);

        for (
            let start = open;
            start + selectedDuration * 60 <= close;
            start += 60
        ) {
            const end = start + selectedDuration * 60;

            const startLabel = toTime(start);
            const endLabel = toTime(end);

            const button = document.createElement("button");

            button.type = "button";
            button.className = "time-slot";
            button.textContent = `${startLabel} - ${endLabel}`;

            const past = isPastSlot(start);

            const occupied = reservations.some(item => {
                return overlaps(
                    start,
                    end,
                    toMinutes(item.start),
                    toMinutes(item.end)
                );
            });

            if (past || occupied) {
                button.classList.add("unavailable");
                button.disabled = true;

                button.title = occupied
                    ? "Waktu sudah dipesan"
                    : "Waktu sudah lewat";
            } else {
                button.classList.add("available");

                button.addEventListener("click", function () {
                    document.querySelectorAll(".time-slot").forEach(slot => {
                        slot.classList.remove("selected");
                    });

                    button.classList.add("selected");

                    selectedSlot = {
                        start: startLabel,
                        end: endLabel
                    };

                    startTime.value = startLabel;
                    endTime.value = endLabel;

                    bookingButton.disabled = false;
                    updateSummary();
                });
            }

            timeSlots.appendChild(button);
        }

        scheduleMessage.hidden = timeSlots.children.length > 0;

        if (!timeSlots.children.length) {
            scheduleMessage.textContent =
                "Tidak ada rentang waktu tersedia untuk durasi ini.";
        }
    }

    // ==========================================
    // CEK KETERSEDIAAN
    // ==========================================

    async function loadAvailability() {
        if (!bookingDate.value || !duration.value) {
            timeSlots.innerHTML = "";

            scheduleMessage.hidden = false;
            scheduleMessage.textContent =
                "Pilih tanggal dan durasi untuk melihat jadwal.";

            operational = null;
            reservations = [];

            resetSelection();
            return;
        }

        const currentRequest = ++requestNumber;

        loading = true;
        operational = null;
        reservations = [];

        resetSelection();

        timeSlots.innerHTML = "";
        scheduleMessage.hidden = false;
        scheduleMessage.textContent = "Memuat jadwal...";

        scheduleDateLabel.textContent = formatDate(bookingDate.value);

        try {
            const response = await fetch(
                availabilityUrl +
                "?date=" +
                encodeURIComponent(bookingDate.value)
            );

            const data = await readResponse(response);

            if (currentRequest !== requestNumber) return;

            if (!response.ok || !data.success) {
                throw new Error(data.message || "Gagal memuat jadwal.");
            }

            if (!data.is_open) {
                scheduleMessage.textContent =
                    data.message || "Lapangan tutup pada tanggal tersebut.";
                return;
            }

            operational = data.operational;
            reservations = data.reservations || [];

            renderSlots();

        } catch (error) {
            if (currentRequest !== requestNumber) return;

            scheduleMessage.hidden = false;
            scheduleMessage.textContent =
                error.message || "Terjadi kesalahan saat memuat jadwal.";

        } finally {
            if (currentRequest === requestNumber) {
                loading = false;
            }
        }
    }

    bookingDate.addEventListener("change", function () {
        updateSummary();
        loadAvailability();
    });

    duration.addEventListener("change", function () {
        loadAvailability();
    });

    // ==========================================
    // TAHAP 1 KE TAHAP 2
    // ==========================================

    bookingButton.addEventListener("click", function () {
        if (
            loading ||
            !bookingDate.value ||
            !duration.value ||
            !selectedSlot
        ) {
            alert("Silakan lengkapi tanggal, durasi, dan jadwal.");
            return;
        }

        showStage(2);
    });

    // ==========================================
    // FORM DINAMIS JENIS KEGIATAN
    // ==========================================

    function setFieldsRequired(container, required) {
        container.querySelectorAll("input").forEach(input => {
            input.required = required;
        });
    }

    function updateActivityForm() {
        const activity = activityType.value;

        trainingFields.hidden = activity !== "latihan";
        friendlyFields.hidden = activity !== "friendly_match";

        setFieldsRequired(trainingFields, activity === "latihan");
        setFieldsRequired(friendlyFields, activity === "friendly_match");
    }

    activityType.addEventListener("change", updateActivityForm);

    // ==========================================
    // VALIDASI TAHAP 2
    // ==========================================

    function validateStage2() {
        if (!activityType.value) {
            alert("Silakan pilih jenis kegiatan.");
            activityType.focus();
            return false;
        }

        const activeFields = activityType.value === "latihan"
            ? trainingFields
            : friendlyFields;

        const inputs = activeFields.querySelectorAll("input");

        for (const input of inputs) {
            if (!input.checkValidity()) {
                input.reportValidity();
                return false;
            }
        }

        if (activityType.value === "friendly_match") {
            if (
                teamAName.value.trim().toLowerCase() ===
                teamBName.value.trim().toLowerCase()
            ) {
                alert("Nama Tim A dan Tim B tidak boleh sama.");
                teamBName.focus();
                return false;
            }
        }

        return true;
    }

    // ==========================================
    // RINGKASAN KONFIRMASI
    // ==========================================

    function addTeamDetail(label, value) {
        const row = document.createElement("div");
        row.className = "summary-row";

        const title = document.createElement("span");
        title.textContent = label;

        const content = document.createElement("strong");
        content.textContent = value;

        row.append(title, content);
        confirmTeamDetails.appendChild(row);
    }

    function updateConfirmation() {
        confirmDate.textContent = formatDate(bookingDate.value);

        confirmTime.textContent =
            `${selectedSlot.start} - ${selectedSlot.end}`;

        confirmDuration.textContent = `${duration.value} Jam`;

        confirmActivity.textContent =
            activityType.value === "latihan"
                ? "Latihan"
                : "Friendly Match";

        confirmTeamDetails.innerHTML = "";

        if (activityType.value === "latihan") {
            addTeamDetail("Nama Tim", trainingTeamName.value.trim());
            addTeamDetail("Jumlah Pemain", `${trainingPlayers.value} Orang`);
        } else {
            addTeamDetail("Tim A", teamAName.value.trim());
            addTeamDetail("Pemain Tim A", `${teamAPlayers.value} Orang`);
            addTeamDetail("Tim B", teamBName.value.trim());
            addTeamDetail("Pemain Tim B", `${teamBPlayers.value} Orang`);
        }

        confirmNotes.textContent =
            bookingNotes.value.trim() || "-";

        // Ini hanya estimasi. Total final dihitung backend.
        confirmTotal.textContent = formatRupiah(
            pricePerHour * Number(duration.value)
        );
    }

    // ==========================================
    // NAVIGASI TAHAP 2 DAN 3
    // ==========================================

    document.getElementById("backToStage1").addEventListener(
        "click",
        function () {
            showStage(1);
        }
    );

    document.getElementById("nextToStage3").addEventListener(
        "click",
        function () {
            if (!validateStage2()) return;

            updateConfirmation();
            showStage(3);
        }
    );

    document.getElementById("backToStage2").addEventListener(
        "click",
        function () {
            showStage(2);
        }
    );

    // ==========================================
    // COUNTDOWN PEMBAYARAN
    // ==========================================

    function startCountdown(expirationTime) {
        if (countdownInterval) {
            clearInterval(countdownInterval);
        }

        const expiration = new Date(expirationTime).getTime();

        if (Number.isNaN(expiration)) {
            paymentCountdown.textContent = "--:--";
            return;
        }

        function updateCountdown() {
            const remaining = Math.max(
                0,
                Math.floor((expiration - Date.now()) / 1000)
            );

            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;

            paymentCountdown.textContent =
                `${String(minutes).padStart(2, "0")}:` +
                `${String(seconds).padStart(2, "0")}`;

            if (remaining <= 0) {
                clearInterval(countdownInterval);
                countdownInterval = null;

                paymentReservationStatus.textContent = "Kedaluwarsa";
                paymentStatus.textContent = "Kedaluwarsa";

                submitPayment.disabled = true;
                paymentProof.disabled = true;

                paymentMessage.textContent =
                    "Waktu pembayaran telah habis. Jadwal tidak lagi ditahan.";
                paymentMessage.hidden = false;

                paymentCountdown.textContent = "00:00";
            }
        }

        updateCountdown();

        if (expiration > Date.now()) {
            countdownInterval = setInterval(updateCountdown, 1000);
        }
    }

    // ==========================================
    // TAMPILKAN DATA PEMBAYARAN
    // ==========================================

    function displayPayment(data) {
        const reservation = data.reservation;
        const payment = data.payment;

        paymentTransactionCode.textContent = payment.transaction_code;
        paymentReservationStatus.textContent = "Ditahan";
        paymentStatus.textContent = "Menunggu";

        paymentFieldName.textContent = reservation.field;
        paymentDate.textContent = formatDate(reservation.date);

        paymentTime.textContent =
            `${reservation.start_time} - ${reservation.end_time}`;

        paymentTotal.textContent = formatRupiah(payment.amount);

        // Perbarui total dengan harga final dari backend.
        confirmTotal.textContent = formatRupiah(payment.amount);
        summaryTotal.textContent = formatRupiah(payment.amount);

        startCountdown(reservation.hold_expires_at);
    }

    // ==========================================
    // KONFIRMASI RESERVASI KE BACKEND
    // ==========================================

    async function confirmReservation() {
        if (reservationCreated || loading) return;

        if (!selectedSlot) {
            alert("Silakan pilih jadwal terlebih dahulu.");
            showStage(1);
            return;
        }

        if (!validateStage2()) {
            showStage(2);
            return;
        }

        const payload = {
            field_id: fieldId,
            date: bookingDate.value,
            start_time: startTime.value,
            end_time: endTime.value,
            duration: Number(duration.value),
            activity_type: activityType.value,
            notes: bookingNotes.value.trim()
        };

        if (activityType.value === "latihan") {
            payload.training_team_name = trainingTeamName.value.trim();
            payload.training_players = Number(trainingPlayers.value);
        } else {
            payload.team_a_name = teamAName.value.trim();
            payload.team_b_name = teamBName.value.trim();
            payload.team_a_players = Number(teamAPlayers.value);
            payload.team_b_players = Number(teamBPlayers.value);
        }

        loading = true;
        confirmButton.disabled = true;
        confirmButton.textContent = "Memproses reservasi...";

        try {
            const response = await fetch("/reservations/confirm", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await readResponse(response);

            if (!response.ok || !data.success) {
                throw new Error(
                    data.message || "Gagal membuat reservasi."
                );
            }

            if (!data.reservation || !data.payment) {
                throw new Error(
                    "Data reservasi dari server tidak lengkap."
                );
            }

            reservationCreated = true;

            displayPayment(data);

            // Cegah pembuatan reservasi kedua dari tombol yang sama.
            confirmButton.disabled = true;
            confirmButton.textContent = "Reservasi Berhasil";

            // Pembayaran belum terintegrasi, jadi tetap nonaktif.
            paymentProof.disabled = true;
            submitPayment.disabled = true;

            showStage(4);

        } catch (error) {
            alert(error.message || "Terjadi kesalahan saat membuat reservasi.");

        } finally {
            loading = false;

            if (!reservationCreated) {
                confirmButton.disabled = false;
                confirmButton.textContent = "Konfirmasi Reservasi";
            }
        }
    }

    confirmButton.addEventListener("click", confirmReservation);

    // ==========================================
    // NAVIGASI TAHAP 4
    // ==========================================

    document.getElementById("backToStage3").addEventListener(
        "click",
        function () {
            if (reservationCreated) {
                showStage(4);
                return;
            }

            showStage(3);
        }
    );

    // ==========================================
    // PEMBAYARAN
    // BELUM TERHUBUNG KE BACKEND
    // ==========================================

    submitPayment.addEventListener("click", function () {
        alert("Fitur unggah bukti pembayaran belum terhubung ke backend.");
    });

    // ==========================================
    // INISIALISASI
    // ==========================================

    updateSummary();
    updateActivityForm();
    showStage(1);
});
