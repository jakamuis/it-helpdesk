<?php
require_once __DIR__ . '/service.class.php';
class PluginProviderslaTicket extends CommonGLPI
{
    public static function getTypeName($nb = 0) { return 'SLA Provider'; }
    public static function getMenuName() { return self::getTypeName(); }
    public static function getMenuContent()
    {
        return ['title' => self::getTypeName(), 'page' => Plugin::getWebDir('providersla') . '/front/report.php',
            'icon' => 'ti ti-clock-share'];
    }
    public function getTabNameForItem(CommonGLPI $item, $withtemplate = 0)
    {
        return $item instanceof Ticket && PluginProviderslaService::allowed() ? 'SLA Provider' : '';
    }
    public static function displayTabContentForItem(CommonGLPI $item, $tabnum = 1, $withtemplate = 0)
    {
        if ($item instanceof Ticket) {
            self::show((int) $item->getID());
        }
        return true;
    }
    public static function h($value): string { return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
    public static function field(string $name, string $label, string $type = 'text', bool $required = false, string $value = ''): void
    {
        $id = 'providersla_' . $name . '_' . bin2hex(random_bytes(4));
        echo '<label class="form-label d-block mb-3" for="' . $id . '">' . self::h($label);
        if ($type === 'textarea') {
            echo '<textarea class="form-control" rows="3" name="' . self::h($name) . '" id="' . $id . '" maxlength="4000"'
                . ($required ? ' required' : '') . '>' . self::h($value) . '</textarea>';
        } else {
            echo '<input class="form-control" name="' . self::h($name) . '" id="' . $id . '" type="' . self::h($type)
                . '" value="' . self::h($value) . '"' . ($required ? ' required' : '') . ($type === 'text' ? ' maxlength="255"' : '') . '>';
        }
        echo '</label>';
    }
    private static function form(int $ticket, string $action, ?int $episode = null): void
    {
        echo '<form method="post" action="' . self::h(Plugin::getWebDir('providersla') . '/front/action.php') . '" class="mt-3">';
        foreach (['tickets_id' => $ticket, 'action' => $action, 'episode_id' => $episode ?? 0,
            '_glpi_csrf_token' => Session::getNewCSRFToken()] as $key => $value) {
            echo '<input type="hidden" name="' . self::h($key) . '" value="' . self::h($value) . '">';
        }
    }
    private static function button(string $label, string $color = 'primary'): void
    {
        echo '<button type="submit" class="btn btn-' . $color . '">' . self::h($label) . '</button></form>';
    }
    public static function show(int $id): void
    {
        global $DB;
        $ticket = PluginProviderslaService::ticket($id);
        $canWrite = $ticket->can($id, UPDATE);
        $rows = PluginProviderslaService::rows($id);
        $now = time();
        $active = false;
        $providerSeconds = 0;
        $times = $DB->doQuery('SELECT UNIX_TIMESTAMP(date) AS created, UNIX_TIMESTAMP(solvedate) AS solved,
            UNIX_TIMESTAMP(closedate) AS closed FROM glpi_tickets WHERE id=' . $id)->fetch_assoc();
        $cutoff = in_array((int) $ticket->fields['status'], [Ticket::SOLVED, Ticket::CLOSED], true)
            ? (int) ($times['solved'] ?: $times['closed'] ?: $now) : $now;
        foreach ($rows as $row) {
            if (empty($row['is_void'])) {
                $active = $active || $row['restored_epoch'] === null;
                $providerSeconds += max(0, min((int) ($row['restored_epoch'] ?? $now), $cutoff) - (int) $row['transferred_epoch']);
            }
        }
        $gross = max(0, $cutoff - (int) $times['created']);
        echo '<div class="card"><div class="card-body"><h2 class="card-title">SLA Provider — pengalihan manual</h2>';
        echo '<p>Hitungan provider dimulai saat laporan dikirim oleh Helpdesk, berjalan 24×7, dan berhenti pada waktu pulih yang diverifikasi. Semua jam menggunakan Asia/Jakarta.</p>';
        echo '<div class="alert alert-info">Provider: <strong>' . self::h(PluginProviderslaClock::duration($providerSeconds))
            . '</strong> · Waktu non-provider: <strong>' . self::h(PluginProviderslaClock::duration(max(0, $gross - $providerSeconds)))
            . '</strong> · Siklus sampai saat ini/Solved: ' . self::h(PluginProviderslaClock::duration($gross))
            . '<br>Waktu non-provider mencakup antrean, pemeriksaan, dan waktu tunggu lain; bukan jam kerja aktif atau total downtime.</div>';
        echo '<p>Pengalihan mengubah tiket ke Pending sehingga TTR bawaan GLPI dijeda. Timer provider di tab ini tetap berjalan. Saat pemulihan dicatat, tiket dikembalikan untuk penanganan Helpdesk; Solved tetap melalui proses biasa. Jeda bawaan mengikuti waktu tombol disimpan; pencatatan tanggal lampau hanya berlaku pada laporan SLA Provider.</p>';
        if ($active && (int) $ticket->fields['status'] !== Ticket::WAITING) {
            echo '<div class="alert alert-warning">Ada episode provider aktif tetapi status tiket sudah berubah di luar tab ini. Timer provider tetap berjalan; catat pemulihan atau batalkan episode dengan alasan.</div>';
        }
        if (!$rows) { echo '<p class="text-muted">Belum ada pengalihan provider pada tiket ini.</p>'; }
        foreach ($rows as $row) {
            $m = PluginProviderslaClock::metrics($row, $now);
            echo '<section class="border rounded p-3 mb-3"><h3>Episode #' . (int) $row['id'] . ' · ' . self::h($row['provider_name']) . '</h3>';
            echo '<dl class="row">';
            foreach (['Layanan / aset / lokasi' => $row['circuit'], 'No. Incident dari Provider' => $row['reference'],
                'Nomor SID/Pelanggan' => $row['customer_sid'] ?? '',
                'Dialihkan' => PluginProviderslaClock::date((int) $row['transferred_epoch']),
                'Pulih' => PluginProviderslaClock::date(isset($row['restored_epoch']) ? (int) $row['restored_epoch'] : null),
                'Diverifikasi' => PluginProviderslaClock::date(isset($row['verified_epoch']) ? (int) $row['verified_epoch'] : null),
                'Deadline' => PluginProviderslaClock::date($m['deadline']), 'Durasi 24×7' => PluginProviderslaClock::duration($m['seconds']),
                'Hasil' => $m['status'], 'Diagnosis & bukti pengiriman' => $row['transfer_evidence'],
                'Bukti pemulihan' => $row['recovery_evidence'] ?? '—'] as $label => $value) {
                echo '<dt class="col-sm-4">' . self::h($label) . '</dt><dd class="col-sm-8" style="white-space:pre-wrap">' . self::h($value ?: '—') . '</dd>';
            }
            echo '</dl>';
            if ($canWrite && empty($row['is_void'])) {
                if ($row['restored_epoch'] === null) {
                    echo '<details class="mb-3"><summary>Catat layanan pulih</summary>';
                    self::form($id, 'restore', (int) $row['id']);
                    self::field('restored_at', 'Waktu layanan/aset pulih (Asia/Jakarta)', 'datetime-local', true, PluginProviderslaClock::date($now, 'Y-m-d\TH:i'));
                    self::field('recovery_evidence', 'Hasil pemeriksaan dan bukti pemulihan yang telah diverifikasi', 'textarea', true);
                    self::button('Simpan pemulihan & lanjutkan Helpdesk');
                    echo '</details>';
                }
                echo '<details class="mb-3"><summary>Tambah/koreksi nomor incident & SID pelanggan</summary>';
                self::form($id, 'reference', (int) $row['id']);
                self::field('reference', 'No. Incident dari Provider (opsional)', 'text', false, $row['reference']);
                self::field('customer_sid', 'Nomor SID/Pelanggan (opsional)', 'text', false, $row['customer_sid'] ?? '');
                echo '<p class="small text-muted">Perubahan nomor incident/SID tidak mengubah awal hitung.</p>';
                self::button('Simpan nomor incident & SID');echo '</details>';
                echo '<details><summary>Batalkan pencatatan yang keliru</summary><p>Riwayat tetap tersimpan. Episode ini dikeluarkan dari total durasi provider. Untuk koreksi waktu, batalkan lalu catat ulang pada tiket yang masih terbuka.</p>';
                self::form($id, 'void', (int) $row['id']);
                self::field('reason', 'Alasan pembatalan/koreksi', 'textarea', true);
                self::button('Batalkan episode', 'outline-danger');echo '</details>';
            }
            echo '<details class="mt-3"><summary>Riwayat audit</summary><ul>';
            foreach ($DB->request(['FROM' => PluginProviderslaService::EVENTS, 'WHERE' => ['episodes_id' => (int) $row['id']], 'ORDER' => 'id']) as $event) {
                echo '<li>' . self::h(PluginProviderslaClock::date((int) $event['event_epoch'])) . ' · user #' . (int) $event['users_id']
                    . ' · ' . self::h($event['action']) . '<pre class="text-wrap">' . self::h($event['details']) . '</pre></li>';
            }
            echo '</ul></details></section>';
        }
        if ($canWrite && !$active && !in_array((int) $ticket->fields['status'], [Ticket::SOLVED, Ticket::CLOSED], true)) {
            echo '<h3>Eskalasi ke Vendor</h3><p>Kirim laporan ke vendor terlebih dahulu, lalu catat waktu dan buktinya di sini. Form ini tidak mengirim laporan ke vendor.</p>';
            self::form($id, 'start');
            echo '<label class="form-label d-block mb-3">Supplier<select class="form-select" name="suppliers_id"><option value="0">Isi nama vendor secara manual</option>';
            foreach (PluginProviderslaService::suppliers($ticket) as $supplier) {
                echo '<option value="' . (int) $supplier['id'] . '">' . self::h($supplier['name']) . '</option>';
            }
            echo '</select></label>';
            self::field('provider_name', 'Nama vendor (wajib jika Supplier tidak dipilih)');
            self::field('customer_sid', 'Nomor SID/Pelanggan (opsional)');
            self::field('circuit', 'Layanan / aset / lokasi (opsional)');
            self::field('transferred_at', 'Waktu pengalihan/laporan dikirim (Asia/Jakarta)', 'datetime-local', true, PluginProviderslaClock::date($now, 'Y-m-d\TH:i'));
            self::field('reference', 'No. Incident dari Provider (opsional)');
            self::field('target_hours', 'Target pemulihan (jam, opsional; contoh 2 atau 1.5)');
            self::field('transfer_evidence', 'Diagnosis, alasan pengalihan, kanal dan bukti laporan terkirim', 'textarea', true);
            self::button('Eskalasi & mulai hitung');
        }
        echo '<a class="btn btn-outline-secondary mt-3" href="' . self::h(Plugin::getWebDir('providersla') . '/front/report.php') . '">Laporan SLA Provider</a></div></div>';
    }
}
