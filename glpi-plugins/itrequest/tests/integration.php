<?php
/** LOCAL ONLY: all fixtures and business writes roll back; no mail is sent. */
if (PHP_SAPI !== 'cli' || getenv('ITREQUEST_TEST_LOCAL') !== '1') { exit(2); }
require dirname(__DIR__, 3) . '/vendor/autoload.php';
$kernel = new Glpi\Kernel\Kernel(); $kernel->boot();
require_once dirname(__DIR__) . '/inc/view.class.php';
function check($ok, string $msg): void { if (!$ok) { throw new RuntimeException($msg); } }
function rejects(callable $f): void {
    try { $f(); } catch (InvalidArgumentException | RuntimeException $e) { return; }
    throw new Exception('Expected rejection');
}
$user = new User(); check($user->getFromDBbyName('glpi'), 'Local fixture admin');
$auth = new Auth(); $auth->auth_succeded = true; $auth->user = $user; Session::init($auth);
$session = $_SESSION;
$owner = (int) $user->getID(); $entity = PluginItrequestService::entity();
$s = PluginItrequestService::class; $w = PluginItrequestWorkflow::class;
$DB->beginTransaction();
try {
    $others = [];
    foreach ($DB->request(['FROM' => 'glpi_users', 'WHERE' => ['is_active' => 1, 'is_deleted' => 0]]) as $candidate) {
        if ((int) $candidate['id'] !== $owner && $s::member((int) $candidate['id'], $entity)) { $others[] = (int) $candidate['id']; }
        if (count($others) === 3) { break; }
    }
    check(count($others) === 3, 'Three existing local fixture users');
    [$manager,$director,$it] = $others;
    $s::configure('mapping', ['users_id' => $owner, 'approvers_id' => $manager, 'directors_id' => $director]);
    $s::configure('staff', ['users_id' => $it]);
    rejects(fn() => $s::configure('mapping', ['users_id' => $owner, 'approvers_id' => $manager, 'directors_id' => $manager]));
    $_SESSION['glpiactiveprofile']['config'] = 0;
    $base = ['title' => "Email O'Reilly <script>alert(1)</script>", 'type' => 'email', 'email_service' => 'new',
        'recipient' => 'Pengguna yang diwakilkan', 'employee_number' => 'TEST-001', 'department' => 'Finance', 'job_title' => 'Supervisor',
        'location' => 'Cikarang', 'company' => 'Perusahaan fixture', 'reason' => 'Keperluan kerja',
        'needed_date' => date('Y-m-d', time()+86400), 'requested_email' => 'fixture@example.test', 'policy_accepted' => '1'];
    foreach (['employee_number','job_title','company','recipient','reason'] as $key) { rejects(fn() => $w::payload(array_replace($base, [$key => '']), true)); }
    rejects(fn() => $w::payload(array_replace($base, ['policy_accepted' => '0']), true));
    rejects(fn() => $w::payload(array_replace($base, ['requested_email' => 'not-email']), true));
    rejects(fn() => $w::payload(array_replace($base, ['needed_date' => '2026-02-30']), true));
    rejects(fn() => $w::payload(array_replace($base, ['email_service' => 'unknown']), true));
    foreach (['reset','rename','delete'] as $kind) {
        $p = array_replace($base, ['email_service' => $kind, 'current_email' => 'old@example.test']);
        check($w::payload($p, true)['email_service'] === $kind, 'Email service ' . $kind);
        rejects(fn() => $w::payload(array_replace($p, ['current_email' => '']), true));
    }
    rejects(fn() => $w::payload(array_replace($base, ['email_service' => 'rename', 'current_email' => $base['requested_email']]), true));
    $tickets = countElementsInTable('glpi_tickets');
    $id = $s::mutate(0, 'create', $base);
    $row = fn() => $s::rows('requests', ['id' => $id])[0];
    $act = function (string $action, array $extra = []) use ($s,$id,$row) { return $s::mutate($id, $action, ['version' => $row()['version']] + $extra); };
    // Missing director blocks email submission, but not Office 365 later.
    $s::update('mappings', ['directors_id' => 0], ['entities_id' => $entity, 'users_id' => $owner]);
    rejects(fn() => $act('submit'));
    $s::update('mappings', ['directors_id' => $director], ['entities_id' => $entity, 'users_id' => $owner]);
    $act('submit');
    $_SESSION['glpiID'] = $director;
    rejects(fn() => $s::get($id));
    rejects(fn() => $act('approve'));
    $_SESSION['glpiID'] = $manager;
    rejects(fn() => $act('revise'));
    $act('revise', ['note' => 'Lengkapi keterangan']);
    $_SESSION['glpiID'] = $owner;
    $act('save', $base); $act('submit');
    rejects(fn() => $act('approve'));
    $_SESSION['glpiID'] = $manager;
    $act('approve');
    check($row()['status'] === 'director_approval' && empty($row()['approved_at']), 'Manager cannot queue email for IT');
    ob_start(); PluginItrequestView::listing('approval'); $managerList=ob_get_clean();
    check(!str_contains($managerList, PluginItrequestView::number($row())), 'Manager queue excludes director stage');
    rejects(fn() => $act('approve'));
    $_SESSION['glpiID'] = $it;
    rejects(fn() => $s::get($id)); rejects(fn() => $act('start', ['target_date' => date('Y-m-d')]));
    $_SESSION['glpiID'] = $director;
    ob_start(); PluginItrequestView::listing('approval'); $list=ob_get_clean();
    check(str_contains($list, PluginItrequestView::number($row())), 'Director sees own approval queue');
    $act('revise', ['note' => 'Revisi dari direktur']);
    $_SESSION['glpiID'] = $owner;
    $act('save', $base); $act('submit');
    check(empty($row()['manager_approved_at']), 'Resubmission resets previous approval');
    $_SESSION['glpiID'] = $director;
    rejects(fn() => $act('approve'));
    $_SESSION['glpiID'] = $manager; $act('approve');
    // Explicit, audited director substitution removes the old decision right.
    $_SESSION['glpiID'] = $owner; $_SESSION['glpiactiveprofile']['config'] = UPDATE;
    $act('reassign', ['approvers_id' => $it, 'note' => 'Direktur pengganti fixture']);
    $_SESSION['glpiactiveprofile']['config'] = 0; $_SESSION['glpiID'] = $director;
    rejects(fn() => $act('approve'));
    $_SESSION['glpiID'] = $owner; $_SESSION['glpiactiveprofile']['config'] = UPDATE;
    $act('reassign', ['approvers_id' => $director, 'note' => 'Kembali ke direktur awal']);
    $_SESSION['glpiactiveprofile']['config'] = 0; $_SESSION['glpiID'] = $director;
    $stale = $row()['version']; $act('approve');
    check($row()['status'] === 'queued' && !empty($row()['approved_at']), 'Director queues email for IT');
    rejects(fn() => $s::mutate($id, 'reject', ['version' => $stale, 'note' => 'Stale decision']));
    $_SESSION['glpiID'] = $owner;
    rejects(fn() => $act('save', $base));
    $act('change', ['note' => 'Perubahan lingkup']);
    $act('save', $base); $act('submit');
    $_SESSION['glpiID'] = $manager; $act('approve');
    $_SESSION['glpiID'] = $director; $act('approve');
    $_SESSION['glpiID'] = $it; $act('ask', ['note' => 'Konfirmasi lokasi']);
    $_SESSION['glpiID'] = $owner; $act('answer', ['note' => 'Cikarang']);
    check($row()['status'] === 'queued', 'Answer resumes queued state');
    $_SESSION['glpiID'] = $it; $act('start', ['target_date' => date('Y-m-d', time()+86400)]);
    $act('ask', ['note' => 'Konfirmasi pengguna']);
    $_SESSION['glpiID'] = $owner; $act('answer', ['note' => 'Pengguna pada form']);
    check($row()['status'] === 'processing', 'Answer resumes processing');
    rejects(fn() => $act('cancel', ['note' => 'Too late for owner cancellation']));
    $_SESSION['glpiID'] = $it; rejects(fn() => $act('finish')); $act('finish', ['note' => 'Email dibuat; kredensial lewat jalur aman']);
    ob_start(); PluginItrequestView::detail($s::get($id)); $html=ob_get_clean();
    check(str_contains($html, 'Direktur:') && str_contains($html, 'kredensial lewat jalur aman') && !str_contains($html, '<script>alert(1)</script>'), 'Detail, history and escaping');
    $events=$s::rows('events', ['requests_id' => $id, 'action' => 'submit']);
    $details=json_decode($events[0]['details'],true);
    check($details['policy'] === $w::POLICY && (int) $details['policy_accepted_by'] === $owner, 'Consent text and actor saved');
    $_SESSION['glpiID'] = $owner;
    $_SESSION['glpiactive_entity'] = 999999; rejects(fn() => $s::get($id)); $_SESSION['glpiactive_entity'] = $entity;
    // Office 365 requires no director, reaches IT directly after manager approval.
    $office=array_replace($base, ['type' => 'office365', 'title' => 'Office fixture', 'office_email' => 'office@example.test', 'asset' => 'TEST-PC', 'office_apps' => 'Word, Excel']);
    rejects(fn() => $w::payload(array_replace($office,['asset'=>'']),true));
    $s::update('mappings', ['directors_id' => 0], ['entities_id' => $entity, 'users_id' => $owner]);
    $oid=$s::mutate(0,'create',$office);
    $orow=fn() => $s::rows('requests',['id'=>$oid])[0];
    $oact=fn($a,$extra=[]) => $s::mutate($oid,$a,['version'=>$orow()['version']]+$extra);
    $oact('submit'); check((int) $orow()['directors_id']===0,'No director on Office request');
    $_SESSION['glpiID']=$manager; $oact('approve');
    check($orow()['status']==='queued','Office skips director stage');
    $_SESSION['glpiID']=$it; $oact('start',['target_date'=>date('Y-m-d')]); $oact('finish',['note'=>'Lisensi diperiksa dan Office dipasang']);
    check($orow()['status']==='done','Office completes');
    // Rejection at director stage never exposes an email request to IT.
    $_SESSION['glpiID']=$owner;
    $s::update('mappings',['directors_id'=>$director],['entities_id'=>$entity,'users_id'=>$owner]);
    $rid=$s::mutate(0,'create',$base);
    $rev=fn() => $s::rows('requests',['id'=>$rid])[0]['version'];
    $s::mutate($rid,'submit',['version'=>$rev()]);
    $_SESSION['glpiID']=$manager; $s::mutate($rid,'approve',['version'=>$rev()]);
    $_SESSION['glpiID']=$director; $s::mutate($rid,'reject',['version'=>$rev(),'note'=>'Tidak disetujui']);
    $_SESSION['glpiID']=$it; rejects(fn() => $s::get($rid));
    check(countElementsInTable('glpi_tickets')===$tickets,'No tickets created');
    $_SESSION['glpiID']=$owner;
    ob_start(); PluginItrequestView::editor(null); $form=ob_get_clean();
    check(str_contains($form,'policy_accepted') && str_contains($form,'email-service') && str_contains($form,'_glpi_csrf_token'),'Specialized form with consent and CSRF');
    echo "PASS: Email two-stage approval, Office one-stage approval, consent, conditional fields, revisions, reassignment, rejection, access, stale decisions, audit, escaping and zero tickets.\n";
} finally { $_SESSION=$session; $DB->rollBack(); }
