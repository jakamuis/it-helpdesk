<?php
require_once __DIR__ . '/ticket.class.php';

/** Native GLPI fields-panel hook; forms are loaded outside the native ticket form. */
final class PluginProviderslaSidebar
{
    private static function active(int $id): ?array
    {
        foreach (PluginProviderslaService::rows($id) as $row) {
            if (empty($row['is_void']) && $row['restored_epoch'] === null) {
                return $row;
            }
        }
        return null;
    }

    public static function show(array $params): void
    {
        $ticket = $params['item'] ?? null;
        if (!$ticket instanceof Ticket || $ticket->isNewItem() || !PluginProviderslaService::allowed()
            || !empty($params['options']['template_preview']) || !empty($ticket->fields['is_deleted'])
            || !$ticket->can($ticket->getID(), READ)) {
            return;
        }
        $id = (int) $ticket->getID();
        $active = self::active($id);
        $canWrite = $ticket->can($id, UPDATE);
        $closed = in_array((int) $ticket->fields['status'], [Ticket::SOLVED, Ticket::CLOSED], true);
        $url = Plugin::getWebDir('providersla') . '/front/assign.php?tickets_id=' . $id;
        $history = Ticket::getFormURLWithID($id) . '&forcetab=' . rawurlencode('PluginProviderslaTicket$1');
        echo '<section class="accordion-item providersla-sidebar" aria-label="SLA Provider"><div class="p-3">';
        echo '<h3 class="h4 mb-2"><i class="ti ti-clock-share me-1" aria-hidden="true"></i>SLA Provider</h3>';
        if ($active !== null) {
            $metrics = PluginProviderslaClock::metrics($active, time());
            echo '<div class="mb-2"><strong>' . PluginProviderslaTicket::h($active['provider_name']) . '</strong>'
                . '<div class="text-muted">Sejak ' . PluginProviderslaTicket::h(PluginProviderslaClock::date((int) $active['transferred_epoch'])) . ' WIB</div>'
                . '<div>Durasi: <strong>' . PluginProviderslaTicket::h(PluginProviderslaClock::duration($metrics['seconds'])) . '</strong>'
                . ' · ' . PluginProviderslaTicket::h($metrics['status']) . '</div></div>';
            foreach (['Incident' => $active['reference'], 'SID/Pelanggan' => $active['customer_sid'] ?? ''] as $label => $value) {
                if ($value !== '') {
                    echo '<div class="small mb-1 text-break">' . $label . ': ' . PluginProviderslaTicket::h($value) . '</div>';
                }
            }
            if ($canWrite) {
                self::button($url . '&mode=restore', 'Catat layanan pulih');
            }
        } elseif ($canWrite && !$closed) {
            echo '<p class="text-muted mb-2">Eskalasi dari Helpdesk untuk mulai menghitung durasi vendor. Tanpa target.</p>';
            self::button($url, 'Eskalasi ke Vendor');
        } else {
            echo '<p class="text-muted mb-2">Tidak ada pengalihan provider aktif.</p>';
        }
        echo '<a class="d-block small mt-2" href="' . PluginProviderslaTicket::h($history) . '">Riwayat & detail vendor</a>';
        echo '</div></section>';
    }

    private static function button(string $url, string $label): void
    {
        // type=button avoids submitting the surrounding GLPI ticket form.
        echo '<button type="button" class="btn btn-outline-primary w-100" data-providersla-dialog="'
            . PluginProviderslaTicket::h($url) . '">' . PluginProviderslaTicket::h($label) . '</button>';
    }

    public static function form(int $id, string $mode): void
    {
        $ticket = PluginProviderslaService::ticket($id, true);
        $active = self::active($id);
        $restore = $mode === 'restore';
        if ($restore && $active === null) {
            throw new InvalidArgumentException('Tidak ada pengalihan aktif. Muat ulang tiket.');
        }
        if (!$restore && ($active !== null || in_array((int) $ticket->fields['status'], [Ticket::SOLVED, Ticket::CLOSED], true))) {
            throw new InvalidArgumentException('Tiket sudah dialihkan atau sudah selesai. Muat ulang tiket.');
        }
        echo '<h2 id="providersla-dialog-title" class="h2 mb-3">' . ($restore ? 'Catat layanan pulih' : 'Eskalasi ke Vendor') . '</h2>';
        echo '<form method="post" action="' . PluginProviderslaTicket::h(Plugin::getWebDir('providersla') . '/front/action.php') . '">';
        foreach (['tickets_id' => $id, 'action' => $restore ? 'restore' : 'start', 'episode_id' => $active['id'] ?? 0,
            '_glpi_csrf_token' => Session::getNewCSRFToken(), 'return_to' => 'sidebar', '_use_current_time' => '1'] as $key => $value) {
            echo '<input type="hidden" name="' . PluginProviderslaTicket::h($key) . '" value="' . PluginProviderslaTicket::h($value) . '">';
        }
        if ($restore) {
            echo '<p>Vendor: <strong>' . PluginProviderslaTicket::h($active['provider_name']) . '</strong></p>';
            PluginProviderslaTicket::field('recovery_evidence', 'Hasil pemeriksaan / bukti layanan pulih', 'textarea', true);
            echo '<p class="text-muted">Durasi provider berhenti saat disimpan. Penanganan Helpdesk dilanjutkan.</p>';
        } else {
            $suppliers = PluginProviderslaService::suppliers($ticket);
            if ($suppliers) {
                echo '<label class="form-label d-block mb-3">Vendor<select class="form-select" name="suppliers_id"><option value="0">Isi nama vendor di bawah</option>';
                foreach ($suppliers as $supplier) {
                    echo '<option value="' . (int) $supplier['id'] . '">' . PluginProviderslaTicket::h($supplier['name']) . '</option>';
                }
                echo '</select></label>';
            }
            PluginProviderslaTicket::field('provider_name', $suppliers ? 'Nama vendor (jika tidak dipilih di atas)' : 'Nama vendor', 'text', !$suppliers);
            PluginProviderslaTicket::field('reference', 'No. Incident dari Provider (opsional)');
            PluginProviderslaTicket::field('customer_sid', 'Nomor SID/Pelanggan (opsional)');
            PluginProviderslaTicket::field('transfer_evidence', 'Catatan pemeriksaan / bukti laporan ke vendor', 'textarea', true);
            echo '<p class="text-muted">Mulai dihitung saat disimpan, 24×7, tanpa target. Tiket menjadi Pending. Pastikan laporan sudah dikirim ke vendor.</p>';
        }
        echo '<details class="mb-3"><summary>Detail tambahan / ubah waktu</summary><div class="mt-3">';
        PluginProviderslaTicket::field($restore ? 'restored_at' : 'transferred_at', $restore ? 'Waktu pulih (WIB)' : 'Waktu pengalihan (WIB)', 'datetime-local');
        echo '<p class="small text-muted">Kosong = waktu saat disimpan. Isi jika mencatat kejadian sebelumnya.</p>';
        if (!$restore) {
            PluginProviderslaTicket::field('circuit', 'Layanan / aset / lokasi (opsional)');
        }
        echo '</div></details><div class="d-flex justify-content-end gap-2">'
            . '<button type="button" class="btn btn-outline-secondary" data-providersla-close>Batal</button>'
            . '<button type="submit" class="btn btn-primary">' . ($restore ? 'Simpan pemulihan' : 'Eskalasi & mulai hitung') . '</button></div></form>';
    }
}
