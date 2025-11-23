/* ---------------------------------------------------------
   BIRTHDAYS — Homepage scroll cards
--------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("birthdayScroll");
    if (!container) return;

    fetch("/api/birthdays")
        .then(res => res.json())
        .then(data => {
            container.innerHTML = "";
            data.forEach(item => {
                const card = document.createElement("div");
                card.className = "bday-card";
                card.innerHTML = `
                    <div class="name">${item.label}</div>
                    <div class="date">${item.display_date}</div>
                    <div class="days_from_today">${item.days_from_today}</div>
                `;
                container.appendChild(card);
            });
        });
});
