<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/view.class.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('layananit') || ($_SESSION['glpiactiveprofile']['interface'] ?? '') !== 'central') {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
$page = (string) ($_GET['page'] ?? 'dashboard');
if (!in_array($page, ['dashboard','incident','request','Computer','Monitor','Printer','users','report','more'], true)) { $page = 'dashboard'; }
$q = mb_substr(trim((string) ($_GET['q'] ?? '')), 0, 100);
$v = PluginLayananitView::class;
$report = null;
if ($page === 'report') {
    require_once dirname(__DIR__) . '/inc/report.class.php';
    $report = new PluginLayananitReport($_GET);
    if (isset($_GET['csv']) && !$report->error) { return $report->csv(); }
}
Html::header('Layanan TI', '', 'tools', 'pluginlayananitmenu');
$v::header($page);
if ($page === 'report') { $report->render(); }
elseif ($page === 'dashboard') { $v::dashboard(); }
elseif ($page === 'request') { echo '<h1>Request IT</h1>'; $v::requests($q); }
elseif ($page === 'incident') { echo '<h1>Incident</h1>'; $v::nativeList('Ticket'); }
elseif (in_array($page, ['Computer','Monitor','Printer'], true)) { echo '<h1>Asset · ' . $v::h($page) . '</h1>'; $v::nativeList($page); }
elseif ($page === 'users') {
    echo '<h1>Manajemen User</h1><p>Kelola akun dan profil GLPI. Admin mengatur pemetaan approver, IT Manager, serta IT melalui Pengaturan Request IT.</p>';
    $v::nativeList('User');
    if ($v::admin()) { echo '<a class="lti-button" href="' . $v::h($v::native('/plugins/itrequest/front/index.php?tab=settings')) . '">Pengaturan Request IT</a>'; }
} else {
    echo '<h1>Fitur Lainnya</h1><section class="lti-card">';
    if (Plugin::isPluginActive('providersla') && Session::haveRight('ticket', UPDATE)) { echo '<a href="' . $v::h($v::native('/plugins/providersla/front/report.php')) . '">Laporan SLA Provider</a>'; }
    echo '<p>Fitur lanjutan mengikuti plugin aktif dan hak akses GLPI.</p></section>';
}
$v::footer(); Html::footer();
