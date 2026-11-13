<?php
require_once __DIR__ . '/service.class.php';
class PluginItrequestView
{
    public static function h($v): string { return htmlspecialchars((string) $v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
    public static function url(): string { return Plugin::getWebDir('itrequest') . '/front/index.php'; }
    public static function name(int $id): string
    {
        $u = new User();
        return $id && $u->getFromDB($id) ? $u->getFriendlyName() : '—';
    }
    public static function number(array $r): string { return 'REQ-' . substr($r['created_at'], 0, 4) . '-' . str_pad((string) $r['id'], 6, '0', STR_PAD_LEFT); }
    public static function field(string $name, string $label, string $value = '', string $type = 'text', bool $required = false): void
    {
        echo '<label class="form-label d-block mb-3">' . self::h($label);
        $attrs = ' name="' . self::h($name) . '" class="form-control"' . ($required ? ' required' : '');
        if ($type === 'textarea') { echo '<textarea rows="3" maxlength="4000"' . $attrs . '>' . self::h($value) . '</textarea>'; }
        else { echo '<input type="' . self::h($type) . '" maxlength="255" value="' . self::h($value) . '"' . $attrs . '>'; }
        echo '</label>';
    }
    public static function form(string $action, ?array $r = null): void
    {
        echo '<form method="post" action="' . self::h(Plugin::getWebDir('itrequest') . '/front/action.php') . '" enctype="multipart/form-data" class="mb-3">';
        foreach (['action' => $action, 'id' => $r['id'] ?? 0, 'version' => $r['version'] ?? 0,
            '_glpi_csrf_token' => Session::getNewCSRFToken()] as $k => $v) {
            echo '<input type="hidden" name="' . self::h($k) . '" value="' . self::h($v) . '">';
        }
    }
    public static function button(string $label, string $color = 'primary'): void
    { echo '<button class="btn btn-' . self::h($color) . '">' . self::h($label) . '</button></form>'; }
    public static function editor(?array $r): void
    {
        $p = $r ? json_decode($r['payload'], true) : ['type' => 'email', 'email_service' => 'new', 'recipient' => self::name(PluginItrequestService::uid())];
        $legacy = !isset(PluginItrequestWorkflow::TYPES[$p['type'] ?? '']);
        if ($legacy) { echo '<div class="alert alert-warning">Ini draft dari form lama. Pilih jenis layanan baru dan lengkapi identitas sebelum mengirim ulang.</div>'; }
        self::form($r ? 'save' : 'create', $r);
        echo '<p>Pemohon: <strong>' . self::h(self::name(PluginItrequestService::uid())) . '</strong>. Nama pengguna di bawah boleh berbeda jika pengajuan diwakilkan. Jangan masukkan password atau OTP.</p>';
        echo '<label class="form-label d-block mb-3">Jenis request<select id="request-type" name="type" class="form-select">';
        foreach (PluginItrequestWorkflow::TYPES as $key => $label) { echo '<option value="' . $key . '"' . (($p['type'] ?? '') === $key ? ' selected' : '') . '>' . self::h($label) . '</option>'; }
        echo '</select></label><div data-request-types="email" class="alert alert-info">Alur Email: Pemohon → Atasan Langsung (Mengetahui) → Direktur (Menyetujui) → IT.</div>';
        echo '<div data-request-types="office365" class="alert alert-info">Alur Office 365: Pemohon → Atasan Langsung → IT.</div>';
        self::field('title', 'Judul pengajuan', $p['title'] ?? '');
        echo '<h3>Identitas pengguna fasilitas</h3><div class="row"><div class="col-md-6">';
        foreach (['recipient' => 'Nama pengguna', 'employee_number' => 'NIK', 'department' => 'Bagian / departemen'] as $key => $label) { self::field($key, $label, $p[$key] ?? ''); }
        echo '</div><div class="col-md-6">';
        foreach (['job_title' => 'Jabatan', 'location' => 'Cabang / lokasi', 'company' => 'Perusahaan / beban biaya'] as $key => $label) { self::field($key, $label, $p[$key] ?? ''); }
        echo '</div></div><div data-request-types="email"><h3>Layanan email yang diminta</h3>';
        echo '<label class="form-label d-block mb-3">Layanan email<select id="email-service" name="email_service" class="form-select">';
        foreach (PluginItrequestWorkflow::EMAIL_SERVICES as $key => $label) { echo '<option value="' . $key . '"' . (($p['email_service'] ?? 'new') === $key ? ' selected' : '') . '>' . self::h($label) . '</option>'; }
        echo '</select></label><div data-email-services="reset rename delete">';
        self::field('current_email', 'Alamat email saat ini', $p['current_email'] ?? '', 'email'); echo '</div><div data-email-services="new rename">';
        self::field('requested_email', 'Usulan alamat email baru (termasuk domain)', $p['requested_email'] ?? '', 'email');
        echo '</div><p data-email-services="reset">IT memverifikasi identitas sebelum reset. Password atau link pemulihan disampaikan melalui jalur aman, bukan catatan request.</p></div>';
        echo '<div data-request-types="office365"><h3>Pemasangan Office 365</h3>';
        self::field('office_email', 'Email perusahaan pengguna', $p['office_email'] ?? '', 'email');
        self::field('asset', 'Hostname / nomor aset perangkat tujuan', $p['asset'] ?? '');
        self::field('office_apps', 'Aplikasi yang dibutuhkan (misalnya Word, Excel, Outlook)', $p['office_apps'] ?? '');
        echo '<p>IT memeriksa ketersediaan lisensi dan kelayakan perangkat sebelum pemasangan.</p></div>';
        self::field('reason', 'Keterangan / alasan kebutuhan', $p['reason'] ?? ($p['description'] ?? ''), 'textarea');
        self::field('needed_date', 'Tanggal dibutuhkan', $p['needed_date'] ?? '', 'date');
        echo '<div class="border rounded p-3 mb-3"><p>' . self::h(PluginItrequestWorkflow::POLICY) . '</p><label><input type="checkbox" name="policy_accepted" value="1"'
            . (($p['policy_accepted'] ?? '') === '1' ? ' checked' : '') . '> Saya menyetujui ketentuan penggunaan fasilitas perusahaan di atas.</label></div>';
        echo '<p class="text-muted">Draft boleh belum lengkap. Seluruh identitas, detail layanan, tanggal dan pernyataan wajib lengkap saat dikirim. Simpan perubahan sebelum mengirim ke atasan.</p>';
        self::button('Simpan draft / revisi');
        echo '<script src="' . self::h(Plugin::getWebDir('itrequest') . '/public/form.js?v=020') . '" defer></script>';
    }
    public static function detail(array $r): void
    {
        $p = json_decode($r['payload'], true);
        echo '<h2>' . self::h(self::number($r)) . ' · ' . self::h($p['title'] ?: '(Tanpa judul)') . '</h2>';
        echo '<p><span class="badge bg-blue-lt">' . self::h(PluginItrequestWorkflow::STATES[$r['status']]) . '</span> · Pemohon: '
            . self::h(self::name((int) $r['users_id'])) . ' · Atasan: ' . self::h(self::name((int) $r['approvers_id']))
            . ' · Direktur: ' . self::h(self::name((int) ($r['directors_id'] ?? 0))) . ' · PIC IT: ' . self::h(self::name((int) $r['assigned_id'])) . ' · Target: ' . self::h($r['target_date'] ?: '—') . '</p>';
        if (in_array($p['type'] ?? '', ['email','office365'], true)) {
            echo '<p><strong>Alur:</strong> ' . (($p['type'] === 'email') ? 'Pemohon → Atasan Langsung (Mengetahui) → Direktur (Menyetujui) → IT' : 'Pemohon → Atasan Langsung → IT') . '</p>';
            if (!empty($r['manager_approved_at'])) { echo '<p>Atasan mengetahui / menyetujui: ' . self::h($r['manager_approved_at']) . '</p>'; }
            if (!empty($r['approved_at'])) { echo '<p>Persetujuan akhir: ' . self::h($r['approved_at']) . '</p>'; }
        }
        $owner = (int) $r['users_id'] === PluginItrequestService::uid();
        if ($owner && in_array($r['status'], ['draft','revision'], true)) { self::editor($r); }
        else {
            echo '<dl class="row">';
            foreach (['type' => 'Jenis', 'recipient' => 'Nama pengguna', 'employee_number' => 'NIK', 'department' => 'Bagian / departemen',
                'job_title' => 'Jabatan', 'location' => 'Cabang / lokasi', 'company' => 'Perusahaan / beban biaya',
                'email_service' => 'Layanan email', 'current_email' => 'Email saat ini', 'requested_email' => 'Usulan email baru',
                'office_email' => 'Email pengguna Office', 'asset' => 'Hostname / nomor aset', 'office_apps' => 'Aplikasi Office',
                'reason' => 'Keterangan / alasan', 'needed_date' => 'Tanggal dibutuhkan',
                'description' => 'Detail form lama', 'specification' => 'Spesifikasi form lama'] as $k => $label) {
                if (($p[$k] ?? '') === '') { continue; }
                $value = match ($k) {
                    'type' => PluginItrequestWorkflow::TYPES[$p[$k]] ?? $p[$k],
                    'email_service' => PluginItrequestWorkflow::EMAIL_SERVICES[$p[$k]] ?? $p[$k],
                    default => $p[$k],
                };
                echo '<dt class="col-md-3">' . self::h($label) . '</dt><dd class="col-md-9">' . nl2br(self::h($value)) . '</dd>';
            }
            if (($p['policy_accepted'] ?? '') === '1') {
                echo '<dt class="col-md-3">Pernyataan</dt><dd class="col-md-9">Disetujui pemohon. ' . self::h(PluginItrequestWorkflow::POLICY) . '</dd>';
            }
            echo '</dl>';
        }
        $actions = ['change' => 'Kembalikan untuk perubahan kebutuhan dan approval ulang', 'submit' => 'Kirim ke atasan', 'withdraw' => 'Tarik ke draft', 'approve' => 'Setujui',
            'revise' => 'Minta revisi', 'reject' => 'Tolak', 'start' => 'Ambil dan mulai proses', 'ask' => 'Minta kelengkapan',
            'answer' => 'Kirim kelengkapan', 'finish' => 'Selesaikan', 'it_reject' => 'Tolak secara teknis', 'cancel' => 'Batalkan'];
        echo '<hr><div class="row">';
        foreach ($actions as $action => $label) {
            try { PluginItrequestWorkflow::transition($r['status'], $action, $owner,
                PluginItrequestService::currentApprover($r) === PluginItrequestService::uid(), PluginItrequestService::staff((int) $r['entities_id']), (string) ($p['type'] ?? '')); }
            catch (InvalidArgumentException $e) { continue; }
            if ($action === 'approve') { $label = $r['status'] === 'approval' && ($p['type'] ?? '') === 'email' ? 'Mengetahui — teruskan ke direktur' : 'Setujui — teruskan ke IT'; }
            echo '<div class="col-md-6">'; self::form($action, $r);
            if (!in_array($action, ['submit','withdraw'], true)) {
                self::field('note', $action === 'finish' ? 'Hasil pengerjaan' : 'Catatan / alasan', '', 'textarea', $action !== 'approve' && $action !== 'start');
            }
            if ($action === 'start') { self::field('target_date', 'Target selesai', '', 'date', true); }
            self::button($label, in_array($action, ['reject','cancel','it_reject'], true) ? 'outline-danger' : 'primary'); echo '</div>';
        }
        echo '</div><hr><h3>Lampiran</h3>';
        foreach (PluginItrequestService::rows('attachments', ['requests_id' => $r['id']]) as $file) {
            echo '<p><a href="' . self::h(Plugin::getWebDir('itrequest') . '/front/download.php?id=' . $file['id']) . '">'
                . self::h($file['filename']) . '</a> · ' . round($file['size'] / 1024) . ' KB</p>';
        }
        if (($owner && in_array($r['status'], ['draft','revision','information'], true))
            || (PluginItrequestService::staff((int) $r['entities_id']) && in_array($r['status'], ['queued','processing','information'], true))) {
            self::form('upload', $r);
            echo '<p>PDF, JPG atau PNG; maksimal 10 MB per file. Lampiran ikut dapat dibaca oleh pihak yang berhak melihat request.</p><input class="form-control mb-2" type="file" name="attachment" accept=".pdf,.jpg,.jpeg,.png" required>';
            self::button('Unggah lampiran', 'outline-primary');
        }
        if (PluginItrequestService::admin() && in_array($r['status'], ['approval','director_approval'], true)) {
            echo '<h3>Alihkan approver</h3>';
            self::form('reassign', $r);
            User::dropdown(['name' => 'approvers_id', 'entity' => (int) $r['entities_id'], 'right' => 'all']);
            self::field('note', 'Alasan pengalihan', '', 'textarea', true);
            self::button('Alihkan approval', 'outline-secondary');
        }
        echo '<div>';
        echo '</div><hr><h3>Riwayat proses</h3><p>Catatan pada versi ini dapat dibaca pemohon dan approver. Jangan tulis catatan internal rahasia.</p>';
        foreach (PluginItrequestService::rows('events', ['requests_id' => $r['id']], ['ORDER' => 'id DESC']) as $event) {
            $d = json_decode($event['details'], true);
            echo '<div class="border rounded p-3 mb-2"><strong>' . self::h($actions[$event['action']] ?? $event['action']) . '</strong> · '
                . self::h(isset($d['stage']) ? (PluginItrequestWorkflow::STATES[$d['stage']] ?? $d['stage']) . ' · ' : '') . self::h(self::name((int) $event['users_id'])) . ' · ' . self::h($event['created_at']) . '<br>' . nl2br(self::h($d['note'] ?? ''));
            if (isset($d['snapshot'])) {
                echo '<details><summary>Isi pengajuan pada versi ini</summary><pre>' . self::h(json_encode($d['snapshot'], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)) . '</pre></details>';
            }
            echo '</div>';
        }
    }
    public static function listing(string $tab): void
    {
        $s = PluginItrequestService::class;
        $where = ['entities_id' => $s::entity()];
        if ($tab === 'approval') { $where['OR'] = [['approvers_id' => $s::uid(), 'status' => 'approval'], ['directors_id' => $s::uid(), 'status' => 'director_approval']]; }
        elseif ($tab === 'it') {
            if (!$s::staff($s::entity())) { throw new RuntimeException('Anda belum terdaftar sebagai tim IT di entity ini.'); }
            $where['status'] = ['queued','processing','information','done','rejected','cancelled'];
        } else { $where['users_id'] = $s::uid(); }
        echo '<p>Maksimal 200 request terbaru dalam entity aktif.</p><div class="table-responsive"><table class="table table-striped"><thead><tr><th>Nomor / judul</th><th>Pemohon</th><th>Status</th><th>Dibutuhkan</th><th>Target IT</th></tr></thead><tbody>';
        $rows = $s::rows('requests', $where, ['ORDER' => 'id DESC', 'LIMIT' => 200]);
        foreach ($rows as $r) {
            try { $s::get((int) $r['id']); } catch (RuntimeException $e) { continue; }
            $p = json_decode($r['payload'], true);
            echo '<tr><td><a href="' . self::h(self::url() . '?id=' . $r['id']) . '">' . self::h(self::number($r)) . '</a><br>' . self::h($p['title'] ?: '(Tanpa judul)') . '</td><td>'
                . self::h(self::name((int) $r['users_id'])) . '</td><td>' . self::h(PluginItrequestWorkflow::STATES[$r['status']]) . '</td><td>'
                . self::h($p['needed_date']) . '</td><td>' . self::h($r['target_date']) . '</td></tr>';
        }
        echo '</tbody></table></div>';
    }
    public static function settings(): void
    {
        if (!PluginItrequestService::admin()) { throw new RuntimeException('Hanya admin konfigurasi.'); }
        echo '<h2>Pengaturan entity aktif</h2><p>Pemetaan berlaku untuk pengiriman berikutnya. Atasan dan direktur tersimpan saat pengajuan dikirim. Direktur wajib untuk Email; Office 365 hanya memerlukan atasan. Atasan dan direktur harus akun berbeda dari pemohon dan satu sama lain.</p>';
        self::form('mapping');
        User::dropdown(['name' => 'users_id', 'entity' => PluginItrequestService::entity(), 'right' => 'all']);
        echo ' → Atasan: ';
        User::dropdown(['name' => 'approvers_id', 'entity' => PluginItrequestService::entity(), 'right' => 'all']);
        echo ' → Direktur (untuk email): ';
        User::dropdown(['name' => 'directors_id', 'entity' => PluginItrequestService::entity(), 'right' => 'all']);
        self::button('Simpan pemetaan atasan');
        echo '<h3>Pemetaan saat ini</h3><ul>';
        foreach (PluginItrequestService::rows('mappings', ['entities_id' => PluginItrequestService::entity()]) as $m) {
            echo '<li>' . self::h(self::name((int) $m['users_id'])) . ' → ' . self::h(self::name((int) $m['approvers_id'])) . ' → Direktur: ' . self::h(self::name((int) ($m['directors_id'] ?? 0))) . '</li>';
        }
        echo '</ul><h3>Anggota tim IT</h3>';
        self::form('staff'); User::dropdown(['name' => 'users_id', 'entity' => PluginItrequestService::entity(), 'right' => 'all']); self::button('Tambahkan anggota IT');
        foreach (PluginItrequestService::rows('staff', ['entities_id' => PluginItrequestService::entity()]) as $m) {
            self::form('remove_staff'); echo '<input type="hidden" name="users_id" value="' . (int) $m['users_id'] . '">' . self::h(self::name((int) $m['users_id'])) . ' '; self::button('Hapus akses IT', 'outline-danger');
        }
    }
}
