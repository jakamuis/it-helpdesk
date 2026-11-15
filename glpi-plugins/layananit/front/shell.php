<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/view.class.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('layananit') || empty($_SESSION['layananit_workspace']) || ($_SESSION['glpiactiveprofile']['interface'] ?? '') !== 'central') {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
$page = (string) ($_GET['page'] ?? 'incident');
if (!in_array($page, ['incident','request','Computer','Monitor','Printer','users','more'], true)) { $page = 'incident'; }
ob_start(); PluginLayananitView::header($page); $header = ob_get_clean();
preg_match('~<aside class="lti-sidebar">.*?</aside>~s', $header, $match);
return new Symfony\Component\HttpFoundation\JsonResponse(['sidebar' => $match[0] ?? '']);
