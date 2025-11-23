/* ---------------------------------------------------------
   TABS — universal across all pages
--------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", function () {
    const tabs = document.querySelectorAll(".tab");
    const contents = document.querySelectorAll(".tab-content");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.dataset.target;

            // Remove active class everywhere
            tabs.forEach(t => t.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            // Activate the selected tab + content
            tab.classList.add("active");
            document.querySelector(`.${target}`).classList.add("active");
        });
    });
});
