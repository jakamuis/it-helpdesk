const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('poll starts at the page baseline, recovers from an outage and notifies each ID once', async () => {
    let poll;
    let online;
    const requests = [];
    const alerts = [];
    function element() {
        return {
            children: [],
            append(...children) { this.children.push(...children); },
            addEventListener() {},
            setAttribute() {},
        };
    }
    const anchor = {
        dataset: {ticketFeed: '/feed', view: 'request', after: '405', ticketUrl: '/front/ticket.form.php?id='},
        append(message) { alerts.push(message); },
    };
    const location = new URL('https://glpi.invalid/list?page=request&q=Printer');
    const events = [
        Error('Offline'),
        {tickets: [{id: 406, summary: 'Laptop'}, {id: 407, summary: 'Internet'}], after: 407, through: 409, more: true},
        {tickets: [{id: 409, summary: 'Printer'}], after: 409, through: 409, more: false},
        {tickets: [{id: 409, summary: 'Updated Printer'}], after: 409, through: 409, more: false},
    ];
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../public/ticket-feed.js'), 'utf8'), {
        URL, URLSearchParams, location, AbortSignal,
        document: {querySelector: () => anchor, createElement: element},
        window: {addEventListener: (event, callback) => { if (event === 'online') online = callback; }},
        setInterval: (callback, delay) => { assert.equal(delay, 15000); poll = callback; },
        fetch: async url => {
            requests.push(new URL(url));
            const event = events.shift();
            if (event instanceof Error) throw event;
            return {ok: true, json: () => event};
        },
    });
    assert.equal(requests.length, 0);
    await poll();
    assert.equal(alerts.length, 0);
    await online();
    await poll();
    assert.deepEqual(requests.map(url => url.searchParams.get('after')), ['405', '405', '407', '409']);
    assert.equal(requests[2].searchParams.get('through'), '409');
    assert.equal(requests[1].searchParams.get('q'), 'Printer');
    assert.deepEqual(alerts.map(alert => alert.children[0].href), [
        '/front/ticket.form.php?id=406', '/front/ticket.form.php?id=407', '/front/ticket.form.php?id=409',
    ]);
    assert.equal(alerts[0].children[0].textContent, 'Tiket baru #406 · Laptop');
});
