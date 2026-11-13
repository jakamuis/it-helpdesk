<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/attachment.class.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('itrequest')) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
$a = PluginItrequestService::rows('attachments', ['id' => (int) ($_GET['id'] ?? 0)])[0] ?? null;
if (!$a) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
try { PluginItrequestService::get((int) $a['requests_id']); }
catch (RuntimeException $e) { throw new Glpi\Exception\Http\AccessDeniedHttpException(); }
if (!preg_match('/^[a-f0-9]{48}$/', $a['storage_key'])) { throw new RuntimeException('Lampiran tidak valid.'); }
$path = PluginItrequestAttachment::directory() . '/' . $a['storage_key'];
if (!is_file($path)) { throw new RuntimeException('File tidak tersedia.'); }
$response = new Symfony\Component\HttpFoundation\BinaryFileResponse($path, 200,
    ['Content-Type' => $a['mime'], 'Cache-Control' => 'private, no-store', 'X-Content-Type-Options' => 'nosniff'],
    false, Symfony\Component\HttpFoundation\ResponseHeaderBag::DISPOSITION_ATTACHMENT);

$response->setContentDisposition(Symfony\Component\HttpFoundation\ResponseHeaderBag::DISPOSITION_ATTACHMENT, $a['filename'], 'lampiran');
return $response;
