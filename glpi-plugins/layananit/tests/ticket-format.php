<?php

require_once dirname(__DIR__) . '/inc/ticketformat.class.php';

function htmlescape(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function getUserName(int $id): string
{
    return $id === 9 ? 'Jaka' : '';
}

function expect(bool $valid, string $message): void
{
    if (!$valid) {
        throw new RuntimeException($message);
    }
}

$format = PluginLayananitTicketFormat::class;
$portal = $format::portalFields(9, '', 'Printer rusak di SIG Bekasi', 'Saya dari HO.');
expect($format::portalTitle($portal) === 'Jaka - SIG Bekasi - Printer rusak', 'Lokasi gangguan harus dipakai.');
$old = $format::describe(['name' => '[WhatsApp] 628000000001', 'content' => "WhatsApp Helpdesk Ticket\n[WAHA_MSG_ID: old]"]);
expect($old === null, 'Tiket baseline harus memakai format sebelumnya.');
$link = '<a href="/front/ticket.form.php?id=42">#42</a>';
$waTitle = 'Jaka - SIG Bekasi - Problem Printer';
$wa = $format::describe(['name' => $waTitle, 'content' => '<p>[HELPDESK_WHATSAPP_V1]</p>']);
expect($format::cell($link, $waTitle, $wa) === "$link<br>Jaka - <strong>SIG Bekasi</strong> - Problem Printer", 'Tebalkan cabang saja.');
$zabbixTitle = '[Zabbix] Unavailable by ICMP ping';
$zabbix = $format::describe(['name' => $zabbixTitle, 'content' => '[HELPDESK_ZABBIX_V1:SGI%20Narogong%20FS]<br>']);
expect($format::cell($link, $zabbixTitle, $zabbix) === "$link · <strong>SGI Narogong FS</strong><br>$zabbixTitle", 'Tampilkan nama host lengkap.');
echo "Ticket format fixtures passed.\n";
