<?php
/** LOCAL ONLY: creates fixtures inside an outer transaction, then rolls everything back. */
if (PHP_SAPI !== 'cli' || getenv('PROVIDERSLA_TEST_LOCAL') !== '1') { exit(2); }
require dirname(__DIR__, 3) . '/vendor/autoload.php';
$kernel = new Glpi\Kernel\Kernel(); $kernel->boot();
require_once dirname(__DIR__) . '/inc/service.class.php';
require_once dirname(__DIR__) . '/inc/ticket.class.php';
require_once dirname(__DIR__) . '/inc/sidebar.class.php';
function check($ok, string $message): void { if (!$ok) { throw new RuntimeException($message); } }
function rejects(callable $fn): void { try { $fn(); } catch (InvalidArgumentException) { return; } throw new RuntimeException('Expected invalid input rejection'); }
$user = new User(); check($user->getFromDBbyName('glpi'), 'Local fixture user');
$auth = new Auth(); $auth->auth_succeded = true; $auth->user = $user; Session::init($auth);
$DB->beginTransaction();
try {
    $ticket = new Ticket();
    $id = $ticket->add(['name' => 'LOCAL PROVIDER SLA TRANSACTION TEST', 'content' => 'Rollback-only fixture',
        'date' => gmdate('Y-m-d H:i:s', time() - 4 * 3600), 'entities_id' => 0,
        '_disablenotif' => true, '_actors' => ['assign' => [['itemtype' => 'User', 'items_id' => (int) $user->getID(), 'use_notification' => 0]]]]);
    check((bool) $id, 'Ticket created');
    $input = ['provider_name' => 'ISP TEST', 'transferred_at' => PluginProviderslaClock::date(time() - 7200, 'Y-m-d\TH:i'),
        'target_hours' => '2', 'transfer_evidence' => 'Test escalation, not sent externally', 'circuit' => 'LOCAL-ONLY'];
    PluginProviderslaService::mutate($id, 'start', $input);
    $rows = array_values(PluginProviderslaService::rows($id));
    check(count($rows) === 1, 'One episode'); $episode = $rows[0];
    $ticket->getFromDB($id); check((int) $ticket->fields['status'] === Ticket::WAITING, 'Pending pauses native TTR');
    ob_start(); PluginProviderslaSidebar::show(['item' => $ticket]); $sidebar = ob_get_clean();
    check(str_contains($sidebar, 'ISP TEST') && str_contains($sidebar, 'Catat layanan pulih')
        && !str_contains($sidebar, 'Eskalasi ke Vendor') && !str_contains($sidebar, '<form'), 'Active sidebar offers recovery without nested forms');
    ob_start(); PluginProviderslaSidebar::form($id, 'restore'); $quickForm = ob_get_clean();
    check(str_contains($quickForm, 'recovery_evidence') && str_contains($quickForm, '_glpi_csrf_token'), 'Quick recovery form and CSRF');
    rejects(fn() => PluginProviderslaSidebar::form($id, 'start'));
    rejects(fn() => PluginProviderslaService::mutate($id, 'start', $input));
    rejects(fn() => PluginProviderslaService::mutate($id, 'restore', ['episode_id' => $episode['id'], 'restored_at' => '2999-01-01T00:00', 'recovery_evidence' => 'future']));
    check(count(PluginProviderslaService::rows($id)) === 1, 'Failed mutations rolled back');
    PluginProviderslaService::mutate($id, 'reference', ['episode_id' => $episode['id'], 'reference' => 'ISP-123']);
    $after = array_values(PluginProviderslaService::rows($id))[0];
    check($after['transferred_epoch'] === $episode['transferred_epoch'], 'Reference does not reset clock');
    PluginProviderslaService::mutate($id, 'restore', ['episode_id' => $episode['id'],
        'restored_at' => PluginProviderslaClock::date(time() - 900, 'Y-m-d\TH:i'), 'recovery_evidence' => 'Verified local fixture']);
    $after = array_values(PluginProviderslaService::rows($id))[0];
    check($after['open_ticket_id'] === null && $after['restored_epoch'] !== null, 'Episode closed');
    check(PluginProviderslaClock::metrics($after, time())['status'] === 'Memenuhi', 'SLA met');
    $ticket->getFromDB($id); check((int) $ticket->fields['status'] !== Ticket::WAITING, 'Helpdesk resumed');
    rejects(fn() => PluginProviderslaService::mutate($id, 'restore', ['episode_id' => $episode['id']]));
    rejects(fn() => PluginProviderslaService::mutate($id, 'start', $input));
    ob_start(); PluginProviderslaTicket::show($id); $html = ob_get_clean();
    check(str_contains($html, 'ISP TEST') && str_contains($html, '_glpi_csrf_token'), 'Native tab renders with CSRF');
    PluginProviderslaService::mutate($id, 'void', ['episode_id' => $episode['id'], 'reason' => 'Fixture correction']);
    $after = array_values(PluginProviderslaService::rows($id))[0];
    check((int) $after['is_void'] === 1, 'Void preserves evidence');
    check(count($DB->request(['FROM' => PluginProviderslaService::EVENTS, 'WHERE' => ['tickets_id' => $id]])) === 4, 'Append-only audit');
    $input['transferred_at'] = PluginProviderslaClock::date(time() - 600, 'Y-m-d\TH:i');
    $input['suppliers_id'] = 999999;
    rejects(fn() => PluginProviderslaService::mutate($id, 'start', $input));
    $supplier = new Supplier();
    $supplierId = $supplier->add(['name' => "ISP O'Reilly", 'entities_id' => 0]);
    check((bool) $supplierId, 'Supplier fixture');
    $input['suppliers_id'] = $supplierId;
    $input['target_hours'] = '';
    PluginProviderslaService::mutate($id, 'start', $input);
    $all = array_values(PluginProviderslaService::rows($id));
    $second = $all[count($all) - 1];
    check($second['provider_name'] === "ISP O'Reilly", 'Supplier snapshot and raw apostrophe');
    check($second['target_seconds'] === null, 'Optional target preserved');
    check(count((new Supplier_Ticket())->find(['tickets_id' => $id, 'suppliers_id' => $supplierId])) === 1, 'Native supplier actor linked');
    PluginProviderslaService::mutate($id, 'void', ['episode_id' => $second['id'], 'reason' => 'Provider attribution correction']);
    $ticket->getFromDB($id);
    check((int) $ticket->fields['status'] !== Ticket::WAITING, 'Cancellation resumes Helpdesk');
    ob_start(); PluginProviderslaSidebar::show(['item' => $ticket]); $sidebar = ob_get_clean();
    check(str_contains($sidebar, 'Eskalasi ke Vendor') && !str_contains($sidebar, '<form'), 'Ticket sidebar offers direct assignment');
    ob_start(); PluginProviderslaSidebar::form($id, 'start'); $quickForm = ob_get_clean();
    check(str_contains($quickForm, 'return_to') && str_contains($quickForm, '_use_current_time')
        && !str_contains($quickForm, 'name="target_hours"'), 'Quick assignment defaults to save time without target');
    $before = time();
    PluginProviderslaService::mutate($id, 'start', ['provider_name' => 'QUICK ISP', '_use_current_time' => '1',
        'transfer_evidence' => 'Local quick assignment fixture', 'reference' => 'INC-PRINTER-001', 'customer_sid' => 'SID-000123']);
    $quick = array_values(array_filter(PluginProviderslaService::rows($id), fn($r) => empty($r['is_void']) && $r['restored_epoch'] === null))[0];
    check((int) $quick['transferred_epoch'] >= $before && $quick['target_seconds'] === null, 'Quick assignment uses actual save time, no target');
    check($quick['reference'] === 'INC-PRINTER-001' && $quick['customer_sid'] === 'SID-000123', 'Incident and SID stored separately');
    PluginProviderslaService::mutate($id, 'reference', ['episode_id' => $quick['id'], 'reference' => 'INC-PRINTER-002', 'customer_sid' => 'SID-000456']);
    $updated = array_values(array_filter(PluginProviderslaService::rows($id), fn($r) => (int) $r['id'] === (int) $quick['id']))[0];
    check($updated['customer_sid'] === 'SID-000456' && $updated['reference'] === 'INC-PRINTER-002'
        && $updated['transferred_epoch'] === $quick['transferred_epoch'], 'Incident and SID correction preserves clock');
    PluginProviderslaService::mutate($id, 'restore', ['episode_id' => $quick['id'], '_use_current_time' => '1',
        'recovery_evidence' => 'Local quick verification fixture']);
    $ticket->getFromDB($id);
    check((int) $ticket->fields['status'] !== Ticket::WAITING, 'Quick recovery resumes Helpdesk');
    ob_start(); PluginProviderslaSidebar::show(['item' => $ticket, 'options' => ['template_preview' => true]]);
    check(ob_get_clean() === '', 'No assignment in template preview');
    $saved = $_SESSION['glpiactiveprofile']['ticket']; $_SESSION['glpiactiveprofile']['ticket'] = 0;
    try { PluginProviderslaService::ticket($id); throw new RuntimeException('ACL bypass'); }
    catch (Glpi\Exception\Http\AccessDeniedHttpException) {}
    ob_start(); PluginProviderslaSidebar::show(['item' => $ticket]);
    check(ob_get_clean() === '', 'Sidebar hidden without technician ticket rights');
    $_SESSION['glpiactiveprofile']['ticket'] = $saved;
    echo "Integration: workflow, overlap/duplicate, future date, audit, native tab/sidebar, quick assignment/recovery and ACL passed\n";
} finally { $DB->rollBack(); }
