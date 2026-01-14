/* ---------------------------------------------------------
   STICKY HEADERS — Custom implementation for DataTables

   Provides:
   - Sticky column headers (top) when scrolling down
   - Sticky first column (left) when scrolling right
   - Headers scroll horizontally with table content
--------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", function () {

    // Track all managed tables
    const managedTables = [];

    // Initialize sticky behavior for all DataTables
    function initStickyHeaders() {
        document.querySelectorAll('.dataTables_wrapper').forEach(wrapper => {
            const table = wrapper.querySelector('table.dataTable');
            if (!table) return;

            const thead = table.querySelector('thead');
            if (!thead) return;

            // Skip if already initialized
            if (wrapper.dataset.stickyInit) return;
            wrapper.dataset.stickyInit = 'true';

            // Create container for the fixed header
            const cloneContainer = document.createElement('div');
            cloneContainer.classList.add('sticky-header-container');
            cloneContainer.style.cssText = `
                position: fixed;
                top: 0;
                z-index: 1000;
                display: none;
                overflow: hidden;
                background: #f4f4f4;
                box-shadow: 0 2px 4px rgba(0,0,0,0.15);
            `;

            // Inner scroll wrapper - scrolls horizontally with sticky first column
            const scrollWrapper = document.createElement('div');
            scrollWrapper.classList.add('sticky-header-scroll');
            scrollWrapper.style.cssText = `
                overflow-x: auto;
                overflow-y: hidden;
            `;

            // Clone the entire table but we'll only show thead
            const cloneTable = table.cloneNode(true);
            cloneTable.classList.add('sticky-header-table');

            // Remove tbody from clone - we only want header
            const cloneTbody = cloneTable.querySelector('tbody');
            if (cloneTbody) cloneTbody.remove();

            // Remove any DataTables-added elements
            cloneTable.querySelectorAll('.dataTables_empty').forEach(el => el.remove());

            scrollWrapper.appendChild(cloneTable);
            cloneContainer.appendChild(scrollWrapper);
            document.body.appendChild(cloneContainer);

            // Store reference
            const tableData = {
                wrapper,
                table,
                thead,
                cloneContainer,
                scrollWrapper,
                cloneTable,
                isSticky: false
            };
            managedTables.push(tableData);

            // Sync horizontal scroll - listen on the table itself (it's the scroll container now)
            table.addEventListener('scroll', () => {
                if (tableData.isSticky) {
                    scrollWrapper.scrollLeft = table.scrollLeft;
                }
            });
        });
    }

    // Sync column widths between original and clone
    function syncColumnWidths(tableData) {
        const { table, cloneTable } = tableData;

        // Get original header cells
        const originalCells = table.querySelectorAll('thead th');
        const cloneCells = cloneTable.querySelectorAll('thead th');

        // First, set table to same width
        const tableWidth = table.offsetWidth;
        cloneTable.style.width = tableWidth + 'px';
        cloneTable.style.minWidth = tableWidth + 'px';
        cloneTable.style.tableLayout = 'fixed';

        // Copy exact widths from each original cell
        originalCells.forEach((cell, i) => {
            if (cloneCells[i]) {
                const width = cell.getBoundingClientRect().width;
                cloneCells[i].style.width = width + 'px';
                cloneCells[i].style.minWidth = width + 'px';
                cloneCells[i].style.maxWidth = width + 'px';
                cloneCells[i].style.boxSizing = 'border-box';

                // Copy padding and other computed styles
                const computed = window.getComputedStyle(cell);
                cloneCells[i].style.padding = computed.padding;
            }
        });
    }

    // Check visibility and update sticky state
    function updateStickyState() {
        managedTables.forEach(tableData => {
            const { wrapper, table, thead, cloneContainer, scrollWrapper, isSticky } = tableData;

            // Check if table's tab is visible
            const tabContent = wrapper.closest('.tab-content');
            if (tabContent && !tabContent.classList.contains('active')) {
                if (tableData.isSticky) {
                    cloneContainer.style.display = 'none';
                    tableData.isSticky = false;
                }
                return;
            }

            const wrapperRect = wrapper.getBoundingClientRect();
            const theadRect = thead.getBoundingClientRect();
            const tableRect = table.getBoundingClientRect();

            // Check if original header is above viewport AND table is still visible
            const shouldBeSticky = theadRect.top < 0 && wrapperRect.bottom > 100;

            if (shouldBeSticky && !tableData.isSticky) {
                // Sync widths before showing
                syncColumnWidths(tableData);

                // Position container to match table position
                const tableRect = table.getBoundingClientRect();
                cloneContainer.style.left = tableRect.left + 'px';
                cloneContainer.style.width = tableRect.width + 'px';

                // Match scroll position
                scrollWrapper.scrollLeft = table.scrollLeft;

                cloneContainer.style.display = 'block';
                tableData.isSticky = true;
            } else if (!shouldBeSticky && tableData.isSticky) {
                cloneContainer.style.display = 'none';
                tableData.isSticky = false;
            } else if (shouldBeSticky && tableData.isSticky) {
                // Update position continuously while sticky
                const tableRect = table.getBoundingClientRect();
                cloneContainer.style.left = tableRect.left + 'px';
                cloneContainer.style.width = tableRect.width + 'px';
            }
        });
    }

    // Update on resize
    function handleResize() {
        managedTables.forEach(tableData => {
            if (tableData.isSticky) {
                syncColumnWidths(tableData);
                const tableRect = tableData.table.getBoundingClientRect();
                tableData.cloneContainer.style.left = tableRect.left + 'px';
                tableData.cloneContainer.style.width = tableRect.width + 'px';
            }
        });
    }

    // Initialize after DataTables loads
    setTimeout(initStickyHeaders, 300);

    // Re-init when tabs change
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            // Hide all sticky headers first
            managedTables.forEach(td => {
                td.cloneContainer.style.display = 'none';
                td.isSticky = false;
            });

            setTimeout(() => {
                initStickyHeaders();
                updateStickyState();
            }, 150);
        });
    });

    // Listen for scroll and resize
    window.addEventListener('scroll', updateStickyState, { passive: true });
    window.addEventListener('resize', handleResize, { passive: true });

    // Also check periodically for DataTables that initialize later
    let initAttempts = 0;
    const initInterval = setInterval(() => {
        initStickyHeaders();
        initAttempts++;
        if (initAttempts > 10) clearInterval(initInterval);
    }, 500);

});
