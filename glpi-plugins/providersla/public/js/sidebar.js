/* Delegated events also work when GLPI reloads the ticket's main tab through AJAX. */
(() => {
    'use strict';
    document.addEventListener('click', async (event) => {
        const trigger = event.target.closest('[data-providersla-dialog]');
        if (!trigger) return;
        event.preventDefault();
        if (document.querySelector('.providersla-dialog')) return;

        const dialog = document.createElement('dialog');
        dialog.className = 'providersla-dialog';
        dialog.setAttribute('aria-labelledby', 'providersla-dialog-title');
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'btn-close providersla-dialog-close';
        close.setAttribute('aria-label', 'Tutup');
        close.dataset.providerslaClose = '';
        const content = document.createElement('div');
        content.setAttribute('aria-live', 'polite');
        content.textContent = 'Memuat form provider…';
        dialog.append(close, content);
        document.body.append(dialog); // Never nest the provider form inside GLPI's ticket form.
        const controller = new AbortController();
        dialog.addEventListener('close', () => {
            controller.abort();
            dialog.remove();
            if (trigger.isConnected) trigger.focus();
        }, {once: true});
        dialog.addEventListener('click', (click) => {
            if (click.target.closest('[data-providersla-close]')) dialog.close();
        });
        dialog.addEventListener('submit', (submit) => {
            const button = submit.submitter;
            if (button) {
                button.disabled = true;
                button.textContent = 'Menyimpan…';
            }
        });
        dialog.showModal();
        try {
            const response = await fetch(trigger.dataset.providerslaDialog, {
                credentials: 'same-origin', signal: controller.signal,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const html = await response.text();
            if (!response.ok || response.redirected || !html.includes('providersla-dialog-title')) {
                content.textContent = response.status === 409
                    ? 'Status pengalihan sudah berubah. Tutup form dan muat ulang tiket.'
                    : 'Form tidak dapat dimuat. Periksa sesi login dan hak Update tiket, lalu muat ulang.';
                return;
            }
            content.innerHTML = html;
            content.querySelector('select, input:not([type="hidden"]), textarea')?.focus();
        } catch (error) {
            if (error.name !== 'AbortError') content.textContent = 'Koneksi gagal. Tutup form dan coba lagi.';
        }
    });
})();
