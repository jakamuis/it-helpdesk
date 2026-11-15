<?php
class PluginLayananitView
{
    public static function h($v): string { return htmlspecialchars((string) $v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
    public static function root(): string { return rtrim((string) ($GLOBALS['CFG_GLPI']['root_doc'] ?? ''), '/'); }
    public static function native(string $path): string { return self::root() . $path; }
    public static function url(string $page = 'dashboard'): string { return Plugin::getWebDir('layananit') . '/front/index.php?page=' . rawurlencode($page); }
    public static function admin(): bool { return Session::haveRight('config', UPDATE); }
    public static function requestAvailable(): bool { return Plugin::isPluginActive('itrequest'); }
    public static function header(string $page): void
    {
        $h = [self::class, 'h'];
        $links = ['dashboard' => ['Dashboard Layanan TI','ti-layout-dashboard'], 'incident' => ['Incident','ti-ticket'],
            'request' => ['Request IT','ti-clipboard-check'], 'Computer' => ['Computer','ti-device-desktop'],
            'Monitor' => ['Monitor','ti-device-desktop'], 'Printer' => ['Printer','ti-printer'], 'users' => ['Manajemen User','ti-users'], 'more' => ['Fitur Lainnya','ti-apps']];
        echo '<link rel="stylesheet" href="' . $h(Plugin::getWebDir('layananit') . '/public/app.css') . '"><div class="lti"><aside class="lti-sidebar"><a class="lti-brand" href="' . $h(self::url()) . '"><em>GLPI</em><span>Layanan TI</span></a><nav aria-label="Navigasi Layanan TI">';
        foreach ($links as $key => [$label,$icon]) {
            if ($key === 'users' && !Session::haveRight('user', READ)) { continue; }
            if (in_array($key, ['Computer','Monitor','Printer'], true) && !Session::haveRight(strtolower($key), READ)) { continue; }
            if ($key === 'incident' && !Ticket::canView()) { continue; }
            echo '<a' . ($key === $page ? ' aria-current="page" class="active"' : '') . ' href="' . $h(self::url($key)) . '"><i aria-hidden="true" class="ti ' . $icon . '"></i>' . $h($label) . '</a>';
        }
        echo '</nav>';
        if (self::admin()) { echo '<div class="lti-developer"><strong>Developer</strong><p>Halaman asli GLPI</p><a href="' . $h(self::native('/front/central.php')) . '">〈/〉 Buka GLPI</a></div>'; }
        echo '</aside><main class="lti-main"><div class="lti-top"><span>Layanan TI / ' . $h($links[$page][0] ?? 'Dashboard') . '</span><span>' . $h($_SESSION['glpifriendlyname'] ?? $_SESSION['glpiname'] ?? '') . ' · Entity #' . (int) ($_SESSION['glpiactive_entity'] ?? 0) . '</span></div><div class="lti-content">';
    }
    public static function footer(): void { echo '<footer class="lti-footer">Layanan TI · Data mengikuti hak akses dan entity GLPI.</footer></div></main></div>'; }
    public static function requestRows(string $q): array
    {
        if (!self::requestAvailable()) { return []; }
        require_once dirname(__DIR__, 2) . '/itrequest/inc/view.class.php';
        $s = PluginItrequestService::class;
        $rows = $s::rows('requests', ['entities_id' => $s::entity()], ['ORDER' => 'id DESC', 'LIMIT' => 201]);
        $visible = [];
        foreach ($rows as $r) {
            try { $s::get((int) $r['id']); } catch (RuntimeException $e) { continue; }
            $p = json_decode($r['payload'], true) ?: [];
            if ($q !== '' && mb_stripos(PluginItrequestView::number($r) . ' ' . ($p['title'] ?? '') . ' ' . ($p['location'] ?? ''), $q) === false) { continue; }
            $visible[] = [$r,$p];
        }
        return $visible;
    }
    public static function requests(string $q): void
    {
        echo '<section class="lti-card"><div class="lti-section"><h2>Antrean Request IT</h2><a class="lti-button" href="' . self::h(self::native('/plugins/itrequest/front/index.php?tab=new')) . '">Buat Request</a></div>';
        if (!self::requestAvailable()) { echo '<p>Plugin Request IT belum aktif. Aktifkan plugin yang sudah tersedia untuk membuka antrean.</p></section>'; return; }
        self::search('request', $q);
        $rows = self::requestRows($q);
        echo '<p class="lti-muted">Maksimal 200 pengajuan terbaru yang dapat Anda akses. Target dan SLA belum dihitung pada tampilan ini.</p><div class="lti-scroll"><table><thead><tr><th>Nomor / judul</th><th>Layanan</th><th>Cabang</th><th>Status</th><th>PIC</th></tr></thead><tbody>';
        foreach (array_slice($rows, 0, 200) as [$r,$p]) {
            echo '<tr><td><a href="' . self::h(PluginItrequestView::url() . '?id=' . (int) $r['id']) . '">' . self::h(PluginItrequestView::number($r)) . '</a><br>' . self::h(($p['title'] ?? '') ?: '(Tanpa judul)') . '</td><td>' . self::h(PluginItrequestWorkflow::TYPES[$p['type'] ?? ''] ?? ($p['type'] ?? '—')) . '</td><td>' . self::h($p['location'] ?? '—') . '</td><td><span class="lti-badge">' . self::h(PluginItrequestWorkflow::STATES[$r['status']] ?? $r['status']) . '</span></td><td>' . self::h(PluginItrequestView::name((int) $r['assigned_id'])) . '</td></tr>';
        }
        if (!$rows) { echo '<tr><td colspan="5">Tidak ada pengajuan yang sesuai dan dapat diakses.</td></tr>'; }
        echo '</tbody></table></div></section>';
    }
    public static function search(string $page, string $q): void
    {
        echo '<form class="lti-search" method="get"><input type="hidden" name="page" value="' . self::h($page) . '"><label class="visually-hidden" for="lti-query">Cari</label><input id="lti-query" name="q" maxlength="100" placeholder="Cari nomor, judul atau cabang…" value="' . self::h($q) . '"><button class="lti-button">Cari</button></form>';
    }
    public static function nativeList(string $type): void
    {
        $rights = ['Ticket'=>'ticket','Computer'=>'computer','Monitor'=>'monitor','Printer'=>'printer','User'=>'user'];
        if (!isset($rights[$type]) || !$type::canView()) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
        echo '<section class="lti-card lti-native"><p class="lti-muted">Daftar dan aksi berikut memakai pencarian serta permission asli GLPI. Daftar Ticket mencakup data native; Request layanan menggunakan menu Request IT.</p>';
        // Native Search applies GLPI rights, entity visibility, pagination and action checks.
        if ($type === 'Ticket' && !isset($_GET['criteria'])) {
            $_GET['criteria'] = [['field' => 14, 'searchtype' => 'equals', 'value' => Ticket::INCIDENT_TYPE]];
            $_GET['reset'] = 'reset';
        }
        Search::show($type);
        echo '</section>';
    }
    public static function incidentQueue(): void
    {
        if (!Ticket::canView()) { return; }
        $data = Search::getDatas('Ticket', ['criteria' => [['field' => 14, 'searchtype' => 'equals', 'value' => Ticket::INCIDENT_TYPE]],
            'start' => 0, 'list_limit' => 8, 'sort' => 2, 'order' => 'DESC'], [1,2,12,3]);
        echo '<section class="lti-card lti-incident"><div class="lti-section"><h2>Antrean Incident</h2><a href="' . self::h(self::url('incident')) . '">Lihat semua →</a></div><div class="lti-scroll"><table><thead><tr><th>Nomor / judul</th><th>Status</th><th>Prioritas</th></tr></thead><tbody>';
        foreach (array_slice($data['data']['rows'] ?? [], 0, 8) as $row) {
            $raw = $row['raw'];
            echo '<tr><td><a href="' . self::h(self::native('/front/ticket.form.php?id=' . (int) $row['id'])) . '">#' . (int) $row['id'] . '</a><br>' . self::h($raw['ITEM_Ticket_1'] ?? '') . '</td><td><span class="lti-badge">' . self::h(Ticket::getStatus((int) ($raw['ITEM_Ticket_12'] ?? 1))) . '</span></td><td>' . self::h(Ticket::getPriorityName((int) ($raw['ITEM_Ticket_3'] ?? 3))) . '</td></tr>';
        }
        if (empty($data['data']['rows'])) { echo '<tr><td colspan="3">Tidak ada Incident yang dapat diakses.</td></tr>'; }
        echo '</tbody></table></div><p class="lti-muted">Delapan Incident terbaru dalam cakupan akses Anda.</p></section>';
    }
    public static function dashboard(): void
    {
        echo '<div class="lti-title"><div><h1>Dashboard Layanan TI</h1><p>Pantau antrean dan penanganan layanan TI.</p></div><div class="lti-actions"><a class="lti-button" href="' . self::h(self::native('/front/ticket.form.php')) . '">＋ Buat Incident</a><a class="lti-button secondary" href="' . self::h(self::native('/plugins/itrequest/front/index.php?tab=new')) . '">Buat Request</a></div></div>';
        echo '<div class="lti-summary">';
        foreach (['Baru','Diproses','Menunggu','Selesai'] as $label) { echo '<div class="lti-card"><span>' . $label . '</span><strong>—</strong><small>Perhitungan tahap berikutnya</small></div>'; }
        echo '</div><div class="lti-grid"><section class="lti-card"><h2>Antrean pekerjaan</h2><p>Pilih jenis pekerjaan untuk membuka antrean yang sesuai.</p><div class="lti-tabs"><a href="' . self::h(self::url('incident')) . '">Incident</a><a href="' . self::h(self::url('request')) . '">Request IT</a></div><p class="lti-muted">Incident memakai Ticket GLPI. Request IT mempertahankan approval dan nomor referensinya sendiri.</p></section><section class="lti-card"><h2>Tindak lanjut</h2><a href="' . self::h(self::native('/plugins/itrequest/front/index.php?tab=approval')) . '">Persetujuan Saya →</a><p>Indikator SLA, target, dan beban teknisi menunggu definisi perhitungan.</p></section></div>';
        self::incidentQueue();
        self::requests('');
    }
}
