<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/service.class.php';
Session::checkLoginUser();
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
// GLPI 11's CheckCsrfListener validates the POST before this controller runs.
$id = (int) ($_POST['tickets_id'] ?? 0);
PluginProviderslaService::ticket($id, true);
try {
    PluginProviderslaService::mutate($id, (string) ($_POST['action'] ?? ''), $_POST);
    Session::addMessageAfterRedirect('Pencatatan SLA provider berhasil disimpan.');
} catch (InvalidArgumentException | RuntimeException $e) {
    Session::addMessageAfterRedirect(htmlspecialchars($e->getMessage(), ENT_QUOTES, 'UTF-8'), false, ERROR);
}
Session::setActiveTab('Ticket', ($_POST['return_to'] ?? '') === 'sidebar' ? 'Ticket$main' : 'PluginProviderslaTicket$1');
Html::redirect(Ticket::getFormURLWithID($id));
