<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/view.class.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('itrequest')) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
$view = PluginItrequestView::class;
$selfService = ($_SESSION['glpiactiveprofile']['interface'] ?? '') === 'helpdesk';
if ($selfService) { Html::helpHeader('Request IT'); }
else { Html::header('Request IT', '', 'tools', 'pluginitrequestmenu'); }
echo '<div class="container-xl py-3"><div class="card"><div class="card-body"><h1>Request IT</h1><p>Request Email dan pemasangan Office 365 dengan alur persetujuan sesuai jenis layanan.</p>';
echo '<div class="alert alert-info">Notifikasi email belum diaktifkan. Pantau pengajuan dan persetujuan melalui halaman ini.</div><nav class="d-flex gap-2 flex-wrap mb-4">';
foreach (['mine' => 'Request Saya', 'new' => 'Buat Request', 'approval' => 'Persetujuan Saya', 'it' => 'Antrean IT'] as $tab => $title) {
    if ($tab === 'it' && !PluginItrequestService::staff(PluginItrequestService::entity())) { continue; }
    echo '<a class="btn btn-outline-primary" href="' . $view::h($view::url() . '?tab=' . $tab) . '">' . $view::h($title) . '</a>';
}
if (PluginItrequestService::admin()) { echo '<a class="btn btn-outline-secondary" href="' . $view::h($view::url() . '?tab=settings') . '">Pengaturan</a>'; }
echo '</nav>';
try {
    if (isset($_GET['id'])) { $view::detail(PluginItrequestService::get((int) $_GET['id'])); }
    elseif (($_GET['tab'] ?? '') === 'new') { $view::editor(null); }
    elseif (($_GET['tab'] ?? '') === 'settings') { $view::settings(); }
    else { $view::listing((string) ($_GET['tab'] ?? 'mine')); }
} catch (InvalidArgumentException | RuntimeException $e) {
    echo '<div class="alert alert-danger">' . $view::h($e->getMessage()) . '</div>';
}
echo '</div></div></div>';
if ($selfService) { Html::helpFooter(); } else { Html::footer(); }
