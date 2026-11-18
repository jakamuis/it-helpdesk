<?php
require_once __DIR__ . '/workflow.class.php';
class PluginItrequestService
{
    public const PREFIX = 'glpi_plugin_itrequest_';
    public static function uid(): int { return (int) Session::getLoginUserID(); }
    public static function entity(): int { return (int) ($_SESSION['glpiactive_entity'] ?? 0); }
    public static function admin(): bool { return Session::haveRight('config', UPDATE); }
    public static function rows(string $table, array $where = [], array $extra = []): array
    {
        global $DB;
        return iterator_to_array($DB->request(['FROM' => self::PREFIX . $table, 'WHERE' => $where] + $extra), false);
    }
    public static function staff(int $entity): bool
    {
        return count(self::rows('staff', ['entities_id' => $entity, 'users_id' => self::uid()])) > 0;
    }
    public static function manager(int $entity): bool
    {
        return self::admin() || count(self::rows('managers', ['entities_id' => $entity, 'users_id' => self::uid()])) > 0;
    }
    public static function worker(array $r): bool
    {
        return self::manager((int) $r['entities_id']) || (self::staff((int) $r['entities_id']) && (int) $r['assigned_id'] === self::uid());
    }
    public static function member(int $uid, int $entity): bool
    {
        global $DB;
        $user = new User();
        if (!$user->getFromDB($uid) || !$user->fields['is_active'] || $user->fields['is_deleted']) { return false; }
        $ancestors = array_map('intval', array_values(getAncestorsOf('glpi_entities', $entity)));
        $ancestors[] = 0;
        foreach ($DB->request(['FROM' => 'glpi_profiles_users', 'WHERE' => ['users_id' => $uid]]) as $profile) {
            if ((int) $profile['entities_id'] === $entity || ($profile['is_recursive'] && in_array((int) $profile['entities_id'], $ancestors, true))) { return true; }
        }
        return false;
    }
    public static function currentApprover(array $r): int
    {
        return (int) ($r[$r['status'] === 'director_approval' ? 'directors_id' : 'approvers_id'] ?? 0);
    }
    public static function get(int $id): array
    {
        $r = self::rows('requests', ['id' => $id])[0] ?? null;
        if (!$r || (int) $r['entities_id'] !== self::entity()) { throw new RuntimeException('Request tidak ditemukan dalam entity aktif.'); }
        $owner = (int) $r['users_id'] === self::uid();
        $approver = ((int) $r['approvers_id'] === self::uid() || ((int) ($r['directors_id'] ?? 0) === self::uid() && !empty($r['manager_approved_at']))) && $r['status'] !== 'draft';
        $staff = !empty($r['approved_at']) && self::worker($r) && !in_array($r['status'], ['draft','approval','director_approval','revision'], true);
        if (!$owner && !$approver && !$staff && !self::admin()) { throw new RuntimeException('Anda tidak memiliki akses ke request ini.'); }
        return $r;
    }
    public static function insert(string $table, array $data): int
    {
        global $DB;
        if (!$DB->insert(self::PREFIX . $table, $data)) { throw new RuntimeException('Gagal menyimpan data.'); }
        return (int) $DB->insertId();
    }
    public static function update(string $table, array $data, array $where): void
    {
        global $DB;
        if (!$DB->update(self::PREFIX . $table, $data, $where)) { throw new RuntimeException('Gagal memperbarui data.'); }
    }
    public static function event(int $id, string $action, array $details): void
    {
        self::insert('events', ['requests_id' => $id, 'users_id' => self::uid(), 'action' => $action,
            'details' => json_encode($details, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE), 'created_at' => date('Y-m-d H:i:s')]);
    }
    private static function createPortalTicket(array $request, array $data): array
    {
        require_once dirname(__DIR__, 2) . '/layananit/inc/ticketformat.class.php';
        $entity = (int) $request['entities_id'];
        $requester = (int) $request['users_id'];
        $fields = PluginLayananitTicketFormat::portalFields($requester, $data['location'], $data['title'], $data['reason']);
        $url = Plugin::getWebDir('itrequest') . '/front/index.php?id=' . (int) $request['id'];
        $ticket = new Ticket();
        $id = $ticket->add([
            '_layananit_portal_ticket' => true,
            '_users_id_requester' => $requester,
            '_skip_auto_assign' => true,
            'type' => Ticket::DEMAND_TYPE,
            'entities_id' => $entity,
            'locations_id' => PluginLayananitTicketFormat::locationId($fields['site'], $entity),
            'name' => PluginLayananitTicketFormat::portalTitle($fields),
            'content' => '[HELPDESK_PORTAL_V1]<br>' . htmlescape($data['title']) . '<br>'
                . nl2br(htmlescape($data['reason'])) . '<br><a href="' . htmlescape($url)
                . '">Pengajuan dan persetujuan Request IT</a>',
        ]);
        if (!$id) {
            throw new RuntimeException('Tiket GLPI untuk pengajuan ini gagal dibuat.');
        }
        return ['id' => (int) $id, 'fields' => $fields];
    }

    public static function mutate(int $id, string $action, array $input): int
    {
        global $DB;
        $DB->beginTransaction();
        try {
            if ($action === 'create') {
                $data = PluginItrequestWorkflow::payload($input, false);
                $data['_helpdesk_v1'] = Plugin::isPluginActive('layananit');
                $now = date('Y-m-d H:i:s');
                $id = self::insert('requests', ['entities_id' => self::entity(), 'users_id' => self::uid(),
                    'status' => 'draft', 'payload' => json_encode($data, JSON_THROW_ON_ERROR), 'created_at' => $now, 'updated_at' => $now]);
                self::event($id, 'create', ['snapshot' => $data]);
            } else {
                // Serializes decisions; version also prevents stale forms from overwriting newer work.
                $DB->doQuery('SELECT id FROM ' . self::PREFIX . 'requests WHERE id=' . $id . ' FOR UPDATE');
                $r = self::get($id);
                if ((int) ($input['version'] ?? 0) !== (int) $r['version']) { throw new InvalidArgumentException('Request sudah berubah. Muat ulang halaman.'); }
                $owner = (int) $r['users_id'] === self::uid();
                $approver = self::currentApprover($r) === self::uid();
                $payload = json_decode($r['payload'], true, 512, JSON_THROW_ON_ERROR);
                $staff = self::worker($r);
                $changes = ['version' => (int) $r['version'] + 1, 'updated_at' => date('Y-m-d H:i:s')];
                $note = trim((string) ($input['note'] ?? ''));
                if (mb_strlen($note) > 4000) { throw new InvalidArgumentException('Catatan maksimal 4000 karakter.'); }
                $details = ['note' => $note, 'from' => $r['status']];
                if ($action === 'assign') {
                    if (!self::manager((int) $r['entities_id']) || empty($r['approved_at']) || !in_array($r['status'], ['queued','processing','information'], true)) { throw new InvalidArgumentException('Hanya IT Manager dapat menugaskan pengajuan yang telah disetujui.'); }
                    $pic = (int) ($input['assigned_id'] ?? 0);
                    if (!self::member($pic, (int) $r['entities_id']) || !self::rows('staff', ['entities_id' => $r['entities_id'], 'users_id' => $pic])) { throw new InvalidArgumentException('PIC harus anggota IT aktif pada entity ini.'); }
                    if ((int) $r['assigned_id'] && $note === '') { throw new InvalidArgumentException('Alasan pergantian PIC wajib diisi.'); }
                    $changes['assigned_id'] = $pic;
                    $details += ['previous_assigned_id' => (int) $r['assigned_id'], 'assigned_id' => $pic];
                } elseif ($action === 'reassign') {
                    if (!self::admin() || !in_array($r['status'], ['approval','director_approval'], true) || $note === '') { throw new InvalidArgumentException('Pengalihan hanya oleh admin pada status menunggu approval, dengan alasan.'); }
                    $aid = (int) ($input['approvers_id'] ?? 0);
                    if ($aid === (int) $r['users_id'] || $aid === (int) ($r[$r['status'] === 'director_approval' ? 'approvers_id' : 'directors_id'] ?? 0) || !self::member($aid, (int) $r['entities_id'])) { throw new InvalidArgumentException('Approver pengganti tidak valid.'); }
                    $column = $r['status'] === 'director_approval' ? 'directors_id' : 'approvers_id';
                    $changes[$column] = $aid;
                    $details['previous_approver'] = (int) $r[$column];
                    $details['stage'] = $r['status'];
                    $details['approvers_id'] = $aid;
                } elseif ($action === 'save') {
                    if (!$owner || !in_array($r['status'], ['draft','revision'], true)) { throw new InvalidArgumentException('Isi request tidak dapat diedit pada status ini.'); }
                    $data = PluginItrequestWorkflow::payload($input, false);
                    $data += array_intersect_key($payload, array_flip(['_helpdesk_v1', '_glpi_ticket']));
                    $changes['payload'] = json_encode($data, JSON_THROW_ON_ERROR);
                    $details['snapshot'] = $data;
                } else {
                    $changes['status'] = PluginItrequestWorkflow::transition($r['status'], $action, $owner, $approver, $staff, (string) ($payload['type'] ?? ''));
                    if (in_array($action, ['revise','reject','it_reject','ask','answer','finish','cancel','change'], true) && $note === '') {
                        throw new InvalidArgumentException('Alasan, jawaban, atau hasil pengerjaan wajib diisi.');
                    }
                    if ($action === 'submit') {
                        $data = PluginItrequestWorkflow::payload(json_decode($r['payload'], true, 512, JSON_THROW_ON_ERROR), true);
                        $mapping = self::rows('mappings', ['entities_id' => $r['entities_id'], 'users_id' => self::uid()])[0] ?? [];
                        $aid = (int) ($mapping['approvers_id'] ?? 0);
                        if (!$aid || $aid === self::uid() || !self::member($aid, (int) $r['entities_id'])) { throw new InvalidArgumentException('Atasan belum dipetakan atau tidak aktif. Hubungi admin.'); }
                        $director = $data['type'] === 'email' ? (int) ($mapping['directors_id'] ?? 0) : 0;
                        if ($data['type'] === 'email' && (!$director || $director === self::uid() || $director === $aid || !self::member($director, (int) $r['entities_id']))) {
                            throw new InvalidArgumentException('Direktur belum dipetakan atau tidak valid. Direktur harus akun lain dari pemohon dan atasan. Hubungi admin.');
                        }
                        $changes += ['approvers_id' => $aid, 'directors_id' => $director, 'manager_approved_at' => null, 'approved_at' => null];
                        $details['directors_id'] = $director;
                        $details['policy'] = PluginItrequestWorkflow::POLICY;
                        $details['policy_accepted_by'] = self::uid();
                        $details['snapshot'] = $data;
                        $details['approvers_id'] = $aid;
                        if (!empty($payload['_helpdesk_v1']) && empty($payload['_glpi_ticket']) && Plugin::isPluginActive('layananit')) {
                            $payload['_glpi_ticket'] = self::createPortalTicket($r, $data);
                            $changes['payload'] = json_encode($payload, JSON_THROW_ON_ERROR);
                        }

                    }
                    if ($action === 'change') { $changes += ['assigned_id' => 0, 'target_date' => '', 'approved_at' => null]; }
                    if ($action === 'approve') {
                        if (!self::member(self::currentApprover($r), (int) $r['entities_id'])) { throw new InvalidArgumentException('Approver tidak aktif dalam entity ini.'); }
                        if ($changes['status'] === 'director_approval' && (empty($r['directors_id']) || !self::member((int) $r['directors_id'], (int) $r['entities_id']))) { throw new InvalidArgumentException('Direktur tidak aktif. Hubungi admin.'); }
                        if ($r['status'] === 'director_approval' && empty($r['manager_approved_at'])) { throw new InvalidArgumentException('Persetujuan atasan belum tersedia.'); }
                        $changes[$r['status'] === 'approval' ? 'manager_approved_at' : 'approved_at'] = date('Y-m-d H:i:s');
                        if ($changes['status'] === 'queued') { $changes['approved_at'] = date('Y-m-d H:i:s'); }
                        $details['stage'] = $r['status'];
                    }
                    if ($action === 'start') {
                        $target = (string) ($input['target_date'] ?? '');
                        if (!PluginItrequestWorkflow::date($target) || $target < date('Y-m-d')) { throw new InvalidArgumentException('Isi target selesai yang valid.'); }
                        if (!(int) $r['assigned_id']) { throw new InvalidArgumentException('IT Manager harus menunjuk PIC sebelum pekerjaan dimulai.'); }
                        $changes['target_date'] = $target;
                        $details['target_date'] = $target;
                    }
                    // Resume exactly the state before IT asked for information.
                    if ($action === 'answer') {
                        $events = self::rows('events', ['requests_id' => $id, 'action' => 'ask'], ['ORDER' => 'id DESC', 'LIMIT' => 1]);
                        $previous = json_decode($events[0]['details'] ?? '{}', true)['from'] ?? 'queued';
                        $changes['status'] = $previous === 'processing' ? 'processing' : 'queued';
                    }
                    $details['to'] = $changes['status'];
                }
                self::update('requests', $changes, ['id' => $id]);
                $details['version'] = $changes['version'];
                self::event($id, $action, $details);
            }
            $DB->commit();
            return $id;
        } catch (Throwable $e) { $DB->rollBack(); throw $e; }
    }
    public static function configure(string $action, array $input): void
    {
        if (!self::admin()) { throw new RuntimeException('Hanya admin konfigurasi.'); }
        $uid = (int) ($input['users_id'] ?? 0);
        $aid = (int) ($input['approvers_id'] ?? 0);
        $director = (int) ($input['directors_id'] ?? 0);
        $entity = self::entity();
        if (!self::member($uid, $entity)) { throw new InvalidArgumentException('User tidak aktif atau bukan anggota entity ini.'); }
        if ($action === 'mapping' && ($uid === $aid || !self::member($aid, $entity))) { throw new InvalidArgumentException('Atasan harus akun aktif lain dalam entity ini.'); }
        if ($action === 'mapping' && $director && ($director === $uid || $director === $aid || !self::member($director, $entity))) { throw new InvalidArgumentException('Direktur harus akun aktif lain dari pemohon dan atasan dalam entity ini.'); }
        if ($action === 'contact') {
            $chat = trim((string) ($input['chat_id'] ?? ''));
            if (!preg_match('/^[1-9][0-9]{7,14}@c\.us$/D', $chat)) { throw new InvalidArgumentException('Gunakan nomor WA terverifikasi dengan format 628xxxxxxxxxx@c.us.'); }
            $where = ['entities_id' => $entity, 'users_id' => $uid];
            $last = self::rows('events', [], ['ORDER' => 'id DESC', 'LIMIT' => 1]);
            $contact = ['chat_id' => $chat, 'after_event_id' => (int) ($last[0]['id'] ?? 0)];
            if (self::rows('contacts', $where)) { self::update('contacts', $contact, $where); }
            else { self::insert('contacts', $where + $contact); }
            self::event(0, 'contact', $where); // Do not copy personal phone numbers into the audit trail.
            return;
        }
        $table = $action === 'mapping'  ? 'mappings' : (in_array($action, ['manager','remove_manager'], true) ? 'managers' : 'staff');
        $where = ['entities_id' => $entity, 'users_id' => $uid];
        if (in_array($action, ['remove_staff','remove_manager'], true)) {
            global $DB;
            if (!$DB->delete(self::PREFIX . $table, $where)) { throw new RuntimeException('Gagal menghapus akses IT.'); }
        } elseif ($table === 'mappings') {
            if (self::rows($table, $where)) { self::update($table, ['approvers_id' => $aid, 'directors_id' => $director], $where); }
            else { self::insert($table, $where + ['approvers_id' => $aid, 'directors_id' => $director]); }
        } elseif (!self::rows($table, $where)) { self::insert($table, $where); }
        self::event(0, $action, $where + ['approvers_id' => $aid, 'directors_id' => $director]);
    }
}
