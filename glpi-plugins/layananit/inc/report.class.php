<?php
/** Ticket reporting uses GLPI's per-ticket read check, including entity scope. */
class PluginLayananitReport
{
    public array $rows = [];
    public array $locations = [];
    public array $technicians = [];
    public array $filters;
    public ?string $error = null;
    public function __construct(array $input)
    {
        global $DB;
        if (!Ticket::canView()) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
        $this->filters = ['from' => (string) ($input['from'] ?? date('Y-01-01')), 'until' => (string) ($input['until'] ?? date('Y-m-d')),
            'location' => max(0, (int) ($input['location'] ?? 0)), 'technician' => max(0, (int) ($input['technician'] ?? 0))];
        foreach (['from','until'] as $key) {
            $date = DateTimeImmutable::createFromFormat('!Y-m-d', $this->filters[$key]);
            if (!$date || $date->format('Y-m-d') !== $this->filters[$key]) { $this->error = 'Tanggal tidak valid.'; return; }
        }
        if ((int) substr($this->filters['until'],0,4) - (int) substr($this->filters['from'],0,4) > 10) { $this->error = 'Rentang laporan maksimal 10 tahun.'; return; }
        if ($this->filters['from'] > $this->filters['until']) { $this->error = 'Tanggal awal harus sebelum atau sama dengan tanggal akhir.'; return; }
        $end = (new DateTimeImmutable($this->filters['until']))->modify('+1 day')->format('Y-m-d');
        $where = ['is_deleted' => 0, 'date' => ['>=', $this->filters['from'] . ' 00:00:00'], 'AND' => [['date' => ['<', $end . ' 00:00:00']]]];
        $where += getEntitiesRestrictCriteria('glpi_tickets');
        $ticket = new Ticket(); $count = 0;
        foreach ($DB->request(['FROM'=>'glpi_tickets', 'WHERE'=>$where, 'ORDER'=>['date DESC','id DESC'], 'LIMIT'=>10001]) as $r) {
            if (++$count > 10000) { $this->rows = []; $this->error = 'Rentang melebihi 10.000 kandidat tiket. Persempit periode untuk laporan lengkap.'; return; }
            if (!$ticket->can((int) $r['id'], READ)) { continue; }
            $lid = (int) $r['locations_id'];
            $location = $lid ? Dropdown::getDropdownName('glpi_locations', $lid) : 'Tanpa lokasi';
            if ($lid) { $this->locations[$lid] = $location; }
            $techs = [];
            foreach ($DB->request(['FROM'=>'glpi_tickets_users','WHERE'=>['tickets_id'=>$r['id'],'type'=>CommonITILActor::ASSIGN]]) as $actor) {
                $uid = (int) $actor['users_id'];
                if ($uid) { $techs[$uid] = getUserName($uid); $this->technicians[$uid] = $techs[$uid]; }
            }
            if ($this->filters['location'] && $lid !== $this->filters['location']) { continue; }
            if ($this->filters['technician'] && !isset($techs[$this->filters['technician']])) { continue; }
            $r['location_label'] = $location; $r['technicians'] = implode(', ', $techs) ?: 'Belum ditugaskan';
            $r['hours'] = null;
            if (in_array((int) $r['status'], [5,6], true) && !empty($r['solvedate'])) {
                $seconds = strtotime($r['solvedate']) - strtotime($r['date']);
                if ($seconds >= 0) { $r['hours'] = round($seconds / 3600, 2); }
            }
            $this->rows[] = $r;
        }
        asort($this->locations); asort($this->technicians);
    }
    public function csv()
    {
        $fp = fopen('php://temp','w+'); fwrite($fp,"\xEF\xBB\xBF");
        fputcsv($fp,['ID','Judul','Jenis','Status','Prioritas','Lokasi','Teknisi','Dibuka','Diselesaikan','Durasi penyelesaian jam 24x7'],',','"','');
        foreach ($this->rows as $r) {
            $cells = [$r['id'],$r['name'],(int) $r['type'] === 1 ? 'Incident' : 'Request native',Ticket::getStatus((int) $r['status']),Ticket::getPriorityName((int) $r['priority']),$r['location_label'],$r['technicians'],$r['date'],$r['solvedate'],$r['hours']];
            fputcsv($fp,array_map(static function($v) { $v = (string) $v; return preg_match('/^[\s\x00-\x1f]*[=+@-]/u',$v) ? "'" . $v : $v; },$cells),',','"','');
        }
        rewind($fp); $body = stream_get_contents($fp); fclose($fp);
        return new Symfony\Component\HttpFoundation\Response($body,200,['Content-Type'=>'text/csv; charset=UTF-8','Content-Disposition'=>'attachment; filename="laporan-tiket.csv"','Cache-Control'=>'no-store']);
    }
    public function render(): void
    {
        $h = [PluginLayananitView::class,'h']; $f = $this->filters;
        echo '<div class="lti-title"><div><h1>Reporting Tiket</h1><p>Ringkasan layanan berdasarkan tanggal pembukaan tiket.</p></div></div><section class="lti-card"><form class="lti-report-filters" method="get"><input type="hidden" name="page" value="report">';
        foreach (['from'=>'Dari tanggal','until'=>'Sampai tanggal'] as $key=>$label) { echo '<label>' . $label . '<input type="date" required name="'.$key.'" value="'.$h($f[$key]).'"></label>'; }
        foreach (['location'=>['Lokasi',$this->locations],'technician'=>['Teknisi',$this->technicians]] as $key=>[$label,$options]) {
            echo '<label>'.$label.'<select name="'.$key.'"><option value="0">Semua '.$label.'</option>';
            foreach ($options as $id=>$name) { echo '<option value="'.$id.'"'.($f[$key]===$id ? ' selected':'').'>'.$h($name).'</option>'; }
            echo '</select></label>';
        }
        echo '<button class="lti-button">Tampilkan</button><button class="lti-button secondary" name="csv" value="1">Ekspor CSV</button></form></section>';
        if ($this->error) { echo '<div class="alert alert-warning">'.$h($this->error).'</div>'; return; }
        $counts = ['Total'=>count($this->rows),'Baru'=>0,'Diproses'=>0,'Menunggu'=>0,'Selesai / ditutup'=>0]; $months=[]; $hours=[];
        foreach ($this->rows as $r) {
            $key = [1=>'Baru',2=>'Diproses',3=>'Diproses',4=>'Menunggu',5=>'Selesai / ditutup',6=>'Selesai / ditutup'][(int)$r['status']] ?? null;
            if ($key) { $counts[$key]++; }
            $m=substr($r['date'],0,7); $months[$m]=($months[$m] ?? 0)+1;
            if ($r['hours'] !== null) { $hours[]=$r['hours']; }
        }
        echo '<div class="lti-summary lti-report-summary">';
        foreach ($counts as $label=>$count) { echo '<div class="lti-card"><span>'.$h($label).'</span><strong>'.$count.'</strong></div>'; }
        echo '</div><div class="lti-dashboard-grid lti-report-overview"><section class="lti-card"><h2>Tren tiket dibuka per bulan</h2>';
        $cursor = new DateTimeImmutable(substr($f['from'],0,7).'-01'); $last = substr($f['until'],0,7); $max=max([1,...array_values($months)]);
        while ($cursor->format('Y-m') <= $last) {
            $m=$cursor->format('Y-m'); $n=$months[$m] ?? 0;
            echo '<div class="lti-report-bar"><span>'.$m.'</span><meter min="0" max="'.$max.'" value="'.$n.'">'.$n.'</meter><strong>'.$n.'</strong></div>';
            $cursor=$cursor->modify('+1 month');
        }
        echo '</section><section class="lti-card"><h2>Waktu penyelesaian rata-rata</h2><strong class="lti-report-average">'.($hours ? $h(round(array_sum($hours)/count($hours),1)).' jam':'—').'</strong><p class="lti-muted">Dari '.count($hours).' tiket selesai dengan tanggal penyelesaian valid. Durasi kalender 24×7 sejak dibuka, termasuk waktu menunggu; bukan perhitungan SLA.</p></section></div>';
        $pages=max(1,(int)ceil(count($this->rows)/50)); $page=min($pages,max(1,(int)($_GET['p'] ?? 1)));
        echo '<section class="lti-card"><div class="lti-section"><h2>Detail tiket</h2><span>'.count($this->rows).' tiket</span></div><p class="lti-muted">Mengikuti hak akses dan entity aktif, tanpa Trash. Mencakup Incident dan Request native GLPI; pengajuan Request IT terpisah.</p><div class="lti-scroll"><table><thead><tr><th>Tiket</th><th>Status</th><th>Prioritas</th><th>Lokasi</th><th>Teknisi</th><th>Dibuka</th><th>Selesai</th></tr></thead><tbody>';
        foreach (array_slice($this->rows,($page-1)*50,50) as $r) {
            echo '<tr><td><a href="'.$h(Ticket::getFormURLWithID((int)$r['id'])).'">#'.(int)$r['id'].'</a><br>'.$h($r['name']).'</td>';
            foreach ([Ticket::getStatus((int)$r['status']),Ticket::getPriorityName((int)$r['priority']),$r['location_label'],$r['technicians'],$r['date'],$r['solvedate'] ?: '—'] as $cell) { echo '<td>'.$h($cell).'</td>'; }
            echo '</tr>';
        }
        if (!$this->rows) { echo '<tr><td colspan="7">Tidak ada tiket pada filter ini.</td></tr>'; }
        echo '</tbody></table></div><div class="lti-section lti-report-pagination"><span>Halaman '.$page.' / '.$pages.' · 50 tiket per halaman</span><div class="lti-actions">';
        foreach (['Sebelumnya'=>$page-1,'Berikutnya'=>$page+1] as $label=>$p) { if ($p<1 || $p>$pages) { continue; } echo '<a class="lti-button secondary" href="'.$h(PluginLayananitView::url('report').'&'.http_build_query($f+['p'=>$p])).'">'.$label.'</a>'; }
        echo '</div></div></section>';
    }
}
