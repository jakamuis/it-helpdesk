/* Keep native GLPI forms, URLs and AJAX behavior inside the workspace shell. */
(() => {
    const script = document.currentScript;
    const base = script ? new URL('../', script.src) : null;
    const mount = async () => {
        if (!base || document.querySelector('.lti')) return;
        const path = window.location.pathname;
        // Never wrap API, AJAX, download, print, or the original GLPI landing page.
        const native = /\/front\/(ticket(?:\.form)?|computer(?:\.form)?|monitor(?:\.form)?|printer(?:\.form)?|user(?:\.form)?)\.php$/.test(path);
        const plugin = /\/plugins\/(itrequest|providersla)\/front\/(index|report)\.php$/.test(path);
        if ((!native && !plugin) || new URLSearchParams(location.search).has('display_type')) return;
        const main = document.querySelector('main#page');
        if (!main) return;
        let page = 'incident';
        for (const type of ['Computer', 'Monitor', 'Printer']) {
            if (path.includes('/front/' + type.toLowerCase())) page = type;
        }
        if (path.includes('/front/user')) page = 'users';
        if (path.includes('/plugins/itrequest/')) page = 'request';
        if (path.includes('/plugins/providersla/')) page = 'more';
        try {
            const url = new URL('front/shell.php', base); url.searchParams.set('page', page);
            const response = await fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            const data = await response.json();
            if (!data.sidebar || document.querySelector('.lti')) return;
            const css = document.createElement('link'); css.rel = 'stylesheet';
            css.href = new URL('public/app.css?v=20261115e', base).href; document.head.append(css);
            const shell = document.createElement('div'); shell.className = 'lti';
            const template = document.createElement('template'); template.innerHTML = data.sidebar;
            shell.append(template.content);
            const body = document.createElement('div'); body.className = 'lti-main';
            const content = document.createElement('div'); content.className = 'lti-content lti-native-detail';
            while (main.firstChild) content.append(main.firstChild);
            body.append(content); shell.append(body); main.append(shell);
        } catch (error) {
            console.warn('Layanan TI: native navigation remains available.', error);
        }
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once:true});
    else mount();
})();
