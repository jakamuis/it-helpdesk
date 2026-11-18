<?php
function plugin_init_layananit()
{
    global $PLUGIN_HOOKS;
    $PLUGIN_HOOKS['csrf_compliant']['layananit'] = true;
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH) ?: '';
    $PLUGIN_HOOKS['post_init']['layananit'] = 'plugin_layananit_default_landing';
    if (($_GET['legacy'] ?? '') === '1' && str_ends_with($path, '/front/central.php')) { $_SESSION['layananit_legacy'] = true; $_SESSION['layananit_workspace'] = false; }
    if (str_contains($path, '/plugins/layananit/front/index.php')) { $_SESSION['layananit_workspace'] = true; $_SESSION['layananit_legacy'] = false; }
    if (!empty($_SESSION['layananit_workspace']) && ($_SESSION['glpiactiveprofile']['interface'] ?? '') === 'central') {
        $PLUGIN_HOOKS['add_javascript']['layananit'] = ['public/workspace.js?v=20261116b'];
        $native = preg_match('~/front/(ticket(?:\.form)?|computer(?:\.form)?|monitor(?:\.form)?|printer(?:\.form)?|user(?:\.form)?)\.php$~', $path);
        $plugin = preg_match('~/plugins/(itrequest|providersla)/front/(index|report)\.php$~', $path);
        if (($native || $plugin) && !isset($_GET['display_type'])) {
            // Head styles apply before the first paint, before the async shell is mounted.
            $PLUGIN_HOOKS['add_css']['layananit'] = ['public/app.css', 'public/native-shell.css'];
            if (str_ends_with($path, '/front/ticket.form.php')) {
                $PLUGIN_HOOKS['add_css']['layananit'][] = 'public/ticket-fields.css?v=20261116c';
            }
        }
    }

    $PLUGIN_HOOKS['post_prepareadd']['layananit'] = [Ticket::class => 'plugin_layananit_format_portal_ticket'];
    $PLUGIN_HOOKS['menu_toadd']['layananit'] = ['tools' => 'PluginLayananitMenu'];
}
function plugin_version_layananit()
{
    return ['name' => 'Layanan TI', 'version' => '0.1.0', 'author' => 'IT Helpdesk', 'license' => 'GPLv3+',
        'requirements' => ['glpi' => ['min' => '11.0.8', 'max' => '11.0.99']]];
}

function plugin_layananit_default_landing()
{
    if (empty($_SESSION['glpiID']) || ($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET'
        || !empty($_SESSION['layananit_legacy']) || !empty($_SERVER['HTTP_X_REQUESTED_WITH'])) { return; }
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH) ?: '';
    if (str_ends_with($path, '/front/central.php') && ($_SESSION['glpiactiveprofile']['interface'] ?? '') === 'central') {
        $_SESSION['layananit_workspace'] = true;
        // POST_INIT runs during kernel boot, before redirect exceptions can be handled.
        session_write_close();
        header('Location: ' . Plugin::getWebDir('layananit') . '/front/index.php', true, 302);
        exit;
    }
    if (str_ends_with($path, '/front/helpdesk.public.php') && !isset($_GET['id']) && Plugin::isPluginActive('itrequest')) {
        session_write_close();
        header('Location: ' . Plugin::getWebDir('itrequest') . '/front/index.php', true, 302);
        exit;
    }
}
