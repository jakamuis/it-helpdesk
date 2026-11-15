<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/attachment.class.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('itrequest') || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
// GLPI 11 CheckCsrfListener validates POST tokens before reaching this controller.
$id = max(0, (int) ($_POST['id'] ?? 0));
$action = (string) ($_POST['action'] ?? '');
$config = in_array($action, ['mapping','staff','remove_staff','manager','remove_manager','contact'], true);
try {
    if ($config) { PluginItrequestService::configure($action, $_POST); }
    elseif ($action === 'upload') { PluginItrequestAttachment::upload($id, $_POST, $_FILES['attachment'] ?? []); }
    else { $id = PluginItrequestService::mutate($id, $action, $_POST); }
    Session::addMessageAfterRedirect('Perubahan Request IT berhasil disimpan.');
} catch (InvalidArgumentException | RuntimeException $e) {
    Session::addMessageAfterRedirect(htmlspecialchars($e->getMessage(), ENT_QUOTES, 'UTF-8'), false, ERROR);
}
Html::redirect(Plugin::getWebDir('itrequest') . '/front/index.php' . ($config ? '?tab=settings' : ($id ? '?id=' . $id : '?tab=new')));
