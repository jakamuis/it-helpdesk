const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const webhook = fs.readFileSync(path.join(__dirname, '../glpi-ticket-webhook.js'), 'utf8');
const media = require('../media-type.json');

function deliver(overrides = {}) {
    const writes = [];
    class HttpRequest {
        addHeader() {}
        get() { return '{"session_token":"fixture"}'; }
        getStatus() { return 200; }
        post(url, input) {
            writes.push({method: 'POST', url, input: JSON.parse(input).input});
            return '{"id":789}';
        }
        put(url, input) {
            writes.push({method: 'PUT', url, input: JSON.parse(input).input});
            return '{"id":789}';
        }
    }
    const result = new Function('value', 'HttpRequest', 'Zabbix', webhook)(JSON.stringify({
        alert_subject: '[Zabbix] Unavailable by ICMP ping',
        alert_message: 'The monitored host is unavailable.',
        host_name: 'SGI Narogong FS',
        event_source: '0',
        event_value: '1',
        event_update_status: '0',
        event_recovery_value: '0',
        event_nseverity: '4',
        event_id: '222',
        trigger_id: '333',
        zabbix_url: 'https://monitor.invalid/',
        glpi_url: 'https://glpi.invalid/',
        glpi_token: 'fixture',
        ...overrides,
    }), HttpRequest, {log() {}});
    return {writes, tags: JSON.parse(result).tags};
}

test('media export and source contain the same webhook and the full host macro', () => {
    assert.equal(media.script.replace(/\r\n/g, '\n'), webhook.trimEnd());
    assert.equal(media.parameters.find(parameter => parameter.name === 'host_name').value, '{HOST.NAME}');
});

test('new High problem uses the full host and keeps the problem in the GLPI title', () => {
    const {writes, tags} = deliver();
    assert.equal(writes.length, 1);
    assert.equal(writes[0].input.name, '[Zabbix] Unavailable by ICMP ping');
    assert.match(writes[0].input.content, /^\[HELPDESK_ZABBIX_V1:SGI%20Narogong%20FS\]/);
    assert.equal(tags.__zbx_glpi_ticket_id, 789);
});

test('low severity does not create a ticket', () => {
    assert.deepEqual(deliver({event_nseverity: '3'}).writes, []);
});

test('update and recovery retain the existing title and creation metadata', () => {
    const update = deliver({event_update_status: '1', glpi_ticket_id: '42'}).writes;
    const recovery = deliver({event_value: '0', glpi_ticket_id: '42'}).writes;
    assert.equal(update[0].input.name, undefined);
    assert.equal(update[1].input.items_id, '42');
    assert.equal(recovery.length, 1);
    assert.equal(recovery[0].input.items_id, '42');
});
