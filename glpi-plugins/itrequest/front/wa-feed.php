<?php
/** Opt-in, read-only machine feed. No session, requester payload or free-text notes are returned. */
require_once dirname(__DIR__, 3) . '/inc/includes.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$secret = (string) getenv('ITREQUEST_BRIDGE_TOKEN');
$entity = getenv('ITREQUEST_BRIDGE_ENTITY');
$auth = (string) ($_SERVER['HTTP_AUTHORIZATION'] ?? '');
if (!Plugin::isPluginActive('itrequest') || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET'
    || strlen($secret) < 32 || $entity === false || !ctype_digit($entity)
    || !hash_equals('Bearer ' . $secret, $auth)) {
    http_response_code(403); echo json_encode(['error' => 'Forbidden']); exit;
}
require_once dirname(__DIR__) . '/inc/service.class.php';
global $DB;
$s = PluginItrequestService::class;
$after = filter_var($_GET['after'] ?? 0, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
if ($after === false) { http_response_code(400); echo json_encode(['error' => 'Invalid cursor']); exit; }
// Entity filtering occurs in the DB query, not after a global limit.
$events = iterator_to_array($DB->request([
    'SELECT' => ['e.id', 'e.action', 'r.id AS request_id', 'r.created_at', 'c.chat_id'],
    'FROM' => $s::PREFIX . 'events AS e',
    'INNER JOIN' => [$s::PREFIX . 'requests AS r' => ['ON' => ['e' => 'requests_id', 'r' => 'id']],
        $s::PREFIX . 'contacts AS c' => ['ON' => ['r' => 'users_id', 'c' => 'users_id', ['AND' => ['c.entities_id' => (int) $entity]]]]],
    'WHERE' => ['r.entities_id' => (int) $entity, 'e.id' => ['>', $after], new Glpi\DBAL\QueryExpression('e.id > c.after_event_id')],
    'ORDER' => 'e.id ASC', 'LIMIT' => 100,
]), false);
$out = [];
$allowed = ['submit','approve','revise','reject','assign','start','ask','answer','finish','it_reject','cancel','change'];
foreach ($events as $e) {
    if (!in_array($e['action'], $allowed, true)) { continue; }
    $out[] = ['id' => (int) $e['id'], 'reference' => 'REQ-' . substr($e['created_at'], 0, 4) . '-' . str_pad((string) $e['request_id'], 6, '0', STR_PAD_LEFT),
        'action' => $e['action'], 'chat_id' => $e['chat_id']];
}
echo json_encode(['events' => $out, 'cursor' => $events ? (int) end($events)['id'] : $after, 'has_more' => count($events) === 100], JSON_THROW_ON_ERROR);
