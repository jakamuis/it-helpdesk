(() => {
    const alerts = document.querySelector('[data-ticket-feed]');
    if (!alerts) return;
    const feed = new URL(alerts.dataset.ticketFeed, location.href);
    const view = alerts.dataset.view;
    const seen = new Set();
    let after = Number(alerts.dataset.after);
    let pending = false;
    const nativeTable = '.lti-native table.search-results';
    let renderedTable;
    let renderedRows;

    async function get(url, json = true) {
        const response = await fetch(url, {
            cache: 'no-store',
            headers: {'Accept': json ? 'application/json' : 'text/html'},
            signal: AbortSignal.timeout(10000),
        });
        if (!response.ok || response.redirected) throw new Error('Ticket feed unavailable');
        return json ? response.json() : response.text();
    }

    function idFromLink(link) {
        const url = new URL(link.href, location.href);
        if (!url.pathname.endsWith('/front/ticket.form.php')) return 0;
        return Number(url.searchParams.get('id')) || 0;
    }

    function applyTitle(cell, ticket) {
        const link = document.createElement('a');
        link.href = alerts.dataset.ticketUrl + ticket.id;
        link.textContent = `#${ticket.id}`;
        const bold = document.createElement('strong');
        if (ticket.host) {
            bold.textContent = ticket.host;
            cell.replaceChildren(link, ' · ', bold, document.createElement('br'), ticket.summary);
        } else {
            bold.textContent = ticket.site;
            cell.replaceChildren(link, document.createElement('br'), ticket.name + ' - ', bold, ' - ' + ticket.summary);
        }
    }

    async function formatNativeTitles() {
        const cells = new Map();
        document.querySelectorAll(`${nativeTable} td[data-searchopt-content-id="1"]`).forEach(cell => {
            const link = [...cell.querySelectorAll('a[href]')].find(a => idFromLink(a));
            if (link) cells.set(idFromLink(link), cell);
        });
        if (!cells.size) return;
        const url = new URL(feed);
        url.searchParams.set('visible', [...cells.keys()].join(','));
        const data = await get(url);
        for (const ticket of data.tickets) {
            const cell = cells.get(ticket.id);
            if (!cell?.isConnected || (!ticket.site && !ticket.host)) continue;
            const signature = JSON.stringify(ticket);
            if (cell.dataset.ticketTitle !== signature) {
                applyTitle(cell, ticket);
                cell.dataset.ticketTitle = signature;
            }
        }
    }

    async function refreshNative() {
        const table = document.querySelector(nativeTable);
        const form = table?.closest('form.masssearchform');
        const pageUrl = location.href;
        if (!form || form.querySelector('input:checked') || form.contains(document.activeElement)) return false;
        const url = new URL(pageUrl);
        url.searchParams.set('start', form.dataset.start || '0');
        url.searchParams.set('_ticket_rows', '1');
        const incoming = new DOMParser().parseFromString(await get(url, false), 'text/html');
        const fresh = incoming.querySelector('table.search-results');
        if (!fresh || pageUrl !== location.href || table !== document.querySelector(nativeTable)
            || form.querySelector('input:checked') || form.contains(document.activeElement)) return false;

        const scroll = table.parentElement;
        const left = scroll.scrollLeft;
        const top = scroll.scrollTop;
        const x = window.scrollX;
        const y = window.scrollY;
        const newForm = fresh.closest('form');
        const oldBody = table.tBodies[0];
        const newBody = fresh.tBodies[0];
        newBody.querySelectorAll('[form]').forEach(input => input.setAttribute('form', form.id));
        const markup = newBody.innerHTML;
        if (table !== renderedTable || markup !== renderedRows) {
            if (oldBody.innerHTML !== markup) oldBody.replaceWith(newBody);
            renderedTable = table;
            renderedRows = markup;
        }
        table.tHead.rows[0].style.display = fresh.tHead.rows[0].style.display;
        if (form.dataset.count !== newForm.dataset.count) {
            form.dataset.count = newForm.dataset.count;
            const updatePager = (oldScope, newScope) => {
                const oldFooter = oldScope?.querySelector('.search-footer');
                const newFooter = newScope?.querySelector('.search-footer');
                if (oldFooter && newFooter) oldFooter.replaceWith(newFooter);
                else if (oldFooter) oldFooter.remove();
                else if (newFooter) oldScope.append(newFooter);
            };
            updatePager(form, newForm);
        }
        scroll.scrollLeft = left;
        scroll.scrollTop = top;
        window.scrollTo(x, y);
        return true;
    }

    function updateRows(selector, markup) {
        const current = document.querySelector(selector);
        if (!current || !markup) return;
        const fresh = new DOMParser().parseFromString(markup, 'text/html').querySelector(selector);
        const body = current.querySelector('tbody');
        if (fresh && body.innerHTML !== fresh.querySelector('tbody').innerHTML) {
            const scroller = body.closest('.lti-scroll');
            const left = scroller?.scrollLeft ?? 0;
            const top = scroller?.scrollTop ?? 0;
            const x = window.scrollX;
            const y = window.scrollY;
            body.replaceWith(fresh.querySelector('tbody'));
            if (scroller) {
                scroller.scrollLeft = left;
                scroller.scrollTop = top;
            }
            window.scrollTo(x, y);
        }
    }

    function notify(ticket) {
        if (seen.has(ticket.id)) return;
        seen.add(ticket.id);
        const message = document.createElement('div');
        message.className = 'lti-ticket-alert';
        const link = document.createElement('a');
        link.href = alerts.dataset.ticketUrl + ticket.id;
        link.textContent = `Tiket baru #${ticket.id} · ${ticket.summary}`;
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.setAttribute('aria-label', `Tutup notifikasi tiket #${ticket.id}`);
        dismiss.textContent = '×';
        dismiss.addEventListener('click', () => message.remove());
        message.append(link, dismiss);
        alerts.append(message);
    }

    async function poll() {
        if (pending) return;
        pending = true;
        try {
            const url = new URL(feed);
            url.searchParams.set('view', view);
            const q = new URLSearchParams(location.search).get('q');
            if (q) url.searchParams.set('q', q);
            let batch;
            do {
                url.searchParams.set('after', after);
                batch = await get(url);
                batch.tickets.forEach(notify);
                after = batch.after;
                url.searchParams.set('through', batch.through);
                // Request the dashboard fragments only with the first batch.
                if (batch.incident) updateRows('[data-live-incidents]', batch.incident);
                if (batch.requests) updateRows('[data-live-requests]', batch.requests);
                url.searchParams.delete('view');
            } while (batch.more);
            if (view === 'incident') {
                // A follow-up can change which rows match the current search.
                await refreshNative();
                await formatNativeTitles();
            }
        } catch (error) {
            // Keep the last successful cursor for the next poll or online event.
        } finally {
            pending = false;
        }
    }

    if (view === 'incident') {
        formatNativeTitles().catch(() => {});
        const container = document.querySelector('.lti-native');
        if (container) {
            new MutationObserver(records => {
                if (records.some(record => [...record.addedNodes].some(node =>
                    node.nodeType === 1 && (node.matches('table.search-results') || node.querySelector('table.search-results'))
                ))) {
                    formatNativeTitles().catch(() => {});
                }
            }).observe(container, {subtree: true, childList: true});
        }
    }
    setInterval(poll, 15000);
    window.addEventListener('online', poll);
})();
