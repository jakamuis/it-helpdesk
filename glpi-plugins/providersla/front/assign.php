<?php
require_once dirname(__DIR__, 3) . '/inc/includes.php';
require_once dirname(__DIR__) . '/inc/sidebar.class.php';
Session::checkLoginUser();
header('Content-Type: text/html; charset=UTF-8');
header('Cache-Control: no-store');
try {
    PluginProviderslaSidebar::form((int) ($_GET['tickets_id'] ?? 0), (string) ($_GET['mode'] ?? 'start'));
} catch (InvalidArgumentException $e) {
    http_response_code(409);
    echo '<p>' . PluginProviderslaTicket::h($e->getMessage()) . '</p>';
}
