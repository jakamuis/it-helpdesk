<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/ticket.class.php';
global $DB;
Session::checkLoginUser();
if (!PluginProviderslaService::allowed()) {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
$now = time();
$from = (string) ($_GET['from'] ?? PluginProviderslaClock::date($now - 29 * 86400, 'Y-m-d'));
$until = (string) ($_GET['until'] ?? PluginProviderslaClock::date($now, 'Y-m-d'));
$error = null;
$rows = [];
$overflow = false;
try {
    $start = PluginProviderslaClock::parse($from . ' 00:00');
    $end = PluginProviderslaClock::parse($until . ' 00:00') + 86400;
    if ($end <= $start) { throw new InvalidArgumentException('Rentang tanggal tidak valid.'); }
    $where = ['transferred_epoch' => ['>=', $start],
        'AND' => [['transferred_epoch' => ['<', $end]]]]
        + getEntitiesRestrictCriteria(PluginProviderslaService::TABLE);
    foreach ($DB->request(['FROM' => PluginProviderslaService::TABLE, 'WHERE' => $where,
        'ORDER' => ['transferred_epoch DESC', 'id DESC']]) as $row) {
        $ticket = new Ticket();
        if (!$ticket->can((int) $row['tickets_id'], READ) || !empty($ticket->fields['is_deleted'])) { continue; }
        if (count($rows) >= 500) { $overflow = true; break; }
        $row['ticket_name'] = $ticket->fields['name'];
        $row['metrics'] = PluginProviderslaClock::metrics($row, $now);
        $rows[] = $row;
    }
} catch (InvalidArgumentException $e) { $error = $e->getMessage(); }
if (isset($_GET['csv']) && !$error) {
    $output = fopen('php://temp', 'w+');
    // UTF-8 BOM keeps Indonesian provider names readable in desktop spreadsheet apps.
    fwrite($output, "\xEF\xBB\xBF");
    fputcsv($output, ['Episode', 'Ticket GLPI', 'Judul', 'Vendor', 'Layanan / aset / lokasi', 'No. Incident dari Provider',
        'Dialihkan Asia/Jakarta', 'Pulih Asia/Jakarta', 'Target detik', 'Deadline Asia/Jakarta', 'Durasi detik',
        'Hasil', 'Snapshot Asia/Jakarta', 'Ekspor terpotong (maks 500)', 'Nomor SID/Pelanggan'], ',', '"', '');
    foreach ($rows as $row) {
        $m = $row['metrics'];
        fputcsv($output, array_map(fn($v) => PluginProviderslaClock::csv((string) $v),
            [$row['id'], $row['tickets_id'], $row['ticket_name'], $row['provider_name'], $row['circuit'], $row['reference'],
            PluginProviderslaClock::date((int) $row['transferred_epoch']),
            PluginProviderslaClock::date(isset($row['restored_epoch']) ? (int) $row['restored_epoch'] : null),
            $row['target_seconds'] ?? '', PluginProviderslaClock::date($m['deadline']), $m['seconds'], $m['status'],
            PluginProviderslaClock::date($now), $overflow ? 'Ya; persempit tanggal' : 'Tidak', $row['customer_sid'] ?? '']), ',', '"', '');
    }
    rewind($output); $csv = stream_get_contents($output); fclose($output);
    return new Symfony\Component\HttpFoundation\Response($csv, 200, ['Content-Type' => 'text/csv; charset=UTF-8',
        'Content-Disposition' => 'attachment; filename="sla-provider.csv"', 'Cache-Control' => 'no-store']);
}
Html::header('Laporan SLA Provider', '', 'tools', 'pluginproviderslaticket');
echo '<div class="card"><div class="card-body"><h1 class="card-title">Laporan SLA Provider</h1>';
echo '<p>Dipilih berdasarkan tanggal pengalihan. Durasi episode dihitung penuh sampai pulih atau snapshot saat ini: '
    . PluginProviderslaTicket::h(PluginProviderslaClock::date($now)) . ' Asia/Jakarta. Episode dibatalkan tetap terlihat dan dikecualikan dari ringkasan.</p>';
echo '<form method="get" class="row g-3 mb-3"><div class="col-md-4">';
PluginProviderslaTicket::field('from', 'Pengalihan dari', 'date', true, $from);
echo '</div><div class="col-md-4">';PluginProviderslaTicket::field('until', 'Sampai', 'date', true, $until);
echo '</div><div class="col-md-4 align-self-center"><button class="btn btn-primary">Tampilkan</button> '
    . '<button class="btn btn-outline-secondary" name="csv" value="1">Unduh CSV</button></div></form>';
if ($error) { echo '<div class="alert alert-danger">' . PluginProviderslaTicket::h($error) . '</div>'; }
if ($overflow) { echo '<div class="alert alert-warning">Hasil dan CSV dibatasi 500 episode. Persempit rentang tanggal untuk laporan lengkap.</div>'; }
$counts = [];
foreach ($rows as $row) { $s = $row['metrics']['status']; $counts[$s] = ($counts[$s] ?? 0) + 1; }
$total = ($counts['Memenuhi'] ?? 0) + ($counts['Melanggar'] ?? 0);
echo '<p>Kepatuhan episode selesai dengan target: <strong>' . ($total ? round(100 * ($counts['Memenuhi'] ?? 0) / $total, 2) . '%' : 'N/A')
    . '</strong> · Memenuhi ' . ($counts['Memenuhi'] ?? 0) . ' · Melanggar ' . ($counts['Melanggar'] ?? 0)
    . ' · Berjalan belum lewat ' . ($counts['Berjalan, belum lewat'] ?? 0) . ' · Berjalan terlambat ' . ($counts['Berjalan, terlambat'] ?? 0)
    . ' · Tanpa Target ' . ($counts['Tanpa Target'] ?? 0) . ' · Dibatalkan ' . ($counts['Dibatalkan'] ?? 0) . '</p>';
echo '<div class="table-responsive"><table class="table table-striped"><thead><tr>';
foreach (['Tiket / episode', 'Vendor / layanan / aset', 'No. Incident dari Provider', 'Nomor SID/Pelanggan', 'Dialihkan', 'Pulih', 'Deadline', 'Durasi 24×7', 'Hasil'] as $h) {
    echo '<th>' . PluginProviderslaTicket::h($h) . '</th>';
}
echo '</tr></thead><tbody>';
foreach ($rows as $row) {
    $m = $row['metrics'];
    echo '<tr><td><a href="' . PluginProviderslaTicket::h(Ticket::getFormURLWithID((int) $row['tickets_id'])) . '">#'
        . (int) $row['tickets_id'] . '</a> / ' . (int) $row['id'] . '</td>';
    foreach ([$row['provider_name'] . ' / ' . $row['circuit'], $row['reference'], $row['customer_sid'] ?? '',
        PluginProviderslaClock::date((int) $row['transferred_epoch']),
        PluginProviderslaClock::date(isset($row['restored_epoch']) ? (int) $row['restored_epoch'] : null),
        PluginProviderslaClock::date($m['deadline']), PluginProviderslaClock::duration($m['seconds']), $m['status']] as $cell) {
        echo '<td>' . PluginProviderslaTicket::h($cell) . '</td>';
    }
    echo '</tr>';
}
if (!$rows) { echo '<tr><td colspan="9">Belum ada pengalihan vendor pada rentang ini.</td></tr>'; }
echo '</tbody></table></div></div></div>';
Html::footer();
