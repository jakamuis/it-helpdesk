<?php

require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/view.class.php';

Session::checkLoginUser();
if (!Plugin::isPluginActive('layananit') || Session::getCurrentInterface() !== 'central' || !Ticket::canView()) {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
header('Content-Type: application/json; charset=UTF-8');
header('Cache-Control: no-store');

if (isset($_GET['visible'])) {
    $ids = array_values(array_unique(array_filter(array_map('intval', explode(',', (string) $_GET['visible'])))));
    echo json_encode(['tickets' => array_values(PluginLayananitTicketFeed::visible(array_slice($ids, 0, 500)))], JSON_THROW_ON_ERROR);
    return;
}

$after = max(0, (int) ($_GET['after'] ?? 0));
$through = isset($_GET['through']) ? (int) $_GET['through'] : null;
$data = PluginLayananitTicketFeed::page($after, $through);
if (($_GET['view'] ?? '') === 'dashboard') {
    ob_start();
    PluginLayananitView::incidentQueue();
    $data['incident'] = ob_get_clean();
}
if (in_array($_GET['view'] ?? '', ['dashboard', 'request'], true) && PluginLayananitView::requestAvailable()) {
    ob_start();
    PluginLayananitView::requestTable(mb_substr(trim((string) ($_GET['q'] ?? '')), 0, 100));
    $data['requests'] = ob_get_clean();
}
echo json_encode($data, JSON_THROW_ON_ERROR);
