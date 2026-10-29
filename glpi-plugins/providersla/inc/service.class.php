<?php
require_once __DIR__ . '/clock.class.php';
/** All mutations require native technician/ticket rights and are serialized per ticket. */
final class PluginProviderslaService
{
    public const TABLE = 'glpi_plugin_providersla_episodes';
    public const EVENTS = 'glpi_plugin_providersla_events';

    public static function allowed(): bool
    {
        return Session::getCurrentInterface() === 'central' && Session::haveRight('ticket', UPDATE);
    }
    public static function ticket(int $id, bool $write = false): Ticket
    {
        if (!self::allowed()) {
            throw new Glpi\Exception\Http\AccessDeniedHttpException();
        }
        $ticket = new Ticket();
        if (!$ticket->can($id, READ) || ($write && !$ticket->can($id, UPDATE)) || !empty($ticket->fields['is_deleted'])) {
            throw new Glpi\Exception\Http\AccessDeniedHttpException();
        }
        return $ticket;
    }
    public static function rows(int $ticket): array
    {
        global $DB;
        return iterator_to_array($DB->request(['FROM' => self::TABLE, 'WHERE' => ['tickets_id' => $ticket],
            'ORDER' => ['transferred_epoch', 'id']]));
    }
    public static function suppliers(Ticket $ticket): array
    {
        global $DB;
        return iterator_to_array($DB->request(['SELECT' => ['id', 'name'], 'FROM' => 'glpi_suppliers',
            'WHERE' => ['is_deleted' => 0] + getEntitiesRestrictCriteria('glpi_suppliers', '', (int) $ticket->fields['entities_id'], true),
            'ORDER' => 'name']));
    }
    private static function text(array $input, string $key, bool $required = false, int $max = 4000): string
    {
        $text = trim((string) ($input[$key] ?? ''));
        if (($required && $text === '') || mb_strlen($text) > $max) {
            throw new InvalidArgumentException('Isi ' . $key . ' wajib/terlalu panjang (maksimal ' . $max . ' karakter).');
        }
        return $text;
    }
    private static function event(int $episode, int $ticket, string $action, array $details): void
    {
        global $DB;
        $DB->insert(self::EVENTS, ['episodes_id' => $episode, 'tickets_id' => $ticket,
            'users_id' => (int) Session::getLoginUserID(), 'event_epoch' => time(), 'action' => $action,
            'details' => json_encode($details, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)]);
    }
    private static function instant(array $input, string $key): int
    {
        $value = trim((string) ($input[$key] ?? ''));
        // The quick form uses the actual save time unless Helpdesk supplies a past event time.
        return $value === '' && (string) ($input['_use_current_time'] ?? '') === '1'
            ? time() : PluginProviderslaClock::parse($value);
    }
    public static function mutate(int $id, string $action, array $input): void
    {
        global $DB;
        self::ticket($id, true);
        if (!in_array($action, ['start', 'restore', 'reference', 'void'], true)) {
            throw new InvalidArgumentException('Aksi tidak dikenal.');
        }
        $DB->beginTransaction();
        try {
            // Serializes transfers, restores, and cancellations even for concurrent POSTs.
            $DB->doQuery('SELECT id FROM glpi_tickets WHERE id=' . $id . ' FOR UPDATE');
            $ticket = self::ticket($id, true);
            $rows = self::rows($id);
            if ($action === 'start') {
                self::start($ticket, $rows, $input);
            } else {
                $episode = null;
                foreach ($rows as $row) {
                    if ((int) $row['id'] === (int) ($input['episode_id'] ?? 0)) {
                        $episode = $row;
                    }
                }
                if ($episode === null || !empty($episode['is_void'])) {
                    throw new InvalidArgumentException('Episode tidak ditemukan atau sudah dibatalkan.');
                }
                self::change($ticket, $episode, $action, $input);
            }
            $DB->commit();
        } catch (Throwable $e) {
            $DB->rollBack();
            throw $e;
        }
    }
    private static function start(Ticket $ticket, array $rows, array $input): void
    {
        global $DB;
        if (in_array((int) $ticket->fields['status'], [Ticket::SOLVED, Ticket::CLOSED], true)) {
            throw new InvalidArgumentException('Buka kembali tiket melalui proses GLPI sebelum pengalihan baru.');
        }
        $start = self::instant($input, 'transferred_at');
        $boundary = $DB->doQuery('SELECT UNIX_TIMESTAMP(date) AS epoch FROM glpi_tickets WHERE id=' . (int) $ticket->getID())->fetch_assoc();
        if ($start > time() || $start < (int) $boundary['epoch']) {
            throw new InvalidArgumentException('Pengalihan harus setelah tiket dibuat dan tidak boleh di masa depan.');
        }
        foreach ($rows as $row) {
            if (!empty($row['is_void'])) {
                continue;
            }
            if ($row['restored_epoch'] === null) {
                throw new InvalidArgumentException('Masih ada pengalihan aktif. Hitungan tidak direset; selesaikan atau batalkan dahulu.');
            }
            if ($start < (int) $row['restored_epoch']) {
                throw new InvalidArgumentException('Pengalihan tidak boleh tumpang tindih dengan episode sebelumnya.');
            }
        }
        if ((int) $ticket->fields['status'] === Ticket::WAITING) {
            throw new InvalidArgumentException('Tiket sudah Pending. Lanjutkan penanganan Helpdesk terlebih dahulu sebelum pengalihan baru.');
        }
        $supplierId = (int) ($input['suppliers_id'] ?? 0);
        $name = self::text($input, 'provider_name', false, 255);
        if ($supplierId > 0) {
            $supplier = array_values(array_filter(self::suppliers($ticket), fn($r) => (int) $r['id'] === $supplierId));
            if (!$supplier) {
                throw new InvalidArgumentException('Supplier tidak tersedia pada entity tiket.');
            }
            $name = $supplier[0]['name'];
        }
        if ($name === '') {
            throw new InvalidArgumentException('Pilih Supplier atau isi nama provider.');
        }
        $target = PluginProviderslaClock::target((string) ($input['target_hours'] ?? ''));
        $evidence = self::text($input, 'transfer_evidence', true);
        $oldStatus = (int) $ticket->fields['status'];
        // GLPI's native timers pause on Pending; the independent provider clock does not.
        if ($oldStatus !== Ticket::WAITING) {
            if (!$ticket->isAllowedStatus($oldStatus, Ticket::WAITING)
                || !$ticket->update(['id' => $ticket->getID(), 'status' => Ticket::WAITING, '_disablenotif' => true])) {
                throw new RuntimeException('Status Pending tidak dapat diterapkan. Pengalihan dibatalkan.');
            }
            $ticket->getFromDB($ticket->getID());
            if ((int) $ticket->fields['status'] !== Ticket::WAITING) {
                throw new RuntimeException('GLPI tidak menerima perubahan status Pending.');
            }
        }
        if ($supplierId > 0) {
            $actor = new Supplier_Ticket();
            $found = count($actor->find(['tickets_id' => $ticket->getID(), 'suppliers_id' => $supplierId, 'type' => CommonITILActor::ASSIGN]));
            if (!$found && !$actor->add(['tickets_id' => $ticket->getID(), 'suppliers_id' => $supplierId,
                'type' => CommonITILActor::ASSIGN, 'use_notification' => 0, '_disablenotif' => true])) {
                throw new RuntimeException('Supplier gagal ditautkan. Pengalihan dibatalkan.');
            }
        }
        $DB->insert(self::TABLE, ['tickets_id' => $ticket->getID(), 'entities_id' => $ticket->fields['entities_id'],
            'open_ticket_id' => $ticket->getID(), 'suppliers_id' => $supplierId, 'provider_name' => $name,
            'circuit' => self::text($input, 'circuit', false, 255), 'reference' => self::text($input, 'reference', false, 255),
            'transferred_epoch' => $start, 'target_seconds' => $target, 'transfer_evidence' => $evidence,
            'users_id_start' => (int) Session::getLoginUserID(), 'previous_status' => $oldStatus,
            'paused_by_plugin' => (int) ($oldStatus !== Ticket::WAITING), 'created_epoch' => time()]);
        $episodeId = (int) $DB->insertId();
        self::event($episodeId, (int) $ticket->getID(), 'start', ['provider' => $name, 'transferred_epoch' => $start,
            'target_seconds' => $target, 'evidence' => $evidence, 'previous_status' => $oldStatus]);
    }
    private static function change(Ticket $ticket, array $row, string $action, array $input): void
    {
        global $DB;
        $update = [];
        if ($action === 'reference') {
            $update['reference'] = self::text($input, 'reference', true, 255);
        } elseif ($action === 'restore') {
            if ($row['restored_epoch'] !== null) {
                throw new InvalidArgumentException('Pemulihan sudah tercatat.');
            }
            $end = self::instant($input, 'restored_at');
            if ($end < (int) $row['transferred_epoch'] || $end > time()) {
                throw new InvalidArgumentException('Pemulihan harus setelah pengalihan dan tidak boleh di masa depan.');
            }
            $update = ['restored_epoch' => $end, 'verified_epoch' => time(), 'users_id_end' => (int) Session::getLoginUserID(),
                'open_ticket_id' => null, 'recovery_evidence' => self::text($input, 'recovery_evidence', true)];
        } else {
            $update = ['is_void' => 1, 'open_ticket_id' => null];
        }
        // Resume only a Pending state created by this episode. Preserve unrelated workflow changes.
        if (in_array($action, ['restore', 'void'], true) && $row['restored_epoch'] === null
            && !empty($row['paused_by_plugin']) && (int) $ticket->fields['status'] === Ticket::WAITING) {
            $status = $action === 'void' ? (int) $row['previous_status'] : Ticket::ASSIGNED;
            if (!$ticket->isAllowedStatus(Ticket::WAITING, $status)
                || !$ticket->update(['id' => $ticket->getID(), 'status' => $status, '_disablenotif' => true])) {
                throw new RuntimeException('Status Helpdesk tidak dapat dilanjutkan; perubahan dibatalkan.');
            }
        }
        $details = ['before' => $row, 'after' => $update];
        if ($action === 'void') {
            $details['reason'] = self::text($input, 'reason', true);
        }
        $DB->update(self::TABLE, $update, ['id' => (int) $row['id']]);
        self::event((int) $row['id'], (int) $ticket->getID(), $action, $details);
    }
}
