<?php
require_once dirname(__DIR__) . '/inc/clock.class.php';
$checks = 0;
function check($condition, string $message): void { global $checks; if (!$condition) { throw new RuntimeException($message); } $checks++; }
function rejects(callable $fn): void { try { $fn(); } catch (InvalidArgumentException) { global $checks; $checks++; return; } throw new RuntimeException('Expected rejection'); }
$start = PluginProviderslaClock::parse('2026-10-29T08:15');
check(gmdate('H:i', $start) === '01:15', 'Jakarta converted to UTC instant');
check(PluginProviderslaClock::date($start) === '29-10-2026 08:15', 'Jakarta display');
rejects(fn() => PluginProviderslaClock::parse('2026-02-30T08:15'));
rejects(fn() => PluginProviderslaClock::parse('tomorrow'));
check(PluginProviderslaClock::target('1.5') === 5400, 'Fractional target');
check(PluginProviderslaClock::target('') === null, 'No default target');
rejects(fn() => PluginProviderslaClock::target('-1'));
rejects(fn() => PluginProviderslaClock::target('0'));
rejects(fn() => PluginProviderslaClock::target('9000'));
$row = ['transferred_epoch' => $start, 'target_seconds' => 7200];
check(PluginProviderslaClock::metrics($row, $start + 7200)['status'] === 'Berjalan, belum lewat', 'Deadline inclusive');
check(PluginProviderslaClock::metrics($row, $start + 7201)['status'] === 'Berjalan, terlambat', 'Running overdue');
$row['restored_epoch'] = $start + 7200;
check(PluginProviderslaClock::metrics($row, $start + 9000)['status'] === 'Memenuhi', 'Restoration exactly at deadline');
$row['restored_epoch']++;
check(PluginProviderslaClock::metrics($row, $start + 9000)['status'] === 'Melanggar', 'Late restoration');
$row['is_void'] = 1;
check(PluginProviderslaClock::metrics($row, $start + 9000)['status'] === 'Dibatalkan', 'Voided excluded');
$row = ['transferred_epoch' => $start];
check(PluginProviderslaClock::metrics($row, $start + 90000)['seconds'] === 90000, 'Elapsed beyond 24h, no pending pause');
check(PluginProviderslaClock::metrics($row, $start + 90000)['status'] === 'Tanpa Target', 'No target is not compliant');
rejects(fn() => PluginProviderslaClock::metrics($row, $start - 1));
check(PluginProviderslaClock::csv('=HYPERLINK("url")')[0] === "'", 'CSV injection neutralized');
check(PluginProviderslaClock::csv('ISP A') === 'ISP A', 'Plain CSV text');
echo "Clock: $checks checks passed\n";
