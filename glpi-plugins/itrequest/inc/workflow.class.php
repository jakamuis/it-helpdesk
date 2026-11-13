<?php
class PluginItrequestWorkflow
{
    public const STATES = ['draft' => 'Draft', 'approval' => 'Menunggu Atasan Langsung',
        'director_approval' => 'Menunggu Persetujuan Direktur', 'revision' => 'Perlu Revisi',
        'queued' => 'Menunggu IT', 'processing' => 'Diproses', 'information' => 'Menunggu Kelengkapan',
        'done' => 'Selesai', 'rejected' => 'Ditolak', 'cancelled' => 'Dibatalkan'];
    public const TYPES = ['email' => 'Request Email', 'office365' => 'Pemasangan Office 365'];
    public const EMAIL_SERVICES = ['new' => 'Email baru', 'reset' => 'Reset / ubah password',
        'rename' => 'Ubah alamat email', 'delete' => 'Hapus alamat email'];
    public const POLICY = 'Fasilitas di atas hanya dipergunakan untuk keperluan dan kepentingan perusahaan serta menunjang aktivitas kerja. Tidak diperkenankan untuk meneruskan (forward) email perusahaan ke alamat email pribadi.';
    public static function transition(string $state, string $action, bool $owner, bool $approver, bool $staff, string $type = ''): string
    {
        $approval = ['approval','director_approval'];
        $rules = [
            'change' => [['queued','processing','information'], $staff || ($owner && $state === 'queued'), 'revision'],
            'submit' => [['draft','revision'], $owner, 'approval'],
            'withdraw' => [$approval, $owner, 'draft'],
            'approve' => [$approval, $approver && !$owner, $state === 'approval' && $type === 'email' ? 'director_approval' : 'queued'],
            'revise' => [$approval, $approver && !$owner, 'revision'],
            'reject' => [$approval, $approver && !$owner, 'rejected'],
            'start' => [['queued'], $staff, 'processing'],
            'ask' => [['queued','processing'], $staff, 'information'],
            'answer' => [['information'], $owner, 'processing'],
            'finish' => [['processing'], $staff, 'done'],
            'it_reject' => [['queued','processing','information'], $staff, 'rejected'],
            'cancel' => [['draft','approval','director_approval','revision','queued','processing','information'],
                $staff || ($owner && in_array($state, ['draft','approval','director_approval','revision','queued'], true)), 'cancelled'],
        ];
        if (!isset($rules[$action]) || !$rules[$action][1] || !in_array($state, $rules[$action][0], true)) {
            throw new InvalidArgumentException('Aksi tidak diizinkan pada status atau akun ini.');
        }
        return $rules[$action][2];
    }
    public static function payload(array $input, bool $complete): array
    {
        $data = [];
        foreach (['title','type','department','location','recipient','employee_number','job_title','company',
            'reason','needed_date','email_service','current_email','requested_email','asset','office_email','office_apps'] as $key) {
            $value = $input[$key] ?? '';
            if (!is_scalar($value)) { throw new InvalidArgumentException('Format field tidak valid: ' . $key); }
            $data[$key] = trim((string) $value);
            if (mb_strlen($data[$key]) > ($key === 'reason' ? 4000 : 255)) { throw new InvalidArgumentException('Isi field terlalu panjang: ' . $key); }
        }
        if (!isset(self::TYPES[$data['type']])) { throw new InvalidArgumentException('Pilih Request Email atau Pemasangan Office 365.'); }
        $data['policy_accepted'] = (string) ($input['policy_accepted'] ?? '') === '1' ? '1' : '0';
        if ($data['type'] === 'email') {
            foreach (['asset','office_email','office_apps'] as $key) { $data[$key] = ''; }
            if (!isset(self::EMAIL_SERVICES[$data['email_service']])) { throw new InvalidArgumentException('Pilih jenis layanan email.'); }
            if ($data['email_service'] === 'new') { $data['current_email'] = ''; }
            if (in_array($data['email_service'], ['reset','delete'], true)) { $data['requested_email'] = ''; }
        } else {
            foreach (['email_service','current_email','requested_email'] as $key) { $data[$key] = ''; }
        }
        foreach (['current_email','requested_email','office_email'] as $key) {
            if ($data[$key] !== '' && !filter_var($data[$key], FILTER_VALIDATE_EMAIL)) { throw new InvalidArgumentException('Format alamat email tidak valid: ' . $key); }
        }
        if ($complete) {
            foreach (['title','department','location','recipient','employee_number','job_title','company','reason','needed_date'] as $key) {
                if ($data[$key] === '') { throw new InvalidArgumentException('Field wajib belum lengkap: ' . $key); }
            }
            if (!self::date($data['needed_date']) || $data['needed_date'] < date('Y-m-d')) { throw new InvalidArgumentException('Tanggal dibutuhkan tidak valid atau sudah lewat.'); }
            if ($data['policy_accepted'] !== '1') { throw new InvalidArgumentException('Pernyataan penggunaan fasilitas wajib disetujui sebelum dikirim.'); }
            if ($data['type'] === 'email') {
                if ($data['email_service'] !== 'new' && $data['current_email'] === '') { throw new InvalidArgumentException('Alamat email saat ini wajib diisi.'); }
                if (in_array($data['email_service'], ['new','rename'], true) && $data['requested_email'] === '') { throw new InvalidArgumentException('Usulan alamat email baru wajib diisi.'); }
                if ($data['email_service'] === 'rename' && strcasecmp($data['current_email'], $data['requested_email']) === 0) { throw new InvalidArgumentException('Alamat email lama dan baru harus berbeda.'); }
            } elseif ($data['office_email'] === '' || $data['asset'] === '' || $data['office_apps'] === '') {
                throw new InvalidArgumentException('Email perusahaan, hostname/nomor aset, dan aplikasi Office yang dibutuhkan wajib diisi.');
            }
        }
        return $data;
    }
    public static function date(string $date): bool
    {
        $d = DateTimeImmutable::createFromFormat('!Y-m-d', $date);
        return $d !== false && $d->format('Y-m-d') === $date;
    }
}
